"""
AutoTax-HUB Invoice Parser v2.0
───────────────────────────────
Extracts structured data from OCR raw text:
  - vendor name
  - category (auto-detected from vendor)
  - date (multi-format)
  - total amount
  - VAT rate & amount (with country defaults)
  - invoice/receipt number
  - payment method
  - country detection
"""

import re
from datetime import datetime

# ════════════════════════════════════════════════════════════════
# VENDOR → CATEGORY MAPPING
# ════════════════════════════════════════════════════════════════

VENDOR_CATEGORY_MAP: dict[str, str] = {
    # Supermarkets / Food
    "lidl": "food",
    "aldi": "food",
    "auchan": "food",
    "rewe": "food",
    "edeka": "food",
    "netto": "food",
    "penny": "food",
    "kaufland": "food",
    "norma": "food",
    "carrefour": "food",
    "leclerc": "food",
    "intermarche": "food",
    "intermarché": "food",
    "monoprix": "food",
    "migros": "food",
    "coop": "food",
    "spar": "food",
    "globus": "food",
    "real": "food",
    "tegut": "food",
    "hit": "food",
    "nahkauf": "food",
    "wasgau": "food",
    "famila": "food",
    "combi": "food",
    "marktkauf": "food",
    "denn's": "food",
    "bio company": "food",
    "basic": "food",
    "alnatura": "food",

    # Restaurants / Cafes
    "starbucks": "restaurant",
    "mcdonald": "restaurant",
    "mcdonalds": "restaurant",
    "mcdonald's": "restaurant",
    "burger king": "restaurant",
    "subway": "restaurant",
    "kfc": "restaurant",
    "dominos": "restaurant",
    "domino's": "restaurant",
    "pizza hut": "restaurant",
    "dunkin": "restaurant",
    "nordsee": "restaurant",
    "backwerk": "restaurant",
    "back-factory": "restaurant",
    "dean & david": "restaurant",
    "vapiano": "restaurant",
    "hans im glück": "restaurant",
    "hans im glueck": "restaurant",
    "peter pane": "restaurant",
    "alex": "restaurant",
    "block house": "restaurant",

    # Clothing / Shoes
    "deichmann": "clothing",
    "h&m": "clothing",
    "zara": "clothing",
    "c&a": "clothing",
    "primark": "clothing",
    "kik": "clothing",
    "takko": "clothing",
    "new yorker": "clothing",
    "esprit": "clothing",
    "jack & jones": "clothing",
    "peek & cloppenburg": "clothing",
    "p&c": "clothing",
    "zalando": "clothing",

    # Fuel / Gas Stations
    "shell": "fuel",
    "aral": "fuel",
    "total": "fuel",
    "totalenergies": "fuel",
    "esso": "fuel",
    "bp": "fuel",
    "jet": "fuel",
    "star": "fuel",
    "agip": "fuel",
    "eni": "fuel",
    "hem": "fuel",
    "avia": "fuel",
    "q1": "fuel",
    "tankstelle": "fuel",
    "bft": "fuel",

    # Electronics
    "saturn": "electronics",
    "mediamarkt": "electronics",
    "media markt": "electronics",
    "conrad": "electronics",
    "apple": "electronics",
    "notebooksbilliger": "electronics",
    "cyberport": "electronics",
    "alternate": "electronics",
    "expert": "electronics",
    "euronics": "electronics",

    # Drugstores / Health
    "dm": "health",
    "rossmann": "health",
    "müller": "health",
    "mueller": "health",
    "apotheke": "health",
    "pharmacy": "health",
    "pharmacie": "health",
    "douglas": "health",

    # Office Supplies
    "staples": "office",
    "viking": "office",
    "bürobedarf": "office",
    "mcpaper": "office",
    "pagro": "office",

    # Hardware / Home
    "bauhaus": "home",
    "obi": "home",
    "hornbach": "home",
    "toom": "home",
    "hagebau": "home",
    "ikea": "home",
    "roller": "home",
    "poco": "home",
    "mömax": "home",

    # Transport / Travel
    "deutsche bahn": "transport",
    "db ": "transport",
    "flixbus": "transport",
    "uber": "transport",
    "bolt": "transport",
    "taxi": "transport",
    "lufthansa": "transport",
    "ryanair": "transport",
    "easyjet": "transport",

    # Telecom / Internet
    "telekom": "telecom",
    "vodafone": "telecom",
    "o2": "telecom",
    "1&1": "telecom",
    "congstar": "telecom",

    # Insurance
    "allianz": "insurance",
    "huk": "insurance",
    "ergo": "insurance",
    "axa": "insurance",

    # Post / Shipping
    "deutsche post": "shipping",
    "dhl": "shipping",
    "hermes": "shipping",
    "dpd": "shipping",
    "gls": "shipping",
    "ups": "shipping",
    "fedex": "shipping",

    # Software / Subscriptions
    "amazon": "shopping",
    "ebay": "shopping",
    "paypal": "shopping",
    "walmart": "shopping",
    "action": "shopping",
    "tedi": "shopping",
    "target": "shopping",
    "costco": "shopping",
    "tk maxx": "shopping",
    "microsoft": "software",
    "google": "software",
    "adobe": "software",
    "spotify": "subscription",
    "netflix": "subscription",
}

# ════════════════════════════════════════════════════════════════
# COUNTRY DETECTION & DEFAULT VAT RATES
# ════════════════════════════════════════════════════════════════

COUNTRY_VAT_DEFAULTS: dict[str, float] = {
    "DE": 19.0,
    "FR": 20.0,
    "AT": 20.0,
    "NL": 21.0,
    "BE": 21.0,
    "IT": 22.0,
    "ES": 21.0,
    "PT": 23.0,
    "CH": 8.1,
    "LU": 17.0,
    "PL": 23.0,
    "CZ": 21.0,
    "DK": 25.0,
    "SE": 25.0,
    "FI": 25.5,
    "IE": 23.0,
    "GR": 24.0,
    "HU": 27.0,
    "RO": 19.0,
    "BG": 20.0,
    "HR": 25.0,
    "SK": 23.0,
    "SI": 22.0,
    "LT": 21.0,
    "LV": 21.0,
    "EE": 22.0,
    "CY": 19.0,
    "MT": 18.0,
}

COUNTRY_INDICATORS: dict[str, list[str]] = {
    "DE": [
        "deutschland", "germany", "steuer-nr", "steuernummer",
        "ust-id", "ustid", "finanzamt", "handelsregister", "hrb",
        "beleg", "kassenbon", "plz",
        # These are shared with AT/CH but weighted here for DE-only context
        "gmbh", "e.v.", "eur",
    ],
    "FR": [
        "france", "tva", "siret", "siren", "sarl", "sas", "eurl",
        "facture", "montant", "total ttc", "total ht", "rue ",
        "cedex", "arrondissement",
    ],
    "AT": [
        "österreich", "austria", "wien", "graz", "linz", "salzburg",
        "innsbruck", "klagenfurt", "uid-nr", "uid nr",
    ],
    "NL": [
        "nederland", "netherlands", "btw", "kvk", "b.v.", "bv ",
    ],
    "BE": [
        "belgique", "belgie", "belgium", "tva/btw",
    ],
    "IT": [
        "italia", "italy", "iva", "p.iva", "fattura", "scontrino",
        "codice fiscale", "s.r.l.", "s.p.a.",
    ],
    "ES": [
        "españa", "spain", "nif", "cif", "factura", "iva ",
    ],
    "CH": [
        "schweiz", "suisse", "svizzera", "switzerland", "chf",
        "mwst-nr", "che-", "zürich", "bern", "basel", "genf",
        "luzern", "lausanne",
    ],
    "LU": [
        "luxembourg", "luxemburg",
    ],
}

# Known reduced VAT rates per country
KNOWN_VAT_RATES: dict[str, list[float]] = {
    "DE": [19.0, 7.0],
    "FR": [20.0, 10.0, 5.5, 2.1],
    "AT": [20.0, 13.0, 10.0],
    "NL": [21.0, 9.0],
    "BE": [21.0, 12.0, 6.0],
    "IT": [22.0, 10.0, 5.0, 4.0],
    "ES": [21.0, 10.0, 4.0],
    "CH": [8.1, 3.8, 2.6],
    "LU": [17.0, 14.0, 8.0, 3.0],
}

# ════════════════════════════════════════════════════════════════
# NORMALIZATION
# ════════════════════════════════════════════════════════════════

def normalize(text: str) -> str:
    """Normalize OCR text for amount/keyword extraction."""
    t = text.lower()
    # Replace newlines with spaces (OCR splits keywords across lines)
    t = re.sub(r"\n+", " ", t)
    # Standardize currency symbols
    t = t.replace("€", " EUR ")
    t = t.replace("chf", " CHF ")
    # Fix common OCR artifacts
    t = re.sub(r"[|l](?=\d)", "1", t)  # l or | before digits -> 1
    # Normalize spaces around EUR
    t = re.sub(r"\beur\.?\b", " EUR ", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_amount_text(text: str) -> str:
    """Prepare text for amount extraction: handle EU comma decimals."""
    t = text
    # Convert "1.234,56" to "1234.56" (dot-thousands + comma-decimals)
    t = re.sub(r"(\d{1,3})\.(\d{3}),(\d{2})\b", lambda m: f"{m.group(1)}{m.group(2)}.{m.group(3)}", t)
    # Simple comma decimal: "12,99" -> "12.99"
    t = re.sub(r"(\d+),(\d{2})\b", r"\1.\2", t)
    return t


# ════════════════════════════════════════════════════════════════
# VENDOR EXTRACTION
# ════════════════════════════════════════════════════════════════

# Common non-vendor lines to skip
_SKIP_PATTERNS = re.compile(
    r"^("
    r"datum|date|kasse|filiale|bon|beleg|rechnung|quittung|invoice|facture|receipt"
    r"|tel\.?\s|fax|fon|phone|www\.|http|email|e-mail"
    r"|ust|mwst|steuer|tax\b|tva|iva|btw"
    r"|str\.|straße|strasse|platz\b|weg\b|allee|gasse|rue |avenue|boulevard"
    r"|am\s+\w+\s+\d"  # "Am Staden 4" style addresses
    r"|[a-zäöü]+\w*\s+str\.?\s"  # "Mainzer Str. 45" style
    r"|[a-zäöü]+\w*\s+straße"  # "Hauptstraße" etc.
    r"|\w+str\.?\s+\d"  # "Stiftsbergstr. 1" style
    r"|[a-zäöü]+-?\w*-?str\.\s*\d"  # "Heinrich-Deichmann-Str. 9"
    r"|europa-allee|berliner\s+promenade"  # common street names
    r"|\d{4,5}\s+\w"  # postal code + city
    r"|.*@.*\.\w{2,4}"  # email
    r"|vielen\s+dank|merci|thank"  # thank you lines
    r"|zone\s+commerciale"  # FR shopping zone
    r")",
    re.IGNORECASE
)

# Business entity suffixes — matched with word boundaries
_VENDOR_SUFFIX_RE = re.compile(
    r"\b(?:gmbh|mbh|ohg|e\.?k\.?|e\.?v\.?|"
    r"ltd\.?|inc\.?|sarl|sas|eurl|"
    r"s\.?r\.?l\.?|s\.?p\.?a\.?|b\.?v\.?|ug)\b"
    r"|(?:\bco\.\s*kg\b|\b&\s*co\.?\b|\bag\b|\bkg\b|\bsa\b)",
    re.IGNORECASE,
)

# Lines that look like product/item lines (text + price at end)
_ITEM_LINE_RE = re.compile(r".+\s+\d+[.,]\d{2}\s*$")

# Lines that are totals/subtotals
_TOTAL_LINE_RE = re.compile(
    r"^(summe|total|gesamt|betrag|brutto|netto|gesamtbetrag|endbetrag|"
    r"zu\s*zahlen|zahlbetrag|zwischensumme|subtotal|montant|inkl|davon|"
    r"mwst|ust|tva|vat|steuer|gegeben|rückgeld|wechselgeld|"
    r"kartenzahlung|barzahlung|visa|mastercard|ec-karte|girocard|"
    r"paiement|payment|bezahlt|rendu)\b",
    re.IGNORECASE,
)


def extract_vendor(raw_text: str) -> str:
    """Extract vendor/store name from the first meaningful lines of OCR text."""
    lines = raw_text.strip().split("\n")
    candidates = []

    for line in lines[:12]:
        cleaned = line.strip()
        if not cleaned or len(cleaned) < 2:
            continue
        # Skip lines that are purely numbers/symbols
        if re.match(r"^[\d\s\.\-\/,€%:;#*+]+$", cleaned):
            continue
        # Skip common non-vendor header patterns
        if _SKIP_PATTERNS.match(cleaned):
            continue
        # Skip item/product lines (text followed by price)
        if _ITEM_LINE_RE.match(cleaned):
            continue
        # Skip total/payment lines
        if _TOTAL_LINE_RE.match(cleaned):
            continue
        # Skip very long lines (likely description/address)
        if len(cleaned) > 60:
            continue
        candidates.append(cleaned)

    if not candidates:
        return "Unbekannt"

    # Priority 1: line containing a business entity suffix (GmbH, Ltd, etc.)
    for c in candidates[:5]:
        if _VENDOR_SUFFIX_RE.search(c):
            return _clean_vendor_name(c)

    # Priority 2: line matching a known vendor name
    for c in candidates[:5]:
        cl = c.lower()
        for known_vendor in VENDOR_CATEGORY_MAP:
            # Only match vendors with 3+ chars to avoid false positives
            if len(known_vendor) >= 3 and known_vendor in cl:
                return _clean_vendor_name(c)

    # Priority 3: first candidate (usually store name at top of receipt)
    return _clean_vendor_name(candidates[0])


_VENDOR_OCR_CORRECTIONS = {
    # Supermarkets — common OCR misreads
    "lödl": "LIDL", "lōdl": "LIDL", "l1dl": "LIDL", "lidl": "LIDL",
    "lldi": "LIDL", "lid1": "LIDL", "iidl": "LIDL", "lidl.de": "LIDL",
    "lidii": "LIDL", "lidll": "LIDL", "liidl": "LIDL", "lidi": "LIDL",
    "lad1": "LIDL", "ladi": "LIDL", "lidl": "LIDL", "ildl": "LIDL",
    "1idl": "LIDL", "iidii": "LIDL", "lidii": "LIDL",
    "aldl": "ALDI", "a1di": "ALDI", "aldi": "ALDI", "aidi": "ALDI",
    "aldi süd": "ALDI SÜD", "aldi sud": "ALDI SÜD", "aldi nord": "ALDI NORD",
    "rewe": "REWE", "rew3": "REWE", "r3we": "REWE", "rewe.de": "REWE",
    "edeka": "EDEKA", "edek4": "EDEKA", "3deka": "EDEKA",
    "penny": "PENNY", "p3nny": "PENNY", "pennymarkt": "PENNY",
    "netto": "NETTO", "n3tto": "NETTO", "nettomarkt": "NETTO",
    "kaufland": "KAUFLAND", "kauf1and": "KAUFLAND",
    "norma": "NORMA", "n0rma": "NORMA",
    "auchan": "AUCHAN", "auchan.fr": "AUCHAN",
    "carrefour": "CARREFOUR", "carref0ur": "CARREFOUR",
    "leclerc": "E.LECLERC", "e.leclerc": "E.LECLERC",
    "monoprix": "MONOPRIX", "m0noprix": "MONOPRIX",
    "migros": "MIGROS", "coop": "COOP", "spar": "SPAR",
    # Restaurants
    "amazon": "AMAZON", "amaz0n": "AMAZON", "amazon.de": "AMAZON",
    "starbucks": "STARBUCKS", "starbuck5": "STARBUCKS", "starbuks": "STARBUCKS",
    "mcdonald": "MCDONALDS", "mcdonalds": "MCDONALDS", "mcdona1ds": "MCDONALDS",
    "mc donald": "MCDONALDS", "mcdo": "MCDONALDS",
    "burger king": "BURGER KING", "burgerking": "BURGER KING",
    "subway": "SUBWAY", "kfc": "KFC",
    # Fuel
    "shell": "SHELL", "sh3ll": "SHELL", "shell.de": "SHELL",
    "aral": "ARAL", "ara1": "ARAL", "aral.de": "ARAL",
    "total": "TOTALENERGIES", "totalenergies": "TOTALENERGIES",
    "esso": "ESSO", "ess0": "ESSO", "bp": "BP",
    # Drugstores
    "dm": "DM", "dm-drogerie": "DM", "dm drogerie": "DM",
    "rossmann": "ROSSMANN", "r0ssmann": "ROSSMANN",
    "mueller": "MÜLLER", "müller": "MÜLLER", "muller": "MÜLLER",
    # Electronics
    "saturn": "SATURN", "mediamarkt": "MEDIA MARKT", "media markt": "MEDIA MARKT",
    "apple": "APPLE", "apple.com": "APPLE",
    # Clothing
    "deichmann": "DEICHMANN", "de'chmann": "DEICHMANN", "delchmann": "DEICHMANN",
    "h&m": "H&M", "hm": "H&M", "zara": "ZARA", "c&a": "C&A",
    "primark": "PRIMARK", "kik": "KIK", "takko": "TAKKO",
    # Home / DIY
    "ikea": "IKEA", "1kea": "IKEA", "bauhaus": "BAUHAUS", "obi": "OBI",
    "hornbach": "HORNBACH", "h0rnbach": "HORNBACH",
    # Transport
    "deutsche bahn": "DEUTSCHE BAHN", "db ": "DEUTSCHE BAHN",
    "flixbus": "FLIXBUS", "uber": "UBER", "bolt": "BOLT",
    # Telecom
    "telekom": "TELEKOM", "vodafone": "VODAFONE", "o2": "O2",
    # Post
    "dhl": "DHL", "deutsche post": "DEUTSCHE POST", "hermes": "HERMES",
    # Software
    "microsoft": "MICROSOFT", "google": "GOOGLE", "adobe": "ADOBE",
    "spotify": "SPOTIFY", "netflix": "NETFLIX", "paypal": "PAYPAL",
    # === FRANCE ===
    "auchan": "AUCHAN", "auchan.fr": "AUCHAN", "auchanfr": "AUCHAN",
    "carrefour": "CARREFOUR", "carref0ur": "CARREFOUR", "carrefour market": "CARREFOUR",
    "carrefour city": "CARREFOUR", "carrefour express": "CARREFOUR",
    "leclerc": "E.LECLERC", "e.leclerc": "E.LECLERC", "e leclerc": "E.LECLERC",
    "monoprix": "MONOPRIX", "m0noprix": "MONOPRIX", "monop'": "MONOPRIX",
    "intermarche": "INTERMARCHÉ", "intermarché": "INTERMARCHÉ",
    "casino": "CASINO", "géant casino": "GÉANT CASINO", "geant casino": "GÉANT CASINO",
    "franprix": "FRANPRIX", "picard": "PICARD",
    "boulangerie": "BOULANGERIE", "patisserie": "PÂTISSERIE",
    "bricomarche": "BRICOMARCHÉ", "bricorama": "BRICORAMA",
    "leroy merlin": "LEROY MERLIN", "leroymerlin": "LEROY MERLIN",
    "castorama": "CASTORAMA", "darty": "DARTY", "fnac": "FNAC",
    "boulanger": "BOULANGER", "sncf": "SNCF", "ratp": "RATP",
    "la poste": "LA POSTE", "chronopost": "CHRONOPOST",
    "orange": "ORANGE", "sfr": "SFR", "bouygues": "BOUYGUES TELECOM",
    "free": "FREE", "free mobile": "FREE",
    "total": "TOTALENERGIES", "totalenergies": "TOTALENERGIES",
    "decathlon": "DECATHLON", "d3cathlon": "DECATHLON",
    "kiabi": "KIABI", "action": "ACTION",
    # === ITALY ===
    "esselunga": "ESSELUNGA", "conad": "CONAD", "coop italia": "COOP",
    "eurospin": "EUROSPIN", "lidl italia": "LIDL", "md discount": "MD",
    "pam": "PAM", "despar": "DESPAR", "bennet": "BENNET",
    "autogrill": "AUTOGRILL", "eni": "ENI", "agip": "AGIP",
    "trenitalia": "TRENITALIA", "italo": "ITALO",
    "tim": "TIM", "wind tre": "WINDTRE", "iliad": "ILIAD",
    "poste italiane": "POSTE ITALIANE", "mediaworld": "MEDIAWORLD",
    "unieuro": "UNIEURO", "feltrinelli": "FELTRINELLI",
    "ovs": "OVS", "calzedonia": "CALZEDONIA", "intimissimi": "INTIMISSIMI",
    # === SPAIN ===
    "mercadona": "MERCADONA", "mercad0na": "MERCADONA",
    "dia": "DIA", "el corte ingles": "EL CORTE INGLÉS",
    "el corte inglés": "EL CORTE INGLÉS", "eroski": "EROSKI",
    "hipercor": "HIPERCOR", "alcampo": "ALCAMPO",
    "consum": "CONSUM", "bonpreu": "BONPREU", "caprabo": "CAPRABO",
    "repsol": "REPSOL", "cepsa": "CEPSA",
    "renfe": "RENFE", "iberia": "IBERIA", "vueling": "VUELING",
    "movistar": "MOVISTAR", "vodafone": "VODAFONE",
    "correos": "CORREOS", "mediamarkt": "MEDIA MARKT",
    "zara": "ZARA", "mango": "MANGO", "desigual": "DESIGUAL",
    "massimo dutti": "MASSIMO DUTTI", "bershka": "BERSHKA",
    "pull&bear": "PULL&BEAR", "stradivarius": "STRADIVARIUS",
    # === UK / USA ===
    "tesco": "TESCO", "tesc0": "TESCO", "sainsbury": "SAINSBURY'S",
    "sainsbury's": "SAINSBURY'S", "asda": "ASDA", "morrisons": "MORRISONS",
    "waitrose": "WAITROSE", "marks & spencer": "MARKS & SPENCER", "m&s": "M&S",
    "walmart": "WALMART", "wa1mart": "WALMART", "wal-mart": "WALMART",
    "target": "TARGET", "targ3t": "TARGET",
    "costco": "COSTCO", "c0stco": "COSTCO",
    "whole foods": "WHOLE FOODS", "trader joe": "TRADER JOE'S",
    "trader joe's": "TRADER JOE'S", "kroger": "KROGER",
    "walgreens": "WALGREENS", "cvs": "CVS", "rite aid": "RITE AID",
    "home depot": "HOME DEPOT", "lowe's": "LOWE'S", "lowes": "LOWE'S",
    "best buy": "BEST BUY", "bestbuy": "BEST BUY",
    "apple store": "APPLE", "amazon.com": "AMAZON",
    "uber eats": "UBER EATS", "doordash": "DOORDASH", "grubhub": "GRUBHUB",
    "lyft": "LYFT", "uber": "UBER",
    "at&t": "AT&T", "verizon": "VERIZON", "t-mobile": "T-MOBILE",
    "usps": "USPS", "fedex": "FEDEX", "ups": "UPS",
    "nike": "NIKE", "adidas": "ADIDAS", "gap": "GAP",
    "old navy": "OLD NAVY", "forever 21": "FOREVER 21",
    # === TURKEY ===
    "bim": "BİM", "a101": "A101", "şok": "ŞOK", "sok": "ŞOK",
    "migros": "MİGROS", "carrefoursa": "CARREFOURSA",
    "macro center": "MACRO CENTER", "metro": "METRO",
    "gratis": "GRATIS", "watsons": "WATSONS",
    "teknosa": "TEKNOSA", "mediamarkt": "MEDIA MARKT",
    "koçtaş": "KOÇTAŞ", "koctas": "KOÇTAŞ", "bauhaus": "BAUHAUS",
    "lc waikiki": "LC WAIKIKI", "defacto": "DEFACTO",
    "turkcell": "TURKCELL", "vodafone": "VODAFONE", "türk telekom": "TÜRK TELEKOM",
    "ptt": "PTT", "yurtiçi kargo": "YURTİÇİ KARGO", "aras kargo": "ARAS KARGO",
    "thy": "TÜRK HAVA YOLLARI", "türk hava": "TÜRK HAVA YOLLARI",
    "pegasus": "PEGASUS", "sunexpress": "SUNEXPRESS",
    "opet": "OPET", "petrol ofisi": "PETROL OFİSİ", "bp": "BP",
    "starbucks": "STARBUCKS", "burger king": "BURGER KING",
}

# Website → Vendor mapping (found in OCR text)
_WEBSITE_VENDOR_MAP = {
    "lidl.de": "LIDL", "lidl.fr": "LIDL", "lidl.com": "LIDL",
    "aldi-sued.de": "ALDI SÜD", "aldi-nord.de": "ALDI NORD", "aldi.de": "ALDI",
    "rewe.de": "REWE", "edeka.de": "EDEKA", "penny.de": "PENNY",
    "netto-online.de": "NETTO", "kaufland.de": "KAUFLAND",
    "auchan.fr": "AUCHAN", "carrefour.fr": "CARREFOUR", "carrefour.com": "CARREFOUR",
    "leclerc.fr": "E.LECLERC", "monoprix.fr": "MONOPRIX",
    "amazon.de": "AMAZON", "amazon.com": "AMAZON", "amazon.fr": "AMAZON",
    "ebay.de": "EBAY", "ebay.com": "EBAY",
    "starbucks.com": "STARBUCKS", "starbucks.de": "STARBUCKS",
    "mcdonalds.de": "MCDONALDS", "mcdonalds.com": "MCDONALDS",
    "shell.de": "SHELL", "shell.com": "SHELL",
    "aral.de": "ARAL", "bp.com": "BP", "totalenergies.de": "TOTALENERGIES",
    "dm.de": "DM", "rossmann.de": "ROSSMANN",
    "saturn.de": "SATURN", "mediamarkt.de": "MEDIA MARKT",
    "apple.com": "APPLE", "microsoft.com": "MICROSOFT",
    "ikea.de": "IKEA", "ikea.com": "IKEA",
    "deichmann.de": "DEICHMANN", "deichmann.com": "DEICHMANN",
    "hm.com": "H&M", "zara.com": "ZARA",
    "bauhaus.info": "BAUHAUS", "obi.de": "OBI", "hornbach.de": "HORNBACH",
    "bahn.de": "DEUTSCHE BAHN", "flixbus.de": "FLIXBUS",
    "telekom.de": "TELEKOM", "vodafone.de": "VODAFONE",
    "dhl.de": "DHL", "paypal.com": "PAYPAL",
    "spotify.com": "SPOTIFY", "netflix.com": "NETFLIX",
    "google.com": "GOOGLE", "adobe.com": "ADOBE",
    # France
    "auchan.fr": "AUCHAN", "carrefour.fr": "CARREFOUR", "leclerc.fr": "E.LECLERC",
    "monoprix.fr": "MONOPRIX", "intermarche.com": "INTERMARCHÉ",
    "fnac.com": "FNAC", "darty.com": "DARTY", "leroymerlin.fr": "LEROY MERLIN",
    "sncf.com": "SNCF", "decathlon.fr": "DECATHLON",
    # Italy
    "esselunga.it": "ESSELUNGA", "conad.it": "CONAD", "trenitalia.it": "TRENITALIA",
    "mediaworld.it": "MEDIAWORLD", "posteitaliane.it": "POSTE ITALIANE",
    # Spain
    "mercadona.es": "MERCADONA", "elcorteingles.es": "EL CORTE INGLÉS",
    "renfe.com": "RENFE", "zara.com": "ZARA", "mango.com": "MANGO",
    # UK
    "tesco.com": "TESCO", "sainsburys.co.uk": "SAINSBURY'S", "asda.com": "ASDA",
    # USA
    "walmart.com": "WALMART", "target.com": "TARGET", "costco.com": "COSTCO",
    "bestbuy.com": "BEST BUY", "homedepot.com": "HOME DEPOT",
    # Turkey
    "bim.com.tr": "BİM", "a101.com.tr": "A101", "migros.com.tr": "MİGROS",
    "teknosa.com": "TEKNOSA", "lcwaikiki.com": "LC WAIKIKI",
    "thy.com": "TÜRK HAVA YOLLARI", "pegasus.com": "PEGASUS",
}

# Tax ID prefixes → known vendors (German USt-IdNr.)
_TAX_ID_VENDOR_MAP = {
    "DE127282923": "LIDL", "DE811207047": "ALDI SÜD", "DE129491404": "ALDI NORD",
    "DE812706034": "REWE", "DE132600790": "EDEKA",
    "DE137389567": "AMAZON", "DE814865842": "SATURN",
    "DE811154539": "SHELL", "DE811515593": "ARAL",
    "DE113549055": "DM", "DE116304402": "ROSSMANN",
    "DE129384285": "IKEA", "DE811228562": "TELEKOM",
    # France (SIRET/SIREN patterns — first digits)
    "FR40303656985": "CARREFOUR", "FR39552096281": "AUCHAN",
    "FR72428240760": "E.LECLERC", "FR03552083297": "MONOPRIX",
    # Spain (CIF)
    "ESA46103834": "MERCADONA",
    # Italy (P.IVA)
    "IT02153300963": "ESSELUNGA",
}


def _clean_vendor_name(name: str) -> str:
    """Clean up vendor name: remove trailing punctuation, asterisks, OCR corrections."""
    name = re.sub(r"[*#]+", "", name).strip()
    name = re.sub(r"[\s\-:,]+$", "", name).strip()

    # Garbage detection — if too few real letters vs symbols, it's OCR noise
    # BUT first check if it's a known short vendor name (H&M, DM, etc.)
    letters_only = re.sub(r"[^a-zA-ZäöüÄÖÜß]", "", name)
    name_check = name.lower().strip()
    is_known_vendor = any(v in name_check for v in VENDOR_CATEGORY_MAP if len(v) >= 2)
    if not is_known_vendor:
        if len(letters_only) < 3:
            return "Unbekannt"
        if len(name) > 0 and len(letters_only) / len(name) < 0.5:
            return "Unbekannt"

    # OCR correction: check if cleaned name matches a known misread
    name_lower = re.sub(r"[^a-zäöüß0-9]", "", name.lower())
    for wrong, correct in _VENDOR_OCR_CORRECTIONS.items():
        if wrong in name_lower:
            return correct
    # Title-case if all upper
    if name == name.upper() and len(name) > 3:
        name = name.title()
    return name if name else "Unbekannt"


def _deep_vendor_search(raw_text: str) -> str:
    """Deep search for vendor when extract_vendor returns Unbekannt.
    Searches entire OCR text for: websites, tax IDs, known vendor names, fuzzy matches.
    """
    text_lower = raw_text.lower()
    text_clean = re.sub(r"[^a-zäöüß0-9\s./@\-]", "", text_lower)

    # 1. Website detection (most reliable)
    for site, vendor in _WEBSITE_VENDOR_MAP.items():
        if site in text_lower:
            return vendor

    # 2. Tax ID detection (DE, FR, ES, IT, etc.)
    tax_patterns = [
        r"(DE\d{9})",                    # Germany USt-IdNr
        r"(FR\d{11})",                   # France TVA
        r"(ES[A-Z]\d{8})",              # Spain CIF
        r"(IT\d{11})",                   # Italy P.IVA
        r"(GB\d{9})",                    # UK VAT
        r"(AT\d{9})",                    # Austria
        r"(CH\d{9})",                    # Switzerland
    ]
    for pat in tax_patterns:
        tax_match = re.search(pat, raw_text)
        if tax_match:
            tax_id = tax_match.group(1)
            if tax_id in _TAX_ID_VENDOR_MAP:
                return _TAX_ID_VENDOR_MAP[tax_id]

    # 3. Known vendor name in full text (not just first lines)
    for vendor_key in sorted(VENDOR_CATEGORY_MAP.keys(), key=len, reverse=True):
        if len(vendor_key) >= 4 and vendor_key in text_clean:
            return vendor_key.upper() if len(vendor_key) <= 5 else vendor_key.title()

    # 4. OCR corrections on full text
    for wrong, correct in _VENDOR_OCR_CORRECTIONS.items():
        if len(wrong) >= 4 and wrong in text_clean:
            return correct

    # 5. Fuzzy matching — simple character similarity
    words = set(re.findall(r"[a-zäöüß]{4,15}", text_clean))
    known_vendors = list(VENDOR_CATEGORY_MAP.keys())
    for word in words:
        for known in known_vendors:
            if len(known) < 4:
                continue
            # Simple similarity: count matching chars
            if len(word) >= 4 and len(known) >= 4:
                common = sum(1 for a, b in zip(word, known) if a == b)
                similarity = common / max(len(word), len(known))
                if similarity >= 0.75:  # 75% match
                    return known.upper() if len(known) <= 5 else known.title()

    # 6. Look for company suffix patterns anywhere in text (international)
    company_match = re.search(
        r"([A-ZÄÖÜa-zäöüß][\w\s&\-'.]{2,40})\s*(?:GmbH|Co\.?\s?KG|AG|e\.K\.|OHG|UG|SE|Ltd\.?|Inc\.?|SAS|SARL|S\.A\.?|S\.L\.?|S\.R\.L\.?|Oy|AB|NV|BV|PLC|LLC|Corp\.?|Pty|A\.Ş\.|Ş[tT]i\.?|LTD\.?\s*ŞTİ)",
        raw_text
    )
    if company_match:
        name = company_match.group(1).strip()
        name = re.sub(r"[\s\-:,]+$", "", name).strip()
        if len(name) >= 3 and name.lower() not in ("die", "der", "das", "für", "und", "mit"):
            return name

    return "Unbekannt"


# ════════════════════════════════════════════════════════════════
# CATEGORY DETECTION
# ════════════════════════════════════════════════════════════════

def detect_category(vendor: str, raw_text: str) -> str:
    """Auto-detect invoice category from vendor name and content."""
    vendor_lower = vendor.lower()
    text_lower = raw_text.lower()

    # 1. Direct vendor match
    for key, cat in VENDOR_CATEGORY_MAP.items():
        if key in vendor_lower:
            return cat

    # 2. Scan full text for known vendor mentions
    for key, cat in VENDOR_CATEGORY_MAP.items():
        if len(key) >= 4 and key in text_lower:
            return cat

    # 3. Content-based heuristics
    fuel_keywords = ["liter", "diesel", "benzin", "super e", "tankstelle", "zapfsäule", "unleaded", "gasoil"]
    if any(k in text_lower for k in fuel_keywords):
        return "fuel"

    food_keywords = ["lebensmittel", "grocery", "bio ", "obst", "gemüse", "milch", "brot", "fleisch"]
    if any(k in text_lower for k in food_keywords):
        return "food"

    restaurant_keywords = ["restaurant", "café", "cafe", "bistro", "gaststätte", "speisen", "getränke", "trinkgeld", "tip", "bedienung"]
    if any(k in text_lower for k in restaurant_keywords):
        return "restaurant"

    office_keywords = ["büromaterial", "office", "druckerpatrone", "toner", "papier a4", "kopierpapier"]
    if any(k in text_lower for k in office_keywords):
        return "office"

    transport_keywords = ["fahrkarte", "ticket", "boarding", "flug", "flight", "bahn", "zug ", "train"]
    if any(k in text_lower for k in transport_keywords):
        return "transport"

    telecom_keywords = ["mobilfunk", "internet", "flatrate", "datenvolumen", "rufnummer"]
    if any(k in text_lower for k in telecom_keywords):
        return "telecom"

    return "other"


# ════════════════════════════════════════════════════════════════
# COUNTRY DETECTION
# ════════════════════════════════════════════════════════════════

def detect_country(raw_text: str) -> str:
    """Detect the country of origin from receipt text."""
    text_lower = raw_text.lower()

    scores: dict[str, int] = {}
    for country, indicators in COUNTRY_INDICATORS.items():
        score = sum(1 for ind in indicators if ind in text_lower)
        if score > 0:
            scores[country] = score

    if scores:
        return max(scores, key=scores.get)

    # Default to Germany
    return "DE"


# ════════════════════════════════════════════════════════════════
# DATE EXTRACTION
# ════════════════════════════════════════════════════════════════

_MONTH_MAP = {
    # Deutsch
    "jan": "01", "januar": "01",
    "feb": "02", "februar": "02",
    "mär": "03", "märz": "03",
    "apr": "04", "april": "04",
    "mai": "05",
    "jun": "06", "juni": "06",
    "jul": "07", "juli": "07",
    "aug": "08", "august": "08",
    "sep": "09", "september": "09",
    "okt": "10", "oktober": "10",
    "nov": "11", "november": "11",
    "dez": "12", "dezember": "12",
    # English
    "january": "01", "february": "02", "march": "03", "mar": "03",
    "april": "04", "may": "05", "june": "06", "july": "07",
    "august": "08", "october": "10", "oct": "10",
    "december": "12", "dec": "12",
    # Français
    "janvier": "01", "janv": "01",
    "février": "02", "fevrier": "02", "fév": "02", "fev": "02",
    "mars": "03",
    "avril": "04", "avr": "04",
    "mai": "05",
    "juin": "06",
    "juillet": "07", "juil": "07",
    "août": "08", "aout": "08",
    "septembre": "09", "sept": "09",
    "octobre": "10",
    "novembre": "11",
    "décembre": "12", "decembre": "12",
    # Türkçe
    "ocak": "01", "oca": "01",
    "şubat": "02", "subat": "02", "şub": "02", "sub": "02",
    "mart": "03",
    "nisan": "04", "nis": "04",
    "mayıs": "05", "mayis": "05",
    "haziran": "06", "haz": "06",
    "temmuz": "07", "tem": "07",
    "ağustos": "08", "agustos": "08", "ağu": "08", "agu": "08",
    "eylül": "09", "eylul": "09", "eyl": "09",
    "ekim": "10", "eki": "10",
    "kasım": "11", "kasim": "11", "kas": "11",
    "aralık": "12", "aralik": "12", "ara": "12",
    # Español
    "enero": "01", "ene": "01",
    "febrero": "02",
    "marzo": "03",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12", "dic": "12",
    # Italiano
    "gennaio": "01", "gen": "01",
    "febbraio": "02",
    "marzo": "03",
    "aprile": "04",
    "maggio": "05", "mag": "05",
    "giugno": "06", "giu": "06",
    "luglio": "07", "lug": "07",
    "settembre": "09", "set": "09",
    "ottobre": "10", "ott": "10",
    "dicembre": "12",
}


def extract_date(raw_text: str) -> str:
    """Extract date from OCR text, supporting multiple formats."""
    text = raw_text

    # 1. Try keyword-prefixed dates first (most reliable)
    keyword_match = re.search(
        r"(?:datum|date|le|fecha)\s*:?\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})",
        text, re.IGNORECASE
    )
    if keyword_match:
        d, m, y = keyword_match.group(1), keyword_match.group(2), keyword_match.group(3)
        if len(y) == 2:
            y = "20" + y
        result = _validate_date(y, m.zfill(2), d.zfill(2))
        if result:
            return result

    # 2. Try named month patterns (e.g., "15. März 2024", "16 mars 2026", "3 Ocak 2025")
    _month_names = sorted(_MONTH_MAP.keys(), key=len, reverse=True)
    _month_pattern = "|".join(re.escape(m) for m in _month_names)
    month_match = re.search(
        rf"(\d{{1,2}})\.?\s+({_month_pattern})\s+(\d{{4}})",
        text, re.IGNORECASE
    )
    if not month_match:
        # Also try: "mars 16, 2026" or "March 16 2026" (month first)
        month_match2 = re.search(
            rf"({_month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})",
            text, re.IGNORECASE
        )
        if month_match2:
            month_str = month_match2.group(1).lower()
            day = month_match2.group(2).zfill(2)
            year = month_match2.group(3)
            if month_str in _MONTH_MAP:
                result = _validate_date(year, _MONTH_MAP[month_str], day)
                if result:
                    return result
    if month_match:
        day = month_match.group(1).zfill(2)
        month_str = month_match.group(2).lower()
        year = month_match.group(3)
        if month_str in _MONTH_MAP:
            result = _validate_date(year, _MONTH_MAP[month_str], day)
            if result:
                return result
        # Fallback: startswith match for abbreviated forms
        for key, val in _MONTH_MAP.items():
            if month_str.startswith(key) or key.startswith(month_str):
                result = _validate_date(year, val, day)
                if result:
                    return result
                break

    # 3. DD.MM.YYYY (German standard)
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        result = _validate_date(m.group(3), m.group(2), m.group(1))
        if result:
            return result

    # 4. DD.MM.YY
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{2})\b", text)
    if m:
        result = _validate_date("20" + m.group(3), m.group(2), m.group(1))
        if result:
            return result

    # 5. YYYY-MM-DD (ISO)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        result = _validate_date(m.group(1), m.group(2), m.group(3))
        if result:
            return result

    # 6. DD/MM/YYYY
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        result = _validate_date(m.group(3), m.group(2), m.group(1))
        if result:
            return result

    # 7. DD/MM/YY
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})\b", text)
    if m:
        result = _validate_date("20" + m.group(3), m.group(2), m.group(1))
        if result:
            return result

    # 8. DD-MM-YYYY
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", text)
    if m:
        result = _validate_date(m.group(3), m.group(2), m.group(1))
        if result:
            return result

    return datetime.now().strftime("%Y-%m-%d")


def _validate_date(year: str, month: str, day: str) -> str | None:
    """Validate and return YYYY-MM-DD or None. Rejects unrealistic years."""
    try:
        dt = datetime(int(year), int(month), int(day))
        current_year = datetime.now().year
        if 2020 <= dt.year <= current_year + 1:
            return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    return None


# ════════════════════════════════════════════════════════════════
# TOTAL AMOUNT EXTRACTION
# ════════════════════════════════════════════════════════════════

_TOTAL_KEYWORDS_HIGH = [
    # Deutsch — highest priority (final totals on receipts)
    r"zu\s*zahlen", r"zahlbetrag", r"gesamtbetrag", r"endbetrag",
    r"rechnungsbetrag", r"rechnungssumme", r"gesamtsumme", r"endsumme",
    r"summe\s*brutto", r"brutto\s*gesamt", r"bruttobetrag", r"gesamtpreis",
    r"fälliger\s*betrag", r"gesamtbetrag\s*brutto",
    r"gesamtbetrag\s*inkl", r"summe\s*inkl",
    r"summe\s*eur", r"summe", r"s[uü]mme",  # "SUMME" alone = receipt total
    # English
    r"grand\s*total", r"total\s*amount", r"amount\s*due", r"balance\s*due",
    r"total\s*due", r"invoice\s*total", r"total\s*payable", r"amount\s*payable",
    r"sum\s*total", r"final\s*total", r"total\s*incl", r"total\s*inc\s*vat",
    r"amount\s*to\s*pay", r"pay\s*this\s*amount", r"bill\s*total",
    r"order\s*total", r"payment\s*due", r"net\s*total", r"gross\s*total",
    # Français
    r"montant\s*total", r"total\s*ttc", r"net\s*[àa]\s*payer",
    r"montant\s*ttc", r"somme\s*totale", r"total\s*[àa]\s*payer",
    r"montant\s*[àa]\s*payer", r"montant\s*d[ûu]", r"solde\s*[àa]\s*payer",
    r"total\s*g[ée]n[ée]ral",
    r"montant\s*r[ée]el", r"montant\s*net", r"montant\s*brut",
    r"montant\s*facture", r"montant\s*hors\s*taxe", r"montant\s*ht",
    r"prix\s*total", r"prix\s*[àa]\s*payer", r"prix\s*net",
    r"reste\s*d[ûu]", r"solde\s*d[ûu]",
    r"total\s*facture", r"total\s*net", r"total\s*brut",
    # Türkçe
    r"toplam\s*tutar", r"genel\s*toplam", r"[öo]denecek\s*tutar",
    r"toplam\s*fiyat", r"kdv\s*dahil\s*toplam", r"vergiler\s*dahil",
    r"net\s*toplam", r"fatura\s*toplam[ıi]", r"ara\s*toplam",
    # Español
    r"importe\s*total", r"total\s*a\s*pagar", r"monto\s*total",
    r"cantidad\s*total", r"suma\s*total", r"total\s*factura",
    r"importe\s*a\s*pagar", r"total\s*con\s*iva", r"saldo\s*a\s*pagar",
    # Italiano
    r"importo\s*totale", r"totale\s*fattura", r"totale\s*da\s*pagare",
    r"importo\s*da\s*pagare", r"totale\s*complessivo", r"somma\s*totale",
    r"totale\s*generale", r"netto\s*a\s*pagare", r"importo\s*dovuto",
    # Nederlands
    r"totaalbedrag", r"te\s*betalen", r"totaal\s*te\s*betalen",
    r"verschuldigd\s*bedrag", r"factuurtotaal", r"eindbedrag",
    r"totaal\s*incl", r"totaalprijs",
    # Português
    r"valor\s*total", r"total\s*a\s*pagar", r"montante\s*total",
    r"valor\s*a\s*pagar", r"total\s*da\s*fatura",
    # Polski
    r"do\s*zap[łl]aty", r"kwota\s*do\s*zap[łl]aty", r"razem\s*do\s*zap[łl]aty",
    r"suma\s*do\s*zap[łl]aty", r"warto[śs][ćc]\s*brutto", r"razem\s*brutto",
    r"og[óo][łl]em", r"nale[żz]no[śs][ćc]",
    # Русский
    r"итого", r"всего", r"сумма\s*к\s*оплате", r"итого\s*к\s*оплате",
    r"общая\s*сумма", r"к\s*оплате", r"итого\s*с\s*ндс",
    # العربية
    r"المبلغ\s*الإجمالي", r"الإجمالي", r"المجموع", r"المبلغ\s*المستحق",
]

_TOTAL_KEYWORDS_MED = [
    # Generic / multi-language
    r"zwischensumme", r"total", r"gesamt", r"betrag", r"brutto", r"netto",
    r"5umme", r"surnme", r"sumrne", r"ge5amt", r"t0tal", r"tota1",  # OCR misreads
    r"subtotal", r"sub\s*total", r"amount", r"sum", r"due", r"price",
    # Deutsch
    r"preis", r"steuerbetrag", r"teilbetrag", r"restbetrag",
    # English
    r"net\s*amount", r"gross\s*amount", r"tax\s*amount",
    # Français
    r"montant", r"prix", r"sous.total", r"reste\s*[àa]\s*payer",
    # Türkçe
    r"tutar", r"toplam", r"bakiye", r"[öo]deme", r"fiyat",
    r"net\s*tutar", r"iskonto",
    # Español
    r"importe", r"monto", r"cantidad", r"base\s*imponible",
    # Italiano
    r"importo", r"totale", r"imponibile", r"subtotale",
    # Nederlands
    r"totaal", r"bedrag", r"nettobedrag",
    # Polski
    r"razem", r"suma", r"[łl][aą]cznie", r"kwota",
    # Português
    r"valor", r"montante",
    # Русский
    r"сумма", r"всего", r"итого",
    # Currency / receipt abbreviations
    r"eur", r"usd", r"gbp", r"chf", r"try", r"pln",
    r"ttl", r"tot", r"amt", r"bal",
]


def extract_total(raw_text: str) -> float:
    """Extract total amount from OCR text."""
    text = normalize(raw_text)
    text = normalize_amount_text(text)

    # Try high-priority keywords first (word boundary to avoid partial matches)
    for kw in _TOTAL_KEYWORDS_HIGH:
        match = re.search(rf"(?<!\w){kw}\s*:?\s*(\d+\.\d{{2}})", text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if 0.01 <= val < 100000:
                return val

    # Try medium-priority keywords
    for kw in _TOTAL_KEYWORDS_MED:
        match = re.search(rf"(?<!\w){kw}\s*:?\s*(\d+\.\d{{2}})", text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if 0.01 <= val < 100000:
                return val

    # Try EUR-prefixed or suffixed amounts
    eur_match = re.search(r"EUR\s*(\d+\.\d{2})", text, re.IGNORECASE)
    if eur_match:
        val = float(eur_match.group(1))
        if 0.01 <= val < 100000:
            return val

    # Try € symbol patterns (€12.34 or 12.34€ or 12,34 € or 30 EUR)
    euro_patterns = [
        r"€\s*(\d+\.\d{2})",
        r"(\d+\.\d{2})\s*€",
        r"(\d+\.\d{2})\s*eur\b",
        r"(\d+\.\d{2})\s*tl\b",     # Türk Lirası
        r"€\s*(\d+)\b",             # €30 (integer)
        r"(\d+)\s*€",               # 30€
        r"(\d+)\s+eur\b",           # 30 EUR
        r"(\d+)\s+tl\b",            # 30 TL
    ]
    for pat in euro_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 0.01 <= val < 100000:
                return val

    # Fallback: largest reasonable amount on the receipt
    amounts = []
    for m in re.findall(r"(\d+\.\d{2})", text):
        val = float(m)
        if 0.01 <= val < 100000:
            amounts.append(val)

    if amounts:
        return max(amounts)

    # Last resort: integer amounts near currency keywords
    for m in re.findall(r"(?:montant|betrag|summe|total|amount)\s*(?:reel\s*)?(\d+)\s*(?:eur|€|tl|usd|\$)", text, re.IGNORECASE):
        val = float(m)
        if 1 <= val < 100000:
            return val

    return 0.0


# ════════════════════════════════════════════════════════════════
# VAT EXTRACTION & CALCULATION
# ════════════════════════════════════════════════════════════════

def extract_vat_info(raw_text: str, total: float, country: str) -> tuple[list[float], float]:
    """
    Extract VAT rates and calculate VAT amount.
    Returns (vat_rates, vat_amount).
    """
    text = normalize(raw_text)
    text = normalize_amount_text(text)

    # 1. Try to find explicit VAT amount on receipt
    vat_amount = _extract_explicit_vat_amount(text)

    # 2. Try to find explicit VAT rate
    vat_rates = _extract_vat_rates(text, country)

    # 3. If we have an explicit VAT amount, use it
    if vat_amount and vat_amount > 0:
        if total > 0 and vat_amount < total:
            if not vat_rates:
                implied_rate = round((vat_amount / (total - vat_amount)) * 100, 1)
                known = KNOWN_VAT_RATES.get(country, [])
                for kr in known:
                    if abs(implied_rate - kr) < 1.5:
                        vat_rates = [kr]
                        break
                if not vat_rates:
                    vat_rates = [implied_rate]
            return vat_rates, round(vat_amount, 2)

    # 4. If we found rates but no amount, calculate
    if vat_rates and total > 0:
        rate = vat_rates[0]
        amount = round(total * rate / (100 + rate), 2)
        return vat_rates, amount

    # 5. Country default
    default_rate = COUNTRY_VAT_DEFAULTS.get(country, 19.0)
    if total > 0:
        amount = round(total * default_rate / (100 + default_rate), 2)
        return [default_rate], amount

    return [default_rate], 0.0


def _extract_explicit_vat_amount(text: str) -> float | None:
    """Try to find an explicitly stated VAT/MwSt amount."""
    patterns = [
        r"(?:mwst|ust|mehrwertsteuer|umsatzsteuer)\s*(?:\d+\s*%\s*)?:?\s*(\d+\.\d{2})",
        r"(?:tva|taxe)\s*(?:\d+[\.,]\d+\s*%\s*)?:?\s*(\d+\.\d{2})",
        r"(?:vat|tax)\s*(?:\d+\s*%\s*)?:?\s*(\d+\.\d{2})",
        r"(?:steuer|imposta|iva)\s*:?\s*(\d+\.\d{2})",
        r"davon\s*mwst\s*:?\s*(\d+\.\d{2})",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _extract_vat_rates(text: str, country: str) -> list[float]:
    """Extract VAT percentage rates from text."""
    rates = set()
    known = KNOWN_VAT_RATES.get(country, [])

    # Find all percentage mentions
    for m in re.findall(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", text):
        val = float(m.replace(",", "."))
        if 0 < val <= 30:
            rates.add(val)

    # Look for MwSt/USt specific patterns
    for m in re.findall(r"(?:mwst|ust|tva|vat|iva|btw|kdv)\s*:?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%?", text, re.IGNORECASE):
        val = float(m.replace(",", "."))
        if 0 < val <= 30:
            rates.add(val)

    return sorted(rates, reverse=True)


# ════════════════════════════════════════════════════════════════
# INVOICE NUMBER EXTRACTION
# ════════════════════════════════════════════════════════════════

_INVOICE_NUMBER_PATTERNS = [
    # Standalone patterns with known prefixes (highest priority)
    (r"\b(RE-[\w\-]{4,25})\b", 0),
    (r"\b(INV-[\w\-]{4,25})\b", 0),
    (r"\b(RG-[\w\-]{4,25})\b", 0),
    (r"\b(FC-[\w\-]{4,25})\b", 0),
    # German patterns
    (r"(?:rechnungs?\.?\s*(?:nr|nummer|no)\.?|re\.?\s*nr\.?)\s*:?\s*([A-Z0-9][\w\-/]{2,25})", re.IGNORECASE),
    (r"(?:beleg\.?\s*(?:nr|nummer|no)\.?|beleg-nr\.?)\s*:?\s*([A-Z0-9][\w\-/]{2,25})", re.IGNORECASE),
    (r"(?:bon\.?\s*(?:nr|nummer)\.?|bon-nr\.?)\s*:?\s*(\d[\w\-/]{2,20})", re.IGNORECASE),
    (r"(?:quittungs?\.?\s*(?:nr|nummer)\.?|quittung\s*nr\.?)\s*:?\s*([A-Z0-9][\w\-/]{2,20})", re.IGNORECASE),
    # International patterns
    (r"(?:invoice\.?\s*(?:no|number|nr|#)\.?|inv[\.-])\s*:?\s*([A-Z0-9][\w\-/]{2,20})", re.IGNORECASE),
    (r"(?:receipt\.?\s*(?:no|number|#)\.?)\s*:?\s*(\d[\w\-/]{2,20})", re.IGNORECASE),
    (r"(?:facture\.?\s*(?:no|numéro|n°)\.?)\s*:?\s*([A-Z0-9][\w\-/]{2,20})", re.IGNORECASE),
    (r"(?:ticket\.?\s*(?:no|nr)\.?)\s*:?\s*(\d[\w\-/]{2,20})", re.IGNORECASE),
    # Generic document number
    (r"(?:dok(?:ument)?\.?\s*(?:nr|nummer)\.?|doc\.?\s*(?:no|#)\.?)\s*:?\s*([A-Z0-9][\w\-/]{2,20})", re.IGNORECASE),
    # Rechnung-Nr.: with colon (MediaMarkt style)
    (r"(?:rechnung-nr\.?)\s*:?\s*([A-Z0-9][\w\-/]{2,25})", re.IGNORECASE),
]


def extract_invoice_number(raw_text: str) -> str:
    """Extract invoice/receipt number."""
    for pattern, flags in _INVOICE_NUMBER_PATTERNS:
        match = re.search(pattern, raw_text, flags)
        if match:
            num = match.group(1).strip()
            if num and not re.match(r"^0+$", num) and len(num) <= 25:
                return num
    return ""


# ════════════════════════════════════════════════════════════════
# PAYMENT METHOD DETECTION
# ════════════════════════════════════════════════════════════════

_PAYMENT_PATTERNS: dict[str, list[str]] = {
    "card": [
        "karte", "card", "carte", "ec-karte", "ec karte", "girocard",
        "maestro", "debit", "kredit", "credit", "visa", "mastercard",
        "amex", "american express", "contactless", "kontaktlos", "nfc",
        "kartenzahlung", "elektronisch",
    ],
    "cash": [
        "bar ", "bargeld", "cash", "barzahlung", "gegeben", "rückgeld",
        "wechselgeld", "espèces",
    ],
    "transfer": [
        "überweisung", "transfer", "bank transfer", "virement",
        "sepa", "iban",
    ],
    "paypal": ["paypal"],
    "klarna": ["klarna"],
    "apple_pay": ["apple pay"],
    "google_pay": ["google pay"],
}


def detect_payment_method(raw_text: str) -> str:
    """Detect payment method from receipt text."""
    text_lower = raw_text.lower()

    for method, keywords in _PAYMENT_PATTERNS.items():
        for kw in keywords:
            if kw in text_lower:
                return method

    return ""


# ════════════════════════════════════════════════════════════════
# MAIN PARSER
# ════════════════════════════════════════════════════════════════

def parse_invoice(raw_text: str) -> dict:
    """
    Parse OCR text into structured invoice data.

    Returns dict with keys:
        total_amount, vat_amount, vat_rate, vendor, date,
        category, invoice_number, payment_method, country, raw_text
    """
    if not raw_text or not raw_text.strip():
        return {
            "total_amount": 0.0,
            "vat_amount": 0.0,
            "vat_rate": "0%",
            "vendor": "Unbekannt",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "category": "other",
            "invoice_number": "",
            "payment_method": "",
            "country": "DE",
            "raw_text": raw_text or "",
        }

    vendor = extract_vendor(raw_text)
    # If vendor not found, try deep search in full OCR text
    if vendor == "Unbekannt" or len(vendor) <= 2:
        deep_vendor = _deep_vendor_search(raw_text)
        if deep_vendor != "Unbekannt":
            vendor = deep_vendor
    country = detect_country(raw_text)
    category = detect_category(vendor, raw_text)
    date = extract_date(raw_text)
    total = extract_total(raw_text)
    vat_rates, vat_amount = extract_vat_info(raw_text, total, country)
    vat_rate_str = f"{vat_rates[0]}%" if vat_rates else "0%"
    invoice_number = extract_invoice_number(raw_text)
    payment_method = detect_payment_method(raw_text)

    return {
        "total_amount": total,
        "vat_amount": vat_amount,
        "vat_rate": vat_rate_str,
        "vendor": vendor,
        "date": date,
        "category": category,
        "invoice_number": invoice_number,
        "payment_method": payment_method,
        "country": country,
        "raw_text": raw_text,
    }
