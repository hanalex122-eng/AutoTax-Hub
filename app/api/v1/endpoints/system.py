"""
app/api/v1/endpoints/system.py — AutoTax-HUB v5.2
System info endpoints: currencies, languages, tax rates, VAT info.
Public endpoints (no auth required).
"""
from fastapi import APIRouter, Query

from app.services.currency_service import (
    convert_amount,
    get_all_currencies,
    get_currency_info,
)
from app.services.i18n import get_supported_languages
from app.services.tax_engine import (
    estimate_income_tax,
    get_all_vat_rates,
    get_supported_tax_countries,
    get_vat_info,
)

router = APIRouter(prefix="/system", tags=["System"])


# ── Currencies ────────────────────────────────────────────
@router.get("/currencies")
def list_currencies():
    """List all supported currencies with symbols and exchange rates."""
    return {"currencies": get_all_currencies()}


@router.get("/currencies/{code}")
def currency_detail(code: str):
    """Get details for a specific currency."""
    info = get_currency_info(code)
    if not info:
        return {"error": f"Currency {code.upper()} not found"}
    return info


@router.get("/currencies/convert/{from_code}/{to_code}")
def convert(
    from_code: str,
    to_code: str,
    amount: float = Query(..., gt=0, description="Amount to convert"),
):
    """Convert amount between currencies."""
    return convert_amount(amount, from_code, to_code)


# ── Languages ─────────────────────────────────────────────
@router.get("/languages")
def list_languages():
    """List all supported languages."""
    return {"languages": get_supported_languages()}


# ── VAT Rates ─────────────────────────────────────────────
@router.get("/vat-rates")
def list_vat_rates():
    """List VAT rates for all supported countries."""
    return {"vat_rates": get_all_vat_rates()}


@router.get("/vat-rates/{country_code}")
def vat_rate_detail(country_code: str):
    """Get VAT info for a specific country."""
    return get_vat_info(country_code)


# ── Tax Estimation ────────────────────────────────────────
@router.get("/tax-countries")
def list_tax_countries():
    """List all countries with income tax estimation support."""
    return {"countries": get_supported_tax_countries()}


@router.get("/tax-estimate")
def tax_estimate(
    net_profit: float = Query(..., description="Net profit for tax estimation"),
    country: str = Query("DE", description="Country code (DE, AT, TR, FR, ES, IT, GB, CH, US, NL, PL)"),
):
    """
    Estimate income tax for given net profit and country.
    Note: These are simplified estimates. Consult a tax advisor for exact calculations.
    """
    result = estimate_income_tax(net_profit, country)
    result["disclaimer"] = "This is a simplified estimate. Please consult a Steuerberater/tax advisor."
    return result
