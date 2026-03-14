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
#  MULTILINGUAL INVOICE DICTIONARY
#  30+ languages — every word that can appear on invoices
# ═══════════════════════════════════════════════════════

# ── TOTAL / GROSS amount keywords ─────────────────────
# All words meaning: total, gross, sum, amount due, payable, grand total, balance
TOTAL_KEYWORDS = [
    # German
    "Gesamtbetrag", "Gesamtsumme", "Gesamt", "Bruttobetrag", "Brutto",
    "Rechnungsbetrag", "Endbetrag", "Summe", "Zu zahlen", "Zahlbetrag",
    "Betrag", "Fälliger Betrag", "Rechnungssumme", "Endpreis", "Gesamtpreis",
    "Ausstehender Betrag", "Gesamtwert", "Wert", "Preis", "Eder", "Tutar",
    # English
    "Total", "Grand Total", "Amount Due", "Balance Due", "Total Due",
    "Amount Payable", "Net Payable", "Total Payable", "Invoice Total",
    "Total Amount", "Amount", "Sum", "Gross", "Gross Total", "Payment Due",
    "Total Price", "Final Amount", "Outstanding", "Balance",
    # Turkish
    "Toplam", "Genel Toplam", "Toplam Tutar", "Ödenecek Tutar", "Tutar",
    "Toplam Fiyat", "Genel Tutar", "Brüt Tutar", "Brüt", "Yekün", "Yekun",
    "Net Tutar", "Fatura Tutarı", "Ödenecek", "Eder", "Değer", "Bedel",
    "Toplam Bedel", "KDV Dahil Toplam", "KDV Dahil", "Son Tutar",
    # French
    "Total", "Montant Total", "Total TTC", "Net à Payer", "Montant Dû",
    "Somme", "Total Général", "Montant", "À Payer", "Solde", "Prix Total",
    "Total à Payer", "Montant à Régler", "Règlement",
    # Spanish
    "Total", "Importe Total", "Total a Pagar", "Monto Total", "Suma Total",
    "Importe", "Monto", "Valor Total", "Total Factura", "Saldo", "A Pagar",
    "Precio Total", "Importe a Pagar",
    # Italian
    "Totale", "Importo Totale", "Totale Fattura", "Importo Dovuto",
    "Totale da Pagare", "Importo", "Somma", "Totale Complessivo",
    "Importo Lordo", "Lordo", "Saldo",
    # Portuguese
    "Total", "Valor Total", "Total a Pagar", "Montante Total",
    "Importância", "Valor", "Soma", "Total Geral", "Saldo",
    # Dutch
    "Totaal", "Totaalbedrag", "Te Betalen", "Verschuldigd Bedrag",
    "Eindbedrag", "Bedrag", "Bruto", "Totaalprijs",
    # Polish
    "Razem", "Suma", "Łącznie", "Do Zapłaty", "Kwota", "Brutto",
    "Razem Brutto", "Wartość Brutto", "Należność",
    # Czech
    "Celkem", "Celková Částka", "K Úhradě", "Částka", "Hrubý",
    "Celkem k Úhradě", "Součet",
    # Swedish
    "Totalt", "Summa", "Att Betala", "Belopp", "Brutto", "Slutsumma",
    "Totalt att Betala",
    # Norwegian
    "Totalt", "Sum", "Å Betale", "Beløp", "Brutto", "Sluttsum",
    # Danish
    "Total", "I Alt", "At Betale", "Beløb", "Brutto", "Samlet",
    # Finnish
    "Yhteensä", "Maksettava", "Summa", "Brutto", "Loppusumma",
    # Hungarian
    "Összesen", "Bruttó", "Fizetendő", "Végösszeg", "Összeg",
    # Romanian
    "Total", "Suma Totală", "De Plată", "Valoare Totală", "Brut",
    # Bulgarian
    "Общо", "Обща Сума", "За Плащане", "Бруто",
    # Croatian
    "Ukupno", "Sveukupno", "Za Plaćanje", "Bruto", "Iznos",
    # Greek
    "Σύνολο", "Συνολικό Ποσό", "Πληρωτέο", "Μικτό",
    # Arabic
    "المجموع", "الإجمالي", "المبلغ الإجمالي", "المبلغ المستحق", "المبلغ",
    # Chinese
    "合计", "总计", "应付金额", "总额", "金额", "合計", "總計",
    # Japanese
    "合計", "総計", "お支払い金額", "請求金額", "税込合計",
    # Korean
    "합계", "총계", "결제금액", "청구금액",
    # Russian
    "Итого", "Всего", "К оплате", "Сумма", "Брутто", "Общая сумма",
    # Ukrainian
    "Разом", "Всього", "До сплати", "Сума", "Брутто",
    # Hindi
    "कुल", "कुल राशि", "भुगतान योग्य",
]

# ── VAT / TAX keywords ───────────────────────────────
VAT_KEYWORDS = [
    # German
    "MwSt", "Mwst", "MWST", "MWSt", "Mehrwertsteuer", "USt", "Ust",
    "Umsatzsteuer", "Steuer", "davon MwSt", "inkl. MwSt", "zzgl. MwSt",
    "Vorsteuer", "Steuerbetrag", "MwSt-Betrag",
    # English
    "VAT", "V.A.T.", "Tax", "Sales Tax", "GST", "HST",
    "Value Added Tax", "Tax Amount", "incl. VAT", "excl. VAT",
    # Turkish
    "KDV", "Kdv", "Vergi", "KDV Tutarı", "Vergi Tutarı", "ÖTV",
    "KDV Dahil", "KDV Hariç",
    # French
    "TVA", "Taxe", "Montant TVA", "TVA Incluse", "Dont TVA",
    # Spanish
    "IVA", "Impuesto", "Monto IVA", "IVA Incluido",
    # Italian
    "IVA", "Imposta", "Importo IVA",
    # Portuguese
    "IVA", "Imposto", "Valor IVA",
    # Dutch
    "BTW", "Belasting", "BTW Bedrag",
    # Polish
    "VAT", "Podatek", "Kwota VAT",
    # Czech
    "DPH", "Daň",
    # Swedish
    "Moms", "Skatt", "Mervärdesskatt",
    # Norwegian
    "MVA", "Moms", "Merverdiavgift",
    # Danish
    "Moms", "Skat", "Merværdiafgift",
    # Finnish
    "ALV", "Vero", "Arvonlisävero",
    # Hungarian
    "ÁFA", "Adó",
    # Romanian
    "TVA", "Impozit",
    # Croatian
    "PDV", "Porez",
    # Greek
    "ΦΠΑ", "Φόρος",
    # Arabic
    "ضريبة القيمة المضافة", "الضريبة", "ض.ق.م",
    # Chinese
    "增值税", "税额", "税金",
    # Japanese
    "消費税", "税", "税額",
    # Korean
    "부가세", "세금", "부가가치세",
    # Russian
    "НДС", "Налог",
    # Ukrainian
    "ПДВ", "Податок",
]

# ── NET / SUBTOTAL keywords ──────────────────────────
NET_KEYWORDS = [
    # German
    "Nettobetrag", "Netto", "Zwischensumme", "Warenwert",
    # English
    "Subtotal", "Sub-Total", "Net", "Net Amount", "Before Tax",
    # Turkish
    "Ara Toplam", "Net Tutar", "Net", "KDV Hariç", "Matrah",
    # French
    "Sous-Total", "Total HT", "Montant HT", "Net",
    # Spanish
    "Subtotal", "Neto", "Base Imponible",
    # Italian
    "Subtotale", "Netto", "Imponibile",
    # Portuguese
    "Subtotal", "Líquido",
    # Dutch
    "Subtotaal", "Netto",
    # Polish
    "Netto", "Razem Netto", "Wartość Netto",
    # Czech
    "Základ Daně", "Netto",
    # Swedish / Norwegian / Danish
    "Netto", "Delsumma",
    # Finnish
    "Veroton", "Välisumma",
    # Hungarian
    "Nettó", "Részösszeg",
    # Russian
    "Нетто", "Подитог", "Без НДС",
    # Arabic
    "المجموع الفرعي", "صافي",
    # Chinese
    "小计", "不含税",
    # Japanese
    "小計", "税抜",
    # Korean
    "소계", "세전",
]

# ── INVOICE NUMBER keywords ──────────────────────────
INVOICE_NR_KEYWORDS = [
    # German
    "Rechnungsnummer", "Rechnungs-Nr", "Rechnung Nr", "Re. Nr", "Beleg-Nr",
    "Belegnummer", "Dokumentnummer", "Vorgangsnummer",
    # English
    "Invoice No", "Invoice Number", "Invoice #", "Inv No", "Bill No",
    "Receipt No", "Document No", "Reference No", "Ref",
    # Turkish
    "Fatura No", "Fatura Numarası", "Belge No", "Fiş No",
    # French
    "Numéro de Facture", "Facture No", "N° Facture", "Référence",
    # Spanish
    "Número de Factura", "Factura No", "N° Factura", "Referencia",
    # Italian
    "Numero Fattura", "Fattura No", "N° Fattura", "Riferimento",
    # Portuguese
    "Número da Fatura", "Fatura No", "N° Fatura",
    # Dutch
    "Factuurnummer", "Factuur Nr",
    # Polish
    "Numer Faktury", "Faktura Nr",
    # Czech
    "Číslo Faktury", "Faktura č",
    # Russian
    "Номер Счёта", "Счёт №",
    # Arabic
    "رقم الفاتورة",
    # Chinese
    "发票号", "发票编号",
    # Japanese
    "請求書番号",
    # Korean
    "송장번호", "청구서번호",
]

# ── DATE keywords ────────────────────────────────────
DATE_KEYWORDS = [
    # German
    "Rechnungsdatum", "Datum", "Belegdatum", "Ausstellungsdatum", "Leistungsdatum",
    # English
    "Date", "Invoice Date", "Issue Date", "Bill Date",
    # Turkish
    "Tarih", "Fatura Tarihi", "Düzenleme Tarihi",
    # French
    "Date", "Date de Facture", "Date d'Émission",
    # Spanish
    "Fecha", "Fecha de Factura", "Fecha de Emisión",
    # Italian
    "Data", "Data Fattura", "Data di Emissione",
    # Dutch
    "Datum", "Factuurdatum",
    # Polish
    "Data", "Data Faktury", "Data Wystawienia",
    # Russian
    "Дата", "Дата Счёта",
    # Arabic
    "التاريخ", "تاريخ الفاتورة",
    # Chinese
    "日期", "开票日期",
    # Japanese
    "日付", "請求日",
    # Korean
    "날짜", "발행일",
]


# ═══════════════════════════════════════════════════════
#  BUILD REGEX PATTERNS FROM DICTIONARY
# ═══════════════════════════════════════════════════════

def _build_amount_pattern(keywords: list[str]) -> list[str]:
    """Build regex patterns from keyword list for amount extraction."""
    patterns = []
    # Group keywords in batches to avoid too-long regex
    batch_size = 15
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i+batch_size]
        # Escape special regex chars in keywords
        escaped = [re.escape(k) for k in batch]
        keyword_group = "|".join(escaped)
        # Pattern: keyword followed by optional separator then amount
        patterns.append(
            rf"(?:{keyword_group})\s*[:=\-]?\s*[€$£¥₺₽CHF\sEURUSDGBPTRY]*\s*([\d]{{1,3}}(?:[.,]\d{{3}})*[.,]\d{{1,2}})"
        )
        patterns.append(
            rf"(?:{keyword_group})\s*[:=\-]?\s*[€$£¥₺₽CHF\sEURUSDGBPTRY]*\s*([\d]+[.,]\d{{2}})"
        )
    return patterns

def _build_label_pattern(keywords: list[str]) -> list[str]:
    """Build regex patterns from keyword list for label extraction (invoice nr, date)."""
    patterns = []
    batch_size = 15
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i+batch_size]
        escaped = [re.escape(k) for k in batch]
        keyword_group = "|".join(escaped)
        patterns.append(rf"(?:{keyword_group})\s*[:=\-#]?\s*([A-Za-z0-9\-/\.]+)")
    return patterns

def _build_date_pattern(keywords: list[str]) -> list[str]:
    """Build regex patterns for date extraction."""
    patterns = []
    batch_size = 15
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i+batch_size]
        escaped = [re.escape(k) for k in batch]
        keyword_group = "|".join(escaped)
        # DD.MM.YYYY or DD/MM/YYYY or YYYY-MM-DD
        patterns.append(rf"(?:{keyword_group})\s*[:=\-]?\s*(\d{{1,2}}[./\-]\d{{1,2}}[./\-]\d{{2,4}})")
    # Generic date patterns without keywords
    patterns.append(r"(\d{1,2}[./]\d{1,2}[./]\d{4})")
    patterns.append(r"(\d{4}-\d{2}-\d{2})")
    return patterns

def _build_vat_rate_pattern(vat_keywords: list[str]) -> list[str]:
    """Build regex patterns for VAT rate extraction."""
    patterns = []
    batch_size = 15
    for i in range(0, len(vat_keywords), batch_size):
        batch = vat_keywords[i:i+batch_size]
        escaped = [re.escape(k) for k in batch]
        keyword_group = "|".join(escaped)
        patterns.append(rf"(\d{{1,2}})\s*[%]\s*(?:{keyword_group})")
        patterns.append(rf"(?:{keyword_group})\s*[:=]?\s*(\d{{1,2}})\s*[%]")
    return patterns


# Build all patterns from dictionaries
TOTAL_PATTERNS = _build_amount_pattern(TOTAL_KEYWORDS)
VAT_AMOUNT_PATTERNS = _build_amount_pattern(VAT_KEYWORDS)
NET_PATTERNS = _build_amount_pattern(NET_KEYWORDS)
INVOICE_NR_PATTERNS = _build_label_pattern(INVOICE_NR_KEYWORDS)
DATE_PATTERNS = _build_date_pattern(DATE_KEYWORDS)
VAT_RATE_PATTERNS = _build_vat_rate_pattern(VAT_KEYWORDS)

# Extra fallback patterns for amounts with currency symbols
TOTAL_PATTERNS.extend([
    r"[€]\s*([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})",
    r"[€]\s*([\d]+[.,]\d{2})",
    r"([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*[€]",
    r"[$]\s*([\d]{1,3}(?:[,]\d{3})*[.]\d{2})",
    r"[£]\s*([\d]{1,3}(?:[,]\d{3})*[.]\d{2})",
    r"[₺]\s*([\d]{1,3}(?:[.,]\d{3})*[.,]\d{2})",
])

# Currency patterns
CURRENCY_PATTERNS = [
    (r"€|EUR|Euro|euro", "EUR"),
    (r"\$|USD|Dollar|dollar", "USD"),
    (r"£|GBP|Pound|pound", "GBP"),
    (r"₺|TRY|TL|Türk Lirası|Lira", "TRY"),
    (r"CHF|Franken|Schweizer Franken", "CHF"),
    (r"zł|PLN|Złoty", "PLN"),
    (r"Kč|CZK|Koruna", "CZK"),
    (r"kr|SEK|Krona", "SEK"),
    (r"¥|JPY|CNY|Yuan|Yen", "JPY"),
    (r"₽|RUB|Рубль", "RUB"),
    (r"₹|INR|Rupee", "INR"),
    (r"₩|KRW|Won", "KRW"),
    (r"лв|BGN|Лев", "BGN"),
    (r"lei|RON|Leu", "RON"),
    (r"Ft|HUF|Forint", "HUF"),
    (r"kn|HRK|Kuna", "HRK"),
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
