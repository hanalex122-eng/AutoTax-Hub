"""
app/services/currency_service.py — AutoTax-HUB v5.2
Multi-currency support with offline fallback rates.

For production: integrate ECB/Fixer.io/ExchangeRate-API for live rates.
Offline rates are updated periodically as fallback.
"""
import logging
from datetime import datetime

logger = logging.getLogger("autotaxhub.currency")

# ── Currency metadata ─────────────────────────────────────
CURRENCY_INFO: dict[str, dict] = {
    "EUR": {"symbol": "€",  "name": "Euro",                    "decimal_places": 2},
    "USD": {"symbol": "$",  "name": "US Dollar",                "decimal_places": 2},
    "GBP": {"symbol": "£",  "name": "British Pound",            "decimal_places": 2},
    "TRY": {"symbol": "₺",  "name": "Turkish Lira",             "decimal_places": 2},
    "CHF": {"symbol": "Fr", "name": "Swiss Franc",              "decimal_places": 2},
    "PLN": {"symbol": "zł", "name": "Polish Zloty",             "decimal_places": 2},
    "CZK": {"symbol": "Kč", "name": "Czech Koruna",             "decimal_places": 2},
    "SEK": {"symbol": "kr", "name": "Swedish Krona",            "decimal_places": 2},
    "NOK": {"symbol": "kr", "name": "Norwegian Krone",          "decimal_places": 2},
    "DKK": {"symbol": "kr", "name": "Danish Krone",             "decimal_places": 2},
    "HUF": {"symbol": "Ft", "name": "Hungarian Forint",         "decimal_places": 0},
    "RON": {"symbol": "lei","name": "Romanian Leu",             "decimal_places": 2},
    "BGN": {"symbol": "лв", "name": "Bulgarian Lev",            "decimal_places": 2},
    "HRK": {"symbol": "kn", "name": "Croatian Kuna",            "decimal_places": 2},
    "JPY": {"symbol": "¥",  "name": "Japanese Yen",             "decimal_places": 0},
    "CNY": {"symbol": "¥",  "name": "Chinese Yuan",             "decimal_places": 2},
    "KRW": {"symbol": "₩",  "name": "South Korean Won",         "decimal_places": 0},
}

# ── Fallback exchange rates (base: EUR) ───────────────────
# These are approximate rates — use live API in production
FALLBACK_RATES_EUR: dict[str, float] = {
    "EUR": 1.0,
    "USD": 1.08,
    "GBP": 0.86,
    "TRY": 39.5,
    "CHF": 0.94,
    "PLN": 4.28,
    "CZK": 25.2,
    "SEK": 11.2,
    "NOK": 11.6,
    "DKK": 7.46,
    "HUF": 395.0,
    "RON": 4.98,
    "BGN": 1.96,
    "HRK": 7.53,
    "JPY": 163.0,
    "CNY": 7.85,
    "KRW": 1480.0,
}

# Cache for live rates
_live_rates: dict[str, float] = {}
_rates_updated: datetime | None = None


def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """Get exchange rate from one currency to another."""
    from_c = from_currency.upper()
    to_c = to_currency.upper()

    if from_c == to_c:
        return 1.0

    rates = _live_rates if _live_rates else FALLBACK_RATES_EUR

    if from_c not in rates or to_c not in rates:
        logger.warning(f"Unknown currency pair: {from_c}/{to_c}, returning 1.0")
        return 1.0

    # Convert via EUR as base
    from_to_eur = 1.0 / rates[from_c]
    eur_to_target = rates[to_c]
    return from_to_eur * eur_to_target


def convert_amount(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount from one currency to another."""
    rate = get_exchange_rate(from_currency, to_currency)
    converted = amount * rate
    to_info = CURRENCY_INFO.get(to_currency.upper(), {"decimal_places": 2})
    dp = to_info["decimal_places"]

    return {
        "original_amount": amount,
        "original_currency": from_currency.upper(),
        "converted_amount": round(converted, dp),
        "target_currency": to_currency.upper(),
        "exchange_rate": round(rate, 6),
        "rate_source": "live" if _live_rates else "fallback",
        "rate_date": _rates_updated.isoformat() if _rates_updated else "static",
    }


def convert_to_base(amount: float, currency: str, base_currency: str = "EUR") -> float:
    """Convert amount to base currency for aggregation."""
    if currency.upper() == base_currency.upper():
        return amount
    rate = get_exchange_rate(currency, base_currency)
    return round(amount * rate, 2)


def get_currency_info(currency_code: str) -> dict | None:
    """Get metadata for a currency."""
    return CURRENCY_INFO.get(currency_code.upper())


def get_all_currencies() -> list[dict]:
    """List all supported currencies with metadata."""
    return [
        {
            "code": code,
            "symbol": info["symbol"],
            "name": info["name"],
            "decimal_places": info["decimal_places"],
            "rate_to_eur": FALLBACK_RATES_EUR.get(code, 0),
        }
        for code, info in sorted(CURRENCY_INFO.items())
    ]


def format_amount(amount: float, currency_code: str) -> str:
    """Format amount with currency symbol."""
    info = CURRENCY_INFO.get(currency_code.upper())
    if not info:
        return f"{amount:.2f} {currency_code}"
    dp = info["decimal_places"]
    symbol = info["symbol"]
    if currency_code.upper() in ("USD", "GBP"):
        return f"{symbol}{amount:,.{dp}f}"
    return f"{amount:,.{dp}f} {symbol}"


async def update_live_rates() -> bool:
    """
    Fetch live rates from ECB or external API.
    Call periodically (e.g. daily cron).
    Returns True on success.
    """
    global _live_rates, _rates_updated
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            # ECB free rates
            r = await client.get("https://api.exchangerate-api.com/v4/latest/EUR")
            if r.status_code == 200:
                data = r.json()
                _live_rates = {k: v for k, v in data.get("rates", {}).items()
                               if k in CURRENCY_INFO}
                _live_rates["EUR"] = 1.0
                _rates_updated = datetime.utcnow()
                logger.info(f"Live rates updated: {len(_live_rates)} currencies")
                return True
    except Exception as e:
        logger.warning(f"Failed to fetch live rates: {e}, using fallback")
    return False
