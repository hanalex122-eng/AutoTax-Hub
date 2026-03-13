"""
app/api/v1/endpoints/invoices.py — v5
Features:
- Single invoice upload
- Batch upload (up to 20 files)
- Duplicate detection (SHA-256 hash)
- AI expense category detection
"""
import hashlib
import os
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_verified_user, get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.invoice import InvoiceListResponse, InvoiceOut, StatsResponse
from app.services.file_validator import validate_and_save_upload

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _own_or_404(invoice_id: int, user: User, db: Session) -> Invoice:
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


async def _compute_hash(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


async def _process_single(file: UploadFile, db: Session, current_user: User) -> dict:
    tmp_path, detected_mime, file_size = await validate_and_save_upload(file)
    try:
        # Duplicate detection
        content_hash = await _compute_hash(tmp_path)
        existing = db.query(Invoice).filter(
            Invoice.user_id == current_user.id,
            Invoice.content_hash == content_hash,
        ).first()
        if existing:
            return {
                "filename": file.filename,
                "status": "duplicate",
                "duplicate_of": existing.id,
                "message": f"Diese Rechnung wurde bereits hochgeladen (ID: {existing.id})",
            }

        # OCR pipeline
        try:
            from app.services.parser_pipeline import process_invoice
            result = process_invoice(tmp_path)
        except ImportError:
            result = {"ocr_mode": "pending", "vendor": None, "category": None}

        if "error" in result:
            return {"filename": file.filename, "status": "error", "message": result["error"]}

        # AI Category detection
        category = result.get("category")
        if not category or category == "other":
            from app.services.ai_category import detect_category
            category = await detect_category(
                vendor=result.get("vendor") or "",
                invoice_text="",
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
            )

        invoice = Invoice(
            user_id=current_user.id,
            vendor=result.get("vendor"),
            invoice_number=result.get("invoice_number"),
            date=result.get("date"),
            total_amount=float(result.get("total") or 0),
            vat_rate=result.get("vat_rate"),
            vat_amount=float(result.get("vat_amount") or 0),
            currency=result.get("currency", "EUR"),
            category=category,
            payment_method=result.get("payment_method"),
            qr_data=result.get("qr_data"),
            filename=file.filename,
            ocr_mode=result.get("ocr_mode", "standard"),
            status="processed",
            content_hash=content_hash,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return {"filename": file.filename, "status": "ok", "invoice": invoice}

    except IntegrityError:
        db.rollback()
        return {"filename": file.filename, "status": "duplicate", "message": "Diese Rechnung wurde bereits hochgeladen."}
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/upload", response_model=InvoiceOut, status_code=201)
async def upload_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    result = await _process_single(file, db, current_user)
    if result["status"] == "duplicate":
        raise HTTPException(status_code=409, detail=result["message"])
    if result["status"] == "error":
        raise HTTPException(status_code=422, detail=result["message"])
    return result["invoice"]


@router.post("/batch", status_code=207)
async def batch_upload(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Upload up to 20 invoices at once. Returns per-file results."""
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 Dateien pro Batch-Upload erlaubt.")

    results = []
    ok_count = duplicate_count = error_count = 0

    for file in files:
        res = await _process_single(file, db, current_user)
        if res["status"] == "ok":
            ok_count += 1
            results.append({"filename": res["filename"], "status": "ok",
                            "invoice_id": res["invoice"].id, "vendor": res["invoice"].vendor,
                            "total": res["invoice"].total_amount, "category": res["invoice"].category})
        elif res["status"] == "duplicate":
            duplicate_count += 1
            results.append({"filename": res["filename"], "status": "duplicate",
                            "message": res["message"], "duplicate_of": res.get("duplicate_of")})
        else:
            error_count += 1
            results.append({"filename": res["filename"], "status": "error",
                            "message": res.get("message", "Verarbeitung fehlgeschlagen")})

    return {"total": len(files), "ok": ok_count, "duplicates": duplicate_count,
            "errors": error_count, "results": results}


@router.get("", response_model=InvoiceListResponse)
def list_invoices(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    category: str | None = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_verified_user),
):
    q = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if category:
        q = q.filter(Invoice.category == category)
    total = q.count()
    items = q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()
    return InvoiceListResponse(total=total, skip=skip, limit=limit, items=items)


@router.get("/stats/summary", response_model=StatsResponse)
def stats(db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    base = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    total_inv = base.count()
    total_amt = base.with_entities(func.sum(Invoice.total_amount)).scalar() or 0
    total_vat = base.with_entities(func.sum(Invoice.vat_amount)).scalar() or 0
    by_cat = base.with_entities(Invoice.category, func.count(Invoice.id).label("count"),
                                func.sum(Invoice.total_amount).label("total")).group_by(Invoice.category).all()
    return StatsResponse(total_invoices=total_inv, total_amount=round(total_amt, 2),
                         total_vat=round(total_vat, 2),
                         by_category=[{"category": r.category, "count": r.count,
                                       "total": round(r.total or 0, 2)} for r in by_cat])


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    return _own_or_404(invoice_id, current_user, db)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    inv = _own_or_404(invoice_id, current_user, db)
    db.delete(inv)
    db.commit()
