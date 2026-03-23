import os
import io
import httpx
from fastapi import UploadFile

OCR_API_KEY = os.getenv("OCR_API_KEY", "")
OCR_API_URL = "https://api.ocr.space/parse/image"


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
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    OCR_API_URL,
                    data={"apikey": OCR_API_KEY, "OCREngine": "1"},
                    files={"file": (filename, content)},
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
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    OCR_API_URL,
                    data={"apikey": OCR_API_KEY, "OCREngine": "2"},
                    files={"file": (filename, content)},
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
