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
    Grayscale → contrast boost → sharpen → binarize.
    Works well on dark, wrinkled, or low-quality receipts.
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        import math
        img = Image.open(io.BytesIO(content))

        # Fix EXIF rotation (phone photos are often rotated)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Convert to grayscale
        img = img.convert("L")

        # Auto-contrast: stretch histogram
        img = ImageOps.autocontrast(img, cutoff=2)

        # Deskew: detect and fix tilted images
        try:
            # Simple deskew using variance of row sums
            import numpy as np
            arr = np.array(img)
            best_angle = 0
            best_score = 0
            for angle in [a * 0.5 for a in range(-10, 11)]:  # -5 to +5 degrees
                rotated = img.rotate(angle, fillcolor=255, expand=False)
                row_sums = np.sum(np.array(rotated) < 128, axis=1)
                score = np.var(row_sums)
                if score > best_score:
                    best_score = score
                    best_angle = angle
            if abs(best_angle) > 0.5:
                img = img.rotate(best_angle, fillcolor=255, expand=True)
                logger.info("Deskewed image by %.1f degrees", best_angle)
        except ImportError:
            # numpy not available — skip deskew
            pass
        except Exception:
            pass

        # Increase contrast
        img = ImageEnhance.Contrast(img).enhance(1.8)

        # Increase brightness slightly (helps dark receipts)
        img = ImageEnhance.Brightness(img).enhance(1.2)

        # Sharpen
        img = ImageEnhance.Sharpness(img).enhance(2.0)

        # Denoise: median filter removes speckle noise
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # Binarize (adaptive threshold simulation)
        threshold = 140
        img = img.point(lambda x: 255 if x > threshold else 0, "1")

        # Convert back to grayscale for OCR API
        img = img.convert("L")

        # Save to bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        processed = buf.getvalue()
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
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    OCR_API_URL,
                    data={"apikey": OCR_API_KEY, "OCREngine": "2", "detectOrientation": "true", "scale": "true", "isTable": "true"},
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


async def extract_handwriting_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        return ""
    processed = preprocess_image(content)
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
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
