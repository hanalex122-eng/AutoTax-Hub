import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
import io

from autotax.ocr import extract_text
from autotax.parser import parse_invoice
from autotax.db import init_db, save_invoice, SessionLocal
from autotax.models import Invoice, User, CashEntry
from autotax.auth import hash_password, verify_password, create_token, get_current_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("autotax")

app = FastAPI(
    title="AutoTax-HUB",
    version="5.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ok_list(items, total):
    return {"success": True, "items": items, "total": total}


def err(status: int, msg: str):
    raise HTTPException(status_code=status, detail={"success": False, "error": msg})


def safe_str(val, default=""):
    return val if val is not None else default


def safe_float(val, default=0.0):
    return val if val is not None else default


def safe_vat_rate(val):
    return val if val else "0%"


def safe_vendor(val):
    return val if val else "Unbekannt"


def safe_category(val):
    return val if val else "other"


def safe_invoice_type(val):
    return val if val in ("income", "expense") else "expense"


def safe_date_str(val):
    if not val:
        return ""
    return val


def parse_vat_rate_float(vat_rate_str):
    try:
        return float((vat_rate_str or "0").replace("%", ""))
    except (ValueError, TypeError):
        return 0.0


def calc_vat(gross, vat_rate_str):
    if not gross:
        return 0.0
    rate = parse_vat_rate_float(vat_rate_str)
    if rate <= 0:
        return 0.0
    return round(gross * rate / (100 + rate), 2)


def parse_date_str_to_datetime(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        pass
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        pass
    return None


def invoice_to_dict(i):
    return {
        "id": i.id,
        "vendor": safe_vendor(i.vendor),
        "invoice_number": safe_str(i.invoice_number),
        "invoice_type": safe_invoice_type(i.invoice_type),
        "total_amount": safe_float(i.total_amount),
        "vat_amount": safe_float(i.vat_amount),
        "vat_rate": safe_vat_rate(i.vat_rate),
        "date": safe_date_str(i.date),
        "payment_method": safe_str(i.payment_method),
        "category": safe_category(i.category),
        "processed": i.processed or False,
        "created_at": i.created_at.strftime("%Y-%m-%dT%H:%M:%S") if i.created_at else "",
    }


def cash_entry_to_dict(e):
    return {
        "id": e.id,
        "description": safe_str(e.description),
        "vendor": safe_vendor(e.vendor),
        "gross_amount": safe_float(e.gross_amount),
        "vat_amount": safe_float(e.vat_amount),
        "vat_rate": safe_vat_rate(e.vat_rate),
        "entry_type": safe_invoice_type(e.entry_type),
        "category": safe_category(e.category),
        "payment_method": safe_str(e.payment_method),
        "reference": safe_str(e.reference),
        "notes": safe_str(e.notes),
        "is_reconciled": e.is_reconciled or False,
        "invoice_id": e.invoice_id,
        "date": e.date.strftime("%Y-%m-%d") if e.date else "",
        "created_at": e.created_at.strftime("%Y-%m-%dT%H:%M:%S") if e.created_at else "",
    }


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "version": "5.4.0"}


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/app", response_class=HTMLResponse)
async def serve_frontend_app():
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/admin/reparse")
def admin_reparse():
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).all()
        count = 0
        for inv in invoices:
            if not inv.raw_text:
                continue
            parsed = parse_invoice(inv.raw_text)
            inv.total_amount = parsed["total_amount"]
            inv.vat_amount = parsed["vat_amount"]
            inv.vat_rate = parsed["vat_rate"]
            inv.vendor = parsed["vendor"]
            inv.category = parsed["category"]
            inv.date = parsed["date"]
            count += 1
        db.commit()
        return {"status": "done", "count": count}
    except Exception:
        db.rollback()
        logger.exception("Reparse failed")
        err(500, "Reparse failed")
    finally:
        db.close()


ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/tiff", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024


# ============================================================
# AUTH
# ============================================================

class AuthRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


@app.post("/auth/register")
def register(body: RegisterRequest):
    if len(body.password) < 6:
        err(400, "Password must be at least 6 characters")
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == body.email).first():
            err(400, "Email already registered")
        user = User(email=body.email, hashed_password=hash_password(body.password), full_name=body.full_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("User registered: %s", body.email)
        token = create_token(user.id, user.email)
        return {"success": True, "token": token, "email": user.email}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Registration error")
        err(500, "Registration failed")
    finally:
        db.close()


@app.post("/auth/login")
def login(body: AuthRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user or not verify_password(body.password, user.hashed_password):
            logger.warning("Failed login: %s", body.email)
            err(401, "Invalid email or password")
        logger.info("User logged in: %s", body.email)
        token = create_token(user.id, user.email)
        return {"success": True, "token": token, "email": user.email}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login error")
        err(500, "Login failed")
    finally:
        db.close()


# ============================================================
# INVOICES: UPLOAD
# ============================================================

@app.post("/invoices/upload")
async def upload_invoice(file: UploadFile = File(...), handwriting: bool = False, user: dict = Depends(get_current_user)):
    if file.content_type not in ALLOWED_TYPES:
        err(400, f"Invalid file type: {file.content_type}. Allowed: PDF, JPG, PNG, TIFF, WEBP")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        err(400, "File too large (max 5MB)")
    if len(content) == 0:
        err(400, "Empty file")

    await file.seek(0)

    logger.info("Upload by user %s: %s (%s, %d bytes)", user["sub"], file.filename, file.content_type, len(content))

    try:
        raw_text = await asyncio.wait_for(extract_text(file, handwriting=handwriting), timeout=15)
    except asyncio.TimeoutError:
        logger.error("OCR timeout for %s", file.filename)
        err(500, "OCR timeout")
    except Exception:
        logger.exception("OCR failed for %s", file.filename)
        err(500, "OCR processing failed")

    try:
        result = parse_invoice(raw_text)
    except Exception:
        logger.exception("Parsing failed for %s", file.filename)
        err(500, "Invoice parsing failed")

    try:
        invoice_id = save_invoice(result, user_id=user["sub"], filename=file.filename)
    except Exception:
        logger.exception("DB save failed")
        err(500, "Failed to save invoice")

    return {
        "id": invoice_id,
        "total_amount": safe_float(result.get("total_amount")),
        "filename": file.filename,
        "status": "ok",
    }


@app.post("/invoices/batch")
async def upload_batch(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
    results = []
    for file in files:
        try:
            if file.content_type not in ALLOWED_TYPES:
                results.append({"filename": file.filename, "status": "error", "message": "Invalid file type"})
                continue
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                results.append({"filename": file.filename, "status": "error", "message": "File too large"})
                continue
            if len(content) == 0:
                results.append({"filename": file.filename, "status": "error", "message": "Empty file"})
                continue
            await file.seek(0)
            try:
                raw_text = await asyncio.wait_for(extract_text(file, handwriting=False), timeout=15)
            except Exception:
                results.append({"filename": file.filename, "status": "error", "message": "OCR failed"})
                continue
            try:
                parsed = parse_invoice(raw_text)
            except Exception:
                results.append({"filename": file.filename, "status": "error", "message": "Parse failed"})
                continue
            invoice_id = save_invoice(parsed, user_id=user["sub"], filename=file.filename)
            results.append({
                "filename": file.filename,
                "status": "ok",
                "message": f"OK — €{safe_float(parsed.get('total_amount')):.2f}",
                "id": invoice_id,
            })
        except Exception as e:
            results.append({"filename": file.filename, "status": "error", "message": str(e)})
    return {"results": results}


# ============================================================
# INVOICES: LIST
# ============================================================

@app.get("/invoices")
def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = Query(None),
    vendor: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        q = db.query(Invoice).filter(Invoice.user_id == user["sub"])

        if search:
            q = q.filter(Invoice.raw_text.ilike(f"%{search}%"))
        if vendor:
            q = q.filter(Invoice.vendor.ilike(f"%{vendor}%"))
        if status == "processed":
            q = q.filter(Invoice.processed == True)
        elif status == "unprocessed":
            q = q.filter(Invoice.processed == False)
        if category:
            q = q.filter(Invoice.category == category)
        if date_from:
            q = q.filter(Invoice.date >= date_from)
        if date_to:
            q = q.filter(Invoice.date <= date_to)

        total_count = q.count()
        q = q.order_by(Invoice.created_at.desc())
        invoices = q.offset(skip).limit(limit).all()

        return ok_list(
            [invoice_to_dict(i) for i in invoices],
            total_count,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list invoices")
        err(500, "Failed to load invoices")
    finally:
        db.close()


# ============================================================
# INVOICES: DASHBOARD
# ============================================================

@app.get("/invoices/dashboard")
def invoice_dashboard(country: str = Query("DE"), user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()

        inc = [i for i in invoices if safe_invoice_type(i.invoice_type) == "income"]
        exp = [i for i in invoices if safe_invoice_type(i.invoice_type) == "expense"]

        total_income = sum(safe_float(i.total_amount) for i in inc)
        total_expenses = sum(safe_float(i.total_amount) for i in exp)
        net_profit = total_income - total_expenses

        total_vat_paid = sum(safe_float(i.vat_amount) for i in exp)
        total_vat_collected = sum(safe_float(i.vat_amount) for i in inc)
        vat_balance = total_vat_collected - total_vat_paid

        if country == "DE":
            if net_profit > 277826:
                tax_rate = 45
            elif net_profit > 61356:
                tax_rate = 42
            elif net_profit > 17005:
                tax_rate = 30
            elif net_profit > 10908:
                tax_rate = 14
            else:
                tax_rate = 0
        else:
            tax_rate = 30

        tax_estimate = round(net_profit * tax_rate / 100, 2) if net_profit > 0 else 0

        month_map = {}
        for i in invoices:
            d = safe_date_str(i.date)
            if not d or len(d) < 7 or "-" not in d:
                continue
            m = d[:7]
            if m not in month_map:
                month_map[m] = {"month": m, "income": 0.0, "expenses": 0.0}
            if safe_invoice_type(i.invoice_type) == "income":
                month_map[m]["income"] += safe_float(i.total_amount)
            else:
                month_map[m]["expenses"] += safe_float(i.total_amount)
        monthly_breakdown = sorted(month_map.values(), key=lambda x: x["month"])
        for mb in monthly_breakdown:
            mb["income"] = round(mb["income"], 2)
            mb["expenses"] = round(mb["expenses"], 2)

        cat_map = {}
        for i in invoices:
            c = safe_category(i.category)
            cat_map[c] = cat_map.get(c, 0) + safe_float(i.total_amount)
        by_category = [{"category": k, "total": round(v, 2)} for k, v in sorted(cat_map.items(), key=lambda x: -x[1])]

        return {
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_profit": round(net_profit, 2),
            "tax_estimate": tax_estimate,
            "tax_rate_applied": tax_rate,
            "income_count": len(inc),
            "expense_count": len(exp),
            "invoice_count": len(invoices),
            "monthly_breakdown": monthly_breakdown,
            "by_category": by_category,
            "total_vat_paid": round(total_vat_paid, 2),
            "total_vat_collected": round(total_vat_collected, 2),
            "vat_balance": round(vat_balance, 2),
        }
    except Exception:
        logger.exception("Dashboard failed")
        err(500, "Dashboard failed")
    finally:
        db.close()


# ============================================================
# INVOICES: SUMMARY
# ============================================================

@app.get("/invoices/summary")
def invoice_summary(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        total_count = len(invoices)
        processed = sum(1 for i in invoices if i.processed)
        unprocessed = total_count - processed
        total_revenue = sum(safe_float(i.total_amount) for i in invoices)
        return {
            "success": True,
            "total_count": total_count,
            "processed": processed,
            "unprocessed": unprocessed,
            "total_revenue": round(total_revenue, 2),
        }
    except Exception:
        logger.exception("Summary failed")
        err(500, "Failed to load summary")
    finally:
        db.close()


# ============================================================
# INVOICES: UPDATE (PATCH + PUT)
# ============================================================

class InvoiceUpdate(BaseModel):
    vendor: Optional[str] = None
    category: Optional[str] = None
    total_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[str] = None
    date: Optional[str] = None
    invoice_type: Optional[str] = None
    invoice_number: Optional[str] = None
    payment_method: Optional[str] = None
    processed: Optional[bool] = None


def _do_update_invoice(invoice_id: int, body: InvoiceUpdate, user: dict):
    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user["sub"]).first()
        if not inv:
            err(404, "Invoice not found")
        if body.vendor is not None:
            inv.vendor = body.vendor
        if body.category is not None:
            inv.category = body.category
        if body.total_amount is not None:
            inv.total_amount = body.total_amount
        if body.vat_amount is not None:
            inv.vat_amount = body.vat_amount
        if body.vat_rate is not None:
            inv.vat_rate = body.vat_rate
        if body.date is not None:
            inv.date = body.date
        if body.invoice_type is not None:
            inv.invoice_type = body.invoice_type
        if body.invoice_number is not None:
            inv.invoice_number = body.invoice_number
        if body.payment_method is not None:
            inv.payment_method = body.payment_method
        if body.processed is not None:
            inv.processed = body.processed
        db.commit()
        db.refresh(inv)
        return {"success": True, **invoice_to_dict(inv)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Update invoice failed")
        err(500, "Failed to update invoice")
    finally:
        db.close()


@app.patch("/invoices/{invoice_id}")
def patch_invoice(invoice_id: int, body: InvoiceUpdate, user: dict = Depends(get_current_user)):
    return _do_update_invoice(invoice_id, body, user)


@app.put("/invoices/{invoice_id}")
def put_invoice(invoice_id: int, body: InvoiceUpdate, user: dict = Depends(get_current_user)):
    return _do_update_invoice(invoice_id, body, user)


# ============================================================
# INVOICES: DELETE
# ============================================================

@app.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.user_id == user["sub"]).first()
        if not inv:
            err(404, "Invoice not found")
        db.delete(inv)
        db.commit()
        return {"success": True, "deleted": invoice_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Delete invoice failed")
        err(500, "Failed to delete invoice")
    finally:
        db.close()


class BulkDeleteRequest(BaseModel):
    ids: List[int]


@app.post("/invoices/bulk-delete")
def bulk_delete_invoices(body: BulkDeleteRequest, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        deleted = db.query(Invoice).filter(
            Invoice.id.in_(body.ids),
            Invoice.user_id == user["sub"],
        ).delete(synchronize_session="fetch")
        db.commit()
        return {"success": True, "deleted": deleted}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Bulk delete failed")
        err(500, "Bulk delete failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: MODELS
# ============================================================

class CashEntryCreate(BaseModel):
    description: str
    gross_amount: float
    entry_type: str
    vendor: Optional[str] = None
    category: Optional[str] = None
    vat_rate: Optional[str] = None
    payment_method: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    date: Optional[str] = None


class CashEntryUpdate(BaseModel):
    description: Optional[str] = None
    gross_amount: Optional[float] = None
    entry_type: Optional[str] = None
    vendor: Optional[str] = None
    category: Optional[str] = None
    vat_rate: Optional[str] = None
    payment_method: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    date: Optional[str] = None


# ============================================================
# BOOKKEEPING: LIST (GET /bookkeeping + /kassenbuch)
# ============================================================

def _list_bookkeeping(skip, limit, user):
    db = SessionLocal()
    try:
        q = db.query(CashEntry).filter(CashEntry.user_id == user["sub"])
        total_count = q.count()
        entries = q.order_by(CashEntry.date.desc()).offset(skip).limit(limit).all()
        return ok_list(
            [cash_entry_to_dict(e) for e in entries],
            total_count,
        )
    except Exception:
        logger.exception("Failed to list cash entries")
        err(500, "Failed to load cash entries")
    finally:
        db.close()


@app.get("/bookkeeping")
def list_bookkeeping(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), user: dict = Depends(get_current_user)):
    return _list_bookkeeping(skip, limit, user)


@app.get("/kassenbuch")
def list_kassenbuch(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), user: dict = Depends(get_current_user)):
    return _list_bookkeeping(skip, limit, user)


# ============================================================
# BOOKKEEPING: CREATE (POST /bookkeeping + /kassenbuch)
# ============================================================

def _create_bookkeeping(body: CashEntryCreate, user: dict):
    if body.entry_type not in ("income", "expense"):
        err(400, "entry_type must be 'income' or 'expense'")
    db = SessionLocal()
    try:
        entry_date = parse_date_str_to_datetime(body.date)
        vat_amount = calc_vat(body.gross_amount, body.vat_rate)
        entry = CashEntry(
            user_id=user["sub"],
            description=body.description,
            gross_amount=body.gross_amount,
            vat_amount=vat_amount,
            vat_rate=body.vat_rate or "0%",
            vendor=body.vendor or "Unbekannt",
            entry_type=body.entry_type,
            category=body.category or "other",
            payment_method=body.payment_method or "",
            reference=body.reference or "",
            notes=body.notes or "",
            date=entry_date,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return {"success": True, **cash_entry_to_dict(entry)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Create cash entry failed")
        err(500, "Failed to create entry")
    finally:
        db.close()


@app.post("/bookkeeping")
def create_bookkeeping(body: CashEntryCreate, user: dict = Depends(get_current_user)):
    return _create_bookkeeping(body, user)


@app.post("/kassenbuch")
def create_kassenbuch(body: CashEntryCreate, user: dict = Depends(get_current_user)):
    return _create_bookkeeping(body, user)


# ============================================================
# BOOKKEEPING: UPDATE (PATCH+PUT /bookkeeping/{id} + /kassenbuch/{id})
# ============================================================

def _update_bookkeeping(entry_id: int, body: CashEntryUpdate, user: dict):
    db = SessionLocal()
    try:
        entry = db.query(CashEntry).filter(CashEntry.id == entry_id, CashEntry.user_id == user["sub"]).first()
        if not entry:
            err(404, "Entry not found")
        if body.description is not None:
            entry.description = body.description
        if body.gross_amount is not None:
            entry.gross_amount = body.gross_amount
        if body.entry_type is not None:
            if body.entry_type not in ("income", "expense"):
                err(400, "entry_type must be 'income' or 'expense'")
            entry.entry_type = body.entry_type
        if body.vendor is not None:
            entry.vendor = body.vendor
        if body.category is not None:
            entry.category = body.category
        if body.vat_rate is not None:
            entry.vat_rate = body.vat_rate
        if body.payment_method is not None:
            entry.payment_method = body.payment_method
        if body.reference is not None:
            entry.reference = body.reference
        if body.notes is not None:
            entry.notes = body.notes
        if body.date is not None:
            entry.date = parse_date_str_to_datetime(body.date)
        if body.gross_amount is not None or body.vat_rate is not None:
            entry.vat_amount = calc_vat(entry.gross_amount, entry.vat_rate)
        db.commit()
        db.refresh(entry)
        return {"success": True, **cash_entry_to_dict(entry)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Update cash entry failed")
        err(500, "Failed to update entry")
    finally:
        db.close()


@app.patch("/bookkeeping/{entry_id}")
def patch_bookkeeping(entry_id: int, body: CashEntryUpdate, user: dict = Depends(get_current_user)):
    return _update_bookkeeping(entry_id, body, user)


@app.put("/bookkeeping/{entry_id}")
def put_bookkeeping(entry_id: int, body: CashEntryUpdate, user: dict = Depends(get_current_user)):
    return _update_bookkeeping(entry_id, body, user)


@app.patch("/kassenbuch/{entry_id}")
def patch_kassenbuch(entry_id: int, body: CashEntryUpdate, user: dict = Depends(get_current_user)):
    return _update_bookkeeping(entry_id, body, user)


@app.put("/kassenbuch/{entry_id}")
def put_kassenbuch(entry_id: int, body: CashEntryUpdate, user: dict = Depends(get_current_user)):
    return _update_bookkeeping(entry_id, body, user)


# ============================================================
# BOOKKEEPING: DELETE (/bookkeeping/{id} + /kassenbuch/{id})
# ============================================================

def _delete_bookkeeping(entry_id: int, user: dict):
    db = SessionLocal()
    try:
        entry = db.query(CashEntry).filter(CashEntry.id == entry_id, CashEntry.user_id == user["sub"]).first()
        if not entry:
            err(404, "Entry not found")
        db.delete(entry)
        db.commit()
        return {"success": True, "deleted": entry_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Delete cash entry failed")
        err(500, "Failed to delete entry")
    finally:
        db.close()


@app.delete("/bookkeeping/{entry_id}")
def delete_bookkeeping(entry_id: int, user: dict = Depends(get_current_user)):
    return _delete_bookkeeping(entry_id, user)


@app.delete("/kassenbuch/{entry_id}")
def delete_kassenbuch(entry_id: int, user: dict = Depends(get_current_user)):
    return _delete_bookkeeping(entry_id, user)


# ============================================================
# BOOKKEEPING: SYNC INVOICES
# ============================================================

@app.post("/bookkeeping/sync-invoices")
def sync_invoices_to_bookkeeping(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        existing_invoice_ids = set()
        all_entries = db.query(CashEntry).filter(CashEntry.user_id == user["sub"]).all()
        for e in all_entries:
            if e.invoice_id:
                existing_invoice_ids.add(e.invoice_id)

        synced = 0
        skipped = 0
        for inv in invoices:
            if inv.id in existing_invoice_ids:
                skipped += 1
                continue
            vat_amount = calc_vat(safe_float(inv.total_amount), safe_vat_rate(inv.vat_rate))
            entry_date = parse_date_str_to_datetime(inv.date) if inv.date else inv.created_at
            entry = CashEntry(
                user_id=user["sub"],
                description=safe_vendor(inv.vendor),
                vendor=safe_vendor(inv.vendor),
                gross_amount=safe_float(inv.total_amount),
                vat_amount=vat_amount,
                vat_rate=safe_vat_rate(inv.vat_rate),
                entry_type=safe_invoice_type(inv.invoice_type),
                category=safe_category(inv.category),
                payment_method=safe_str(inv.payment_method),
                invoice_id=inv.id,
                date=entry_date,
            )
            db.add(entry)
            synced += 1
        db.commit()
        return {"synced": synced, "skipped": skipped}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Sync invoices failed")
        err(500, "Sync failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: RECONCILE
# ============================================================

@app.post("/bookkeeping/{entry_id}/reconcile")
def reconcile_entry(entry_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        entry = db.query(CashEntry).filter(CashEntry.id == entry_id, CashEntry.user_id == user["sub"]).first()
        if not entry:
            err(404, "Entry not found")
        entry.is_reconciled = not entry.is_reconciled
        db.commit()
        db.refresh(entry)
        return {"success": True, **cash_entry_to_dict(entry)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Reconcile failed")
        err(500, "Reconcile failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: SUMMARY
# ============================================================

@app.get("/bookkeeping/summary/overview")
def bookkeeping_summary(year: int = Query(None), user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        q = db.query(CashEntry).filter(CashEntry.user_id == user["sub"])
        if year:
            q = q.filter(CashEntry.date >= datetime(year, 1, 1))
            q = q.filter(CashEntry.date < datetime(year + 1, 1, 1))
        entries = q.all()
        total_income = sum(safe_float(e.gross_amount) for e in entries if e.entry_type == "income")
        total_expenses = sum(safe_float(e.gross_amount) for e in entries if e.entry_type == "expense")
        vat_collected = sum(safe_float(e.vat_amount) for e in entries if e.entry_type == "income")
        vat_paid = sum(safe_float(e.vat_amount) for e in entries if e.entry_type == "expense")
        return {
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_profit": round(total_income - total_expenses, 2),
            "vat_balance": round(vat_collected - vat_paid, 2),
            "entry_count": len(entries),
        }
    except Exception:
        logger.exception("Summary failed")
        err(500, "Summary failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: EXPORT CSV
# ============================================================

@app.get("/bookkeeping/export/csv")
def export_bookkeeping_csv(year: int = Query(None), user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        q = db.query(CashEntry).filter(CashEntry.user_id == user["sub"])
        if year:
            q = q.filter(CashEntry.date >= datetime(year, 1, 1))
            q = q.filter(CashEntry.date < datetime(year + 1, 1, 1))
        entries = q.order_by(CashEntry.date.desc()).all()
        buf = io.StringIO()
        buf.write("Datum,Typ,Beschreibung,Lieferant,Betrag,MwSt,MwSt-Satz,Kategorie,Zahlungsart,Beleg-Nr.\n")
        for e in entries:
            date_str = e.date.strftime("%d.%m.%Y") if e.date else ""
            desc = (e.description or "").replace('"', '""')
            vendor = (e.vendor or "").replace('"', '""')
            buf.write(f'{date_str},{e.entry_type or ""},"{desc}","{vendor}",{safe_float(e.gross_amount):.2f},{safe_float(e.vat_amount):.2f},{safe_vat_rate(e.vat_rate)},{safe_category(e.category)},{safe_str(e.payment_method)},{safe_str(e.reference)}\n')
        buf.seek(0)
        return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=kassenbuch_{year or 'all'}.csv"})
    except Exception:
        logger.exception("Bookkeeping CSV export failed")
        err(500, "Export failed")
    finally:
        db.close()


# ============================================================
# TAX: EÜR
# ============================================================

@app.get("/tax/euer")
def list_euer(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        years = set()
        for i in invoices:
            d = safe_date_str(i.date)
            if len(d) >= 4:
                years.add(d[:4])
        result = []
        for y in sorted(years):
            year_invs = [i for i in invoices if safe_date_str(i.date).startswith(y)]
            einnahmen = sum(safe_float(i.total_amount) for i in year_invs if safe_invoice_type(i.invoice_type) == "income")
            ausgaben = sum(safe_float(i.total_amount) for i in year_invs if safe_invoice_type(i.invoice_type) == "expense")
            result.append({
                "id": int(y),
                "steuerjahr": int(y),
                "summe_einnahmen": round(einnahmen, 2),
                "summe_ausgaben": round(ausgaben, 2),
                "gewinn_verlust": round(einnahmen - ausgaben, 2),
            })
        return result
    except Exception:
        logger.exception("EÜR list failed")
        err(500, "Failed")
    finally:
        db.close()


@app.post("/tax/euer/auto-fill")
def auto_fill_euer(steuerjahr: int = Query(...), user: dict = Depends(get_current_user)):
    return {"success": True, "steuerjahr": steuerjahr, "status": "generated"}


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat_endpoint(body: dict = Body(...), user: dict = Depends(get_current_user)):
    message = body.get("message", "")
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        total_count = len(invoices)
        total_sum = sum(safe_float(i.total_amount) for i in invoices)
        categories = {}
        for i in invoices:
            c = safe_category(i.category)
            categories[c] = categories.get(c, 0) + 1
        cat_str = ", ".join(f"{k}: {v}" for k, v in categories.items()) if categories else "keine"

        msg_lower = message.lower()
        if any(w in msg_lower for w in ["wie viel", "wieviel", "summe", "total", "gesamt"]):
            reply = f"Du hast insgesamt {total_count} Rechnungen mit einem Gesamtbetrag von €{total_sum:.2f}."
        elif any(w in msg_lower for w in ["kategorie", "categories", "aufteilung"]):
            reply = f"Deine Rechnungen nach Kategorien: {cat_str}."
        elif any(w in msg_lower for w in ["mwst", "steuer", "vat", "umsatzsteuer"]):
            vat_total = sum(safe_float(i.vat_amount) for i in invoices)
            reply = f"Die gesamte MwSt über alle Rechnungen beträgt €{vat_total:.2f}."
        elif any(w in msg_lower for w in ["hilfe", "help", "was kannst"]):
            reply = "Ich kann dir bei Fragen zu deinen Rechnungen helfen: Gesamtbeträge, Kategorien, MwSt-Übersicht, Anzahl der Belege und mehr. Frag einfach!"
        else:
            reply = f"Du hast {total_count} Rechnungen (Gesamt: €{total_sum:.2f}). Kategorien: {cat_str}. Frag mich nach Details zu MwSt, Kategorien oder Beträgen!"
        return {"reply": reply}
    except Exception:
        logger.exception("Chat failed")
        return {"reply": "Entschuldigung, ein Fehler ist aufgetreten. Bitte versuche es erneut."}
    finally:
        db.close()


# ============================================================
# EXPORT: DATEV / CSV / EXCEL / JSON
# ============================================================

@app.get("/export/csv")
def export_csv(year: int = Query(None), user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        buf = io.StringIO()
        buf.write("Datum,Lieferant,Rechnungs-Nr.,Typ,Betrag,MwSt,MwSt-Satz,Kategorie,Zahlungsart\n")
        for i in invoices:
            d = safe_date_str(i.date)
            if year and not d.startswith(str(year)):
                continue
            vendor = (i.vendor or "").replace('"', '""')
            buf.write(f'{d},"{vendor}",{safe_str(i.invoice_number)},{safe_invoice_type(i.invoice_type)},{safe_float(i.total_amount):.2f},{safe_float(i.vat_amount):.2f},{safe_vat_rate(i.vat_rate)},{safe_category(i.category)},{safe_str(i.payment_method)}\n')
        buf.seek(0)
        return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=autotax_csv_{year or 'all'}.csv"})
    except Exception:
        logger.exception("CSV export failed")
        err(500, "Export failed")
    finally:
        db.close()


@app.get("/export/datev")
def export_datev(year: int = Query(None), user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        buf = io.StringIO()
        buf.write("Umsatz;Soll/Haben;Konto;Gegenkonto;BU;Belegdatum;Buchungstext;USt\n")
        for i in invoices:
            d = safe_date_str(i.date)
            if year and not d.startswith(str(year)):
                continue
            sh = "S" if safe_invoice_type(i.invoice_type) == "expense" else "H"
            date_str = ""
            parts = d.split("-")
            if len(parts) == 3:
                date_str = f"{parts[2]}{parts[1]}"
            amt = f"{safe_float(i.total_amount):.2f}".replace(".", ",")
            vendor = (i.vendor or "").replace(";", " ")
            vat = (i.vat_rate or "0%").replace("%", "")
            buf.write(f"{amt};{sh};4400;1200;{vat};{date_str};{vendor};{vat}\n")
        buf.seek(0)
        return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=autotax_datev_{year or 'all'}.csv"})
    except Exception:
        logger.exception("DATEV export failed")
        err(500, "Export failed")
    finally:
        db.close()


@app.get("/export/excel")
def export_excel(year: int = Query(None), user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        buf = io.StringIO()
        buf.write("Datum,Lieferant,Rechnungs-Nr.,Typ,Betrag,MwSt,MwSt-Satz,Kategorie,Zahlungsart\n")
        for i in invoices:
            d = safe_date_str(i.date)
            if year and not d.startswith(str(year)):
                continue
            vendor = (i.vendor or "").replace('"', '""')
            buf.write(f'{d},"{vendor}",{safe_str(i.invoice_number)},{safe_invoice_type(i.invoice_type)},{safe_float(i.total_amount):.2f},{safe_float(i.vat_amount):.2f},{safe_vat_rate(i.vat_rate)},{safe_category(i.category)},{safe_str(i.payment_method)}\n')
        buf.seek(0)
        return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=autotax_excel_{year or 'all'}.xlsx"})
    except Exception:
        logger.exception("Excel export failed")
        err(500, "Export failed")
    finally:
        db.close()


@app.get("/export/json")
def export_json(year: int = Query(None), user: dict = Depends(get_current_user)):
    import json as json_lib
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        data = []
        for i in invoices:
            d = safe_date_str(i.date)
            if year and not d.startswith(str(year)):
                continue
            data.append(invoice_to_dict(i))
        buf = io.StringIO()
        json_lib.dump(data, buf, indent=2, ensure_ascii=False)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/json", headers={"Content-Disposition": f"attachment; filename=autotax_{year or 'all'}.json"})
    except Exception:
        logger.exception("JSON export failed")
        err(500, "Export failed")
    finally:
        db.close()


# ============================================================
# DEBUG
# ============================================================

@app.post("/debug/seed")
def debug_seed(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        seed_data = [
            {"vendor": "Lidl", "total_amount": 45.80, "vat_rate": "19%", "category": "food", "invoice_type": "expense", "date": "2026-03-01"},
            {"vendor": "Amazon", "total_amount": 120.50, "vat_rate": "19%", "category": "electronics", "invoice_type": "expense", "date": "2026-03-05"},
            {"vendor": "Kunde A", "total_amount": 1500.00, "vat_rate": "19%", "category": "other", "invoice_type": "income", "date": "2026-03-10"},
            {"vendor": "Tankstelle", "total_amount": 89.99, "vat_rate": "19%", "category": "fuel", "invoice_type": "expense", "date": "2026-02-15"},
            {"vendor": "Restaurant", "total_amount": 35.50, "vat_rate": "7%", "category": "restaurant", "invoice_type": "expense", "date": "2026-02-20"},
        ]
        created = []
        for s in seed_data:
            rate = parse_vat_rate_float(s["vat_rate"])
            vat_amt = round(s["total_amount"] * rate / (100 + rate), 2) if rate > 0 else 0.0
            inv = Invoice(
                user_id=user["sub"],
                vendor=s["vendor"],
                total_amount=s["total_amount"],
                vat_amount=vat_amt,
                vat_rate=s["vat_rate"],
                category=s["category"],
                invoice_type=s["invoice_type"],
                date=s["date"],
                invoice_number="",
                payment_method="",
                raw_text=f"{s['vendor']} {s['total_amount']} EUR {s['vat_rate']}",
                processed=True,
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            created.append(invoice_to_dict(inv))
        return {"success": True, "items": created, "total": len(created)}
    except Exception:
        logger.exception("Seed failed")
        err(500, "Seed failed")
    finally:
        db.close()


@app.post("/debug/create-user")
def debug_create_user():
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "hanalex122@gmail.com").first():
            return {"success": True, "message": "User already exists"}
        user = User(email="hanalex122@gmail.com", hashed_password=hash_password("123456"))
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"success": True, "message": "User created", "id": user.id, "email": user.email}
    except Exception:
        logger.exception("Debug create-user failed")
        err(500, "Failed to create user")
    finally:
        db.close()
