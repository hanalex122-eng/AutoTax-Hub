"""
app/api/v1/endpoints/invoices.py — v5
Uses streaming upload (no full-file RAM load)
"""
import os
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

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


@router.post("/upload", response_model=InvoiceOut, status_code=201)
async def upload_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    # ✅ Streaming — never loads full file into RAM
    tmp_path, detected_mime, file_size = await validate_and_save_upload(file)

    try:
        from app.services.parser_pipeline import process_invoice
        result = process_invoice(tmp_path)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])

        invoice = Invoice(
            user_id        = current_user.id,
            vendor         = result.get("vendor"),
            invoice_number = result.get("invoice_number"),
            date           = result.get("date"),
            total_amount   = float(result.get("total") or 0),
            vat_rate       = result.get("vat_rate"),
            vat_amount     = float(result.get("vat_amount") or 0),
            currency       = result.get("currency", "EUR"),
            category       = result.get("category"),
            payment_method = result.get("payment_method"),
            qr_data        = result.get("qr_data"),
            filename       = file.filename,
            ocr_mode       = result.get("ocr_mode", "standard"),
            status         = "processed",
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.get("", response_model=InvoiceListResponse)
def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
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
    by_cat = base.with_entities(
        Invoice.category,
        func.count(Invoice.id).label("count"),
        func.sum(Invoice.total_amount).label("total"),
    ).group_by(Invoice.category).all()
    return StatsResponse(
        total_invoices=total_inv,
        total_amount=round(total_amt, 2),
        total_vat=round(total_vat, 2),
        by_category=[{"category": r.category, "count": r.count, "total": round(r.total or 0, 2)} for r in by_cat],
    )


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    return _own_or_404(invoice_id, current_user, db)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    inv = _own_or_404(invoice_id, current_user, db)
    db.delete(inv)
    db.commit()
