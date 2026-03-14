"""
app/models/tax_form.py — AutoTax-HUB v5.2
Steuerformular data models.
Supports:
- Anlage EÜR (Einnahmen-Überschuss-Rechnung)
- UStVA (Umsatzsteuer-Voranmeldung)
- General tax profile (Stammdaten)
"""
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from app.db.database import Base


class TaxProfile(Base):
    """Stammdaten — personal & business info for tax forms."""
    __tablename__ = "tax_profiles"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Personal
    vorname         = Column(String(100), nullable=True)
    nachname        = Column(String(100), nullable=True)
    geburtsdatum    = Column(String(20), nullable=True)
    strasse         = Column(String(255), nullable=True)
    hausnummer      = Column(String(20), nullable=True)
    plz             = Column(String(10), nullable=True)
    ort             = Column(String(100), nullable=True)
    bundesland      = Column(String(50), nullable=True)
    steuernummer    = Column(String(50), nullable=True)
    finanzamt       = Column(String(100), nullable=True)
    ust_id          = Column(String(30), nullable=True)   # USt-ID (VAT ID)

    # Business
    betriebsart     = Column(String(100), nullable=True)  # Gewerbebetrieb / Freiberuf
    rechtsform      = Column(String(50), nullable=True)   # Einzelunternehmer / GbR etc.
    branche         = Column(String(100), nullable=True)
    ist_kleinunternehmer = Column(Boolean, default=False)

    # Tax settings
    tax_country     = Column(String(5), default="DE")
    base_currency   = Column(String(5), default="EUR")
    steuerjahr      = Column(Integer, default=2025)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="tax_profile")


class EuerForm(Base):
    """Anlage EÜR — Einnahmen-Überschuss-Rechnung (annual)."""
    __tablename__ = "euer_forms"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    steuerjahr      = Column(Integer, nullable=False)
    status          = Column(String(30), default="draft")  # draft / submitted / accepted

    # ── Betriebseinnahmen (Zeile 11-22) ───────────────────
    einnahmen_kleinunternehmer     = Column(Float, default=0.0)   # Z.12: Kleinunternehmer
    einnahmen_steuerpflichtig      = Column(Float, default=0.0)   # Z.14: Umsatzsteuerpflichtig (netto)
    einnahmen_steuerfrei           = Column(Float, default=0.0)   # Z.16: Steuerfreie Einnahmen
    einnahmen_anlageverkaeufe      = Column(Float, default=0.0)   # Z.18: Verkauf von Anlagevermögen
    einnahmen_private_kfz_nutzung  = Column(Float, default=0.0)   # Z.19: Private Kfz-Nutzung
    einnahmen_sonstige_entnahmen   = Column(Float, default=0.0)   # Z.20: Sonstige Entnahmen
    einnahmen_vereinnahmte_ust     = Column(Float, default=0.0)   # Z.22: Vereinnahmte Umsatzsteuer

    # ── Betriebsausgaben (Zeile 23-65) ────────────────────
    ausgaben_waren                 = Column(Float, default=0.0)   # Z.26: Waren/Rohstoffe
    ausgaben_fremdleistungen       = Column(Float, default=0.0)   # Z.28: Bezogene Fremdleistungen
    ausgaben_personal              = Column(Float, default=0.0)   # Z.30: Gehälter/Löhne
    ausgaben_sozialversicherung    = Column(Float, default=0.0)   # Z.31: AG-Anteile Sozialvers.
    ausgaben_afa                   = Column(Float, default=0.0)   # Z.33: AfA (Abschreibungen)
    ausgaben_sofortabschreibung    = Column(Float, default=0.0)   # Z.34: Sofortabschreibung GWG
    ausgaben_raumkosten            = Column(Float, default=0.0)   # Z.42: Raumkosten/Miete
    ausgaben_versicherungen        = Column(Float, default=0.0)   # Z.44: Betriebliche Versicherungen
    ausgaben_kfz_kosten            = Column(Float, default=0.0)   # Z.50: Kfz-Kosten
    ausgaben_reisekosten           = Column(Float, default=0.0)   # Z.55: Reisekosten
    ausgaben_bewirtung             = Column(Float, default=0.0)   # Z.53: Bewirtungskosten (70%)
    ausgaben_telefon_internet      = Column(Float, default=0.0)   # Z.46: Telefon/Internet
    ausgaben_buero                 = Column(Float, default=0.0)   # Z.48: Bürobedarf
    ausgaben_fortbildung           = Column(Float, default=0.0)   # Z.49: Fortbildungskosten
    ausgaben_beratung              = Column(Float, default=0.0)   # Z.60: Steuerberatung/Buchführung
    ausgaben_werbung               = Column(Float, default=0.0)   # Z.56: Werbekosten
    ausgaben_gezahlte_vorsteuer    = Column(Float, default=0.0)   # Z.63: Gezahlte Vorsteuer
    ausgaben_ust_zahlung           = Column(Float, default=0.0)   # Z.64: An FA gezahlte USt
    ausgaben_sonstige              = Column(Float, default=0.0)   # Z.58: Sonstige Betriebsausgaben

    # ── Calculated ────────────────────────────────────────
    summe_einnahmen                = Column(Float, default=0.0)
    summe_ausgaben                 = Column(Float, default=0.0)
    gewinn_verlust                 = Column(Float, default=0.0)

    # ── Notes ─────────────────────────────────────────────
    notizen         = Column(Text, nullable=True)
    auto_filled     = Column(Boolean, default=False)   # True if auto-generated from invoices

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="euer_forms")


class UstvaForm(Base):
    """UStVA — Umsatzsteuer-Voranmeldung (monthly/quarterly)."""
    __tablename__ = "ustva_forms"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jahr            = Column(Integer, nullable=False)
    zeitraum        = Column(String(10), nullable=False)   # "01"-"12" or "Q1"-"Q4"
    status          = Column(String(30), default="draft")

    # ── Steuerpflichtige Umsätze ──────────────────────────
    umsaetze_19     = Column(Float, default=0.0)   # Kz.81: Umsätze 19%
    steuer_19       = Column(Float, default=0.0)    # Steuer auf 19%
    umsaetze_7      = Column(Float, default=0.0)    # Kz.86: Umsätze 7%
    steuer_7        = Column(Float, default=0.0)     # Steuer auf 7%

    # ── Innergemeinschaftliche ────────────────────────────
    ig_lieferungen  = Column(Float, default=0.0)    # Kz.41: IG-Lieferungen (steuerfrei)
    ig_erwerbe      = Column(Float, default=0.0)    # Kz.89: IG-Erwerbe 19%
    steuer_ig       = Column(Float, default=0.0)     # Steuer auf IG-Erwerbe

    # ── Vorsteuer ─────────────────────────────────────────
    vorsteuer       = Column(Float, default=0.0)    # Kz.66: Vorsteuerbeträge
    vorsteuer_ig    = Column(Float, default=0.0)    # Kz.61: Vorsteuer IG-Erwerbe

    # ── Berechnung ────────────────────────────────────────
    ust_summe       = Column(Float, default=0.0)    # Summe USt
    vst_summe       = Column(Float, default=0.0)    # Summe VSt
    verbleibend     = Column(Float, default=0.0)    # USt - VSt (pos = Zahlung, neg = Erstattung)

    notizen         = Column(Text, nullable=True)
    auto_filled     = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="ustva_forms")
