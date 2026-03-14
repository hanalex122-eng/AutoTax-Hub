"""
app/api/v1/endpoints/tax_forms.py — AutoTax-HUB v5.2
WISO-style tax form endpoints.
- Tax Profile (Stammdaten)
- Anlage EÜR (auto-fill from invoices + manual edit)
- UStVA (auto-fill + manual edit)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_verified_user, get_db
from app.models.tax_form import TaxProfile, EuerForm, UstvaForm
from app.models.user import User
from app.schemas.tax_form import (
    TaxProfileRequest, TaxProfileOut,
    EuerFormRequest, EuerFormOut,
    UstvaFormRequest, UstvaFormOut,
)
from app.services.tax_form_service import (
    auto_fill_euer, auto_fill_ustva,
    _calculate_euer, _calculate_ustva,
    get_euer_summary,
)

router = APIRouter(prefix="/tax", tags=["Steuerformulare"])


# ═══════════════════════════════════════
#  TAX PROFILE (Stammdaten)
# ═══════════════════════════════════════
@router.get("/profile", response_model=TaxProfileOut)
def get_tax_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Get or create tax profile (Stammdaten)."""
    profile = db.query(TaxProfile).filter(TaxProfile.user_id == current_user.id).first()
    if not profile:
        profile = TaxProfile(
            user_id=current_user.id,
            vorname=current_user.full_name.split()[0] if current_user.full_name else "",
            nachname=" ".join(current_user.full_name.split()[1:]) if current_user.full_name else "",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/profile", response_model=TaxProfileOut)
def update_tax_profile(
    payload: TaxProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Update tax profile."""
    profile = db.query(TaxProfile).filter(TaxProfile.user_id == current_user.id).first()
    if not profile:
        profile = TaxProfile(user_id=current_user.id)
        db.add(profile)
        db.flush()

    update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in update_data.items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


# ═══════════════════════════════════════
#  ANLAGE EÜR
# ═══════════════════════════════════════
@router.post("/euer/auto-fill", response_model=EuerFormOut, status_code=201)
def auto_fill_euer_endpoint(
    steuerjahr: int = Query(2025, description="Steuerjahr"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """
    Auto-generate EÜR from your invoices.
    Maps each invoice category to the correct EÜR field.
    Like WISO's automatic data import.
    """
    existing = db.query(EuerForm).filter(
        EuerForm.user_id == current_user.id,
        EuerForm.steuerjahr == steuerjahr,
    ).first()
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"EÜR für {steuerjahr} existiert bereits (ID: {existing.id}). Verwenden Sie PUT zum Aktualisieren.")

    form = auto_fill_euer(current_user, steuerjahr, db)
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


@router.get("/euer", response_model=list[EuerFormOut])
def list_euer_forms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """List all EÜR forms for current user."""
    return db.query(EuerForm).filter(EuerForm.user_id == current_user.id).order_by(EuerForm.steuerjahr.desc()).all()


@router.get("/euer/{form_id}", response_model=EuerFormOut)
def get_euer_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    form = db.query(EuerForm).filter(EuerForm.id == form_id, EuerForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="EÜR nicht gefunden")
    return form


@router.get("/euer/{form_id}/summary")
def get_euer_form_summary(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Get formatted EÜR summary (like WISO's Steuerberechnung overview)."""
    form = db.query(EuerForm).filter(EuerForm.id == form_id, EuerForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="EÜR nicht gefunden")

    summary = get_euer_summary(form)

    # Add tax estimate
    from app.services.tax_engine import estimate_income_tax
    tax = estimate_income_tax(form.gewinn_verlust, "DE")
    summary["steuer_schaetzung"] = tax

    return summary


@router.put("/euer/{form_id}", response_model=EuerFormOut)
def update_euer_form(
    form_id: int,
    payload: EuerFormRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Update EÜR form fields. Totals are recalculated automatically."""
    form = db.query(EuerForm).filter(EuerForm.id == form_id, EuerForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="EÜR nicht gefunden")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(form, field):
            setattr(form, field, value)

    _calculate_euer(form)
    db.commit()
    db.refresh(form)
    return form


@router.delete("/euer/{form_id}", status_code=204)
def delete_euer_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    form = db.query(EuerForm).filter(EuerForm.id == form_id, EuerForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="EÜR nicht gefunden")
    db.delete(form)
    db.commit()


# ═══════════════════════════════════════
#  UStVA (Umsatzsteuer-Voranmeldung)
# ═══════════════════════════════════════
@router.post("/ustva/auto-fill", response_model=UstvaFormOut, status_code=201)
def auto_fill_ustva_endpoint(
    jahr: int = Query(2025),
    zeitraum: str = Query("01", description="Month (01-12) or Quarter (Q1-Q4)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """
    Auto-generate UStVA from invoices for a specific month or quarter.
    """
    existing = db.query(UstvaForm).filter(
        UstvaForm.user_id == current_user.id,
        UstvaForm.jahr == jahr,
        UstvaForm.zeitraum == zeitraum,
    ).first()
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"UStVA für {zeitraum}/{jahr} existiert bereits (ID: {existing.id})")

    form = auto_fill_ustva(current_user, jahr, zeitraum, db)
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


@router.get("/ustva", response_model=list[UstvaFormOut])
def list_ustva_forms(
    jahr: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    q = db.query(UstvaForm).filter(UstvaForm.user_id == current_user.id)
    if jahr:
        q = q.filter(UstvaForm.jahr == jahr)
    return q.order_by(UstvaForm.jahr.desc(), UstvaForm.zeitraum).all()


@router.get("/ustva/{form_id}", response_model=UstvaFormOut)
def get_ustva_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    form = db.query(UstvaForm).filter(UstvaForm.id == form_id, UstvaForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="UStVA nicht gefunden")
    return form


@router.put("/ustva/{form_id}", response_model=UstvaFormOut)
def update_ustva_form(
    form_id: int,
    payload: UstvaFormRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    form = db.query(UstvaForm).filter(UstvaForm.id == form_id, UstvaForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="UStVA nicht gefunden")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(form, field):
            setattr(form, field, value)

    _calculate_ustva(form)
    db.commit()
    db.refresh(form)
    return form


@router.delete("/ustva/{form_id}", status_code=204)
def delete_ustva_form(
    form_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    form = db.query(UstvaForm).filter(UstvaForm.id == form_id, UstvaForm.user_id == current_user.id).first()
    if not form:
        raise HTTPException(status_code=404, detail="UStVA nicht gefunden")
    db.delete(form)
    db.commit()


# ═══════════════════════════════════════
#  HELPER ENDPOINTS
# ═══════════════════════════════════════
@router.get("/bundeslaender")
def list_bundeslaender():
    """List German federal states for form selection."""
    return {"bundeslaender": [
        "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg",
        "Bremen", "Hamburg", "Hessen", "Mecklenburg-Vorpommern",
        "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz",
        "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
    ]}


@router.get("/rechtsformen")
def list_rechtsformen():
    """List business legal forms."""
    return {"rechtsformen": [
        {"code": "EU", "name": "Einzelunternehmer/in"},
        {"code": "FB", "name": "Freiberufler/in"},
        {"code": "GBR", "name": "GbR (Gesellschaft bürgerlichen Rechts)"},
        {"code": "OHG", "name": "OHG (Offene Handelsgesellschaft)"},
        {"code": "KG", "name": "KG (Kommanditgesellschaft)"},
        {"code": "GMBH", "name": "GmbH"},
        {"code": "UG", "name": "UG (haftungsbeschränkt)"},
        {"code": "AG", "name": "AG (Aktiengesellschaft)"},
    ]}
