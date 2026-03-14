"""
app/services/parser_pipeline.py — AutoTax-HUB v5.2
Invoice parsing pipeline:
1. PDF text extraction (pdfplumber)
2. Regex-based field extraction (Gesamt, Summe, Total, MwSt, USt, etc.)
3. AI Vision fallback via Anthropic Claude (for scanned PDFs / images)

Supports German & international invoice formats.
"""
import base64
import logging
import os
import re
from typing import Optional

logger = logging.getLogger("autotaxhub.parser")


# ═══════════════════════════════════════════════════════
#  REGEX PATTERNS — German + International invoices
# ═══════════════════════════════════════════════════════

# Total amount patterns (Brutto / Gesamt / Total / Summe / Endbetrag / Rechnungsbetrag / Amount Due)
TOTAL_PATTERNS = [
    # German
    r"(?:Gesamtbetrag|Gesamtsumme|Gesamt|GESAMT)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Bruttobetrag|Brutto|BRUTTO)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Rechnungsbetrag|RECHNUNGSBETRAG)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Endbetrag|ENDBETRAG)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Summe|SUMME)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Zu\s*zahlen|ZU\s*ZAHLEN)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Zahlbetrag|ZAHLBETRAG)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Betrag|BETRAG)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    # English
    r"(?:Total|TOTAL)\s*[:=]?\s*[€$£EUR]*\s*([\d.,]+)",
    r"(?:Amount\s*Due|AMOUNT\s*DUE)\s*[:=]?\s*[€$£EUR]*\s*([\d.,]+)",
    r"(?:Grand\s*Total|GRAND\s*TOTAL)\s*[:=]?\s*[€$£EUR]*\s*([\d.,]+)",
    r"(?:Balance\s*Due|BALANCE\s*DUE)\s*[:=]?\s*[€$£EUR]*\s*([\d.,]+)",
    # Amount with € symbol before
    r"€\s*([\d.,]+)\s*(?:Gesamt|Total|Summe|Brutto)",
    # Last resort: € followed by large number
    r"[€]\s*([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})",
]

# VAT amount patterns
VAT_AMOUNT_PATTERNS = [
    r"(?:MwSt|Mwst|MWST|MWSt)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Mehrwertsteuer|MEHRWERTSTEUER)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:USt|Ust|UST|Umsatzsteuer)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:VAT|V\.A\.T\.|Tax)\s*[:=]?\s*[€$£EUR]*\s*([\d.,]+)",
    r"(?:davon\s*MwSt|inkl\.\s*MwSt)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Steuer|STEUER)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
]

# VAT rate patterns
VAT_RATE_PATTERNS = [
    r"(\d{1,2})\s*[%]\s*(?:MwSt|Mwst|USt|Ust|VAT|Steuer)",
    r"(?:MwSt|Mwst|USt|Ust|VAT|Steuer)\s*[:=]?\s*(\d{1,2})\s*[%]",
    r"(\d{1,2})\s*[%]\s*(?:Mehrwertsteuer|Umsatzsteuer)",
]

# Net amount patterns (Netto)
NET_PATTERNS = [
    r"(?:Nettobetrag|Netto|NETTO)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Zwischensumme|ZWISCHENSUMME)\s*[:=]?\s*[€EUR]*\s*([\d.,]+)",
    r"(?:Subtotal|SUBTOTAL|Sub-Total)\s*[:=]?\s*[€$£EUR]*\s*([\d.,]+)",
]

# Vendor patterns
VENDOR_PATTERNS = [
    r"^(.+?)(?:\n|\r)",  # First line of text
]

# Invoice number patterns
INVOICE_NR_PATTERNS = [
    r"(?:Rechnungs?-?\s*(?:Nr|Nummer|nr|nummer)\.?)\s*[:=]?\s*([A-Za-z0-9\-/]+)",
    r"(?:Rechnung\s*Nr\.?|Re\.?\s*Nr\.?)\s*[:=]?\s*([A-Za-z0-9\-/]+)",
    r"(?:Invoice\s*(?:No|Number|#)\.?)\s*[:=]?\s*([A-Za-z0-9\-/]+)",
    r"(?:Beleg-?\s*(?:Nr|Nummer)\.?)\s*[:=]?\s*([A-Za-z0-9\-/]+)",
]

# Date patterns
DATE_PATTERNS = [
    r"(?:Rechnungsdatum|Datum|Date|Belegdatum)\s*[:=]?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    r"(\d{1,2}[./]\d{1,2}[./]\d{4})",
    r"(\d{4}-\d{2}-\d{2})",
]

# Currency patterns
CURRENCY_PATTERNS = [
    (r"€|EUR", "EUR"),
    (r"\$|USD", "USD"),
    (r"£|GBP", "GBP"),
    (r"₺|TRY|TL", "TRY"),
    (r"CHF", "CHF"),
]


# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════

def _parse_german_number(text: str) -> float:
    """
    Parse German/European number formats:
    1.234,56 → 1234.56
    1,234.56 → 1234.56
    1234,56  → 1234.56
    1234.56  → 1234.56
    """
    if not text:
        return 0.0
    text = text.strip().replace(" ", "")

    # German format: 1.234,56
    if re.match(r"^\d{1,3}(\.\d{3})+,\d{2}$", text):
        return float(text.replace(".", "").replace(",", "."))

    # English format: 1,234.56
    if re.match(r"^\d{1,3}(,\d{3})+\.\d{2}$", text):
        return float(text.replace(",", ""))

    # Simple German: 1234,56 or 12,50
    if "," in text and "." not in text:
        return float(text.replace(",", "."))

    # Simple English: 1234.56
    if "." in text and "," not in text:
        return float(text)

    # Fallback
    try:
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", "."))
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _extract_first_match(text: str, patterns: list[str]) -> Optional[str]:
    """Try patterns in order, return first match group 1."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _normalize_date(date_str: str) -> str:
    """Normalize date to YYYY-MM-DD format."""
    if not date_str:
        return ""

    # Already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # DD.MM.YYYY or DD/MM/YYYY
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    # DD.MM.YY
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{2})", date_str)
    if m:
        year = int(m.group(3))
        year = year + 2000 if year < 50 else year + 1900
        return f"{year}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    return date_str


def _detect_currency(text: str) -> str:
    """Detect currency from text."""
    for pattern, currency in CURRENCY_PATTERNS:
        if re.search(pattern, text):
            return currency
    return "EUR"  # Default


def _detect_vendor(text: str) -> str:
    """Extract vendor name from first meaningful line."""
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 2]
    # Skip common header words
    skip_words = {"rechnung", "invoice", "quittung", "beleg", "kassenbon", "receipt", "bon"}
    for line in lines[:5]:
        if line.lower() not in skip_words and not re.match(r"^\d+$", line):
            # Clean up
            vendor = re.sub(r"\s+", " ", line)[:60]
            return vendor
    return ""


# ═══════════════════════════════════════════════════════
#  PDF TEXT EXTRACTION
# ═══════════════════════════════════════════════════════

def _extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF using pdfplumber (preferred) or fallback."""
    text = ""

    # Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:5]:  # Max 5 pages
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text
    except ImportError:
        logger.info("pdfplumber not installed, trying PyPDF2")
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")

    # Fallback: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        for page in reader.pages[:5]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except ImportError:
        logger.warning("No PDF library available (pdfplumber/PyPDF2)")
    except Exception as e:
        logger.warning(f"PyPDF2 failed: {e}")

    return text


# ═══════════════════════════════════════════════════════
#  AI VISION PARSER (Anthropic Claude)
# ═══════════════════════════════════════════════════════

def _parse_with_ai_vision(file_path: str) -> dict:
    """
    Use Anthropic Claude Vision to parse invoice from image/scanned PDF.
    Returns structured invoice data.
    """
    from app.core.config import settings

    if not settings.ANTHROPIC_API_KEY:
        logger.info("No ANTHROPIC_API_KEY — skipping AI vision parsing")
        return {}

    try:
        import anthropic

        # Read file and encode to base64
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        b64 = base64.b64encode(file_bytes).decode("utf-8")

        # Detect media type
        ext = file_path.rsplit(".", 1)[-1].lower()
        media_types = {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "tiff": "image/tiff",
        }
        media_type = media_types.get(ext, "application/pdf")

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document" if ext == "pdf" else "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract invoice data from this document. Return ONLY a JSON object with these fields:\n"
                            "- vendor: company/store name\n"
                            "- invoice_number: invoice/receipt number\n"
                            "- date: date in YYYY-MM-DD format\n"
                            "- total: total/gross amount as number (Gesamtbetrag/Brutto/Total/Summe)\n"
                            "- net: net amount as number (Netto/Subtotal)\n"
                            "- vat_amount: VAT/MwSt amount as number\n"
                            "- vat_rate: VAT rate as string like '19%' or '7%'\n"
                            "- currency: currency code (EUR, USD, etc.)\n"
                            "- category: one of: food, restaurant, clothing, electronics, fuel, drugstore, shoes, transport, office, telecom, other\n"
                            "- payment_method: cash, card, transfer, or unknown\n\n"
                            "Return ONLY valid JSON, no markdown, no explanation."
                        ),
                    },
                ],
            }],
        )

        # Parse AI response
        response_text = message.content[0].text.strip()
        # Remove markdown code blocks if present
        response_text = re.sub(r"```json\s*", "", response_text)
        response_text = re.sub(r"```\s*", "", response_text)

        import json
        data = json.loads(response_text)

        logger.info(f"AI Vision parsed: vendor={data.get('vendor')}, total={data.get('total')}")
        return {
            "vendor": data.get("vendor", ""),
            "invoice_number": data.get("invoice_number", ""),
            "date": data.get("date", ""),
            "total": float(data.get("total", 0) or 0),
            "net": float(data.get("net", 0) or 0),
            "vat_amount": float(data.get("vat_amount", 0) or 0),
            "vat_rate": str(data.get("vat_rate", "")),
            "currency": data.get("currency", "EUR"),
            "category": data.get("category", "other"),
            "payment_method": data.get("payment_method", "unknown"),
            "ocr_mode": "ai_vision",
        }

    except Exception as e:
        logger.warning(f"AI Vision parsing failed: {e}")
        return {}


# ═══════════════════════════════════════════════════════
#  REGEX-BASED TEXT PARSER
# ═══════════════════════════════════════════════════════

def _parse_text(text: str) -> dict:
    """Parse invoice fields from extracted text using regex patterns."""
    if not text or len(text.strip()) < 10:
        return {}

    result = {}

    # Total amount
    total_str = _extract_first_match(text, TOTAL_PATTERNS)
    if total_str:
        result["total"] = _parse_german_number(total_str)

    # Net amount
    net_str = _extract_first_match(text, NET_PATTERNS)
    if net_str:
        result["net"] = _parse_german_number(net_str)

    # VAT amount
    vat_str = _extract_first_match(text, VAT_AMOUNT_PATTERNS)
    if vat_str:
        result["vat_amount"] = _parse_german_number(vat_str)

    # VAT rate
    vat_rate = _extract_first_match(text, VAT_RATE_PATTERNS)
    if vat_rate:
        result["vat_rate"] = f"{vat_rate}%"

    # If we have net and VAT but no total, calculate
    if "total" not in result and "net" in result and "vat_amount" in result:
        result["total"] = round(result["net"] + result["vat_amount"], 2)

    # If we have total and VAT but no net, calculate
    if "net" not in result and "total" in result and "vat_amount" in result:
        result["net"] = round(result["total"] - result["vat_amount"], 2)

    # If we have total and rate but no VAT amount, calculate
    if "vat_amount" not in result and "total" in result and "vat_rate" in result:
        rate = float(result["vat_rate"].replace("%", ""))
        if rate > 0:
            result["vat_amount"] = round(result["total"] * rate / (100 + rate), 2)

    # If we have total but no VAT info, assume 19% German VAT
    if "total" in result and "vat_amount" not in result:
        result["vat_amount"] = round(result["total"] * 19 / 119, 2)
        result["vat_rate"] = "19%"

    # Invoice number
    inv_nr = _extract_first_match(text, INVOICE_NR_PATTERNS)
    if inv_nr:
        result["invoice_number"] = inv_nr

    # Date
    date_str = _extract_first_match(text, DATE_PATTERNS)
    if date_str:
        result["date"] = _normalize_date(date_str)

    # Vendor
    vendor = _detect_vendor(text)
    if vendor:
        result["vendor"] = vendor

    # Currency
    result["currency"] = _detect_currency(text)

    if result.get("total", 0) > 0:
        result["ocr_mode"] = "text_regex"

    return result


# ═══════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════

def process_invoice(file_path: str) -> dict:
    """
    Main invoice processing pipeline:
    1. Try PDF text extraction + regex parsing
    2. If no total found → try AI Vision
    3. Return structured result
    """
    ext = file_path.rsplit(".", 1)[-1].lower()
    result = {}

    # Step 1: PDF text extraction + regex
    if ext == "pdf":
        text = _extract_pdf_text(file_path)
        if text.strip():
            result = _parse_text(text)
            logger.info(f"Text extraction: {len(text)} chars, total={result.get('total', 0)}")

    # Step 2: If no total found (scanned PDF or image), try AI Vision
    if not result.get("total"):
        logger.info(f"No total from text extraction, trying AI Vision for {ext}")
        ai_result = _parse_with_ai_vision(file_path)
        if ai_result.get("total"):
            result = ai_result
        elif ai_result:
            # Merge partial AI results
            for key, val in ai_result.items():
                if val and not result.get(key):
                    result[key] = val

    # Defaults
    result.setdefault("total", 0)
    result.setdefault("vat_amount", 0)
    result.setdefault("vat_rate", "")
    result.setdefault("currency", "EUR")
    result.setdefault("vendor", None)
    result.setdefault("invoice_number", None)
    result.setdefault("date", None)
    result.setdefault("category", None)
    result.setdefault("payment_method", None)
    result.setdefault("ocr_mode", "pending")

    logger.info(f"Pipeline result: vendor={result.get('vendor')}, total={result.get('total')}, vat={result.get('vat_amount')}")
    return result
