"""
app/schemas/tax_form.py — AutoTax-HUB v5.2
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Tax Profile ───────────────────────────────────────────
class TaxProfileRequest(BaseModel):
    vorname: Optional[str] = None
    nachname: Optional[str] = None
    geburtsdatum: Optional[str] = None
    strasse: Optional[str] = None
    hausnummer: Optional[str] = None
    plz: Optional[str] = None
    ort: Optional[str] = None
    bundesland: Optional[str] = None
    steuernummer: Optional[str] = None
    finanzamt: Optional[str] = None
    ust_id: Optional[str] = None
    betriebsart: Optional[str] = None
    rechtsform: Optional[str] = None
    branche: Optional[str] = None
    ist_kleinunternehmer: Optional[bool] = None
    tax_country: Optional[str] = None
    base_currency: Optional[str] = None
    steuerjahr: Optional[int] = None


class TaxProfileOut(BaseModel):
    id: int
    vorname: Optional[str]
    nachname: Optional[str]
    geburtsdatum: Optional[str]
    strasse: Optional[str]
    hausnummer: Optional[str]
    plz: Optional[str]
    ort: Optional[str]
    bundesland: Optional[str]
    steuernummer: Optional[str]
    finanzamt: Optional[str]
    ust_id: Optional[str]
    betriebsart: Optional[str]
    rechtsform: Optional[str]
    branche: Optional[str]
    ist_kleinunternehmer: bool
    tax_country: str
    base_currency: str
    steuerjahr: int
    model_config = {"from_attributes": True}


# ── EÜR Form ─────────────────────────────────────────────
class EuerFormRequest(BaseModel):
    steuerjahr: int = 2025
    einnahmen_kleinunternehmer: float = 0.0
    einnahmen_steuerpflichtig: float = 0.0
    einnahmen_steuerfrei: float = 0.0
    einnahmen_anlageverkaeufe: float = 0.0
    einnahmen_private_kfz_nutzung: float = 0.0
    einnahmen_sonstige_entnahmen: float = 0.0
    einnahmen_vereinnahmte_ust: float = 0.0
    ausgaben_waren: float = 0.0
    ausgaben_fremdleistungen: float = 0.0
    ausgaben_personal: float = 0.0
    ausgaben_sozialversicherung: float = 0.0
    ausgaben_afa: float = 0.0
    ausgaben_sofortabschreibung: float = 0.0
    ausgaben_raumkosten: float = 0.0
    ausgaben_versicherungen: float = 0.0
    ausgaben_kfz_kosten: float = 0.0
    ausgaben_reisekosten: float = 0.0
    ausgaben_bewirtung: float = 0.0
    ausgaben_telefon_internet: float = 0.0
    ausgaben_buero: float = 0.0
    ausgaben_fortbildung: float = 0.0
    ausgaben_beratung: float = 0.0
    ausgaben_werbung: float = 0.0
    ausgaben_gezahlte_vorsteuer: float = 0.0
    ausgaben_ust_zahlung: float = 0.0
    ausgaben_sonstige: float = 0.0
    notizen: Optional[str] = None


class EuerFormOut(BaseModel):
    id: int
    steuerjahr: int
    status: str
    einnahmen_kleinunternehmer: float
    einnahmen_steuerpflichtig: float
    einnahmen_steuerfrei: float
    einnahmen_anlageverkaeufe: float
    einnahmen_private_kfz_nutzung: float
    einnahmen_sonstige_entnahmen: float
    einnahmen_vereinnahmte_ust: float
    ausgaben_waren: float
    ausgaben_fremdleistungen: float
    ausgaben_personal: float
    ausgaben_sozialversicherung: float
    ausgaben_afa: float
    ausgaben_sofortabschreibung: float
    ausgaben_raumkosten: float
    ausgaben_versicherungen: float
    ausgaben_kfz_kosten: float
    ausgaben_reisekosten: float
    ausgaben_bewirtung: float
    ausgaben_telefon_internet: float
    ausgaben_buero: float
    ausgaben_fortbildung: float
    ausgaben_beratung: float
    ausgaben_werbung: float
    ausgaben_gezahlte_vorsteuer: float
    ausgaben_ust_zahlung: float
    ausgaben_sonstige: float
    summe_einnahmen: float
    summe_ausgaben: float
    gewinn_verlust: float
    auto_filled: bool
    notizen: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── UStVA Form ────────────────────────────────────────────
class UstvaFormRequest(BaseModel):
    jahr: int = 2025
    zeitraum: str = "01"
    umsaetze_19: float = 0.0
    steuer_19: float = 0.0
    umsaetze_7: float = 0.0
    steuer_7: float = 0.0
    ig_lieferungen: float = 0.0
    ig_erwerbe: float = 0.0
    steuer_ig: float = 0.0
    vorsteuer: float = 0.0
    vorsteuer_ig: float = 0.0
    notizen: Optional[str] = None


class UstvaFormOut(BaseModel):
    id: int
    jahr: int
    zeitraum: str
    status: str
    umsaetze_19: float
    steuer_19: float
    umsaetze_7: float
    steuer_7: float
    ig_lieferungen: float
    ig_erwerbe: float
    steuer_ig: float
    vorsteuer: float
    vorsteuer_ig: float
    ust_summe: float
    vst_summe: float
    verbleibend: float
    auto_filled: bool
    notizen: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}
