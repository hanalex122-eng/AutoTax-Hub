"""
app/api/v1/endpoints/export.py — AutoTax-HUB v5.1
DATEV, Excel CSV, CSV, JSON export
"""
import csv
import io
import json
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_verified_user, get_db
from app.models.invoice import Invoice
from app.models.user import User

router = APIRouter(prefix="/export", tags=["Export"])


def _get_invoices(user: User, db: Session, year: int | None = None, invoice_type: str | None = None):
    q = db.query(Invoice).filter(Invoice.user_id == user.id)
    if year:
        q = q.filter(Invoice.date.like(f"{year}%"))
    if invoice_type:
        q = q.filter(Invoice.invoice_type == invoice_type)
    return q.order_by(Invoice.date).all()


# ─── CSV Export ────────────────────────────────────────────────────────────────
@router.get("/csv")
def export_csv(
    year: int | None = Query(None, description="Filter by year e.g. 2026"),
    invoice_type: str | None = Query(None, description="Filter: income or expense"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    invoices = _get_invoices(current_user, db, year, invoice_type)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID", "Typ", "Datum", "Lieferant", "Rechnungsnummer",
        "Nettobetrag", "MwSt-Satz", "MwSt-Betrag", "Bruttobetrag",
        "Währung", "Kategorie", "Zahlungsart"
    ])
    for inv in invoices:
        net = round((inv.total_amount or 0) - (inv.vat_amount or 0), 2)
        writer.writerow([
            inv.id,
            "Einnahme" if inv.invoice_type == "income" else "Ausgabe",
            inv.date or "",
            inv.vendor or "",
            inv.invoice_number or "",
            net,
            f"{inv.vat_rate or 0}%",
            inv.vat_amount or 0,
            inv.total_amount or 0,
            inv.currency or "EUR",
            inv.category or "",
            inv.payment_method or "",
        ])

    output.seek(0)
    filename = f"autotaxhub_export_{year or 'all'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── DATEV Export ──────────────────────────────────────────────────────────────
@router.get("/datev")
def export_datev(
    year: int | None = Query(None, description="Filter by year e.g. 2026"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """
    DATEV Buchungsstapel Format (simplified EXTF)
    Compatible with DATEV Unternehmen online import.
    Supports both income (Ausgangsrechnungen) and expense (Eingangsrechnungen).
    """
    invoices = _get_invoices(current_user, db, year)

    output = io.StringIO()

    # DATEV Header
    now = datetime.now().strftime("%Y%m%d%H%M%S%f")[:20]
    y = year or datetime.now().year
    output.write(
        f'"EXTF";700;21;"Buchungsstapel";7;{now};;;"AutoTax-HUB";;1;0;'
        f'{y}0101;{y}1231;"AutoTaxHUB Export";;EUR;;;;\r\n'
    )

    # Column headers
    output.write(
        "Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ Umsatz;"
        "Kurs;Basis-Umsatz;WKZ Basis-Umsatz;Konto;Gegenkonto (ohne BU-Schlüssel);"
        "BU-Schlüssel;Belegdatum;Belegfeld 1;Belegfeld 2;Skonto;Buchungstext;"
        "Postensperre;Diverse Adressnummer;Geschäftspartnerbank;Sachverhalt;"
        "Zinssperre;Beleglink;Beleginfo - Art 1;Beleginfo - Inhalt 1\r\n"
    )

    # DATEV Kontenrahmen SKR03 mapping
    expense_konto_map = {
        "food": "4650",
        "restaurant": "4654",
        "clothing": "4900",
        "electronics": "4980",
        "fuel": "4530",
        "drugstore": "4900",
        "shoes": "4900",
        "transport": "4570",
        "office": "4930",
        "telecom": "4920",
        "other": "4900",
    }

    for inv in invoices:
        amount = inv.total_amount or 0
        date_str = ""
        if inv.date:
            try:
                if "-" in inv.date:
                    d = datetime.strptime(inv.date[:10], "%Y-%m-%d")
                else:
                    d = datetime.strptime(inv.date[:10], "%d.%m.%Y")
                date_str = d.strftime("%d%m")
            except Exception:
                date_str = ""

        vendor = (inv.vendor or "Unbekannt").replace('"', '')[:40]
        inv_nr = (inv.invoice_number or "").replace('"', '')[:36]

        if inv.invoice_type == "income":
            # Ausgangsrechnung: Debit receivables, credit revenue
            konto = "1400"       # Forderungen aus Lieferungen und Leistungen
            gegenkonto = "8400"  # Erlöse 19% USt
            sh_kz = "S"
            buchungstext = f"Ausgangsrechnung {vendor}"
        else:
            # Eingangsrechnung: Debit expense, credit payables
            konto = expense_konto_map.get(inv.category or "other", "4900")
            gegenkonto = "1600"  # Verbindlichkeiten aus Lieferungen und Leistungen
            sh_kz = "S"
            buchungstext = f"Eingangsrechnung {vendor}"

        output.write(
            f'"{amount:.2f}";{sh_kz};EUR;;;;{konto};{gegenkonto};;{date_str};'
            f'"{inv_nr}";;;"{buchungstext}";;;;;;;;\r\n'
        )

    output.seek(0)
    filename = f"DATEV_AutoTaxHUB_{year or 'all'}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("latin-1", errors="replace")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── Excel Export (CSV for Excel) ──────────────────────────────────────────────
@router.get("/excel")
def export_excel(
    year: int | None = Query(None),
    invoice_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Excel-compatible CSV with BOM for proper German encoding"""
    invoices = _get_invoices(current_user, db, year, invoice_type)

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Nr.", "Typ", "Datum", "Lieferant", "Rechnungsnummer",
        "Nettobetrag (€)", "MwSt-Satz", "MwSt-Betrag (€)", "Bruttobetrag (€)",
        "Währung", "Kategorie", "Zahlungsart", "Status"
    ])
    total_net = 0
    total_vat = 0
    total_gross = 0
    total_income = 0
    total_expense = 0

    for inv in invoices:
        net = round((inv.total_amount or 0) - (inv.vat_amount or 0), 2)
        total_net += net
        total_vat += inv.vat_amount or 0
        total_gross += inv.total_amount or 0
        if inv.invoice_type == "income":
            total_income += inv.total_amount or 0
        else:
            total_expense += inv.total_amount or 0

        writer.writerow([
            inv.id,
            "Einnahme" if inv.invoice_type == "income" else "Ausgabe",
            inv.date or "",
            inv.vendor or "",
            inv.invoice_number or "",
            f"{net:.2f}".replace(".", ","),
            f"{inv.vat_rate or 0}%",
            f"{(inv.vat_amount or 0):.2f}".replace(".", ","),
            f"{(inv.total_amount or 0):.2f}".replace(".", ","),
            inv.currency or "EUR",
            inv.category or "",
            inv.payment_method or "",
            inv.status or "",
        ])

    # Summary rows
    writer.writerow([])
    writer.writerow([
        "GESAMT", "", "", "",
        f"{total_net:.2f}".replace(".", ","),
        "",
        f"{total_vat:.2f}".replace(".", ","),
        f"{total_gross:.2f}".replace(".", ","),
        "", "", "", ""
    ])
    writer.writerow([])
    writer.writerow(["Einnahmen gesamt:", f"{total_income:.2f}".replace(".", ",")])
    writer.writerow(["Ausgaben gesamt:", f"{total_expense:.2f}".replace(".", ",")])
    writer.writerow(["Gewinn/Verlust:", f"{(total_income - total_expense):.2f}".replace(".", ",")])

    output.seek(0)
    filename = f"AutoTaxHUB_Rechnungen_{year or 'alle'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── JSON Export ───────────────────────────────────────────────────────────────
@router.get("/json")
def export_json(
    year: int | None = Query(None),
    invoice_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """JSON export for API integrations and backups"""
    invoices = _get_invoices(current_user, db, year, invoice_type)

    data = {
        "export_date": datetime.now().isoformat(),
        "year_filter": year,
        "total_count": len(invoices),
        "invoices": [
            {
                "id": inv.id,
                "invoice_type": inv.invoice_type or "expense",
                "vendor": inv.vendor,
                "invoice_number": inv.invoice_number,
                "date": inv.date,
                "total_amount": inv.total_amount,
                "vat_rate": inv.vat_rate,
                "vat_amount": inv.vat_amount,
                "currency": inv.currency,
                "category": inv.category,
                "payment_method": inv.payment_method,
                "status": inv.status,
                "filename": inv.filename,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in invoices
        ]
    }

    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"AutoTaxHUB_export_{year or 'all'}.json"
    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
