"""
app/api/v1/endpoints/invoices.py — v5.1
Features:
- Single invoice upload
- Batch upload (up to 20 files)
- Duplicate detection (SHA-256 hash)
- AI expense category detection
- Dashboard (income/expense/tax estimate)
- Invoice update (PUT)
- Category filter + date range filter
"""
import hashlib
import os
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, extract, case, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_verified_user, get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.invoice import (
    DashboardResponse,
    InvoiceListResponse,
    InvoiceOut,
    InvoiceUpdateRequest,
    StatsResponse,
)
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

        try:
            from app.services.parser_pipeline import process_invoice
            result = process_invoice(tmp_path)
        except ImportError:
            result = {"ocr_mode": "pending", "vendor": None, "category": None}

        if "error" in result:
            return {"filename": file.filename, "status": "error", "message": result["error"]}

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
            invoice_type="expense",
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


# ═══════════════════════════════════════
#  UPLOAD
# ═══════════════════════════════════════
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


# ═══════════════════════════════════════
#  BATCH UPLOAD
# ═══════════════════════════════════════
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


# ═══════════════════════════════════════
#  LIST (with filters)
# ═══════════════════════════════════════
@router.get("", response_model=InvoiceListResponse)
def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: str | None = None,
    invoice_type: str | None = Query(None, description="Filter: income or expense"),
    year: int | None = Query(None, description="Filter by year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    q = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if category:
        q = q.filter(Invoice.category == category)
    if invoice_type:
        q = q.filter(Invoice.invoice_type == invoice_type)
    if year:
        q = q.filter(Invoice.date.like(f"{year}%"))
    total = q.count()
    items = q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()
    return InvoiceListResponse(total=total, skip=skip, limit=limit, items=items)


# ═══════════════════════════════════════
#  STATS SUMMARY
# ═══════════════════════════════════════
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
                         by_category=[{"category": r.category or "Uncategorized", "count": r.count,
                                       "total": round(r.total or 0, 2)} for r in by_cat])


# ═══════════════════════════════════════
#  DASHBOARD — Income / Expense / Tax
# ═══════════════════════════════════════
@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    year: int | None = Query(None, description="Filter by year"),
    country: str = Query("DE", description="Tax country code (DE, AT, TR, FR, ES, IT, GB, CH, US, NL, PL)"),
    base_currency: str = Query("EUR", description="Base currency for aggregation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """
    Full dashboard with:
    - Total income vs expenses (multi-currency converted to base)
    - Net profit
    - Tax estimate (flexible per country)
    - VAT paid vs collected
    - Monthly breakdown
    - Category breakdown
    """
    from app.services.tax_engine import estimate_income_tax
    from app.services.currency_service import convert_to_base

    base = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if year:
        base = base.filter(Invoice.date.like(f"{year}%"))

    all_invoices = base.all()

    # Multi-currency: convert all amounts to base_currency
    total_income = 0.0
    total_expenses = 0.0
    vat_collected = 0.0
    vat_paid = 0.0

    for inv in all_invoices:
        amt = convert_to_base(inv.total_amount or 0, inv.currency or "EUR", base_currency)
        vat = convert_to_base(inv.vat_amount or 0, inv.currency or "EUR", base_currency)
        if inv.invoice_type == "income":
            total_income += amt
            vat_collected += vat
        else:
            total_expenses += amt
            vat_paid += vat

    net_profit = total_income - total_expenses
    vat_balance = vat_collected - vat_paid

    # Flexible tax estimation per country
    tax_result = estimate_income_tax(net_profit, country)
    tax_estimate = tax_result.get("tax_amount", 0.0)
    tax_rate = tax_result.get("effective_rate", 0.0)

    # Monthly breakdown
    monthly = {}
    for inv in all_invoices:
        month_key = _extract_month(inv.date)
        if month_key not in monthly:
            monthly[month_key] = {"month": month_key, "income": 0.0, "expenses": 0.0, "vat": 0.0}
        if inv.invoice_type == "income":
            monthly[month_key]["income"] += inv.total_amount or 0
        else:
            monthly[month_key]["expenses"] += inv.total_amount or 0
        monthly[month_key]["vat"] += inv.vat_amount or 0

    monthly_list = sorted(monthly.values(), key=lambda x: x["month"])
    for m in monthly_list:
        m["income"] = round(m["income"], 2)
        m["expenses"] = round(m["expenses"], 2)
        m["vat"] = round(m["vat"], 2)
        m["net"] = round(m["income"] - m["expenses"], 2)

    # Category breakdown
    cat_data = {}
    for inv in all_invoices:
        cat = inv.category or "Uncategorized"
        if cat not in cat_data:
            cat_data[cat] = {"category": cat, "count": 0, "total": 0.0, "vat": 0.0}
        cat_data[cat]["count"] += 1
        cat_data[cat]["total"] += inv.total_amount or 0
        cat_data[cat]["vat"] += inv.vat_amount or 0
    by_category = sorted(cat_data.values(), key=lambda x: x["total"], reverse=True)
    for c in by_category:
        c["total"] = round(c["total"], 2)
        c["vat"] = round(c["vat"], 2)

    expense_count = sum(1 for i in all_invoices if i.invoice_type == "expense")
    income_count = sum(1 for i in all_invoices if i.invoice_type == "income")

    return DashboardResponse(
        total_income=round(total_income, 2),
        total_expenses=round(total_expenses, 2),
        net_profit=round(net_profit, 2),
        tax_estimate=round(tax_estimate, 2),
        tax_rate_applied=round(tax_rate, 2),
        total_vat_paid=round(vat_paid, 2),
        total_vat_collected=round(vat_collected, 2),
        vat_balance=round(vat_balance, 2),
        monthly_breakdown=monthly_list,
        by_category=by_category,
        invoice_count=len(all_invoices),
        expense_count=expense_count,
        income_count=income_count,
    )


def _extract_month(date_str: str | None) -> str:
    """Extract YYYY-MM from various date formats."""
    if not date_str:
        return "unknown"
    try:
        if "-" in date_str and len(date_str) >= 7:
            return date_str[:7]
        if "." in date_str and len(date_str) >= 7:
            parts = date_str.split(".")
            if len(parts) >= 3:
                return f"{parts[2][:4]}-{parts[1]}"
    except Exception:
        pass
    return "unknown"


# ═══════════════════════════════════════
#  GET / UPDATE / DELETE
# ═══════════════════════════════════════
@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    return _own_or_404(invoice_id, current_user, db)


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int,
    payload: InvoiceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Update invoice fields. Only non-null fields are updated."""
    inv = _own_or_404(invoice_id, current_user, db)
    update_data = payload.model_dump(exclude_unset=True, exclude_none=True)

    if "invoice_type" in update_data and update_data["invoice_type"] not in ("income", "expense"):
        raise HTTPException(status_code=422, detail="invoice_type must be 'income' or 'expense'")

    for field, value in update_data.items():
        setattr(inv, field, value)
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_verified_user)):
    inv = _own_or_404(invoice_id, current_user, db)
    db.delete(inv)
    db.commit()
