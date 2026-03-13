"""
app/services/file_validator.py — v5
STREAMING validation: never loads whole file into RAM.
- 64KB magic bytes check from stream header
- MIME type from magic bytes (not extension)
- Extension vs content mismatch detection
- Size enforcement via streaming counter
"""
import hashlib
import io
import os
import shutil
import tempfile
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status
from app.core.config import settings

# Magic byte signatures → MIME
MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF",          "application/pdf"),
    (b"\x89PNG\r\n",   "image/png"),
    (b"\xff\xd8\xff",  "image/jpeg"),
    (b"II*\x00",       "image/tiff"),
    (b"MM\x00*",       "image/tiff"),
    # WEBP checked separately (RIFF....WEBP)
]

EXT_TO_MIME: dict[str, str] = {
    "pdf":  "application/pdf",
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "tiff": "image/tiff",
    "tif":  "image/tiff",
}

BLOCKED_EXTENSIONS = {
    "exe","bat","cmd","sh","ps1","vbs","js","jar","msi",
    "dll","so","dylib","php","py","rb","pl","go","rs",
    "zip","tar","gz","rar","7z","iso","img",
}


def _detect_mime(header: bytes) -> str | None:
    for sig, mime in MAGIC_SIGNATURES:
        if header[:len(sig)] == sig:
            return mime
    # WEBP: RIFF????WEBP
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


async def validate_and_save_upload(upload: UploadFile) -> tuple[str, str, int]:
    """
    Streams file to a temp path. Never loads full file into RAM.

    Returns: (tmp_path, detected_mime, file_size_bytes)
    Raises:  HTTPException on any validation failure
    """
    filename  = upload.filename or "upload"
    ext       = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunk_sz  = settings.UPLOAD_CHUNK_SIZE   # 64KB

    # ── 1. Block dangerous extensions immediately ─────────────────────────────
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"File type .{ext} is not allowed")

    # ── 2. Stream to temp file, check size, capture header ────────────────────
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
    header_bytes = b""
    total_size   = 0

    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            first_chunk = True
            while True:
                chunk = await upload.read(chunk_sz)
                if not chunk:
                    break
                total_size += len(chunk)

                if total_size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {settings.MAX_UPLOAD_MB}MB limit",
                    )

                if first_chunk:
                    header_bytes = chunk[:16]   # only need first 16 bytes for magic
                    first_chunk  = False

                tmp_file.write(chunk)
    except HTTPException:
        os.unlink(tmp_path)
        raise
    except Exception as e:
        os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Upload error: {e}")

    if total_size < 8:
        os.unlink(tmp_path)
        raise HTTPException(status_code=422, detail="File is empty or too small")

    # ── 3. Magic bytes → MIME detection ───────────────────────────────────────
    detected_mime = _detect_mime(header_bytes)
    if detected_mime is None:
        os.unlink(tmp_path)
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Allowed: PDF, PNG, JPG, WEBP, TIFF",
        )

    if detected_mime not in settings.ALLOWED_MIME_TYPES:
        os.unlink(tmp_path)
        raise HTTPException(status_code=415, detail=f"File type {detected_mime} not allowed")

    # ── 4. Extension vs content mismatch ─────────────────────────────────────
    declared_mime = EXT_TO_MIME.get(ext)
    if declared_mime and declared_mime != detected_mime:
        os.unlink(tmp_path)
        raise HTTPException(
            status_code=422,
            detail=f"File extension .{ext} does not match content ({detected_mime})",
        )

    return tmp_path, detected_mime, total_size


def file_hash_from_path(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Legacy sync validator (for unit tests) ────────────────────────────────────
def validate_upload(content: bytes, filename: str) -> str:
    """Sync validator for test suite — keeps existing tests working."""
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB}MB limit")
    if len(content) < 8:
        raise HTTPException(status_code=422, detail="File too small or empty")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"File type .{ext} not allowed")

    mime = _detect_mime(content[:16])
    if mime is None:
        raise HTTPException(status_code=415, detail="Unsupported file type")
    if mime not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail=f"File type {mime} not allowed")

    declared = EXT_TO_MIME.get(ext)
    if declared and declared != mime:
        raise HTTPException(status_code=422, detail="File extension does not match content")
    return mime
