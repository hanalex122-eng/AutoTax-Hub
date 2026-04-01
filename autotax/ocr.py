import os
import io
import logging
import httpx
from fastapi import UploadFile

logger = logging.getLogger("autotax")

OCR_API_KEY = os.getenv("OCR_API_KEY", "")
OCR_API_URL = "https://api.ocr.space/parse/image"


def preprocess_image(content: bytes) -> bytes:
    """Light preprocessing for OCR — resize large images to fit API limit (<1MB)."""
    try:
        from PIL import Image, ImageEnhance, ImageOps
        img = Image.open(io.BytesIO(content))

        # Fix EXIF rotation (iPhone photos are often rotated)
        try:
            from PIL import ImageOps as _io
            img = _io.exif_transpose(img)
        except Exception:
            pass

        # Convert to grayscale
        img = img.convert("L")

        # Resize large images (iPhone photos are 3024x4032 = 1.7MB+)
        # OCR.space free plan max 1MB — aim for <800KB
        max_dim = 1600
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Auto-contrast
        img = ImageOps.autocontrast(img, cutoff=1)

        # Mild contrast boost
        img = ImageEnhance.Contrast(img).enhance(1.3)

        # Mild sharpen
        img = ImageEnhance.Sharpness(img).enhance(1.5)

        # Save as JPEG (smaller, faster upload to OCR API)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        processed = buf.getvalue()

        # If still too large, reduce more
        if len(processed) > 900000:
            img.thumbnail((1200, 1200), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            processed = buf.getvalue()

        logger.info("Image preprocessed: %d bytes → %d bytes (%dx%d)", len(content), len(processed), img.width, img.height)
        return processed
    except Exception as e:
        logger.warning("Image preprocessing failed, using original: %s", e)
        return content


def extract_pdf_text(content: bytes) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def extract_pdf_page_as_image(content: bytes) -> bytes:
    """Convert first page of scanned PDF to PNG image bytes."""
    try:
        import pdfplumber
        from PIL import Image
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if pdf.pages:
                img = pdf.pages[0].to_image(resolution=150).original
                # Resize if too large for OCR API (max ~1MB, aim for <500KB)
                max_dim = 2000
                if img.width > max_dim or img.height > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                logger.info("PDF→image: %d bytes, %dx%d", buf.tell(), img.width, img.height)
                return buf.getvalue()
    except Exception as e:
        logger.warning("PDF→image failed: %s", e)
    return b""


async def extract_image_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        logger.warning("OCR skipped — no API key configured")
        return ""
    logger.info("OCR: processing %s (%d bytes), key=%s...", filename, len(content), OCR_API_KEY[:4])
    processed = preprocess_image(content)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OCR_API_URL,
                data={"apikey": OCR_API_KEY, "OCREngine": "1"},
                files={"file": (filename, processed)},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("OCR response: exit=%s, error=%s, text_len=%d",
                data.get("OCRExitCode"), data.get("IsErroredOnProcessing"),
                len(data.get("ParsedResults", [{}])[0].get("ParsedText", "")) if data.get("ParsedResults") else 0)
            if data.get("IsErroredOnProcessing"):
                return ""
            results = data.get("ParsedResults", [])
            if results:
                return results[0].get("ParsedText", "").strip()
            return ""
    except Exception as e:
        logger.warning("OCR API failed for %s: %s", filename, e)
        return ""


async def extract_handwriting_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        return ""
    processed = preprocess_image(content)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                OCR_API_URL,
                data={"apikey": OCR_API_KEY, "OCREngine": "2"},
                files={"file": (filename, processed)},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("IsErroredOnProcessing"):
                return ""
            results = data.get("ParsedResults", [])
            if results:
                return results[0].get("ParsedText", "").strip()
            return ""
    except Exception as e:
        logger.warning("OCR handwriting API failed: %s", e)
        return ""


async def extract_text(file: UploadFile, handwriting: bool = False, file_bytes: bytes = None) -> str:
    content = file_bytes if file_bytes is not None else await file.read()
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    if handwriting:
        return await extract_handwriting_text(content, file.filename or "upload.png")

    if content_type == "application/pdf" or filename.endswith(".pdf"):
        text = extract_pdf_text(content)
        if not text or len(text.strip()) < 20:
            img_bytes = extract_pdf_page_as_image(content)
            if img_bytes:
                return await extract_image_text(img_bytes, "scanned.png")
        return text

    if content_type.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".tiff")):
        return await extract_image_text(content, file.filename or "upload.png")

    # Fallback for plain text files
    return content.decode("utf-8", errors="ignore")


async def extract_text_and_qr(file: UploadFile, handwriting: bool = False, file_bytes: bytes = None) -> tuple[str, dict]:
    """Extract both OCR text and QR code data from a file.
    Returns (ocr_text, qr_data_dict).
    If file_bytes is provided, uses that instead of reading from file (avoids seek issues).
    """
    content = file_bytes if file_bytes is not None else await file.read()
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    logger.info("extract_text_and_qr: file=%s, type=%s, content_len=%d, from_bytes=%s", filename, content_type, len(content), file_bytes is not None)

    # QR code extraction (use original image — binarization can break QR)
    qr_data = {}
    try:
        from autotax.qr_reader import extract_qr_data
        qr_data = extract_qr_data(content, content_type)
    except Exception:
        pass  # QR reading is optional, don't break upload if it fails

    # Convert HEIC/HEIF to JPEG (iPhone camera format — not supported by OCR API)
    if "heic" in content_type or "heif" in content_type or filename.endswith((".heic", ".heif")):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(content))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=90)
            content = buf.getvalue()
            content_type = "image/jpeg"
            logger.info("Converted HEIC→JPEG: %d bytes", len(content))
        except Exception as e:
            logger.warning("HEIC conversion failed: %s", e)

    # OCR text extraction (uses preprocessed image internally)
    if handwriting:
        ocr_text = await extract_handwriting_text(content, file.filename or "upload.png")
    elif content_type == "application/pdf" or filename.endswith(".pdf"):
        ocr_text = extract_pdf_text(content)
        if not ocr_text or len(ocr_text.strip()) < 20:
            img_bytes = extract_pdf_page_as_image(content)
            if img_bytes:
                ocr_text = await extract_image_text(img_bytes, "scanned.png")
    elif content_type.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".tiff", ".heic", ".heif")):
        ocr_text = await extract_image_text(content, file.filename or "upload.png")
    else:
        ocr_text = content.decode("utf-8", errors="ignore")

    return ocr_text, qr_data
