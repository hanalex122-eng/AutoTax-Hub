import os
import io
import logging
import httpx
from fastapi import UploadFile

logger = logging.getLogger("autotax")

OCR_API_KEY = os.getenv("OCR_API_KEY", "")
OCR_API_URL = "https://api.ocr.space/parse/image"


def preprocess_image(content: bytes) -> bytes:
    """Preprocess image for better OCR accuracy.
    EXIF fix → grayscale → auto-contrast → gentle sharpen → resize if too large.
    Deliberately MILD — aggressive binarization destroys text on many receipts.
    """
    try:
        from PIL import Image, ImageEnhance, ImageOps
        img = Image.open(io.BytesIO(content))

        # Fix EXIF rotation (phone photos are often rotated)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Resize if too large (long receipts) — OCR API struggles with huge images
        MAX_HEIGHT = 4000
        MAX_WIDTH = 2000
        w, h = img.size
        if h > MAX_HEIGHT or w > MAX_WIDTH:
            ratio = min(MAX_WIDTH / w, MAX_HEIGHT / h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.info("Resized image: %dx%d → %dx%d", w, h, new_w, new_h)

        # Convert to grayscale
        img = img.convert("L")

        # Auto-contrast: stretch histogram (gentle)
        img = ImageOps.autocontrast(img, cutoff=1)

        # Gentle contrast boost
        img = ImageEnhance.Contrast(img).enhance(1.4)

        # Gentle sharpen
        img = ImageEnhance.Sharpness(img).enhance(1.5)

        # NO binarization — it destroys text on thermal receipts
        # NO median filter — it blurs small text
        # NO deskew — OCR API handles rotation with detectOrientation=true

        # Save to bytes — use JPEG if PNG would be too large (OCR API limit ~1MB)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        processed = buf.getvalue()
        if len(processed) > 1024 * 1024:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            processed = buf.getvalue()
            logger.info("Image too large as PNG, saved as JPEG: %d bytes", len(processed))
        logger.info("Image preprocessed: %d bytes → %d bytes", len(content), len(processed))
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


async def extract_image_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        return ""
    processed = preprocess_image(content)

    # Try Engine 1 first (better for printed receipts), fallback to Engine 2
    for engine in ["1", "2"]:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    resp = await client.post(
                        OCR_API_URL,
                        data={
                            "apikey": OCR_API_KEY,
                            "OCREngine": engine,
                            "detectOrientation": "true",
                            "scale": "true",
                            "isTable": "true",
                        },
                        files={"file": (filename, processed)},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("IsErroredOnProcessing"):
                        break  # try next engine
                    results = data.get("ParsedResults", [])
                    if results:
                        text = results[0].get("ParsedText", "").strip()
                        if text and len(text) > 10:
                            logger.info("OCR Engine %s returned %d chars", engine, len(text))
                            return text
                    break  # empty result, try next engine
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == 1:
                    break  # try next engine
    return ""


async def extract_handwriting_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        return ""
    processed = preprocess_image(content)
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=12) as client:
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
        except (httpx.HTTPError, httpx.TimeoutException):
            if attempt == 1:
                return ""


async def extract_text(file: UploadFile, handwriting: bool = False) -> str:
    content = await file.read()
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    if handwriting:
        return await extract_handwriting_text(content, file.filename or "upload.png")

    if content_type == "application/pdf" or filename.endswith(".pdf"):
        return extract_pdf_text(content)

    if content_type.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".tiff")):
        return await extract_image_text(content, file.filename or "upload.png")

    # Fallback for plain text files
    return content.decode("utf-8", errors="ignore")


async def extract_text_and_qr(file: UploadFile, handwriting: bool = False) -> tuple[str, dict]:
    """Extract both OCR text and QR code data from a file.
    Returns (ocr_text, qr_data_dict).
    """
    content = await file.read()
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    # QR code extraction (use original image — binarization can break QR)
    qr_data = {}
    try:
        from autotax.qr_reader import extract_qr_data
        qr_data = extract_qr_data(content, content_type)
    except Exception:
        pass  # QR reading is optional, don't break upload if it fails

    # OCR text extraction (uses preprocessed image internally)
    if handwriting:
        ocr_text = await extract_handwriting_text(content, file.filename or "upload.png")
    elif content_type == "application/pdf" or filename.endswith(".pdf"):
        ocr_text = extract_pdf_text(content)
    elif content_type.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png", ".tiff")):
        ocr_text = await extract_image_text(content, file.filename or "upload.png")
    else:
        ocr_text = content.decode("utf-8", errors="ignore")

    return ocr_text, qr_data
