import os
import io
import logging
import httpx
from fastapi import UploadFile

logger = logging.getLogger("autotax")

OCR_API_KEY = os.getenv("OCR_API_KEY", "")
OCR_API_URL = "https://api.ocr.space/parse/image"


def _deskew_image(img):
    """Auto-rotate skewed images using projection profile analysis."""
    import numpy as np
    arr = np.array(img)
    # Invert so text is white on black for projection
    inv = 255 - arr
    best_angle = 0
    best_score = 0
    for angle_10x in range(-50, 51, 5):  # -5.0° to +5.0° in 0.5° steps
        angle = angle_10x / 10.0
        rotated = img.rotate(angle, expand=False, fillcolor=255)
        row_sums = np.sum(255 - np.array(rotated), axis=1)
        score = np.sum(row_sums ** 2)  # sharper peaks = better alignment
        if score > best_score:
            best_score = score
            best_angle = angle
    if abs(best_angle) > 0.3:
        logger.info("Deskew: rotating by %.1f°", best_angle)
        img = img.rotate(best_angle, expand=True, fillcolor=255)
    return img


def _prepare_base_image(content: bytes) -> "Image":
    """Load image, fix EXIF, convert to grayscale, resize. Returns PIL Image."""
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(content))
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    img = img.convert("L")
    max_dim = 1800
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img


def _apply_preset(img, preset: str) -> "Image":
    """Apply a named preprocessing preset to a grayscale PIL Image. Returns new Image."""
    from PIL import Image, ImageEnhance, ImageOps, ImageFilter
    import numpy as np
    img = img.copy()

    if preset == "handwriting":
        # Deskew
        try:
            img = _deskew_image(img)
        except Exception:
            pass
        # Shadow removal
        arr_s = np.array(img, dtype=np.float32)
        bg = np.array(img.filter(ImageFilter.GaussianBlur(radius=50)), dtype=np.float32)
        bg[bg == 0] = 1
        img = Image.fromarray(np.clip(arr_s * 255.0 / bg, 0, 255).astype(np.uint8))
        # Contrast + sharpen
        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        # Adaptive threshold
        arr = np.array(img)
        blur_arr = np.array(img.filter(ImageFilter.GaussianBlur(radius=15)))
        img = Image.fromarray(np.where(arr < blur_arr - 20, 0, 255).astype(np.uint8))
        img = img.filter(ImageFilter.MedianFilter(size=3))

    elif preset == "handwriting_bright":
        # For faint/light handwriting: higher gamma, stronger contrast
        try:
            img = _deskew_image(img)
        except Exception:
            pass
        # Gamma correction (brighten midtones)
        arr = np.array(img, dtype=np.float32) / 255.0
        img = Image.fromarray((np.power(arr, 0.6) * 255).astype(np.uint8))
        img = ImageOps.autocontrast(img, cutoff=3)
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = ImageEnhance.Sharpness(img).enhance(2.5)
        # Aggressive threshold
        arr = np.array(img)
        blur_arr = np.array(img.filter(ImageFilter.GaussianBlur(radius=20)))
        img = Image.fromarray(np.where(arr < blur_arr - 10, 0, 255).astype(np.uint8))
        img = img.filter(ImageFilter.MedianFilter(size=3))

    elif preset == "handwriting_dark":
        # For dark/shadow photos: shadow removal first, then softer threshold
        try:
            img = _deskew_image(img)
        except Exception:
            pass
        arr_s = np.array(img, dtype=np.float32)
        bg = np.array(img.filter(ImageFilter.GaussianBlur(radius=60)), dtype=np.float32)
        bg[bg == 0] = 1
        img = Image.fromarray(np.clip(arr_s * 255.0 / bg, 0, 255).astype(np.uint8))
        # Gamma darken
        arr = np.array(img, dtype=np.float32) / 255.0
        img = Image.fromarray((np.power(arr, 1.5) * 255).astype(np.uint8))
        img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Contrast(img).enhance(1.8)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        # Softer threshold
        arr = np.array(img)
        blur_arr = np.array(img.filter(ImageFilter.GaussianBlur(radius=18)))
        img = Image.fromarray(np.where(arr < blur_arr - 25, 0, 255).astype(np.uint8))

    elif preset == "printed":
        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageEnhance.Contrast(img).enhance(2.5)
        arr = np.array(img)
        blur_arr = np.array(img.filter(ImageFilter.GaussianBlur(radius=12)))
        img = Image.fromarray(np.where(arr < blur_arr - 15, 0, 255).astype(np.uint8))
        img = ImageEnhance.Sharpness(img).enhance(2.0)

    elif preset == "printed_soft":
        # Less aggressive — for clean scans that don't need heavy processing
        img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Sharpness(img).enhance(1.8)

    return img


def _image_to_jpeg(img, max_size: int = 950000) -> bytes:
    """Convert PIL Image to JPEG bytes, shrinking if needed to stay under max_size."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    processed = buf.getvalue()
    if len(processed) > max_size:
        img.thumbnail((1400, 1400))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        processed = buf.getvalue()
    return processed


def preprocess_image(content: bytes, for_handwriting: bool = False, preset: str = "") -> bytes:
    """Preprocessing for OCR — applies a preset to the image. If no preset given, uses default."""
    try:
        img = _prepare_base_image(content)

        if not preset:
            preset = "handwriting" if for_handwriting else "printed"

        img = _apply_preset(img, preset)
        processed = _image_to_jpeg(img)

        logger.info("Image preprocessed (preset=%s): %d bytes → %d bytes (%dx%d)",
                     preset, len(content), len(processed), img.width, img.height)
        img.close()
        return processed
    except Exception as e:
        logger.warning("Image preprocessing failed, using original: %s", e)
        return content


def normalize_handwriting_ocr(text: str) -> str:
    """Fix common OCR misreads in handwritten German text.
    Only applied to amount/date tokens — leaves description text intact."""
    import re
    lines = text.split("\n")
    result = []
    for line in lines:
        # Split line into tokens to selectively fix numeric contexts only
        parts = re.split(r"(\s+)", line)
        fixed = []
        for part in parts:
            # Only fix tokens that look numeric (contains digits or common misreads)
            if re.match(r"^[O0-9lISs|.,/:€₺\-]+$", part) and len(part) >= 2:
                part = part.replace("O", "0").replace("o", "0")
                part = part.replace("l", "1").replace("I", "1").replace("|", "1")
                part = part.replace("S", "5").replace("s", "5")
                part = part.replace("B", "8")
                # Fix comma→dot confusion in dates: "05,03,2026" → "05.03.2026"
                if re.match(r"^\d{1,2},\d{1,2},\d{2,4}$", part):
                    part = part.replace(",", ".")
            fixed.append(part)
        result.append("".join(fixed))
    return "\n".join(result)


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


async def _ocr_api_call(client, filename: str, content: bytes, engine: str = "1", is_table: bool = False) -> str:
    """Single OCR API call with given engine."""
    api_data = {"apikey": OCR_API_KEY, "OCREngine": engine}
    resp = await client.post(
        OCR_API_URL,
        data=api_data,
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
    logger.info("OCR: processing %d bytes, engine=dual", len(content))
    # Attempt 1: soft preset (safe for receipts/invoices) + Engine 1
    processed = preprocess_image(content, preset="printed_soft")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            text = await _ocr_api_call(client, filename, processed, "1")

            # If insufficient, try Engine 2 with same preset
            if len(text) < 10:
                logger.info("OCR Engine 1 insufficient (%d chars), retrying with Engine 2...", len(text))
                text2 = await _ocr_api_call(client, filename, processed, "2")
                if len(text2) > len(text):
                    text = text2

            # If still insufficient, try aggressive printed preset (for low quality scans)
            if len(text) < 20:
                logger.info("OCR soft preset insufficient (%d chars), trying printed preset", len(text))
                processed_hard = preprocess_image(content, preset="printed")
                text3 = await _ocr_api_call(client, filename, processed_hard, "1")
                if len(text3) > len(text):
                    text = text3

            return text
    except Exception as e:
        logger.warning("OCR API failed for %s: %s", filename, e)
        return ""


async def extract_handwriting_text(content: bytes, filename: str) -> str:
    if not OCR_API_KEY:
        return ""
    # Try multiple preprocessing presets and keep the best OCR result
    # Attempt 1: default handwriting preset + Engine 2
    processed = preprocess_image(content, preset="handwriting")
    best_text = ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            best_text = await _ocr_api_call(client, filename, processed, "2", is_table=True)
            logger.info("Handwriting preset=handwriting: %d chars", len(best_text))

            # If good enough, skip retries
            if len(best_text) >= 50:
                if best_text:
                    best_text = normalize_handwriting_ocr(best_text)
                return best_text

            # Attempt 2: bright preset (for faint handwriting)
            processed2 = preprocess_image(content, preset="handwriting_bright")
            text2 = await _ocr_api_call(client, filename, processed2, "2", is_table=True)
            logger.info("Handwriting preset=handwriting_bright: %d chars", len(text2))
            if len(text2) > len(best_text):
                best_text = text2

            # If still not enough, try dark preset
            if len(best_text) < 30:
                processed3 = preprocess_image(content, preset="handwriting_dark")
                text3 = await _ocr_api_call(client, filename, processed3, "2", is_table=True)
                logger.info("Handwriting preset=handwriting_dark: %d chars", len(text3))
                if len(text3) > len(best_text):
                    best_text = text3

            # Normalize common handwriting OCR errors (O→0, l→1, etc.)
            if best_text:
                best_text = normalize_handwriting_ocr(best_text)

            return best_text
    except Exception as e:
        logger.warning("OCR handwriting API failed: %s", e)
        # Return whatever we have so far
        if best_text:
            return normalize_handwriting_ocr(best_text)
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
    logger.info("extract_text_and_qr: type=%s, size=%d", content_type, len(content))

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


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ENABLE_LLM = os.getenv("ENABLE_LLM", "true").lower() == "true"
MAX_LLM_CALLS_PER_DAY = int(os.getenv("MAX_LLM_CALLS_PER_DAY", "50"))
MAX_LLM_CALLS_PER_USER = 10
LLM_CALLS_BY_PLAN = {"free": 2, "early": 20, "pro": 20}
LLM_TIMEOUT = 10.0
LLM_MAX_TEXT = 2000
LLM_MIN_TEXT = 50

# Duplicate detection: skip LLM if same text was processed recently
_llm_recent_hashes: dict[str, float] = {}  # hash -> timestamp
_LLM_DEDUP_TTL = 300  # 5 minutes

def _check_llm_limits(user_id: str = "", user_plan: str = "") -> bool:
    """Check if LLM call is allowed using persistent DB counters. Increments on success. Returns True if OK."""
    try:
        from datetime import date
        from sqlalchemy import func
        from autotax.db import SessionLocal
        from autotax.models import LlmUsage
        today = date.today().isoformat()
        db = SessionLocal()
        try:
            # Global daily count
            global_count = db.query(func.coalesce(func.sum(LlmUsage.count), 0)).filter(LlmUsage.date == today).scalar()
            if global_count >= MAX_LLM_CALLS_PER_DAY:
                logger.info("LLM skipped: daily limit reached (%d/%d)", global_count, MAX_LLM_CALLS_PER_DAY)
                return False
            # Per-user daily count
            if user_id:
                user_count = db.query(func.coalesce(func.sum(LlmUsage.count), 0)).filter(
                    LlmUsage.date == today, LlmUsage.user_id == str(user_id)
                ).scalar()
                plan_limit = LLM_CALLS_BY_PLAN.get(user_plan, LLM_CALLS_BY_PLAN.get("free", 2))
                if user_count >= plan_limit:
                    logger.info("LLM skipped: user %s plan=%s limit reached (%d/%d)", user_id, user_plan, user_count, plan_limit)
                    return False
            # Increment: upsert row
            existing = db.query(LlmUsage).filter(LlmUsage.date == today, LlmUsage.user_id == str(user_id or "_global")).first()
            if existing:
                existing.count += 1
            else:
                db.add(LlmUsage(user_id=str(user_id or "_global"), date=today, count=1))
            db.commit()
            return True
        finally:
            db.close()
    except Exception as e:
        logger.warning("LLM limit check failed (DB error), skipping LLM: %s", e)
        return False


async def llm_parse_table(ocr_text: str, user_id: str = "", user_plan: str = "") -> list[dict]:
    """LLM fallback: parse OCR text into structured rows using Claude Haiku.
    Only called when regex strategies fail. Returns [] on any error."""
    if not ENABLE_LLM:
        return []
    if not ANTHROPIC_API_KEY or not ocr_text or len(ocr_text.strip()) < LLM_MIN_TEXT:
        return []
    if user_plan not in ("free", "pro", "early"):
        logger.info("LLM skipped: user plan=%s unknown", user_plan)
        return []
    # Duplicate detection: skip if same text processed recently
    import hashlib, time as _t
    _text_hash = hashlib.md5(ocr_text.strip()[:500].encode()).hexdigest()
    _now = _t.time()
    # Evict expired entries
    _expired = [k for k, v in _llm_recent_hashes.items() if _now - v > _LLM_DEDUP_TTL]
    for k in _expired:
        del _llm_recent_hashes[k]
    if _text_hash in _llm_recent_hashes:
        logger.info("LLM skipped: duplicate text (hash=%s)", _text_hash[:8])
        return []
    if not _check_llm_limits(user_id, user_plan):
        return []
    _llm_recent_hashes[_text_hash] = _now
    logger.info("LLM CALL TRIGGERED: user=%s, plan=%s, text_len=%d", user_id, user_plan, len(ocr_text))
    # Truncate text for cost control
    ocr_text = ocr_text[:LLM_MAX_TEXT]
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": (
                        "Extract table rows from this OCR text of a German Kassenbuch (cash book).\n"
                        "Return ONLY a JSON array. Each element: {\"date\":\"YYYY-MM-DD\",\"description\":\"...\",\"amount\":0.00}\n"
                        "Rules:\n"
                        "- date: convert any format to YYYY-MM-DD. If unclear, use \"\"\n"
                        "- description: the vendor or purpose text\n"
                        "- amount: positive number, no currency symbol\n"
                        "- Skip headers, totals, page numbers\n"
                        "- If no rows found, return []\n\n"
                        "OCR text:\n" + ocr_text
                    )}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [{}])[0].get("text", "")
            # Extract JSON array from response
            import json, re
            m = re.search(r"\[.*\]", content, re.DOTALL)
            if not m:
                return []
            parsed = json.loads(m.group(0))
            if not isinstance(parsed, list):
                return []
            result = []
            for item in parsed[:100]:
                if not isinstance(item, dict):
                    continue
                amt = float(item.get("amount", 0) or 0)
                if amt <= 0:
                    continue
                result.append({
                    "date": str(item.get("date", "") or ""),
                    "description": str(item.get("description", "") or "Eintrag")[:80],
                    "income": 0,
                    "expense": round(amt, 2),
                    "is_uncertain": False,
                    "confidence": 0.75,
                    "llm_parsed": True,
                })
            logger.info("LLM parse: %d rows extracted", len(result))
            return result
    except Exception as e:
        logger.warning("LLM parse failed: %s", e)
        return []
