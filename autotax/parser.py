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
    "lödl": "LIDL", "lōdl": "LIDL", "l1dl": "LIDL", "lidl": "LIDL",
    "lldi": "LIDL", "lid1": "LIDL", "iidl": "LIDL",
    "aldl": "ALDI", "a1di": "ALDI", "aldi": "ALDI", "aidi": "ALDI",
    "rewe": "REWE", "rew3": "REWE", "r3we": "REWE",
    "edeka": "EDEKA", "edek4": "EDEKA", "3deka": "EDEKA",
    "penny": "PENNY", "p3nny": "PENNY",
    "netto": "NETTO", "n3tto": "NETTO",
    "kaufland": "KAUFLAND", "kauf1and": "KAUFLAND",
    "amazon": "AMAZON", "amaz0n": "AMAZON",
    "shell": "SHELL", "sh3ll": "SHELL",
    "aral": "ARAL", "ara1": "ARAL",
    "starbucks": "STARBUCKS", "starbuck5": "STARBUCKS",
    "mcdonald": "MCDONALDS", "mcdonalds": "MCDONALDS", "mcdona1ds": "MCDONALDS",
    "dm": "DM", "rossmann": "ROSSMANN", "mueller": "MÜLLER", "müller": "MÜLLER",
}


def _clean_vendor_name(name: str) -> str:
    """Clean up vendor name: remove trailing punctuation, asterisks, OCR corrections."""
    name = re.sub(r"[*#]+", "", name).strip()
    name = re.sub(r"[\s\-:,]+$", "", name).strip()
    # OCR correction: check if cleaned name matches a known misread
    name_lower = re.sub(r"[^a-zäöüß0-9]", "", name.lower())
    for wrong, correct in _VENDOR_OCR_CORRECTIONS.items():
        if wrong in name_lower:
            return correct
    # Title-case if all upper
    if name == name.upper() and len(name) > 3:
        name = name.title()
    return name if name else "Unbekannt"


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
    r"zu\s*zahlen",
    r"zahlbetrag",
    r"gesamtbetrag",
    r"endbetrag",
    r"total\s*ttc",
    r"rechnungsbetrag",
    r"summe\s*brutto",
    r"brutto\s*gesamt",
    r"toplam\s*tutar",       # Türkçe
    r"genel\s*toplam",       # Türkçe
    r"ödenecek\s*tutar",     # Türkçe
    r"net\s*total",
    r"grand\s*total",
    r"balance\s*due",
    r"total\s*a\s*payer",    # Français
    r"importe\s*total",      # Español
]

_TOTAL_KEYWORDS_MED = [
    r"total",
    r"summe",
    r"gesamt",
    r"betrag",
    r"brutto",
    r"montant",
    r"amount\s*due",
    r"amount",
    r"tutar",                # Türkçe
    r"toplam",               # Türkçe
    r"sum",
    r"netto",
    r"subtotal",
    r"sub\s*total",
    r"net\s*amount",
    r"due",
    r"price",
    r"preis",                # Deutsch
    r"prix",                 # Français
    r"importo",              # Italiano
]


def extract_total(raw_text: str) -> float:
    """Extract total amount from OCR text."""
    text = normalize(raw_text)
    text = normalize_amount_text(text)

    # Try high-priority keywords first
    for kw in _TOTAL_KEYWORDS_HIGH:
        match = re.search(rf"{kw}\s*:?\s*(\d+\.\d{{2}})", text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if 0.01 <= val < 100000:
                return val

    # Try medium-priority keywords
    for kw in _TOTAL_KEYWORDS_MED:
        match = re.search(rf"{kw}\s*:?\s*(\d+\.\d{{2}})", text, re.IGNORECASE)
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

    # Try € symbol patterns (€12.34 or 12.34€ or 12,34 €)
    euro_patterns = [
        r"€\s*(\d+\.\d{2})",
        r"(\d+\.\d{2})\s*€",
        r"(\d+\.\d{2})\s*eur\b",
        r"(\d+\.\d{2})\s*tl\b",     # Türk Lirası
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
        if known and val in known:
            rates.add(val)
        elif 2 <= val <= 27:
            rates.add(val)

    # Look for MwSt/USt specific patterns
    for m in re.findall(r"(?:mwst|ust|tva|vat|iva|btw)\s*:?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%?", text, re.IGNORECASE):
        val = float(m.replace(",", "."))
        if 2 <= val <= 27:
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
