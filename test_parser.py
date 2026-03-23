"""
Test suite for AutoTax-HUB Parser v2.0
Tests with realistic OCR raw_text samples.
"""
import sys
sys.path.insert(0, "/home/claude/project")

from autotax.parser import (
    parse_invoice, extract_vendor, extract_date, extract_total,
    extract_vat_info, extract_invoice_number, detect_category,
    detect_country, detect_payment_method, normalize_amount_text,
)

# ════════════════════════════════════════════════════════════════
# SAMPLE OCR TEXTS (realistic receipts)
# ════════════════════════════════════════════════════════════════

LIDL_RECEIPT = """LIDL Dienstleistung GmbH & Co. KG
Stiftsbergstr. 1
74172 Neckarsulm
Filiale 1234  Kasse 02
Datum: 15.03.2025

Bio Vollmilch 3,5%        1,19
Dinkel Brot 500g           1,79
Bananen 1kg                1,29
Ritter Sport 100g          1,09
Coca Cola 1,5l             1,29

Summe                      6,65
davon MwSt 7%              0,44
davon MwSt 19%             0,00

Gegeben BAR               10,00
Rückgeld                    3,35

Bon-Nr. 4521
USt-ID: DE814544022
"""

STARBUCKS_RECEIPT = """STARBUCKS COFFEE
Am Staden 4
66111 Saarbrücken

Datum: 22.02.2025 14:35

1x Caffe Latte Grande       4,79
1x Chocolate Muffin          2,99

Gesamtbetrag                 7,78
Inkl. MwSt 19%               1,24

Kartenzahlung                7,78
Visa **** 4521

Quittung Nr. 88912
Vielen Dank für Ihren Besuch!
"""

SHELL_RECEIPT = """Shell Station
Mainzer Str. 45
66111 Saarbrücken

Datum: 10.01.2025

Super E10      42,35 Liter
Preis/Liter         1,789
Betrag             75,73 EUR

Gesamtbetrag       75,73 EUR
davon MwSt 19%     12,10 EUR

EC-Karte
Mastercard **** 9988

Beleg-Nr. 002847
USt-ID: DE123456789
"""

DEICHMANN_RECEIPT = """DEICHMANN SE
Heinrich-Deichmann-Str. 9
45359 Essen

Rechnung Nr. RE-20250305-4421

Datum: 05.03.2025

1x Nike Revolution 6       59,95
1x Einlegesohle Memory      9,95

Summe                       69,90
inkl. 19% MwSt             11,17

Zahlung: Girocard
Beleg-Nr. 77123

Vielen Dank!
"""

FRENCH_RECEIPT = """CARREFOUR CITY
12 Rue de la République
75001 Paris

Date: 18/02/2025

Baguette tradition          1,30
Camembert AOC               3,49
Vin rouge Côtes du Rhône    6,99
Yaourt nature x4            2,15

TOTAL TTC                  13,93
dont TVA 5,5%               0,73

Paiement: Carte bancaire
VISA **** 1234

Facture No. FC-2025-00891
SIRET: 652 014 051 00384
Merci de votre visite
"""

AMAZON_INVOICE = """Amazon EU S.à r.l.
5 Rue Plaetis
L-2338 Luxembourg

Rechnung RE-2025-8834521
Rechnungsdatum: 2025-02-28

Bestellung: 302-1234567-8901234

Logitech MX Master 3S      89,99 EUR
Versand                      0,00 EUR

Rechnungsbetrag             89,99 EUR
enthält USt 19%             14,37 EUR

Zahlungsart: SEPA-Lastschrift
USt-IdNr.: LU26375245
"""

AUCHAN_RECEIPT = """AUCHAN Hypermarché
Zone Commerciale
57600 Forbach

Le 12/03/2025 09:42

Lait demi-écrémé 1L        0,95
Pain de mie                 1,45
Jambon blanc x6             2,99
Eau minérale 6x1,5L        3,29
Nutella 750g                4,79

TOTAL                      13,47
TVA 5,5%                    0,70

ESPÈCES                    15,00
RENDU                       1,53

Ticket No. 092841
TVA FR45 612 345 678
"""

REWE_SHORT = """REWE
Berliner Promenade 1
66111 Saarbrücken
11.03.25 18:22 Kasse 3

Apfel Braeburn 1kg    2,49
Dr. Oetker Pizza      3,29
Milch 1L              1,15

SUMME                  6,93
davon 7% MwSt         0,46
EC-Karte               6,93
"""

MEDIAMARKT_RECEIPT = """MediaMarkt
Europa-Allee 6
66113 Saarbrücken

Rechnung-Nr.: INV-20250220-5543

Datum 20.02.2025

Samsung Galaxy Buds FE    99,99
USB-C Kabel 2m             9,99

Gesamtbetrag             109,98
inkl. MwSt 19%            17,56

Bezahlt mit: Apple Pay
Bon Nr. 112233
"""

EMPTY_TEXT = ""
GARBAGE_TEXT = "###  .... *** 12345 ---"


def test_lidl():
    r = parse_invoice(LIDL_RECEIPT)
    assert r["vendor"] != "Unbekannt", f"Vendor should be detected, got: {r['vendor']}"
    assert "lidl" in r["vendor"].lower(), f"Expected Lidl, got: {r['vendor']}"
    assert r["category"] == "food", f"Category should be food, got: {r['category']}"
    assert r["date"] == "2025-03-15", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 6.65, f"Total wrong: {r['total_amount']}"
    assert r["payment_method"] == "cash", f"Payment should be cash, got: {r['payment_method']}"
    assert r["country"] == "DE", f"Country should be DE, got: {r['country']}"
    assert r["invoice_number"], f"Should find bon number"
    print(f"  ✓ Lidl: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), date={r['date']}, "
          f"inv#={r['invoice_number']}, pay={r['payment_method']}")


def test_starbucks():
    r = parse_invoice(STARBUCKS_RECEIPT)
    assert "starbucks" in r["vendor"].lower(), f"Expected Starbucks, got: {r['vendor']}"
    assert r["category"] == "restaurant", f"Category should be restaurant, got: {r['category']}"
    assert r["date"] == "2025-02-22", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 7.78, f"Total wrong: {r['total_amount']}"
    assert r["vat_amount"] == 1.24, f"VAT amount wrong: {r['vat_amount']}"
    assert r["payment_method"] == "card", f"Payment should be card, got: {r['payment_method']}"
    print(f"  ✓ Starbucks: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), inv#={r['invoice_number']}")


def test_shell():
    r = parse_invoice(SHELL_RECEIPT)
    assert "shell" in r["vendor"].lower(), f"Expected Shell, got: {r['vendor']}"
    assert r["category"] == "fuel", f"Category should be fuel, got: {r['category']}"
    assert r["date"] == "2025-01-10", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 75.73, f"Total wrong: {r['total_amount']}"
    assert r["vat_amount"] == 12.10, f"VAT should be 12.10, got: {r['vat_amount']}"
    assert r["payment_method"] == "card", f"Payment should be card, got: {r['payment_method']}"
    print(f"  ✓ Shell: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), inv#={r['invoice_number']}")


def test_deichmann():
    r = parse_invoice(DEICHMANN_RECEIPT)
    assert "deichmann" in r["vendor"].lower(), f"Expected Deichmann, got: {r['vendor']}"
    assert r["category"] == "clothing", f"Category should be clothing, got: {r['category']}"
    assert r["date"] == "2025-03-05", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 69.90, f"Total wrong: {r['total_amount']}"
    assert r["invoice_number"], f"Should find RE- invoice number"
    print(f"  ✓ Deichmann: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), inv#={r['invoice_number']}")


def test_french_carrefour():
    r = parse_invoice(FRENCH_RECEIPT)
    assert "carrefour" in r["vendor"].lower(), f"Expected Carrefour, got: {r['vendor']}"
    assert r["category"] == "food", f"Category should be food, got: {r['category']}"
    assert r["date"] == "2025-02-18", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 13.93, f"Total wrong: {r['total_amount']}"
    assert r["country"] == "FR", f"Country should be FR, got: {r['country']}"
    assert r["payment_method"] == "card", f"Payment should be card, got: {r['payment_method']}"
    assert r["invoice_number"], f"Should find facture number"
    print(f"  ✓ Carrefour FR: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), country={r['country']}, inv#={r['invoice_number']}")


def test_amazon():
    r = parse_invoice(AMAZON_INVOICE)
    assert r["category"] == "shopping", f"Category should be shopping, got: {r['category']}"
    assert r["date"] == "2025-02-28", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 89.99, f"Total wrong: {r['total_amount']}"
    assert r["vat_amount"] == 14.37, f"VAT should be 14.37, got: {r['vat_amount']}"
    assert "RE-2025" in r["invoice_number"], f"Should find RE- number, got: {r['invoice_number']}"
    assert r["payment_method"] == "transfer", f"Payment should be transfer, got: {r['payment_method']}"
    print(f"  ✓ Amazon: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), inv#={r['invoice_number']}, pay={r['payment_method']}")


def test_auchan_french():
    r = parse_invoice(AUCHAN_RECEIPT)
    assert "auchan" in r["vendor"].lower(), f"Expected Auchan, got: {r['vendor']}"
    assert r["category"] == "food", f"Category should be food, got: {r['category']}"
    assert r["date"] == "2025-03-12", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 13.47, f"Total wrong: {r['total_amount']}"
    assert r["country"] == "FR", f"Country should be FR, got: {r['country']}"
    assert r["payment_method"] == "cash", f"Payment should be cash, got: {r['payment_method']}"
    print(f"  ✓ Auchan FR: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"vat={r['vat_amount']}({r['vat_rate']}), country={r['country']}")


def test_rewe_short_date():
    r = parse_invoice(REWE_SHORT)
    assert "rewe" in r["vendor"].lower(), f"Expected REWE, got: {r['vendor']}"
    assert r["category"] == "food", f"Category should be food, got: {r['category']}"
    assert r["date"] == "2025-03-11", f"Date wrong for DD.MM.YY format: {r['date']}"
    assert r["total_amount"] == 6.93, f"Total wrong: {r['total_amount']}"
    assert r["payment_method"] == "card", f"Payment should be card, got: {r['payment_method']}"
    print(f"  ✓ REWE: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"date={r['date']}, pay={r['payment_method']}")


def test_mediamarkt():
    r = parse_invoice(MEDIAMARKT_RECEIPT)
    assert r["category"] == "electronics", f"Category should be electronics, got: {r['category']}"
    assert r["date"] == "2025-02-20", f"Date wrong: {r['date']}"
    assert r["total_amount"] == 109.98, f"Total wrong: {r['total_amount']}"
    assert "INV-" in r["invoice_number"], f"Should find INV- number, got: {r['invoice_number']}"
    assert r["payment_method"] == "apple_pay", f"Payment should be apple_pay, got: {r['payment_method']}"
    print(f"  ✓ MediaMarkt: vendor={r['vendor']}, cat={r['category']}, total={r['total_amount']}, "
          f"inv#={r['invoice_number']}, pay={r['payment_method']}")


def test_empty():
    r = parse_invoice(EMPTY_TEXT)
    assert r["vendor"] == "Unbekannt"
    assert r["total_amount"] == 0.0
    assert r["category"] == "other"
    print(f"  ✓ Empty: handled gracefully")


def test_garbage():
    r = parse_invoice(GARBAGE_TEXT)
    assert r["vendor"] == "Unbekannt"
    assert r["category"] == "other"
    print(f"  ✓ Garbage: handled gracefully")


def test_country_default_vat():
    """Test that country default VAT is applied when no rate found."""
    text_de = "Firma XYZ GmbH\nBetrag: 119,00\nDatum: 01.01.2025"
    r = parse_invoice(text_de)
    assert r["country"] == "DE"
    assert "19" in r["vat_rate"], f"DE default should be 19%, got: {r['vat_rate']}"
    print(f"  ✓ DE default VAT: {r['vat_rate']}, amount={r['vat_amount']}")


def test_normalize_amounts():
    """Test EU number format normalization."""
    assert "1234.56" in normalize_amount_text("1.234,56")
    assert "12.99" in normalize_amount_text("12,99")
    assert "1234567.89" not in normalize_amount_text("1.234,56")  # shouldn't produce weird numbers
    print(f"  ✓ Amount normalization works")


# ════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("Lidl Receipt", test_lidl),
        ("Starbucks Receipt", test_starbucks),
        ("Shell Receipt", test_shell),
        ("Deichmann Receipt", test_deichmann),
        ("Carrefour (French)", test_french_carrefour),
        ("Amazon Invoice", test_amazon),
        ("Auchan (French)", test_auchan_french),
        ("REWE Short Date", test_rewe_short_date),
        ("MediaMarkt", test_mediamarkt),
        ("Empty Text", test_empty),
        ("Garbage Text", test_garbage),
        ("Country Default VAT", test_country_default_vat),
        ("Amount Normalization", test_normalize_amounts),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {name}: EXCEPTION — {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed!")
