"""
app/services/ai_category.py — AutoTax-HUB v5
AI-powered expense category detection using Claude
Falls back to keyword matching if no API key
"""
import logging
import re

logger = logging.getLogger("autotaxhub.ai_category")

# ── Keyword fallback map ─────────────────────────────────────────────────────
KEYWORD_MAP = {
    "food": [
        "netto", "rewe", "edeka", "aldi", "lidl", "kaufland", "penny",
        "norma", "lebensmittel", "supermarkt", "bäckerei", "metzgerei",
        "restaurant", "food", "grocery", "bakery",
    ],
    "restaurant": [
        "mc donalds", "mcdonalds", "burger king", "subway", "pizza",
        "kebab", "döner", "restaurant", "café", "cafe", "bistro",
        "gastronomie", "imbiss", "catering",
    ],
    "electronics": [
        "mediamarkt", "saturn", "amazon", "apple", "samsung", "sony",
        "electronics", "elektro", "computer", "laptop", "iphone", "ipad",
        "tablet", "software", "adobe", "microsoft", "zoom",
    ],
    "clothing": [
        "h&m", "zara", "c&a", "primark", "peek", "cloppenburg",
        "clothing", "fashion", "kleidung", "mode", "textil",
    ],
    "shoes": [
        "deichmann", "snipes", "adidas", "nike", "puma", "schuhe",
        "shoes", "sneaker", "schuhhaus",
    ],
    "fuel": [
        "aral", "shell", "total", "esso", "bp", "tankstelle",
        "benzin", "diesel", "fuel", "gas station", "kraftstoff",
    ],
    "drugstore": [
        "dm", "rossmann", "müller", "douglas", "apotheke", "pharmacy",
        "drogerie", "parfümerie", "kosmetik",
    ],
    "transport": [
        "db", "deutsche bahn", "bvg", "mvv", "hvv", "uber", "bolt",
        "taxi", "flixbus", "lufthansa", "ryanair", "easyjet",
        "transport", "bahn", "flug", "fahrt",
    ],
    "office": [
        "staples", "viking", "otto office", "büro", "office",
        "schreibwaren", "papier", "druckerpatronen",
    ],
    "telecom": [
        "telekom", "vodafone", "o2", "1&1", "congstar", "drillisch",
        "telefon", "internet", "mobilfunk", "handy",
    ],
}


def _keyword_category(vendor: str, text: str = "") -> str:
    """Fast keyword-based category detection"""
    combined = f"{vendor} {text}".lower()
    for category, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in combined:
                return category
    return "other"


async def detect_category(
    vendor: str,
    invoice_text: str = "",
    anthropic_api_key: str = "",
) -> str:
    """
    Detect expense category using AI or keyword fallback.
    Returns category string like 'food', 'electronics', etc.
    """
    if not vendor and not invoice_text:
        return "other"

    # Try AI if API key available
    if anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_api_key)
            prompt = (
                f"Classify this business expense into exactly ONE category.\n"
                f"Vendor: {vendor}\n"
                f"Invoice text snippet: {invoice_text[:200]}\n\n"
                f"Categories: food, restaurant, electronics, clothing, shoes, "
                f"fuel, drugstore, transport, office, telecom, other\n\n"
                f"Reply with ONLY the category name, nothing else."
            )
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=20,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip().lower()
            # Extract just the category word
            valid = {"food","restaurant","electronics","clothing","shoes",
                     "fuel","drugstore","transport","office","telecom","other"}
            # Find first valid category in response
            for word in re.split(r'\W+', raw):
                if word in valid:
                    return word
        except Exception as e:
            logger.warning(f"AI category failed, using keyword fallback: {e}")

    # Keyword fallback
    return _keyword_category(vendor, invoice_text)
