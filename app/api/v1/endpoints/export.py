"""
app/api/v1/endpoints/export.py — AutoTax-HUB v5
DATEV, Excel, CSV export
"""
import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_verified_user, get_db
from app.models.invoice import Invoice
from app.models.user import User

router = APIRouter(prefix="/export", tags=["Export"])


def _get_invoices(user: User, db: Session, year: int | None = None):
    q = db.query(Invoice).filter(Invoice.user_id == user.id)
    if year:
        q = q.filter(Invoice.date.like(f"{year}%"))
    return q.order_by(Invoice.date).all()


# ─── CSV Export ────────────────────────────────────────────────────────────────
@router.get("/csv")
def export_csv(
    year: int | None = Query(None, description="Filter by year e.g. 2026"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    invoices = _get_invoices(current_user, db, year)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID", "Datum", "Lieferant", "Rechnungsnummer",
        "Nettobetrag", "MwSt-Satz", "MwSt-Betrag", "Bruttobetrag",
        "Währung", "Kategorie", "Zahlungsart"
    ])
    for inv in invoices:
        net = round((inv.total_amount or 0) - (inv.vat_amount or 0), 2)
        writer.writerow([
            inv.id,
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
    Compatible with DATEV Unternehmen online import
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

    for inv in invoices:
        amount = inv.total_amount or 0
        date_str = ""
        if inv.date:
            try:
                # Convert YYYY-MM-DD or DD.MM.YYYY to DDMM
                if "-" in inv.date:
                    d = datetime.strptime(inv.date[:10], "%Y-%m-%d")
                else:
                    d = datetime.strptime(inv.date[:10], "%d.%m.%Y")
                date_str = d.strftime("%d%m")
            except Exception:
                date_str = ""

        vendor = (inv.vendor or "Unbekannt").replace('"', '')[:40]
        inv_nr = (inv.invoice_number or "").replace('"', '')[:36]

        # Konto based on category
        konto_map = {
            "food": "4650",
            "clothing": "4900",
            "electronics": "4980",
            "fuel": "4610",
            "restaurant": "4650",
            "drugstore": "4900",
            "shoes": "4900",
            "other": "4980",
        }
        konto = konto_map.get(inv.category or "other", "4980")

        output.write(
            f'"{amount:.2f}";S;EUR;;;;{konto};1600;;{date_str};'
            f'"{inv_nr}";;;"Eingangsrechnung {vendor}";;;;;;;;\r\n'
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Excel-compatible CSV with BOM for proper German encoding"""
    invoices = _get_invoices(current_user, db, year)

    output = io.StringIO()
    # BOM for Excel German encoding
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Nr.", "Datum", "Lieferant", "Rechnungsnummer",
        "Nettobetrag (€)", "MwSt-Satz", "MwSt-Betrag (€)", "Bruttobetrag (€)",
        "Währung", "Kategorie", "Zahlungsart", "Status"
    ])
    total_net = 0
    total_vat = 0
    total_gross = 0

    for inv in invoices:
        net = round((inv.total_amount or 0) - (inv.vat_amount or 0), 2)
        total_net += net
        total_vat += inv.vat_amount or 0
        total_gross += inv.total_amount or 0

        writer.writerow([
            inv.id,
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

    # Totals row
    writer.writerow([])
    writer.writerow([
        "GESAMT", "", "", "",
        f"{total_net:.2f}".replace(".", ","),
        "",
        f"{total_vat:.2f}".replace(".", ","),
        f"{total_gross:.2f}".replace(".", ","),
        "", "", "", ""
    ])

    output.seek(0)
    filename = f"AutoTaxHUB_Rechnungen_{year or 'alle'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
