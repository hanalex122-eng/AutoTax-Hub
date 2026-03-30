import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query, Body, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
import io

from autotax.ocr import extract_text, extract_text_and_qr
from autotax.parser import parse_invoice
from autotax.db import init_db, save_invoice, SessionLocal
from autotax.models import Invoice, User, CashEntry, UserCompany
from autotax.auth import hash_password, verify_password, create_token, create_access_token, create_refresh_token, decode_token, get_current_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("autotax")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="AutoTax-HUB",
    version="5.5.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "https://web-production-489ac.up.railway.app,https://app.autotaxhub.de,http://localhost:3000,http://localhost:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
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


def _fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    if not a or not b:
        return False
    a, b = a.lower().replace(" ", ""), b.lower().replace(" ", "")
    if a == b or a in b or b in a:
        return True
    common = sum(1 for c in a if c in b)
    return common / max(len(a), len(b)) >= threshold


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


def auto_create_cash_entry(invoice_id: int, user_id: int, data: dict):
    """Create a CashEntry automatically when an invoice is uploaded."""
    db = SessionLocal()
    try:
        # Skip if already synced
        existing = db.query(CashEntry).filter(CashEntry.invoice_id == invoice_id, CashEntry.user_id == user_id).first()
        if existing:
            return
        # Parse date safely
        date_val = None
        date_str = data.get("date") or ""
        if date_str:
            date_val = parse_date_str_to_datetime(date_str)
        if not date_val:
            date_val = datetime.now()
        entry = CashEntry(
            user_id=user_id,
            description=f"Rechnung: {data.get('vendor') or 'Unbekannt'}",
            vendor=data.get("vendor") or "Unbekannt",
            gross_amount=float(data.get("total_amount") or 0),
            vat_amount=float(data.get("vat_amount") or 0),
            vat_rate=data.get("vat_rate") or "0%",
            entry_type="expense",
            category=data.get("category") or "other",
            payment_method=data.get("payment_method") or "",
            reference=f"INV-{invoice_id}",
            notes=f"Auto-sync from invoice #{invoice_id}",
            is_reconciled=False,
            invoice_id=invoice_id,
            date=date_val,
        )
        db.add(entry)
        db.commit()
        logger.info("Auto-synced invoice %s to cash_entries", invoice_id)
    except Exception:
        db.rollback()
        logger.exception("Auto cash entry creation failed for invoice %s", invoice_id)
    finally:
        db.close()


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
        "ocr_snippet": (i.raw_text or "")[:200],
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
    return {"status": "ok", "version": "5.5.0"}


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/app", response_class=HTMLResponse)
async def serve_frontend_app():
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/agb", response_class=HTMLResponse)
def agb_page():
    return HTMLResponse(content="""<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><title>AGB — AutoTax-HUB</title>
<style>body{font-family:'DM Sans',sans-serif;max-width:800px;margin:40px auto;padding:20px;background:#050a12;color:#e8edf5;line-height:1.8}
h1{color:#10b981;font-size:28px}h2{color:#00a8cc;margin-top:30px;font-size:18px}strong{color:#f59e0b}
a{color:#10b981}p{margin:12px 0}</style></head><body>
<h1>Allgemeine Geschäftsbedingungen</h1>
<p><em>AutoTax-HUB — Stand: März 2026</em></p>
<h2>§1 Geltungsbereich</h2>
<p>Diese AGB gelten für die Nutzung von AutoTax-HUB, einem Software-Werkzeug zur automatischen Erfassung und Verwaltung von Belegen und Kassenbüchern.</p>
<h2>§2 Leistungsbeschreibung</h2>
<p>AutoTax-HUB bietet: OCR-Erkennung von Belegen, automatische Kategorisierung, Kassenbuchführung, Export in verschiedene Formate (CSV, DATEV, Excel, JSON), sowie eine EÜR-Übersicht.</p>
<h2>§3 Keine Steuerberatung</h2>
<p>AutoTax-HUB ist ein Software-Werkzeug. Der Dienst stellt <strong>KEINE Steuerberatung</strong> dar. Die automatische Erkennung kann Fehler enthalten. Der Nutzer ist <strong>allein verantwortlich</strong> für die Überprüfung aller Daten und die Richtigkeit seiner Buchhaltung. Für die Steuererklärung wird dringend empfohlen, einen Steuerberater zu konsultieren.</p>
<h2>§4 Haftungsbeschränkung</h2>
<p>Der Anbieter haftet <strong>nicht</strong> für: falsch erkannte Beträge, fehlerhafte MwSt-Berechnungen, steuerliche Nachteile, verlorene Daten oder sonstige Schäden, die aus der Nutzung des Dienstes entstehen. Die Haftung ist auf den vom Nutzer gezahlten Betrag der letzten 12 Monate beschränkt.</p>
<h2>§5 Prüfungspflicht</h2>
<p>Der Nutzer ist <strong>verpflichtet</strong>, alle automatisch erkannten Daten (Beträge, Lieferanten, Kategorien, MwSt-Sätze, Datumsangaben) vor Verwendung zu überprüfen und ggf. zu korrigieren.</p>
<h2>§6 Datenschutz</h2>
<p>Daten werden DSGVO-konform in der EU gespeichert. Originalbilder werden nach der OCR-Verarbeitung nicht dauerhaft auf dem Server gespeichert. Personenbezogene Daten werden nicht an Dritte weitergegeben. Details siehe <a href="/datenschutz">Datenschutzerklärung</a>.</p>
<h2>§7 Beta-Phase</h2>
<p>AutoTax-HUB befindet sich in der <strong>Beta-Phase</strong>. Funktionen können sich ändern. Es wird keine Garantie für ununterbrochene Verfügbarkeit gegeben.</p>
<h2>§8 Kündigung</h2>
<p>Das Nutzerkonto kann jederzeit gelöscht werden. Alle Daten werden dabei unwiderruflich entfernt.</p>
<p style="margin-top:40px;color:#64748b;font-size:13px">© 2026 AutoTax-HUB — Alle Rechte vorbehalten.</p>
</body></html>""")


@app.post("/admin/reset-password")
def admin_reset_password(body: dict = Body(...), user: dict = Depends(get_current_user)):
    email = body.get("email")
    new_password = body.get("new_password")
    if not email or not new_password:
        err(400, "email and new_password required")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            err(404, "User not found")
        user.hashed_password = hash_password(new_password)
        db.commit()
        return {"success": True, "message": f"Password reset for {email}"}
    finally:
        db.close()


@app.post("/admin/reparse")
def admin_reparse(user: dict = Depends(get_current_user)):
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
    company_name: Optional[str] = None


@app.post("/auth/register")
@limiter.limit("3/minute")
def register(request: Request, body: RegisterRequest):
    if len(body.password) < 8:
        err(400, "Password must be at least 8 characters")
    if not any(c.isupper() for c in body.password):
        err(400, "Password must contain at least 1 uppercase letter")
    if not any(c.isdigit() for c in body.password):
        err(400, "Password must contain at least 1 digit")
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == body.email).first():
            err(400, "Email already registered")
        user = User(email=body.email, hashed_password=hash_password(body.password), full_name=body.full_name)
        db.add(user)
        db.commit()
        db.refresh(user)
        # Auto-create company
        comp_name = (body.company_name or "").strip()
        if not comp_name:
            comp_name = (body.full_name or "").strip()
        if not comp_name:
            comp_name = body.email.split("@")[0].strip()
        if comp_name:
            company = UserCompany(user_id=user.id, company_name=comp_name)
            db.add(company)
            db.commit()
        logger.info("User registered: %s (company: %s)", body.email, comp_name)
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
@limiter.limit("5/minute")
def login(request: Request, body: AuthRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user or not verify_password(body.password, user.hashed_password):
            logger.warning("Failed login: %s", body.email)
            err(401, "Invalid email or password")
        logger.info("User logged in: %s", body.email)
        token = create_access_token(user.id, user.email)
        refresh = create_refresh_token(user.id, user.email)
        return {"success": True, "token": token, "refresh_token": refresh, "email": user.email}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login error")
        err(500, "Login failed")
    finally:
        db.close()


@app.post("/auth/refresh")
def refresh_token_endpoint(body: dict = Body(...)):
    refresh = body.get("refresh_token", "")
    if not refresh:
        err(400, "refresh_token required")
    try:
        data = decode_token(refresh, expected_type="refresh")
    except HTTPException:
        err(401, "Invalid or expired refresh token")
    new_access = create_access_token(data["sub"], data["email"])
    new_refresh = create_refresh_token(data["sub"], data["email"])
    return {"success": True, "token": new_access, "refresh_token": new_refresh}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@app.post("/auth/change-password")
def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    if len(body.new_password) < 8:
        err(400, "Neues Passwort muss mindestens 8 Zeichen haben")
    if not any(c.isupper() for c in body.new_password):
        err(400, "Neues Passwort muss mindestens 1 Großbuchstaben enthalten")
    if not any(c.isdigit() for c in body.new_password):
        err(400, "Neues Passwort muss mindestens 1 Zahl enthalten")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user["sub"]).first()
        if not u or not verify_password(body.old_password, u.hashed_password):
            err(401, "Altes Passwort ist falsch")
        u.hashed_password = hash_password(body.new_password)
        db.commit()
        return {"success": True, "message": "Passwort erfolgreich geändert"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Password change failed")
        err(500, "Passwort-Änderung fehlgeschlagen")
    finally:
        db.close()


@app.post("/auth/reset-password")
@limiter.limit("3/minute")
def reset_password(request: Request, body: dict = Body(...)):
    """Send password reset — for now just verify email exists and return token."""
    email = body.get("email", "").strip().lower()
    if not email:
        err(400, "E-Mail erforderlich")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            # Don't reveal if email exists
            return {"success": True, "message": "Falls ein Konto existiert, wurde ein Reset-Link gesendet."}
        # Generate reset token (valid 1 hour)
        reset_token = create_access_token(u.id, u.email)
        logger.info("Password reset requested for %s", email)
        # TODO: Send email with reset link. For now return token directly.
        return {"success": True, "message": "Reset-Token generiert. Bitte kontaktiere den Admin.", "reset_token": reset_token}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Password reset failed")
        err(500, "Reset fehlgeschlagen")
    finally:
        db.close()


# ============================================================
# INVOICES: UPLOAD
# ============================================================


@app.post("/invoices/create")
def create_invoice_manual(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Create invoice from JSON (for cross-page transfer). Skips duplicates."""
    db = SessionLocal()
    try:
        # Duplicate check
        dup = db.query(Invoice).filter(
            Invoice.user_id == user["sub"],
            Invoice.vendor == (body.get("vendor") or "Manual"),
            Invoice.total_amount == float(body.get("total_amount") or 0),
        ).first()
        if dup:
            return {"success": True, "id": dup.id, "message": "already exists"}
        inv = Invoice(
            user_id=user["sub"],
            filename=None,
            vendor=body.get("vendor") or "Manual",
            total_amount=float(body.get("total_amount") or 0),
            vat_amount=float(body.get("vat_amount") or 0),
            vat_rate=body.get("vat_rate") or "19%",
            date=body.get("date") or "",
            raw_text=body.get("raw_text") or "Manual entry",
            invoice_type=body.get("invoice_type") or "expense",
            invoice_number=body.get("invoice_number") or "",
            payment_method=body.get("payment_method") or "",
            category=body.get("category") or "other",
            processed=True,
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return {"success": True, "id": inv.id}
    except Exception:
        db.rollback()
        logger.exception("Create invoice failed")
        err(500, "Failed")
    finally:
        db.close()


@app.post("/invoices/upload")
@limiter.limit("20/minute")
async def upload_invoice(request: Request, file: UploadFile = File(...), handwriting: bool = False, invoice_type: str = "expense", user: dict = Depends(get_current_user)):
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
        raw_text, qr_data = await asyncio.wait_for(extract_text_and_qr(file, handwriting=handwriting), timeout=15)
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

    # Merge QR data (QR overrides OCR if available)
    if qr_data:
        logger.info("QR data found for %s: %s", file.filename, {k: v for k, v in qr_data.items() if k != "qr_raw"})
        if qr_data.get("company") and (not result.get("vendor") or result.get("vendor") == "Unbekannt"):
            result["vendor"] = qr_data["company"]
        if qr_data.get("amount") and (not result.get("total_amount") or result.get("total_amount") == 0):
            result["total_amount"] = qr_data["amount"]
        if qr_data.get("date") and (not result.get("date") or result["date"] == datetime.now().strftime("%Y-%m-%d")):
            result["date"] = qr_data["date"]
        if qr_data.get("invoice_number") and not result.get("invoice_number"):
            result["invoice_number"] = qr_data["invoice_number"]
        if qr_data.get("qr_raw"):
            result["raw_text"] = result.get("raw_text", "") + "\n\n[QR] " + qr_data["qr_raw"]

    # Duplicate check
    db_check = SessionLocal()
    try:
        dup = db_check.query(Invoice).filter(
            Invoice.user_id == user["sub"],
            Invoice.filename == file.filename,
            Invoice.total_amount == safe_float(result.get("total_amount")),
        ).first()
        if dup:
            return {"id": dup.id, "total_amount": safe_float(dup.total_amount), "filename": file.filename, "status": "duplicate", "message": "Duplicate invoice detected"}
    finally:
        db_check.close()

    if invoice_type in ("income", "expense"):
        result["invoice_type"] = invoice_type

    try:
        invoice_id = save_invoice(result, user_id=user["sub"], filename=file.filename)
    except Exception:
        logger.exception("DB save failed")
        err(500, "Failed to save invoice")

    auto_create_cash_entry(invoice_id, user["sub"], result)

    # Auto-detect income: if vendor matches user's registered company
    try:
        db_c = SessionLocal()
        user_companies = db_c.query(UserCompany).filter(UserCompany.user_id == user["sub"]).all()
        if user_companies:
            inv = db_c.query(Invoice).filter(Invoice.id == invoice_id).first()
            if inv and inv.vendor:
                vendor_lower = inv.vendor.lower()
                for uc in user_companies:
                    if uc.company_name.lower() in vendor_lower or vendor_lower in uc.company_name.lower() or _fuzzy_match(uc.company_name, inv.vendor):
                        inv.invoice_type = "income"
                        db_c.commit()
                        break
        db_c.close()
    except Exception:
        pass

    return {
        "id": invoice_id,
        "total_amount": safe_float(result.get("total_amount")),
        "filename": file.filename,
        "status": "ok",
    }


@app.post("/invoices/batch")
async def upload_batch(files: List[UploadFile] = File(...), invoice_type: str = "expense", user: dict = Depends(get_current_user)):
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
            # Duplicate check
            db_dup = SessionLocal()
            try:
                dup = db_dup.query(Invoice).filter(
                    Invoice.user_id == user["sub"],
                    Invoice.filename == file.filename,
                    Invoice.total_amount == safe_float(parsed.get("total_amount")),
                ).first()
            finally:
                db_dup.close()
            if dup:
                results.append({"filename": file.filename, "status": "duplicate", "message": "Duplikat erkannt"})
                continue
            if invoice_type in ("income", "expense"):
                parsed["invoice_type"] = invoice_type
            invoice_id = save_invoice(parsed, user_id=user["sub"], filename=file.filename)
            auto_create_cash_entry(invoice_id, user["sub"], parsed)
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
            # Smart multi-keyword search: split by space, ALL keywords must match
            # Search across vendor, category, and raw_text (OCR content)
            import unicodedata
            normalized = unicodedata.normalize("NFKD", search.lower().strip())
            keywords = [k.strip() for k in normalized.split() if k.strip()]
            from sqlalchemy import or_
            for kw in keywords:
                pattern = f"%{kw}%"
                q = q.filter(or_(
                    Invoice.raw_text.ilike(pattern),
                    Invoice.vendor.ilike(pattern),
                    Invoice.category.ilike(pattern),
                    Invoice.invoice_number.ilike(pattern),
                ))
        if vendor:
            q = q.filter(Invoice.vendor.ilike(f"%{vendor}%"))
        if status == "processed":
            q = q.filter(Invoice.processed == True)
        elif status == "unprocessed":
            q = q.filter(Invoice.processed == False)
        if category:
            q = q.filter(Invoice.category == category)
        # Validate date range (reject invalid years like 333333)
        import re as _re
        _current_year = datetime.now().year
        if date_from and _re.match(r"^\d{4}-\d{2}-\d{2}$", date_from):
            if 2020 <= int(date_from[:4]) <= _current_year + 1:
                q = q.filter(Invoice.date >= date_from)
        if date_to and _re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
            if 2020 <= int(date_to[:4]) <= _current_year + 1:
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
        all_invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        # Filter out invalid entries (amount=0 or vendor=Unbekannt)
        invoices = [i for i in all_invoices if safe_float(i.total_amount) > 0 and safe_vendor(i.vendor) != "Unbekannt"]

        # Use ONLY invoices as source of truth (no cash_entries to avoid double counting)
        inv_inc = [i for i in invoices if safe_invoice_type(i.invoice_type) == "income"]
        inv_exp = [i for i in invoices if safe_invoice_type(i.invoice_type) == "expense"]

        total_income = sum(safe_float(i.total_amount) for i in inv_inc)
        total_expenses = sum(safe_float(i.total_amount) for i in inv_exp)
        net_profit = total_income - total_expenses

        total_vat_paid = sum(safe_float(i.vat_amount) for i in inv_exp)
        total_vat_collected = sum(safe_float(i.vat_amount) for i in inv_inc)
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
            "income_count": len(inv_inc),
            "expense_count": len(inv_exp),
            "invoice_count": len(invoices),
            "invalid_count": len(all_invoices) - len(invoices),
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
        all_invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        invoices = [i for i in all_invoices if safe_float(i.total_amount) > 0 and safe_vendor(i.vendor) != "Unbekannt"]
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
        all_entries = q.all()
        entries = q.order_by(CashEntry.date.desc()).offset(skip).limit(limit).all()
        # Calculate totals across ALL entries (not just current page)
        total_gross = sum(safe_float(e.gross_amount) for e in all_entries)
        total_vat = sum(safe_float(e.vat_amount) for e in all_entries)
        total_income = sum(safe_float(e.gross_amount) for e in all_entries if e.entry_type == "income")
        total_expense = sum(safe_float(e.gross_amount) for e in all_entries if e.entry_type == "expense")
        return {
            "success": True,
            "items": [cash_entry_to_dict(e) for e in entries],
            "total": total_count,
            "summary": {
                "total_gross": round(total_gross, 2),
                "total_vat": round(total_vat, 2),
                "total_income": round(total_income, 2),
                "total_expense": round(total_expense, 2),
                "total_expenses": round(total_expense, 2),
                "net": round(total_income - total_expense, 2),
                "net_profit": round(total_income - total_expense, 2),
                "vat_balance": round(
                    sum(safe_float(e.vat_amount) for e in all_entries if e.entry_type == "income") -
                    sum(safe_float(e.vat_amount) for e in all_entries if e.entry_type == "expense"), 2),
                "entry_count": total_count,
            },
        }
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
        # Also create a corresponding Invoice so it appears in dashboard
        try:
            inv = Invoice(
                user_id=user["sub"],
                filename=None,
                vendor=body.vendor or "Manual Entry",
                total_amount=body.gross_amount or 0.0,
                vat_amount=vat_amount,
                vat_rate=body.vat_rate or "0%",
                date=body.date or "",
                raw_text=f"manual entry: {body.description}",
                invoice_type=body.entry_type,
                invoice_number="",
                payment_method=body.payment_method or "",
                category=body.category or "other",
                processed=True,
            )
            db.add(inv)
            db.commit()
            logger.info("Auto-created invoice from manual Kassenbuch entry %s", entry.id)
        except Exception:
            logger.exception("Failed to auto-create invoice from Kassenbuch entry")
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
        # Reverse sync: CashEntry → Invoice (for manual entries without invoice)
        existing_inv_vendors_amounts = set()
        for inv in invoices:
            existing_inv_vendors_amounts.add(f"{(inv.vendor or '').lower()}-{safe_float(inv.total_amount)}")
        rev_synced = 0
        for entry in all_entries:
            if entry.invoice_id:
                continue  # already linked to an invoice
            # Duplicate check: vendor + amount
            dup_key = f"{(entry.vendor or entry.description or '').lower()}-{safe_float(entry.gross_amount)}"
            if dup_key in existing_inv_vendors_amounts:
                continue  # already has matching invoice
            inv = Invoice(
                user_id=user["sub"],
                filename=None,
                vendor=entry.vendor or "Manual Entry",
                total_amount=safe_float(entry.gross_amount),
                vat_amount=safe_float(entry.vat_amount),
                vat_rate=entry.vat_rate or "0%",
                date=entry.date.strftime("%Y-%m-%d") if entry.date else "",
                raw_text=f"Sync from Kassenbuch: {safe_str(entry.description)}",
                invoice_type=entry.entry_type or "expense",
                invoice_number="",
                payment_method=safe_str(entry.payment_method),
                category=safe_category(entry.category),
                processed=True,
            )
            db.add(inv)
            rev_synced += 1

        db.commit()
        return {"synced": synced, "skipped": skipped, "reverse_synced": rev_synced}
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
# BOOKKEEPING: CSV IMPORT
# ============================================================

@app.post("/bookkeeping/import-csv")
async def import_csv(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    import csv
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    first_line = text.split("\n")[0] if text else ""
    delimiter = ";" if ";" in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    db = SessionLocal()
    imported = 0
    errors = []
    try:
        for idx, row in enumerate(reader, 1):
            try:
                # Flexible column mapping — supports Export format + custom formats
                vendor = row.get("Lieferant") or row.get("Vendor") or row.get("vendor") or ""
                beschreibung = row.get("Beschreibung") or row.get("description") or row.get("Description") or vendor or ""
                datum = row.get("Datum") or row.get("date") or row.get("Date") or ""
                betrag_raw = row.get("Betrag") or row.get("Ausgaben") or row.get("amount") or row.get("expenses") or "0"
                einnahmen = row.get("Einnahmen") or row.get("income") or "0"
                typ = row.get("Typ") or row.get("type") or row.get("Type") or ""
                category = row.get("Kategorie") or row.get("category") or row.get("Category") or "other"
                payment = row.get("Zahlungsart") or row.get("Zahlungsmethode") or row.get("payment_method") or ""
                mwst_raw = row.get("MwSt") or row.get("vat_amount") or ""
                mwst_satz = row.get("MwSt-Satz") or row.get("vat_rate") or "19%"
                inv_nr = row.get("Rechnungs-Nr.") or row.get("invoice_number") or ""
                if not vendor:
                    vendor = beschreibung[:50] or "Import"

                def _parse_num(s):
                    return float(str(s).replace(",", ".").replace("€", "").replace("%", "").replace(" ", "").strip() or "0")

                betrag_val = _parse_num(betrag_raw)
                einnahmen_val = _parse_num(einnahmen)

                # Determine type: from Typ column, or from Einnahmen column
                if typ.lower() in ("income", "einnahme", "einnahmen"):
                    entry_type = "income"
                    amount = betrag_val if betrag_val > 0 else einnahmen_val
                elif typ.lower() in ("expense", "ausgabe", "ausgaben"):
                    entry_type = "expense"
                    amount = betrag_val
                elif einnahmen_val > 0:
                    entry_type = "income"
                    amount = einnahmen_val
                else:
                    entry_type = "expense"
                    amount = betrag_val

                if amount <= 0 and not beschreibung:
                    continue

                # Duplicate check
                existing = db.query(CashEntry).filter(
                    CashEntry.user_id == user["sub"],
                    CashEntry.description == (beschreibung or vendor),
                    CashEntry.gross_amount == amount,
                ).first()
                if existing:
                    continue

                date_val = None
                if datum:
                    parts = datum.strip().split(".")
                    if len(parts) == 3:
                        try:
                            date_val = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        except ValueError:
                            pass
                    if not date_val:
                        date_val = parse_date_str_to_datetime(datum)
                if not date_val:
                    date_val = datetime.now()

                # Use MwSt from CSV if provided, otherwise calculate
                if mwst_raw:
                    vat_amount = _parse_num(mwst_raw)
                else:
                    rate = _parse_num(mwst_satz) if mwst_satz else 19
                    vat_amount = round(amount * rate / (100 + rate), 2) if amount > 0 else 0
                vat_rate_str = mwst_satz if mwst_satz else "19%"
                if "%" not in vat_rate_str:
                    vat_rate_str += "%"

                entry = CashEntry(
                    user_id=user["sub"],
                    description=beschreibung or vendor,
                    vendor=vendor,
                    gross_amount=amount,
                    vat_amount=vat_amount,
                    vat_rate=vat_rate_str,
                    entry_type=entry_type,
                    category=category,
                    payment_method=payment,
                    reference=f"CSV-Import Zeile {idx}",
                    notes="Importiert aus CSV",
                    date=date_val,
                )
                db.add(entry)

                inv = Invoice(
                    user_id=user["sub"],
                    filename=f"csv-import-{idx}",
                    vendor=vendor,
                    total_amount=amount,
                    vat_amount=vat_amount,
                    vat_rate=vat_rate_str,
                    date=date_val.strftime("%Y-%m-%d") if date_val else "",
                    raw_text=f"CSV Import: {beschreibung}",
                    invoice_type=entry_type,
                    invoice_number=inv_nr,
                    payment_method=payment,
                    category=category,
                    processed=True,
                )
                db.add(inv)
                imported += 1
            except Exception as e:
                errors.append(f"Zeile {idx}: {str(e)[:80]}")
        db.commit()
        return {"success": True, "imported": imported, "errors": errors}
    except Exception:
        db.rollback()
        logger.exception("CSV import failed")
        err(500, "CSV import failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: XLSX IMPORT
# ============================================================

@app.post("/bookkeeping/import-xlsx")
async def import_xlsx(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Import Excel (.xlsx) file into Kassenbuch + Rechnungen."""
    from openpyxl import load_workbook
    content = await file.read()
    wb = load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active
    db = SessionLocal()
    imported = 0
    errors = []
    try:
        headers = []
        for idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if idx == 1:
                headers = [str(c or "").strip().lower() for c in row]
                continue
            if not any(row):
                continue
            rd = dict(zip(headers, [c for c in row]))

            def _col(names):
                for n in names:
                    v = rd.get(n) or rd.get(n.lower())
                    if v is not None and str(v).strip():
                        return str(v).strip()
                return ""

            beschreibung = _col(["beschreibung", "description", "lieferant", "vendor"])
            datum = _col(["datum", "date"])
            vendor = _col(["lieferant", "vendor"]) or beschreibung[:50] or "Import"
            category = _col(["kategorie", "category"]) or "other"
            payment = _col(["zahlungsart", "zahlungsmethode", "payment_method"]) or ""
            inv_nr = _col(["rechnungs-nr.", "invoice_number"]) or ""
            typ = _col(["typ", "type"]) or ""

            def _num(names):
                raw = _col(names)
                if not raw:
                    return 0.0
                return float(str(raw).replace(",", ".").replace("€", "").replace(" ", "").strip() or "0")

            betrag = _num(["betrag", "ausgaben", "amount", "expenses"])
            einnahmen = _num(["einnahmen", "income"])
            mwst = _num(["mwst", "vat_amount"])
            mwst_satz = _col(["mwst-satz", "vat_rate"]) or "19%"
            if "%" not in mwst_satz:
                mwst_satz += "%"

            if typ.lower() in ("income", "einnahme", "einnahmen"):
                entry_type = "income"
                amount = betrag if betrag > 0 else einnahmen
            elif einnahmen > 0:
                entry_type = "income"
                amount = einnahmen
            else:
                entry_type = "expense"
                amount = betrag

            if amount <= 0 and not beschreibung:
                continue

            date_val = parse_date_str_to_datetime(str(datum)) if datum else None
            if not date_val:
                date_val = datetime.now()
            if not mwst and amount > 0:
                rate = float(mwst_satz.replace("%", "").replace(",", ".").strip() or "19")
                mwst = round(amount * rate / (100 + rate), 2)

            try:
                entry = CashEntry(user_id=user["sub"], description=beschreibung or vendor, vendor=vendor,
                    gross_amount=amount, vat_amount=mwst, vat_rate=mwst_satz, entry_type=entry_type,
                    category=category, payment_method=payment, reference=f"XLSX-Import Zeile {idx}",
                    notes="XLSX Import", date=date_val)
                db.add(entry)
                inv = Invoice(user_id=user["sub"], filename=f"xlsx-import-{idx}", vendor=vendor,
                    total_amount=amount, vat_amount=mwst, vat_rate=mwst_satz,
                    date=date_val.strftime("%Y-%m-%d") if date_val else "", raw_text=f"XLSX Import: {beschreibung}",
                    invoice_type=entry_type, invoice_number=inv_nr, payment_method=payment,
                    category=category, processed=True)
                db.add(inv)
                imported += 1
            except Exception as e:
                errors.append(f"Zeile {idx}: {str(e)[:80]}")
        db.commit()
        return {"success": True, "imported": imported, "errors": errors}
    except Exception:
        db.rollback()
        logger.exception("XLSX import failed")
        err(500, "XLSX Import failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: DATEV IMPORT
# ============================================================

@app.post("/bookkeeping/import-datev")
async def import_datev(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Import DATEV Buchungsstapel (.csv, semicolon-separated)."""
    import csv
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    db = SessionLocal()
    imported = 0
    errors = []
    try:
        for idx, row in enumerate(reader, 1):
            try:
                # DATEV format: Umsatz;Soll/Haben;Konto;Gegenkonto;BU;Belegdatum;Buchungstext;USt
                umsatz_raw = row.get("Umsatz") or row.get("umsatz") or "0"
                sh = row.get("Soll/Haben") or row.get("soll/haben") or "S"
                buchungstext = row.get("Buchungstext") or row.get("buchungstext") or ""
                belegdatum = row.get("Belegdatum") or row.get("belegdatum") or ""
                ust = row.get("USt") or row.get("ust") or "19"

                amount = float(umsatz_raw.replace(",", ".").replace(" ", "").strip() or "0")
                if amount <= 0:
                    continue

                entry_type = "expense" if sh.upper() == "S" else "income"

                # Parse DATEV date: DDMM or DDMMYYYY
                date_val = None
                bd = belegdatum.strip()
                if len(bd) == 4:
                    date_val = parse_date_str_to_datetime(f"20{datetime.now().year % 100}-{bd[2:4]}-{bd[0:2]}")
                elif len(bd) >= 6:
                    date_val = parse_date_str_to_datetime(f"{bd[4:]}-{bd[2:4]}-{bd[0:2]}")
                if not date_val:
                    date_val = datetime.now()

                vat_rate = f"{ust}%"
                rate_f = float(ust.replace(",", ".").strip() or "19")
                vat_amount = round(amount * rate_f / (100 + rate_f), 2)

                entry = CashEntry(user_id=user["sub"], description=buchungstext, vendor=buchungstext[:50] or "DATEV Import",
                    gross_amount=amount, vat_amount=vat_amount, vat_rate=vat_rate, entry_type=entry_type,
                    category="other", payment_method="", reference=f"DATEV-Import Zeile {idx}",
                    notes="DATEV Import", date=date_val)
                db.add(entry)
                inv = Invoice(user_id=user["sub"], filename=f"datev-import-{idx}", vendor=buchungstext[:50] or "DATEV Import",
                    total_amount=amount, vat_amount=vat_amount, vat_rate=vat_rate,
                    date=date_val.strftime("%Y-%m-%d") if date_val else "", raw_text=f"DATEV Import: {buchungstext}",
                    invoice_type=entry_type, invoice_number="", payment_method="",
                    category="other", processed=True)
                db.add(inv)
                imported += 1
            except Exception as e:
                errors.append(f"Zeile {idx}: {str(e)[:80]}")
        db.commit()
        return {"success": True, "imported": imported, "errors": errors}
    except Exception:
        db.rollback()
        logger.exception("DATEV import failed")
        err(500, "DATEV Import failed")
    finally:
        db.close()


# ============================================================
# BOOKKEEPING: PHOTO IMPORT (Handwritten Kassenbuch)
# ============================================================

@app.post("/bookkeeping/import-photo")
async def import_kassenbuch_photo(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Import handwritten Kassenbuch photo — OCR handwriting + table parsing"""
    from autotax.ocr import extract_handwriting_text
    import re as _re

    content = await file.read()
    text = await extract_handwriting_text(content, file.filename or "kassenbuch.jpg")
    if not text:
        err(400, "Konnte das Bild nicht lesen. Bitte bessere Qualität verwenden.")

    lines = text.strip().split("\n")
    db = SessionLocal()
    imported = 0
    try:
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            m = _re.search(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+(.+?)\s+(\d+[.,]\d{2})\s*$", line)
            if not m:
                m = _re.search(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s*[|/]?\s*(.+?)\s+[/|]?\s*(\d+[.,]\d{2})", line)
            if not m:
                continue
            datum_raw = m.group(1)
            beschreibung = m.group(2).strip()
            betrag = float(m.group(3).replace(",", "."))
            if betrag <= 0 or len(beschreibung) < 2:
                continue
            parts = datum_raw.replace("/", ".").split(".")
            date_str = ""
            if len(parts) == 3:
                d, mo, y = parts
                if len(y) == 2:
                    y = "20" + y
                date_str = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
            vat_amount = round(betrag * 19 / 119, 2)
            entry = CashEntry(
                user_id=user["sub"],
                description=beschreibung,
                vendor=beschreibung[:50],
                gross_amount=betrag,
                vat_amount=vat_amount,
                vat_rate="19%",
                entry_type="expense",
                category="other",
                payment_method="",
                reference="",
                notes="Kassenbuch Foto Import",
                date=parse_date_str_to_datetime(date_str),
            )
            db.add(entry)
            inv = Invoice(
                user_id=user["sub"],
                filename="kassenbuch-foto",
                vendor=beschreibung[:50],
                total_amount=betrag,
                vat_amount=vat_amount,
                vat_rate="19%",
                date=date_str,
                raw_text=f"Kassenbuch Foto: {beschreibung}",
                invoice_type="expense",
                invoice_number="",
                payment_method="",
                category="other",
                processed=True,
            )
            db.add(inv)
            imported += 1
        db.commit()
        return {"success": True, "imported": imported, "ocr_text": text[:500]}
    except Exception:
        db.rollback()
        logger.exception("Kassenbuch photo import failed")
        err(500, "Import failed")
    finally:
        db.close()


@app.post("/api/import-image")
async def import_image_table(file: UploadFile = File(...), save: bool = False, user: dict = Depends(get_current_user)):
    """Import Kassenbuch table image → OCR → structured rows + CSV.
    Columns: Nr, Datum, Beschreibung, Einnahmen, Ausgaben, Saldo
    Returns JSON rows + CSV string. If save=true, also saves to DB.
    """
    from autotax.ocr import extract_handwriting_text, extract_image_text, extract_pdf_text, extract_pdf_page_as_image
    import re as _re

    content = await file.read()
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    # PDF support
    if "pdf" in content_type or filename.endswith(".pdf"):
        text = extract_pdf_text(content)
        if not text or len(text.strip()) < 20:
            img_bytes = extract_pdf_page_as_image(content)
            if img_bytes:
                text = await extract_image_text(img_bytes, "scanned.png")
    else:
        # Image: try handwriting OCR first, fallback to printed
        text = await extract_handwriting_text(content, file.filename or "kassenbuch.jpg")

    if not text or len(text.strip()) < 20:
        text = await extract_image_text(content, file.filename or "kassenbuch.png")
    if not text or len(text.strip()) < 10:
        err(400, "Konnte das Bild nicht lesen. Bitte bessere Qualität verwenden.")

    lines = text.strip().split("\n")
    rows = []

    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        # Skip header/total rows
        line_lower = line.lower()
        if any(w in line_lower for w in ["total", "summe", "gesamt", "saldo", "nr.", "datum", "beschreibung", "einnahmen", "ausgaben", "übertrag"]):
            continue

        # Pattern: optional Nr + Date + Description + numbers
        # Try: Nr Date Description Amount1 Amount2
        m = _re.search(
            r"(?:\d{1,3}[.\s])?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+(.+?)\s+([\d.,]+)\s+([\d.,]+)\s*$",
            line
        )
        if m:
            datum_raw, beschreibung, num1, num2 = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
            val1 = float(num1.replace(",", ".")) if num1 else 0
            val2 = float(num2.replace(",", ".")) if num2 else 0
            # Heuristic: if first number is 0 or empty-like, it's Einnahmen=0, Ausgaben=val2
            einnahmen = val1 if val1 > 0 and val2 > 0 else 0
            ausgaben = val2 if val1 == 0 or (val1 > 0 and val2 > 0) else val1
            if einnahmen == 0 and ausgaben == 0:
                ausgaben = max(val1, val2)
        else:
            # Simpler: Date + Description + single amount
            m2 = _re.search(r"(?:\d{1,3}[.\s])?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+(.+?)\s+([\d.,]+)\s*$", line)
            if not m2:
                continue
            datum_raw, beschreibung, betrag_raw = m2.group(1), m2.group(2).strip(), m2.group(3)
            ausgaben = float(betrag_raw.replace(",", "."))
            einnahmen = 0

        if not beschreibung or len(beschreibung) < 2:
            continue

        # Parse date: DD.MM.YY or DD.MM.YYYY
        parts = datum_raw.replace("/", ".").split(".")
        if len(parts) == 3:
            d, mo, y = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if len(y) == 2:
                y = "20" + y
            date_str = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
        else:
            date_str = datum_raw

        rows.append({
            "date": date_str,
            "description": beschreibung,
            "income": round(einnahmen, 2),
            "expense": round(ausgaben, 2),
        })

    # Generate CSV
    csv_lines = ["Datum,Beschreibung,Einnahmen,Ausgaben"]
    for r in rows:
        desc = r["description"].replace('"', '""')
        csv_lines.append(f'{r["date"]},"{desc}",{r["income"]:.2f},{r["expense"]:.2f}')
    csv_text = "\n".join(csv_lines)

    # Optionally save to DB
    saved = 0
    if save and rows:
        db = SessionLocal()
        try:
            for r in rows:
                amount = r["income"] if r["income"] > 0 else r["expense"]
                entry_type = "income" if r["income"] > 0 else "expense"
                vat_amount = round(amount * 19 / 119, 2) if amount > 0 else 0
                date_val = parse_date_str_to_datetime(r["date"])
                if not date_val:
                    date_val = datetime.now()
                entry = CashEntry(
                    user_id=user["sub"],
                    description=r["description"],
                    vendor=r["description"][:50],
                    gross_amount=amount,
                    vat_amount=vat_amount,
                    vat_rate="19%",
                    entry_type=entry_type,
                    category="other",
                    payment_method="",
                    reference="",
                    notes="Bild Import",
                    date=date_val,
                )
                db.add(entry)
                inv = Invoice(
                    user_id=user["sub"],
                    filename="bild-import",
                    vendor=r["description"][:50],
                    total_amount=amount,
                    vat_amount=vat_amount,
                    vat_rate="19%",
                    date=r["date"],
                    raw_text=f"Bild Import: {r['description']}",
                    invoice_type=entry_type,
                    invoice_number="",
                    payment_method="",
                    category="other",
                    processed=True,
                )
                db.add(inv)
                saved += 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Image table import save failed")
        finally:
            db.close()

    return {
        "success": True,
        "rows": rows,
        "row_count": len(rows),
        "saved": saved,
        "csv": csv_text,
        "ocr_text": text[:500],
    }



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


@app.post("/feedback")
def submit_feedback(body: dict = Body(...), user: dict = Depends(get_current_user)):
    message = body.get("message", "")
    if not message.strip():
        err(400, "Feedback message is empty")
    logger.info("FEEDBACK from user %s: %s", user.get("email", user["sub"]), message[:500])
    return {"success": True, "message": "Feedback received"}


# ============================================================
# COMPANIES (max 2 per user)
# ============================================================

@app.get("/companies")
def list_companies(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        companies = db.query(UserCompany).filter(UserCompany.user_id == user["sub"]).all()
        return [{"id": c.id, "company_name": c.company_name} for c in companies]
    finally:
        db.close()


@app.post("/companies")
def add_company(body: dict = Body(...), user: dict = Depends(get_current_user)):
    company_name = body.get("company_name", "").strip()
    if not company_name:
        err(400, "Firmenname ist erforderlich")
    db = SessionLocal()
    try:
        existing = db.query(UserCompany).filter(UserCompany.user_id == user["sub"]).count()
        if existing >= 2:
            err(400, "Maximal 2 Firmen erlaubt. Upgrade auf Pro für mehr.")
        dup = db.query(UserCompany).filter(UserCompany.user_id == user["sub"], UserCompany.company_name == company_name).first()
        if dup:
            err(400, "Firma existiert bereits")
        c = UserCompany(user_id=user["sub"], company_name=company_name)
        db.add(c)
        db.commit()
        db.refresh(c)
        return {"success": True, "id": c.id, "company_name": c.company_name}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Add company failed")
        err(500, "Failed")
    finally:
        db.close()


@app.delete("/companies/{company_id}")
def delete_company(company_id: int, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        c = db.query(UserCompany).filter(UserCompany.id == company_id, UserCompany.user_id == user["sub"]).first()
        if not c:
            err(404, "Firma nicht gefunden")
        db.delete(c)
        db.commit()
        return {"success": True}
    finally:
        db.close()


# ============================================================

@app.post("/chat")
def chat_endpoint(body: dict = Body(...), user: dict = Depends(get_current_user)):
    message = body.get("message", "")
    db = SessionLocal()
    try:
        all_invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        # Filter invalid entries — same logic as dashboard
        invoices = [i for i in all_invoices if safe_float(i.total_amount) > 0 and safe_vendor(i.vendor) != "Unbekannt"]

        inv_count = len(invoices)
        inv_sum = sum(safe_float(i.total_amount) for i in invoices)

        inv_inc = [i for i in invoices if safe_invoice_type(i.invoice_type) == "income"]
        inv_exp = [i for i in invoices if safe_invoice_type(i.invoice_type) == "expense"]

        total_income = sum(safe_float(i.total_amount) for i in inv_inc)
        total_expenses = sum(safe_float(i.total_amount) for i in inv_exp)
        net_profit = total_income - total_expenses

        vat_paid = sum(safe_float(i.vat_amount) for i in inv_exp)
        vat_collected = sum(safe_float(i.vat_amount) for i in inv_inc)
        vat_balance = vat_collected - vat_paid

        cat_map = {}
        for i in invoices:
            c = safe_category(i.category)
            cat_map[c] = cat_map.get(c, 0) + safe_float(i.total_amount)
        cat_str = ", ".join(f"{k}: €{v:.2f}" for k, v in sorted(cat_map.items(), key=lambda x: -x[1])) if cat_map else "keine"

        vendors = {}
        for i in invoices:
            v = safe_vendor(i.vendor)
            vendors[v] = vendors.get(v, 0) + safe_float(i.total_amount)
        top_vendors = ", ".join(f"{k}: €{v:.2f}" for k, v in sorted(vendors.items(), key=lambda x: -x[1])[:5]) if vendors else "keine"

        msg = message.lower().strip()

        # Summe / Gesamt / wie viel
        if any(w in msg for w in ["wie viel", "wieviel", "summe", "total", "gesamt", "how much", "insgesamt", "ne kadar", "kaç", "özet", "zusammenfassung", "overview", "toplam", "was kostet", "kosten", "preis", "fiyat", "wieviel kostet"]):
            reply = f"📊 Übersicht:\n• Rechnungen: {inv_count} (€{inv_sum:.2f})\n• Einnahmen: €{total_income:.2f}\n• Ausgaben: €{total_expenses:.2f}\n• Gewinn: €{net_profit:.2f}"

        # Kategorie
        elif any(w in msg for w in ["kategorie", "categories", "aufteilung", "verteilung", "category", "grup", "sınıf", "kategori"]):
            reply = f"📂 Kategorien:\n{cat_str}"

        # MwSt / VAT / Steuer
        elif any(w in msg for w in ["mwst", "vat", "umsatzsteuer", "mehrwertsteuer", "vorsteuer", "kdv", "vergi", "tva"]):
            reply = f"🧾 MwSt-Übersicht:\n• Gezahlte Vorsteuer: €{vat_paid:.2f}\n• Vereinnahmte USt: €{vat_collected:.2f}\n• Saldo: €{vat_balance:.2f}\n{'→ Du bekommst €'+str(abs(round(vat_balance,2)))+' zurück' if vat_balance < 0 else '→ Du schuldest €'+str(round(vat_balance,2)) if vat_balance > 0 else '→ Ausgeglichen'}"

        # Steuer / Einkommensteuer
        elif any(w in msg for w in ["steuer", "tax", "einkommensteuer", "steuerlast", "vergi", "gelir vergisi"]):
            if net_profit > 277826:
                rate = 45
            elif net_profit > 61356:
                rate = 42
            elif net_profit > 17005:
                rate = 30
            elif net_profit > 10908:
                rate = 14
            else:
                rate = 0
            estimate = round(net_profit * rate / 100, 2) if net_profit > 0 else 0
            reply = f"💰 Steuer-Schätzung (Deutschland):\n• Gewinn: €{net_profit:.2f}\n• Steuersatz: {rate}%\n• Geschätzte Steuer: €{estimate:.2f}\n\nHinweis: Dies ist eine Schätzung. Für genaue Berechnung bitte Steuerberater konsultieren."

        # Einnahmen / Income
        elif any(w in msg for w in ["einnahme", "income", "umsatz", "revenue", "verdien", "gelir", "kazanç"]):
            reply = f"📈 Einnahmen: €{total_income:.2f} ({len(inv_inc)} Positionen)"

        # Ausgaben / Expenses
        elif any(w in msg for w in ["ausgabe", "expense", "kosten", "cost", "bezahl", "gider", "harcama", "masraf"]):
            reply = f"📉 Ausgaben: €{total_expenses:.2f} ({len(inv_exp)} Positionen)"

        # Gewinn / Profit
        elif any(w in msg for w in ["gewinn", "profit", "verlust", "loss", "netto", "ergebnis", "kâr", "kar", "zarar"]):
            emoji = "📈" if net_profit >= 0 else "📉"
            reply = f"{emoji} Netto-Ergebnis: €{net_profit:.2f}\n• Einnahmen: €{total_income:.2f}\n• Ausgaben: €{total_expenses:.2f}"

        # Vendor / Lieferant
        elif any(w in msg for w in ["lieferant", "vendor", "händler", "wer", "anbieter", "firma", "tedarikçi", "şirket", "mağaza"]):
            reply = f"🏢 Top Lieferanten:\n{top_vendors}"

        # Kassenbuch
        elif any(w in msg for w in ["kassenbuch", "bookkeeping", "cash", "kasse"]):
            reply = f"📒 Kassenbuch: Deine Rechnungen werden automatisch ins Kassenbuch synchronisiert.\n• Gesamt Rechnungen: {inv_count}\n• Einnahmen: {len(inv_inc)} | Ausgaben: {len(inv_exp)}\n\nTipp: Im Kassenbuch kannst du auch manuelle Einträge hinzufügen."

        # Rechnung / Invoice
        elif any(w in msg for w in ["rechnung", "invoice", "beleg", "faktur", "fatura", "bon", "quittung"]):
            reply = f"🧾 Rechnungen: {inv_count} gesamt (€{inv_sum:.2f})\n• Einnahmen: {len(inv_inc)}\n• Ausgaben: {len(inv_exp)}\n\nTipp: Über 'Upload' kannst du neue Belege hochladen."

        # Upload
        elif any(w in msg for w in ["upload", "hochladen", "scan", "ocr", "yükle", "bild", "datei"]):
            reply = "📤 Upload & OCR:\n• Unterstützte Formate: PDF, PNG, JPEG, TIFF, WEBP (max. 5 MB)\n• Einzel- oder Batch-Upload (bis zu 20 Dateien)\n• OCR erkennt: Lieferant, Betrag, MwSt, Datum, Kategorie\n• Handschrift-Modus für handgeschriebene Belege\n• Einnahme/Ausgabe vor Upload wählbar\n• Belege erscheinen in Rechnungen UND Kassenbuch\n• Über 350 Firmen werden automatisch erkannt\n• QR-Codes auf Rechnungen werden gelesen"

        # Export
        elif any(w in msg for w in ["export", "excel", "datev", "download", "herunterladen", "exportieren"]):
            reply = "💾 Export-Optionen:\n• CSV — Excel-kompatibel (Komma-getrennt)\n• DATEV — Standard für deutsche Steuerberater\n• Excel — .xlsx mit formatierten Spalten\n• JSON — für Entwickler & Backup\n• Kassenbuch CSV — eigener Export im Kassenbuch\n\nGehe zu 'Export', wähle das Jahr und klicke den Button.\nKassenbuch Export: Kassenbuch → 'CSV Export'\n\nTipp: Exportierte CSV kann direkt wieder importiert werden!"

        # CSV (specific)
        elif any(w in msg for w in ["csv"]):
            reply = "📄 CSV Funktionen:\n\n• CSV Export (Rechnungen): Export-Seite → 'CSV'\n• CSV Export (Kassenbuch): Kassenbuch → 'CSV Export'\n• CSV Import: Kassenbuch → 'CSV Import'\n\nCSV Format: Datum, Lieferant, Rechnungs-Nr., Typ, Betrag, MwSt, MwSt-Satz, Kategorie, Zahlungsart\nTrennzeichen: Komma oder Semikolon (automatisch erkannt)\nSpalten: Deutsch oder Englisch"

        # Import
        elif any(w in msg for w in ["import", "importieren", "csv import", "foto import", "defter", "içe aktar", "einlesen"]):
            reply = "📥 Import-Optionen:\n\n1. CSV Import:\n• Kassenbuch → 'CSV Import' Button\n• Komma oder Semikolon — automatisch erkannt\n• Spalten: Datum, Lieferant, Typ, Betrag, MwSt, Kategorie, Zahlungsart\n• Deutsch oder Englisch\n• Gleiche Format wie CSV Export!\n\n2. Foto Import:\n• Kassenbuch → 'Foto Import' Button\n• OCR erkennt handgeschriebene Tabellen\n• Format: Datum | Beschreibung | Betrag\n\n3. Beleg Upload:\n• Upload-Seite → PDF/Foto hochladen"

        # EÜR / Steuerformular
        elif any(w in msg for w in ["eür", "einnahmen-überschuss", "überschussrechnung", "steuerformular", "steuererklärung"]):
            reply = "🧾 EÜR (Einnahmen-Überschuss-Rechnung):\n• Gehe zu 'Steuer (EÜR)'\n• Wähle das Steuerjahr\n• Klicke 'Generieren'\n• Automatische Berechnung aus Rechnungen + Kassenbuch\n• Enthält: Betriebseinnahmen, Betriebsausgaben, Gewinn/Verlust, MwSt\n• Für Freiberufler und Kleinunternehmer\n\nHinweis: Für die offizielle Steuererklärung immer Steuerberater konsultieren."

        # Dashboard
        elif any(w in msg for w in ["dashboard", "übersicht", "überblick", "grafik", "chart", "diagramm"]):
            reply = f"📊 Dashboard:\n• Einnahmen: €{total_income:.2f} | Ausgaben: €{total_expenses:.2f}\n• Gewinn: €{net_profit:.2f}\n• MwSt-Saldo: €{vat_balance:.2f}\n• Rechnungen: {inv_count}\n\nFeatures:\n• Steuerschätzung nach deutschem Recht\n• Monatliche Auswertung als Diagramm\n• Kategorien-Verteilung\n• CSV Export Button"

        # Löschen / Delete
        elif any(w in msg for w in ["lösch", "delete", "entfern", "zurücksetz", "sil", "kaldır", "temizle"]):
            reply = "🗑️ Löschen:\n• Einzeln: Papierkorb-Symbol neben dem Eintrag\n• Mehrere: Häkchen setzen → 'X löschen' Button\n• Alles zurücksetzen: Dashboard → 'Zurücksetzen'\n  (ACHTUNG: Doppelbestätigung, unwiderruflich!)\n\nLöschen funktioniert in Rechnungen UND Kassenbuch."

        # Passwort / Login
        elif any(w in msg for w in ["passwort", "password", "şifre", "kennwort", "login", "anmeld", "registrier", "konto"]):
            reply = "🔐 Konto & Sicherheit:\n• Passwort: Min. 8 Zeichen, 1 Großbuchstabe, 1 Zahl\n• Login: E-Mail + Passwort\n• Token: Automatische Erneuerung (1h Access, 7 Tage Refresh)\n• Registrierung: Auf der Login-Seite 'Registrieren' klicken"

        # Sync / Synchronisieren
        elif any(w in msg for w in ["sync", "synchron", "senkron", "abgleich"]):
            reply = "🔄 Synchronisation:\n• Upload → Beleg erscheint automatisch in Rechnungen + Kassenbuch\n• Kassenbuch → 'Rechnungen sync' synchronisiert fehlende Einträge\n• Rechnungen → 'Kassenbuch sync' synchronisiert in beide Richtungen\n• Duplikate werden automatisch erkannt und übersprungen"

        # Reconcile / Abstimmen
        elif any(w in msg for w in ["reconcil", "abstimm", "abgleich", "häkchen", "checkbox"]):
            reply = "✅ Abstimmung (Reconcile):\n• Kassenbuch → Klicke ⬜ neben einem Eintrag → wird ✅\n• Markiert den Eintrag als 'abgestimmt'\n• Hilft beim Abgleich mit Kontoauszügen\n• Kann jederzeit rückgängig gemacht werden"

        # QR Code
        elif any(w in msg for w in ["qr", "qr code", "barcode"]):
            reply = "📱 QR-Code Erkennung:\n• QR-Codes auf Rechnungen werden automatisch gelesen\n• Unterstützt: EPC/SEPA (GiroCode), Swiss QR, ZUGFeRD\n• Extrahiert: Firma, IBAN, Betrag, Referenz\n• QR-Daten überschreiben OCR wenn verfügbar (genauer)"

        # Foto / Bild Qualität
        elif any(w in msg for w in ["foto", "qualität", "unscharf", "dunkel", "yamuk", "blurry"]):
            reply = "📸 Foto-Tipps für bessere Erkennung:\n• Gute Beleuchtung — kein Schatten auf dem Beleg\n• Gerade fotografieren — nicht schief\n• Gesamten Beleg im Bild\n• Original-Foto verwenden (nicht WhatsApp-komprimiert)\n• PDF ist besser als Foto (wenn verfügbar)\n• Handschrift-Modus für handgeschriebene Belege aktivieren"

        # Hilfe / Help
        elif any(w in msg for w in ["hilfe", "help", "was kannst", "anleitung", "wie funktioniert", "feature", "yardım", "yardim", "nasıl", "nasil", "nedir", "ne yapabilir", "fonksiyon", "how", "what can", "warum", "wieso", "neden", "weshalb"]):
            reply = "🤖 Ich kann dir helfen mit:\n• 'Wie viel?' — Gesamtbeträge\n• 'Kategorien' — Ausgaben nach Kategorie\n• 'MwSt' / 'KDV' — Vorsteuer & USt\n• 'Steuer' — Steuerschätzung\n• 'Gewinn' — Einnahmen vs. Ausgaben\n• 'Lieferanten' — Top Anbieter\n• 'Dashboard' — Finanzübersicht\n• 'Kassenbuch' — Kassenbuch-Status\n• 'Rechnungen' — Rechnungsübersicht\n• 'Upload' — Belege hochladen\n• 'Import' — CSV oder Foto importieren\n• 'Export' / 'CSV' — Exportieren\n• 'EÜR' — Steuererklärung\n• 'Sync' — Synchronisation\n• 'QR' — QR-Code Erkennung\n• 'Foto' — Tipps für bessere Fotos\n• 'Passwort' — Konto & Login\n• 'Löschen' — Einträge entfernen\n\nAlle Details: Gehe zur 'Hilfe' Seite!"

        # Hallo / Greeting
        elif any(w in msg for w in ["hallo", "hi", "hey", "merhaba", "hello", "guten", "selam", "nabız", "servus", "grüß"]):
            reply = f"👋 Hallo! Du hast {inv_count} Rechnungen. Wie kann ich dir helfen? Tippe 'Hilfe' für eine Übersicht."

        # Danke
        elif any(w in msg for w in ["danke", "thanks", "thx", "merci", "teşekkür", "sağol", "gracias"]):
            reply = "Gerne! Wenn du weitere Fragen hast, frag einfach. 😊"

        # Eintragen / Hinzufügen
        elif any(w in msg for w in ["eintragen", "hinzufügen", "eingeben", "neue", "neuer", "ekle", "gir", "yaz", "kaydet", "add", "create", "erfassen"]):
            reply = "✏️ Eintrag erstellen:\n• Kassenbuch → '+ Eintrag' Button → Formular ausfüllen\n• Upload → Beleg hochladen (OCR erkennt automatisch)\n• Rechnungen → 'Kassenbuch sync' für Synchronisierung\n\nBeide Wege erstellen automatisch Einträge in Rechnungen UND Kassenbuch."

        # Suche / Finden
        elif any(w in msg for w in ["such", "find", "wo ist", "wo sind", "finden", "ara", "bul", "nerede", "search", "where"]):
            reply = "🔍 Suche:\n• Rechnungen → Suchfeld oben (sucht in Vendor, OCR-Text, Kategorie)\n• Mehrere Wörter möglich: z.B. 'Lidl Dezember'\n• Filter: Vendor, Kategorie, Datum (Von/Bis), Status\n• AI Chat: Frag mich z.B. 'Lieferanten' oder 'Kategorien'"

        # Bearbeiten / Ändern
        elif any(w in msg for w in ["bearbeit", "änder", "korrigier", "edit", "update", "düzenle", "değiştir"]):
            reply = "✏️ Bearbeiten:\n• Rechnungen → 'Bearbeiten' neben dem Eintrag\n• Kassenbuch → 'Bearbeiten' neben dem Eintrag\n• Du kannst ändern: Vendor, Betrag, Kategorie, Datum, MwSt-Satz"

        # Wie viele / Anzahl
        elif any(w in msg for w in ["wie viele", "anzahl", "count", "kaç tane", "adet"]):
            reply = f"📊 Anzahl:\n• Rechnungen: {inv_count}\n• Einnahmen: {len(inv_inc)}\n• Ausgaben: {len(inv_exp)}"

        # Datum / Date
        elif any(w in msg for w in ["datum", "date", "tarih", "wann", "zeitraum", "monat", "jahr"]):
            reply = "📅 Datum-Filter:\n• Rechnungen → Von/Bis Felder nutzen\n• Unterstützte Formate: DD.MM.YYYY, YYYY-MM-DD\n• Monatsansicht: Dashboard zeigt monatliche Auswertung\n• Export: Nach Jahr filterbar"

        # Vendor search — if no keyword matched, try searching vendor names
        else:
            vendor_results = [i for i in invoices if msg in (i.vendor or "").lower()]
            if not vendor_results:
                vendor_results = db.query(Invoice).filter(Invoice.user_id == user["sub"], Invoice.vendor.ilike(f"%{msg}%")).all()
            if vendor_results:
                vr_total = sum(safe_float(i.total_amount) for i in vendor_results)
                vr_vat = sum(safe_float(i.vat_amount) for i in vendor_results)
                latest = safe_date_str(vendor_results[0].date) if vendor_results[0].date else "unbekannt"
                reply = f"🔍 Für '{msg.title()}' habe ich {len(vendor_results)} Rechnung(en) gefunden:\n• Gesamtbetrag: €{vr_total:.2f}\n• MwSt: €{vr_vat:.2f}\n• Letzte Rechnung: {latest}"
            else:
                reply = f"Das habe ich nicht ganz verstanden. Versuche z.B.:\n• 'Wie viele Rechnungen?'\n• 'MwSt Übersicht'\n• 'Gewinn'\n• Einen Lieferanten-Namen (z.B. 'Lidl')\n• 'Hilfe' für alle Themen\n\nAktuell: {inv_count} Rechnungen, €{net_profit:.2f} Gewinn"

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
        buf.write("# HINWEIS: Automatisch erstellt von AutoTax-HUB. Alle Daten vor Verwendung pruefen. Keine Steuerberatung.\n")
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
        buf.write("# HINWEIS: AutoTax-HUB - Alle Daten pruefen. Keine Steuerberatung.\n")
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
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, numbers
    db = SessionLocal()
    try:
        invoices = db.query(Invoice).filter(Invoice.user_id == user["sub"]).all()
        wb = Workbook()
        ws = wb.active
        ws.title = "AutoTax Export"
        # Disclaimer row
        disc = ws.cell(row=1, column=1, value="HINWEIS: Automatisch erstellt von AutoTax-HUB. Alle Daten vor Verwendung prüfen. Keine Steuerberatung.")
        disc.font = Font(italic=True, color="F59E0B")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=9)
        headers = ["Datum", "Lieferant", "Rechnungs-Nr.", "Typ", "Betrag", "MwSt", "MwSt-Satz", "Kategorie", "Zahlungsart"]
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        row = 3
        for i in invoices:
            d = safe_date_str(i.date)
            if year and not d.startswith(str(year)):
                continue
            ws.cell(row=row, column=1, value=d)
            ws.cell(row=row, column=2, value=safe_vendor(i.vendor))
            ws.cell(row=row, column=3, value=safe_str(i.invoice_number))
            ws.cell(row=row, column=4, value=safe_invoice_type(i.invoice_type))
            c5 = ws.cell(row=row, column=5, value=safe_float(i.total_amount))
            c5.number_format = '#,##0.00'
            c6 = ws.cell(row=row, column=6, value=safe_float(i.vat_amount))
            c6.number_format = '#,##0.00'
            ws.cell(row=row, column=7, value=safe_vat_rate(i.vat_rate))
            ws.cell(row=row, column=8, value=safe_category(i.category))
            ws.cell(row=row, column=9, value=safe_str(i.payment_method))
            row += 1
        for col in range(1, 10):
            ws.column_dimensions[chr(64 + col)].width = 18
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=autotax_{year or 'all'}.xlsx"})
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



# Build trigger: 2026-03-24
# force deploy 2
