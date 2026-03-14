"""
app/services/tax_form_service.py — AutoTax-HUB v5.2
Auto-fill EÜR and UStVA from invoice data.
Like WISO but API-powered.
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.invoice import Invoice
from app.models.tax_form import EuerForm, UstvaForm, TaxProfile
from app.models.user import User

logger = logging.getLogger("autotaxhub.tax_form")

# Category → EÜR field mapping
CATEGORY_TO_AUSGABE = {
    "food": "ausgaben_waren",
    "restaurant": "ausgaben_bewirtung",
    "electronics": "ausgaben_buero",
    "clothing": "ausgaben_sonstige",
    "shoes": "ausgaben_sonstige",
    "fuel": "ausgaben_kfz_kosten",
    "drugstore": "ausgaben_sonstige",
    "transport": "ausgaben_reisekosten",
    "office": "ausgaben_buero",
    "telecom": "ausgaben_telefon_internet",
    "other": "ausgaben_sonstige",
}


def auto_fill_euer(user: User, steuerjahr: int, db: Session) -> EuerForm:
    """
    Auto-generate EÜR from user's invoice data.
    Maps invoice categories to EÜR expense fields.
    """
    invoices = db.query(Invoice).filter(
        Invoice.user_id == user.id,
        Invoice.date.like(f"{steuerjahr}%"),
    ).all()

    form = EuerForm(user_id=user.id, steuerjahr=steuerjahr, auto_filled=True)

    for inv in invoices:
        amount = inv.total_amount or 0
        vat = inv.vat_amount or 0
        net = amount - vat

        if inv.invoice_type == "income":
            # Income → Betriebseinnahmen
            if vat > 0:
                form.einnahmen_steuerpflichtig += net
                form.einnahmen_vereinnahmte_ust += vat
            else:
                form.einnahmen_steuerfrei += net
        else:
            # Expense → Betriebsausgaben (mapped by category)
            field = CATEGORY_TO_AUSGABE.get(inv.category or "other", "ausgaben_sonstige")
            current = getattr(form, field, 0.0)
            setattr(form, field, current + net)
            if vat > 0:
                form.ausgaben_gezahlte_vorsteuer += vat

    _calculate_euer(form)
    return form


def _calculate_euer(form: EuerForm) -> None:
    """Calculate EÜR totals."""
    form.summe_einnahmen = round(
        form.einnahmen_kleinunternehmer +
        form.einnahmen_steuerpflichtig +
        form.einnahmen_steuerfrei +
        form.einnahmen_anlageverkaeufe +
        form.einnahmen_private_kfz_nutzung +
        form.einnahmen_sonstige_entnahmen +
        form.einnahmen_vereinnahmte_ust,
        2,
    )
    form.summe_ausgaben = round(
        form.ausgaben_waren +
        form.ausgaben_fremdleistungen +
        form.ausgaben_personal +
        form.ausgaben_sozialversicherung +
        form.ausgaben_afa +
        form.ausgaben_sofortabschreibung +
        form.ausgaben_raumkosten +
        form.ausgaben_versicherungen +
        form.ausgaben_kfz_kosten +
        form.ausgaben_reisekosten +
        form.ausgaben_bewirtung +
        form.ausgaben_telefon_internet +
        form.ausgaben_buero +
        form.ausgaben_fortbildung +
        form.ausgaben_beratung +
        form.ausgaben_werbung +
        form.ausgaben_gezahlte_vorsteuer +
        form.ausgaben_ust_zahlung +
        form.ausgaben_sonstige,
        2,
    )
    form.gewinn_verlust = round(form.summe_einnahmen - form.summe_ausgaben, 2)


def auto_fill_ustva(user: User, jahr: int, zeitraum: str, db: Session) -> UstvaForm:
    """
    Auto-generate UStVA from user's invoice data for a month or quarter.
    """
    if zeitraum.startswith("Q"):
        quarter = int(zeitraum[1])
        months = list(range((quarter - 1) * 3 + 1, quarter * 3 + 1))
        date_filters = [Invoice.date.like(f"{jahr}-{m:02d}%") for m in months]
    else:
        month = int(zeitraum)
        date_filters = [Invoice.date.like(f"{jahr}-{month:02d}%")]

    from sqlalchemy import or_
    invoices = db.query(Invoice).filter(
        Invoice.user_id == user.id,
        or_(*date_filters),
    ).all()

    form = UstvaForm(user_id=user.id, jahr=jahr, zeitraum=zeitraum, auto_filled=True)

    for inv in invoices:
        amount = inv.total_amount or 0
        vat = inv.vat_amount or 0
        net = amount - vat
        vat_rate_str = inv.vat_rate or ""

        if inv.invoice_type == "income":
            # Verkäufe → USt
            if "19" in vat_rate_str:
                form.umsaetze_19 += net
                form.steuer_19 += vat
            elif "7" in vat_rate_str:
                form.umsaetze_7 += net
                form.steuer_7 += vat
            else:
                # Default to 19% if rate unclear
                form.umsaetze_19 += net
                form.steuer_19 += vat
        else:
            # Einkäufe → Vorsteuer
            form.vorsteuer += vat

    _calculate_ustva(form)
    return form


def _calculate_ustva(form: UstvaForm) -> None:
    """Calculate UStVA totals."""
    form.ust_summe = round(form.steuer_19 + form.steuer_7 + form.steuer_ig, 2)
    form.vst_summe = round(form.vorsteuer + form.vorsteuer_ig, 2)
    form.verbleibend = round(form.ust_summe - form.vst_summe, 2)


def get_euer_summary(form: EuerForm) -> dict:
    """Generate a human-readable EÜR summary."""
    return {
        "steuerjahr": form.steuerjahr,
        "status": form.status,
        "einnahmen": {
            "Kleinunternehmer (Z.12)": form.einnahmen_kleinunternehmer,
            "Steuerpflichtige Einnahmen netto (Z.14)": form.einnahmen_steuerpflichtig,
            "Steuerfreie Einnahmen (Z.16)": form.einnahmen_steuerfrei,
            "Anlageverkäufe (Z.18)": form.einnahmen_anlageverkaeufe,
            "Private Kfz-Nutzung (Z.19)": form.einnahmen_private_kfz_nutzung,
            "Sonstige Entnahmen (Z.20)": form.einnahmen_sonstige_entnahmen,
            "Vereinnahmte USt (Z.22)": form.einnahmen_vereinnahmte_ust,
            "SUMME EINNAHMEN": form.summe_einnahmen,
        },
        "ausgaben": {
            "Waren/Rohstoffe (Z.26)": form.ausgaben_waren,
            "Fremdleistungen (Z.28)": form.ausgaben_fremdleistungen,
            "Gehälter/Löhne (Z.30)": form.ausgaben_personal,
            "Sozialversicherung (Z.31)": form.ausgaben_sozialversicherung,
            "AfA/Abschreibungen (Z.33)": form.ausgaben_afa,
            "Sofortabschreibung GWG (Z.34)": form.ausgaben_sofortabschreibung,
            "Raumkosten/Miete (Z.42)": form.ausgaben_raumkosten,
            "Versicherungen (Z.44)": form.ausgaben_versicherungen,
            "Telefon/Internet (Z.46)": form.ausgaben_telefon_internet,
            "Bürobedarf (Z.48)": form.ausgaben_buero,
            "Fortbildung (Z.49)": form.ausgaben_fortbildung,
            "Kfz-Kosten (Z.50)": form.ausgaben_kfz_kosten,
            "Bewirtung 70% (Z.53)": form.ausgaben_bewirtung,
            "Reisekosten (Z.55)": form.ausgaben_reisekosten,
            "Werbekosten (Z.56)": form.ausgaben_werbung,
            "Sonstige (Z.58)": form.ausgaben_sonstige,
            "Steuerberatung (Z.60)": form.ausgaben_beratung,
            "Gezahlte Vorsteuer (Z.63)": form.ausgaben_gezahlte_vorsteuer,
            "An FA gezahlte USt (Z.64)": form.ausgaben_ust_zahlung,
            "SUMME AUSGABEN": form.summe_ausgaben,
        },
        "ergebnis": {
            "Gewinn/Verlust": form.gewinn_verlust,
        },
    }
