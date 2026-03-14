"""
app/services/tax_engine.py — AutoTax-HUB v5.2
Flexible multi-country tax engine.

Supports:
- Income tax estimation (DE, AT, TR, FR, ES, IT, US, GB, CH, NL, PL)
- VAT rates per country (standard + reduced)
- Solidaritaetszuschlag (DE), Kirchensteuer hint
- Currency-aware calculations
"""

# ═══════════════════════════════════════════════════════
#  VAT RATES PER COUNTRY
# ═══════════════════════════════════════════════════════
VAT_RATES: dict[str, dict] = {
    "DE": {"standard": 19.0, "reduced": 7.0,  "name": "Mehrwertsteuer (MwSt)"},
    "AT": {"standard": 20.0, "reduced": 10.0, "name": "Umsatzsteuer (USt)"},
    "FR": {"standard": 20.0, "reduced": 5.5,  "name": "TVA"},
    "ES": {"standard": 21.0, "reduced": 10.0, "name": "IVA"},
    "IT": {"standard": 22.0, "reduced": 4.0,  "name": "IVA"},
    "NL": {"standard": 21.0, "reduced": 9.0,  "name": "BTW"},
    "BE": {"standard": 21.0, "reduced": 6.0,  "name": "TVA/BTW"},
    "PL": {"standard": 23.0, "reduced": 8.0,  "name": "VAT/PTU"},
    "CZ": {"standard": 21.0, "reduced": 12.0, "name": "DPH"},
    "SE": {"standard": 25.0, "reduced": 12.0, "name": "Moms"},
    "DK": {"standard": 25.0, "reduced": 0.0,  "name": "Moms"},
    "NO": {"standard": 25.0, "reduced": 15.0, "name": "MVA"},
    "FI": {"standard": 25.5, "reduced": 14.0, "name": "ALV"},
    "PT": {"standard": 23.0, "reduced": 6.0,  "name": "IVA"},
    "GR": {"standard": 24.0, "reduced": 6.0,  "name": "FPA"},
    "IE": {"standard": 23.0, "reduced": 13.5, "name": "VAT"},
    "HU": {"standard": 27.0, "reduced": 5.0,  "name": "AFA"},
    "RO": {"standard": 19.0, "reduced": 5.0,  "name": "TVA"},
    "BG": {"standard": 20.0, "reduced": 9.0,  "name": "DDS"},
    "HR": {"standard": 25.0, "reduced": 5.0,  "name": "PDV"},
    "GB": {"standard": 20.0, "reduced": 5.0,  "name": "VAT"},
    "CH": {"standard": 8.1,  "reduced": 2.6,  "name": "MWST/TVA"},
    "US": {"standard": 0.0,  "reduced": 0.0,  "name": "Sales Tax (varies by state)"},
    "TR": {"standard": 20.0, "reduced": 10.0, "name": "KDV"},
    "JP": {"standard": 10.0, "reduced": 8.0,  "name": "Consumption Tax"},
    "KR": {"standard": 10.0, "reduced": 0.0,  "name": "VAT"},
    "CN": {"standard": 13.0, "reduced": 9.0,  "name": "VAT"},
}


def get_vat_rate(country_code: str, rate_type: str = "standard") -> float:
    """Get VAT rate for a country. rate_type: 'standard' or 'reduced'"""
    country = VAT_RATES.get(country_code.upper(), VAT_RATES["DE"])
    return country.get(rate_type, country["standard"])


def get_vat_info(country_code: str) -> dict:
    """Get full VAT info for a country."""
    cc = country_code.upper()
    if cc not in VAT_RATES:
        return {"country": cc, "supported": False, "message": f"Country {cc} not in database, using DE defaults"}
    info = VAT_RATES[cc]
    return {
        "country": cc,
        "supported": True,
        "name": info["name"],
        "standard_rate": info["standard"],
        "reduced_rate": info["reduced"],
    }


def get_all_vat_rates() -> list[dict]:
    """List all supported countries and their VAT rates."""
    return [
        {
            "country": cc,
            "name": info["name"],
            "standard": info["standard"],
            "reduced": info["reduced"],
        }
        for cc, info in sorted(VAT_RATES.items())
    ]


# ═══════════════════════════════════════════════════════
#  INCOME TAX ESTIMATION
# ═══════════════════════════════════════════════════════

def estimate_income_tax(net_profit: float, country_code: str = "DE") -> dict:
    """
    Estimate income tax for given country.
    Returns dict with tax_amount, effective_rate, brackets_used, notes.
    """
    cc = country_code.upper()
    calculator = TAX_CALCULATORS.get(cc)
    if not calculator:
        return {
            "country": cc,
            "supported": False,
            "tax_amount": 0.0,
            "effective_rate": 0.0,
            "note": f"Tax calculation for {cc} not yet supported. Using 0.",
        }
    return calculator(net_profit)


# ── Germany (DE) ──────────────────────────────────────────
def _tax_de(net_profit: float) -> dict:
    """German Einkommensteuer 2025/2026 (simplified progressive)."""
    if net_profit <= 0:
        return {"country": "DE", "supported": True, "tax_amount": 0.0,
                "effective_rate": 0.0, "note": "Kein steuerpflichtiges Einkommen"}

    taxable = net_profit
    grundfreibetrag = 11784.0

    if taxable <= grundfreibetrag:
        return {"country": "DE", "supported": True, "tax_amount": 0.0,
                "effective_rate": 0.0, "note": f"Unter Grundfreibetrag ({grundfreibetrag}€)"}

    tax = 0.0
    if taxable <= 17005:
        tax = (taxable - grundfreibetrag) * 0.14
    elif taxable <= 66760:
        tax = (17005 - grundfreibetrag) * 0.14 + (min(taxable, 66760) - 17005) * 0.2397
    elif taxable <= 277825:
        tax = (17005 - grundfreibetrag) * 0.14 + (66760 - 17005) * 0.2397 + (min(taxable, 277825) - 66760) * 0.42
    else:
        tax = (17005 - grundfreibetrag) * 0.14 + (66760 - 17005) * 0.2397 + (277825 - 66760) * 0.42 + (taxable - 277825) * 0.45

    soli = 0.0
    if tax > 18130:
        soli = tax * 0.055
        tax += soli

    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {
        "country": "DE", "supported": True,
        "tax_amount": round(tax, 2),
        "effective_rate": round(eff, 2),
        "solidaritaetszuschlag": round(soli, 2),
        "grundfreibetrag": grundfreibetrag,
        "note": "Einkommensteuer + Solidaritätszuschlag (ohne Kirchensteuer)",
    }


# ── Austria (AT) ──────────────────────────────────────────
def _tax_at(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "AT", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Kein Einkommen"}

    brackets = [
        (12816, 0.0), (20818, 0.20), (34513, 0.30),
        (66612, 0.40), (99266, 0.48), (1000000, 0.50), (float("inf"), 0.55),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "AT", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "Einkommensteuer Österreich"}


# ── Turkey (TR) ───────────────────────────────────────────
def _tax_tr(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "TR", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Gelir yok"}

    # TRY brackets 2025
    brackets = [
        (110000, 0.15), (230000, 0.20), (580000, 0.27),
        (3000000, 0.35), (float("inf"), 0.40),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "TR", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "Gelir Vergisi (Türkiye)"}


# ── France (FR) ───────────────────────────────────────────
def _tax_fr(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "FR", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Pas de revenu"}

    brackets = [
        (11294, 0.0), (28797, 0.11), (82341, 0.30), (177106, 0.41), (float("inf"), 0.45),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "FR", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "Impôt sur le revenu (France)"}


# ── Spain (ES) ────────────────────────────────────────────
def _tax_es(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "ES", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Sin ingresos"}

    brackets = [
        (12450, 0.19), (20200, 0.24), (35200, 0.30), (60000, 0.37),
        (300000, 0.45), (float("inf"), 0.47),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "ES", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "IRPF (España)"}


# ── Italy (IT) ────────────────────────────────────────────
def _tax_it(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "IT", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Nessun reddito"}

    brackets = [
        (28000, 0.23), (50000, 0.35), (float("inf"), 0.43),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "IT", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "IRPEF (Italia)"}


# ── United Kingdom (GB) ──────────────────────────────────
def _tax_gb(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "GB", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "No income"}

    brackets = [
        (12570, 0.0), (50270, 0.20), (125140, 0.40), (float("inf"), 0.45),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "GB", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "Income Tax (UK)"}


# ── Switzerland (CH) ─────────────────────────────────────
def _tax_ch(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "CH", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Kein Einkommen"}

    # Federal tax only (cantonal varies heavily)
    brackets = [
        (14500, 0.0), (31600, 0.0077), (41400, 0.0088), (55200, 0.0264),
        (72500, 0.0297), (78100, 0.0528), (103600, 0.066), (134600, 0.088),
        (176000, 0.11), (755200, 0.13), (float("inf"), 0.115),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "CH", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2),
            "note": "Direkte Bundessteuer (ohne Kantons-/Gemeindesteuer)"}


# ── USA (US) ──────────────────────────────────────────────
def _tax_us(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "US", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "No income"}

    # 2025 single filer brackets
    brackets = [
        (11600, 0.10), (47150, 0.12), (100525, 0.22), (191950, 0.24),
        (243725, 0.32), (609350, 0.35), (float("inf"), 0.37),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "US", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2),
            "note": "Federal Income Tax (single filer, no state tax)"}


# ── Netherlands (NL) ─────────────────────────────────────
def _tax_nl(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "NL", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Geen inkomen"}

    brackets = [
        (75518, 0.3693), (float("inf"), 0.495),
    ]
    tax = _progressive_tax(net_profit, brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "NL", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "Inkomstenbelasting (Nederland)"}


# ── Poland (PL) ──────────────────────────────────────────
def _tax_pl(net_profit: float) -> dict:
    if net_profit <= 0:
        return {"country": "PL", "supported": True, "tax_amount": 0.0, "effective_rate": 0.0, "note": "Brak dochodu"}

    free_amount = 30000.0
    if net_profit <= free_amount:
        return {"country": "PL", "supported": True, "tax_amount": 0.0,
                "effective_rate": 0.0, "note": f"Poniżej kwoty wolnej ({free_amount} PLN)"}

    brackets = [
        (120000, 0.12), (float("inf"), 0.32),
    ]
    tax = _progressive_tax(max(net_profit - free_amount, 0), brackets)
    eff = (tax / net_profit * 100) if net_profit > 0 else 0
    return {"country": "PL", "supported": True, "tax_amount": round(tax, 2),
            "effective_rate": round(eff, 2), "note": "PIT (Polska)"}


# ── Helper ────────────────────────────────────────────────
def _progressive_tax(income: float, brackets: list[tuple[float, float]]) -> float:
    """Calculate progressive tax from bracket list [(limit, rate), ...]."""
    tax = 0.0
    prev = 0.0
    for limit, rate in brackets:
        if income <= prev:
            break
        taxable_in_bracket = min(income, limit) - prev
        if taxable_in_bracket > 0:
            tax += taxable_in_bracket * rate
        prev = limit
    return tax


# ── Calculator registry ──────────────────────────────────
TAX_CALCULATORS = {
    "DE": _tax_de,
    "AT": _tax_at,
    "TR": _tax_tr,
    "FR": _tax_fr,
    "ES": _tax_es,
    "IT": _tax_it,
    "GB": _tax_gb,
    "CH": _tax_ch,
    "US": _tax_us,
    "NL": _tax_nl,
    "PL": _tax_pl,
}


def get_supported_tax_countries() -> list[dict]:
    """List all countries with income tax support."""
    country_names = {
        "DE": "Deutschland", "AT": "Österreich", "TR": "Türkiye",
        "FR": "France", "ES": "España", "IT": "Italia",
        "GB": "United Kingdom", "CH": "Schweiz", "US": "United States",
        "NL": "Nederland", "PL": "Polska",
    }
    return [
        {"code": cc, "name": country_names.get(cc, cc), "has_income_tax": True,
         "has_vat": cc in VAT_RATES}
        for cc in sorted(TAX_CALCULATORS.keys())
    ]
