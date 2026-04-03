"""
AutoTax-HUB QR Code Reader
───────────────────────────
Reads QR codes from invoice images and extracts structured data:
  - Company/firm name
  - Amount / total
  - Date
  - Tax ID / VAT number
  - IBAN
  - Invoice number
  - BIC

Supports: ZUGFeRD, Factur-X, Swiss QR, EPC QR (SEPA), generic QR
"""

import re
import logging
from io import BytesIO

logger = logging.getLogger("autotax")


def decode_qr_from_image(content: bytes) -> list[str]:
    """Decode all QR/barcodes from an image. Returns list of decoded strings."""
    results = []

    # Try pyzbar first
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        from PIL import Image
        img = Image.open(BytesIO(content))

        # Resize large images for better barcode detection
        max_dim = 1600
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Try original
        decoded = pyzbar_decode(img)
        for obj in decoded:
            text = obj.data.decode("utf-8", errors="ignore").strip()
            if text:
                logger.info("QR/Barcode found (%s): %s", obj.type, text[:100])
                results.append(text)

        # If nothing found, try grayscale + higher contrast
        if not decoded:
            img_gray = img.convert("L")
            from PIL import ImageOps
            img_gray = ImageOps.autocontrast(img_gray, cutoff=5)
            decoded = pyzbar_decode(img_gray)
            for obj in decoded:
                text = obj.data.decode("utf-8", errors="ignore").strip()
                if text:
                    logger.info("QR/Barcode found after enhance (%s): %s", obj.type, text[:100])
                    results.append(text)

        if results:
            return results
        logger.info("No QR/barcode found in image (%dx%d)", img.width, img.height)
    except ImportError:
        logger.warning("pyzbar not available")
    except Exception as e:
        logger.warning("pyzbar failed: %s", e)

    # Try qreader as fallback
    try:
        from qreader import QReader
        import numpy as np
        from PIL import Image
        img = Image.open(BytesIO(content)).convert("RGB")
        qr = QReader()
        decoded = qr.detect_and_decode(np.array(img))
        for text in decoded:
            if text and text.strip():
                results.append(text.strip())
        if results:
            return results
    except ImportError:
        logger.debug("qreader not available")
    except Exception as e:
        logger.debug("qreader failed: %s", e)

    return results


def decode_qr_from_pdf(content: bytes) -> list[str]:
    """Try to extract QR codes from PDF pages (renders pages as images)."""
    results = []
    try:
        import pdfplumber
        from PIL import Image
        from pyzbar.pyzbar import decode as pyzbar_decode

        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages[:2]:  # First 2 pages only
                img = page.to_image(resolution=150).original
                decoded = pyzbar_decode(img)
                for obj in decoded:
                    text = obj.data.decode("utf-8", errors="ignore").strip()
                    if text:
                        logger.info("PDF QR/Barcode (%s): %s", obj.type, text[:100])
                        results.append(text)
    except ImportError:
        logger.warning("pyzbar not available for PDF QR")
    except Exception as e:
        logger.warning("PDF QR extraction failed: %s", e)

    return results


def parse_epc_qr(text: str) -> dict:
    """Parse EPC/SEPA QR code (GiroCode).
    Format: BCD\\n002\\n1\\nSCT\\nBIC\\nName\\nIBAN\\nEURAmount\\n\\n\\nReference\\nText
    """
    lines = text.strip().split("\n")
    if len(lines) < 7 or lines[0] != "BCD":
        return {}

    data = {}
    try:
        if len(lines) > 3:
            data["bic"] = lines[3].strip()
        if len(lines) > 4:
            data["company"] = lines[4].strip()
        if len(lines) > 5:
            data["iban"] = lines[5].strip()
        if len(lines) > 6:
            amt = lines[6].strip()
            m = re.search(r"(\d+[.,]?\d*)", amt)
            if m:
                data["amount"] = float(m.group(1).replace(",", "."))
        if len(lines) > 9:
            data["reference"] = lines[9].strip()
        if len(lines) > 10:
            data["description"] = lines[10].strip()
    except Exception:
        pass

    return data


def parse_swiss_qr(text: str) -> dict:
    """Parse Swiss QR-bill format (SPC)."""
    lines = text.strip().split("\n")
    if len(lines) < 5 or lines[0] != "SPC":
        return {}

    data = {}
    try:
        if len(lines) > 2:
            data["iban"] = lines[2].strip()
        # Creditor info
        if len(lines) > 4:
            data["company"] = lines[4].strip()
        if len(lines) > 5:
            data["address"] = lines[5].strip()
        # Amount
        if len(lines) > 18:
            amt = lines[18].strip()
            if amt:
                data["amount"] = float(amt.replace(",", "."))
        # Reference
        if len(lines) > 27:
            data["reference"] = lines[27].strip()
    except Exception:
        pass

    return data


def parse_generic_qr(text: str) -> dict:
    """Parse generic QR code text for invoice-related data."""
    data = {}

    # Company / Firm name patterns
    company_patterns = [
        r"(?:firma|company|name|société|unternehmen|firmenname|şirket)\s*[:=]\s*(.+?)(?:\n|$)",
        r"(?:von|from|de)\s*[:=]\s*(.+?)(?:\n|$)",
    ]
    for p in company_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            data["company"] = m.group(1).strip()
            break

    # If no explicit company field, first non-numeric line might be the company
    if "company" not in data:
        for line in text.strip().split("\n")[:3]:
            line = line.strip()
            if len(line) > 3 and not re.match(r"^[\d\s.,:€$%/\-+]+$", line) and not line.startswith(("BCD", "SPC", "http")):
                data["company"] = line
                break

    # Amount
    amt_patterns = [
        r"(?:betrag|amount|total|summe|montant|tutar|gesamt)\s*[:=]\s*(\d+[.,]?\d*)",
        r"(\d+[.,]\d{2})\s*(?:EUR|€|CHF|TRY|USD)",
        r"(?:EUR|€|CHF|TRY|USD)\s*(\d+[.,]\d{2})",
    ]
    for p in amt_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            data["amount"] = float(m.group(1).replace(",", "."))
            break

    # Date
    date_patterns = [
        r"(?:datum|date|tarih|fecha)\s*[:=]\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{2}\.\d{2}\.\d{4})",
    ]
    for p in date_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            data["date"] = m.group(1).strip()
            break

    # Tax ID / VAT number
    tax_patterns = [
        r"(?:ust[.-]?id|vat[.-]?id|tax[.-]?id|steuernummer|steuer-nr|vergi.?no)\s*[:=]?\s*([A-Z]{2}\d{9,12}|\d{2,3}/?\d{3}/?\d{5})",
        r"(DE\d{9}|FR\d{11}|AT\d{9}|CH\d{9}|TR\d{10})",
    ]
    for p in tax_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            data["tax_id"] = m.group(1).strip()
            break

    # IBAN
    m = re.search(r"([A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{0,4}\s?\d{0,2})", text)
    if m:
        data["iban"] = m.group(1).replace(" ", "")

    # Invoice number
    inv_patterns = [
        r"(?:rechnung|invoice|facture|fatura|beleg)\s*(?:nr|no|num|nummer)?\.?\s*[:=]?\s*([A-Za-z0-9\-/]+)",
    ]
    for p in inv_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            data["invoice_number"] = m.group(1).strip()
            break

    return data


def extract_qr_data(content: bytes, content_type: str = "") -> dict:
    """Main function: extract QR code data from file content.
    Returns dict with: company, amount, date, tax_id, iban, invoice_number, qr_raw
    """
    # Decode QR codes
    qr_texts = []
    if "pdf" in content_type.lower():
        qr_texts = decode_qr_from_pdf(content)
    else:
        qr_texts = decode_qr_from_image(content)

    if not qr_texts:
        return {}

    logger.info("QR codes found: %d", len(qr_texts))

    # Try parsing each QR code
    for qr_text in qr_texts:
        logger.info("QR content: %s", qr_text[:200])

        # Try EPC/SEPA QR
        result = parse_epc_qr(qr_text)
        if result:
            result["qr_raw"] = qr_text
            result["qr_type"] = "EPC/SEPA"
            return ensure_vat_fields(result)

        # Try Swiss QR
        result = parse_swiss_qr(qr_text)
        if result:
            result["qr_raw"] = qr_text
            result["qr_type"] = "Swiss QR"
            return ensure_vat_fields(result)

        # Try generic parsing
        result = parse_generic_qr(qr_text)
        if result:
            result["qr_raw"] = qr_text
            result["qr_type"] = "generic"
            return ensure_vat_fields(result)

    # Return raw QR text if nothing parsed
    return {"qr_raw": qr_texts[0], "qr_type": "unknown"}


def ensure_vat_fields(data: dict, default_rate: float = 19.0) -> dict:
    """Ensure QR data always contains total, net, and tax fields.
    If tax is missing, calculate from total using default VAT rate.
    """
    total = data.get("amount") or data.get("total") or 0
    if not total:
        return data
    total = float(total)
    tax = data.get("tax") or data.get("vat_amount") or 0
    tax = float(tax) if tax else 0
    if tax <= 0 and total > 0:
        net = round(total / (1 + default_rate / 100), 2)
        tax = round(total - net, 2)
    else:
        net = round(total - tax, 2)
    data["total"] = round(total, 2)
    data["net"] = net
    data["tax"] = tax
    return data
