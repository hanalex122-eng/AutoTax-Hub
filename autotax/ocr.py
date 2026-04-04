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

        # Resize if needed (OCR.space free max 1MB)
        max_dim = 1800
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Enhance for OCR
        img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Sharpness(img).enhance(1.8)

        # Save as JPEG — always under 1MB for OCR API
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        processed = buf.getvalue()

        # Shrink if still too large
        if len(processed) > 950000:
            img.thumbnail((1400, 1400), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88)
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


async def _ocr_api_call(client, filename: str, content: bytes, engine: str = "1") -> str:
    """Single OCR API call with given engine."""
    resp = await client.post(
        OCR_API_URL,
        data={"apikey": OCR_API_KEY, "OCREngine": engine},
        files={"file": (filename, content)},
    )
    resp.raise_for_status()
    data = resp.json()
    text_len = len(data.get("ParsedResults", [{}])[0].get("ParsedText", "")) if data.get("ParsedResults") else 0
    logger.info("OCR Engine %s: exit=%s, error=%s, text_len=%d", engine, data.get("OCRExitCode"), data.get("IsErroredOnProcessing"), text_len)
    if data.get("IsErroredOnProcessing"):
        return ""
    results = data.get("ParsedResults", [])
    if results:
        return results[0].get("ParsedText", "").strip()
    return ""


async def extract_image_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        logger.warning("OCR skipped — no API key configured")
        return ""
    logger.info("OCR: processing %s (%d bytes), key=%s...", filename, len(content), OCR_API_KEY[:4])
    processed = preprocess_image(content)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Engine 1: fast
            text = await _ocr_api_call(client, filename, processed, "1")

            # If Engine 1 failed or returned very little text, retry with Engine 2
            if len(text) < 10:
                logger.info("OCR Engine 1 insufficient (%d chars), retrying with Engine 2...", len(text))
                text2 = await _ocr_api_call(client, filename, processed, "2")
                if len(text2) > len(text):
                    text = text2

            return text
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


# --- ADDED START: Table-specific OCR preprocessing ---
def preprocess_table_image(content: bytes) -> bytes:
    """Aggressive preprocessing for handwritten table photos (Kassenbuch).
    Does NOT replace preprocess_image — used only for table import.
    Steps: EXIF fix → grayscale → deskew → shadow removal → high contrast → adaptive threshold → denoise."""
    try:
        from PIL import Image, ImageEnhance, ImageOps, ImageFilter
        import numpy as np
        img = Image.open(io.BytesIO(content))

        # Fix EXIF rotation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Grayscale
        img = img.convert("L")

        # Resize — keep larger for table detail (max 2000px)
        max_dim = 2000
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Deskew: find best rotation angle by projection profile
        try:
            thumb = img.copy()
            thumb.thumbnail((500, 500))
            arr_t = 255 - np.array(thumb)
            best_angle, best_score = 0, 0
            for a10 in range(-50, 51, 5):
                angle = a10 / 10.0
                rot = thumb.rotate(angle, expand=False, fillcolor=255)
                row_sums = np.sum(255 - np.array(rot), axis=1)
                score = np.sum(row_sums ** 2)
                if score > best_score:
                    best_score = score
                    best_angle = angle
            if abs(best_angle) > 0.3:
                logger.info("Table deskew: %.1f°", best_angle)
                img = img.rotate(best_angle, expand=True, fillcolor=255)
        except Exception:
            pass

        # Shadow removal: divide by blurred background
        arr_f = np.array(img, dtype=np.float32)
        bg = np.array(img.filter(ImageFilter.GaussianBlur(radius=50)), dtype=np.float32)
        bg[bg == 0] = 1
        no_shadow = np.clip(arr_f * 255.0 / bg, 0, 255).astype(np.uint8)
        img = Image.fromarray(no_shadow)

        # High contrast + sharpen
        img = ImageOps.autocontrast(img, cutoff=3)
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = ImageEnhance.Sharpness(img).enhance(2.5)

        # Adaptive threshold: binarize for clean text
        arr = np.array(img)
        blur_arr = np.array(img.filter(ImageFilter.GaussianBlur(radius=15)))
        binary = np.where(arr < blur_arr - 18, 0, 255).astype(np.uint8)
        img = Image.fromarray(binary)

        # Denoise
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # Save as JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        processed = buf.getvalue()

        if len(processed) > 950000:
            img.thumbnail((1600, 1600), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88)
            processed = buf.getvalue()

        logger.info("Table image preprocessed: %d bytes → %d bytes (%dx%d)", len(content), len(processed), img.width, img.height)
        img.close()
        return processed
    except Exception as e:
        logger.warning("Table preprocessing failed, using standard: %s", e)
        return preprocess_image(content)


async def extract_table_text(content: bytes, filename: str) -> str:
    """OCR for handwritten tables — tries aggressive preprocessing, then standard.
    Does NOT replace extract_handwriting_text — used only for table import."""
    if not OCR_API_KEY:
        return ""
    logger.info("Table OCR: processing %s (%d bytes)", filename, len(content))

    # Attempt 1: aggressive table preprocessing + Engine 2 (handwriting)
    processed = preprocess_table_image(content)
    best_text = ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            best_text = await _ocr_api_call(client, filename, processed, "2")
            logger.info("Table OCR attempt 1 (table_preprocess+E2): %d chars", len(best_text))

            # Attempt 2: if insufficient, try standard preprocess + Engine 2
            if len(best_text) < 40:
                processed_std = preprocess_image(content)
                text2 = await _ocr_api_call(client, filename, processed_std, "2")
                logger.info("Table OCR attempt 2 (standard+E2): %d chars", len(text2))
                if len(text2) > len(best_text):
                    best_text = text2

            return best_text
    except Exception as e:
        logger.warning("Table OCR failed: %s", e)
        return best_text
# --- ADDED END ---


# --- ADDED START: Auto-rotate table OCR (try 4 rotations) ---
async def extract_table_text_autorotate(content: bytes, filename: str) -> str:
    """Try 4 rotations (0, 90, 180, 270) and pick the one with most OCR text.
    Wraps extract_table_text — does NOT replace it."""
    if not OCR_API_KEY:
        return ""
    from PIL import Image, ImageOps

    logger.info("Table OCR autorotate: processing %s (%d bytes)", filename, len(content))

    img = Image.open(io.BytesIO(content))
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    best_text = ""
    best_rot = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for rot in [0, 90, 180, 270]:
            # Rotate image
            if rot == 0:
                rotated = img
            else:
                rotated = img.rotate(-rot, expand=True, fillcolor=255)

            # To bytes
            buf = io.BytesIO()
            rotated.save(buf, format="JPEG", quality=90)
            rot_bytes = buf.getvalue()

            # Preprocess + OCR
            processed = preprocess_table_image(rot_bytes)
            text = await _ocr_api_call(client, filename, processed, "2")
            logger.info("Table autorotate %d°: %d chars", rot, len(text))

            if len(text) > len(best_text):
                best_text = text
                best_rot = rot

            # Good enough — stop
            if len(best_text) >= 100:
                break

        logger.info("Table autorotate best: %d° with %d chars", best_rot, len(best_text))

        # Fallback: standard preprocess if still bad
        if len(best_text) < 40:
            processed_std = preprocess_image(content)
            text2 = await _ocr_api_call(client, filename, processed_std, "2")
            if len(text2) > len(best_text):
                best_text = text2
                logger.info("Table autorotate fallback: standard %d chars", len(text2))

    return best_text
# --- ADDED END ---
