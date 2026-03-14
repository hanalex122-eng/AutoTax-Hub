"""
tests/test_system.py — v5.2
Tax engine, currency service, i18n, and system endpoint tests
"""
import pytest


# ═══════════════════════════════════════════════════════
#  TAX ENGINE
# ═══════════════════════════════════════════════════════
class TestTaxEngine:
    def test_german_tax_zero_income(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(0, "DE")
        assert r["tax_amount"] == 0.0
        assert r["supported"] is True

    def test_german_tax_below_freibetrag(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(10000, "DE")
        assert r["tax_amount"] == 0.0

    def test_german_tax_medium_income(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(50000, "DE")
        assert r["tax_amount"] > 0
        assert r["effective_rate"] > 0
        assert r["effective_rate"] < 50

    def test_german_tax_high_income(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(300000, "DE")
        assert r["tax_amount"] > 50000
        assert "solidaritaetszuschlag" in r

    def test_turkish_tax(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(500000, "TR")
        assert r["supported"] is True
        assert r["tax_amount"] > 0
        assert r["country"] == "TR"

    def test_french_tax(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(60000, "FR")
        assert r["supported"] is True
        assert r["tax_amount"] > 0

    def test_uk_tax(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(80000, "GB")
        assert r["supported"] is True
        assert r["tax_amount"] > 0

    def test_us_tax(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(100000, "US")
        assert r["supported"] is True
        assert r["tax_amount"] > 0

    def test_unsupported_country(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(50000, "XX")
        assert r["supported"] is False

    def test_negative_income(self):
        from app.services.tax_engine import estimate_income_tax
        r = estimate_income_tax(-5000, "DE")
        assert r["tax_amount"] == 0.0

    def test_all_supported_countries(self):
        from app.services.tax_engine import get_supported_tax_countries
        countries = get_supported_tax_countries()
        assert len(countries) >= 10
        codes = [c["code"] for c in countries]
        assert "DE" in codes
        assert "TR" in codes
        assert "US" in codes

    def test_vat_rates(self):
        from app.services.tax_engine import get_vat_rate, get_all_vat_rates
        assert get_vat_rate("DE") == 19.0
        assert get_vat_rate("DE", "reduced") == 7.0
        assert get_vat_rate("TR") == 20.0
        assert get_vat_rate("GB") == 20.0
        all_rates = get_all_vat_rates()
        assert len(all_rates) >= 20

    def test_vat_info(self):
        from app.services.tax_engine import get_vat_info
        info = get_vat_info("DE")
        assert info["supported"] is True
        assert info["name"] == "Mehrwertsteuer (MwSt)"
        assert info["standard_rate"] == 19.0


# ═══════════════════════════════════════════════════════
#  CURRENCY SERVICE
# ═══════════════════════════════════════════════════════
class TestCurrencyService:
    def test_same_currency(self):
        from app.services.currency_service import convert_amount
        r = convert_amount(100.0, "EUR", "EUR")
        assert r["converted_amount"] == 100.0
        assert r["exchange_rate"] == 1.0

    def test_eur_to_usd(self):
        from app.services.currency_service import convert_amount
        r = convert_amount(100.0, "EUR", "USD")
        assert r["converted_amount"] > 0
        assert r["exchange_rate"] > 0

    def test_usd_to_eur(self):
        from app.services.currency_service import convert_amount
        r = convert_amount(100.0, "USD", "EUR")
        assert r["converted_amount"] > 0

    def test_try_to_eur(self):
        from app.services.currency_service import convert_amount
        r = convert_amount(1000.0, "TRY", "EUR")
        assert r["converted_amount"] < 1000.0  # TRY < EUR

    def test_convert_to_base(self):
        from app.services.currency_service import convert_to_base
        assert convert_to_base(100.0, "EUR", "EUR") == 100.0
        assert convert_to_base(100.0, "USD", "EUR") > 0

    def test_format_amount(self):
        from app.services.currency_service import format_amount
        assert "€" in format_amount(100.0, "EUR")
        assert "$" in format_amount(100.0, "USD")
        assert "₺" in format_amount(100.0, "TRY")

    def test_get_all_currencies(self):
        from app.services.currency_service import get_all_currencies
        currencies = get_all_currencies()
        assert len(currencies) >= 15
        codes = [c["code"] for c in currencies]
        assert "EUR" in codes
        assert "USD" in codes
        assert "TRY" in codes

    def test_unknown_currency(self):
        from app.services.currency_service import get_exchange_rate
        rate = get_exchange_rate("XXX", "EUR")
        assert rate == 1.0  # fallback


# ═══════════════════════════════════════════════════════
#  i18n
# ═══════════════════════════════════════════════════════
class TestI18n:
    def test_german_default(self):
        from app.services.i18n import t
        assert t("account_created") == "Konto erfolgreich erstellt."

    def test_english(self):
        from app.services.i18n import t
        assert t("account_created", "en") == "Account created successfully."

    def test_turkish(self):
        from app.services.i18n import t
        result = t("account_created", "tr")
        assert "başarıyla" in result

    def test_french(self):
        from app.services.i18n import t
        result = t("account_created", "fr")
        assert "succès" in result

    def test_arabic(self):
        from app.services.i18n import t
        result = t("account_created", "ar")
        assert len(result) > 0

    def test_chinese(self):
        from app.services.i18n import t
        result = t("account_created", "zh")
        assert "成功" in result

    def test_placeholder_substitution(self):
        from app.services.i18n import t
        result = t("account_locked", "en", minutes=15)
        assert "15" in result

    def test_unknown_key_returns_key(self):
        from app.services.i18n import t
        assert t("nonexistent_key") == "nonexistent_key"

    def test_fallback_to_german(self):
        from app.services.i18n import t
        # Unknown language falls back to German
        result = t("account_created", "xx")
        assert result == "Konto erfolgreich erstellt."

    def test_supported_languages(self):
        from app.services.i18n import get_supported_languages
        langs = get_supported_languages()
        assert len(langs) == 8
        codes = [l["code"] for l in langs]
        assert "de" in codes
        assert "en" in codes
        assert "tr" in codes


# ═══════════════════════════════════════════════════════
#  SYSTEM ENDPOINTS
# ═══════════════════════════════════════════════════════
class TestSystemEndpoints:
    def test_list_currencies(self, client):
        r = client.get("/api/v1/system/currencies")
        assert r.status_code == 200
        assert "currencies" in r.json()
        assert len(r.json()["currencies"]) >= 15

    def test_currency_detail(self, client):
        r = client.get("/api/v1/system/currencies/EUR")
        assert r.status_code == 200
        assert r.json()["symbol"] == "€"

    def test_currency_convert(self, client):
        r = client.get("/api/v1/system/currencies/convert/EUR/USD?amount=100")
        assert r.status_code == 200
        assert r.json()["converted_amount"] > 0

    def test_list_languages(self, client):
        r = client.get("/api/v1/system/languages")
        assert r.status_code == 200
        assert len(r.json()["languages"]) == 8

    def test_list_vat_rates(self, client):
        r = client.get("/api/v1/system/vat-rates")
        assert r.status_code == 200
        assert len(r.json()["vat_rates"]) >= 20

    def test_vat_rate_detail(self, client):
        r = client.get("/api/v1/system/vat-rates/DE")
        assert r.status_code == 200
        assert r.json()["standard_rate"] == 19.0

    def test_tax_countries(self, client):
        r = client.get("/api/v1/system/tax-countries")
        assert r.status_code == 200
        assert len(r.json()["countries"]) >= 10

    def test_tax_estimate_de(self, client):
        r = client.get("/api/v1/system/tax-estimate?net_profit=50000&country=DE")
        assert r.status_code == 200
        assert r.json()["tax_amount"] > 0
        assert "disclaimer" in r.json()

    def test_tax_estimate_tr(self, client):
        r = client.get("/api/v1/system/tax-estimate?net_profit=500000&country=TR")
        assert r.status_code == 200
        assert r.json()["supported"] is True

    def test_tax_estimate_zero(self, client):
        r = client.get("/api/v1/system/tax-estimate?net_profit=0&country=DE")
        assert r.status_code == 200
        assert r.json()["tax_amount"] == 0.0
