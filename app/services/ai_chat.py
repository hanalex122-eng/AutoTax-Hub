"""
app/services/ai_chat.py
AI chat service — Anthropic Claude integration
Provides invoice-aware context: injects user's recent stats into system prompt
"""
import logging
from typing import AsyncIterator

from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.chat import ChatMessage
from app.models.invoice import Invoice
from app.models.user import User

logger = logging.getLogger("autotaxhub.chat")

MAX_HISTORY_MESSAGES = 20    # last N messages sent as context
MAX_MESSAGE_LENGTH   = 2000  # user input cap


def _build_context_prompt(user: User, db: Session) -> str:
    """
    Inject user's invoice stats into system prompt.
    AI can answer questions like 'how much did I spend last month?'
    """
    from sqlalchemy import func
    base = db.query(Invoice).filter(Invoice.user_id == user.id)
    total_inv  = base.count()
    total_amt  = base.with_entities(func.sum(Invoice.total_amount)).scalar() or 0
    total_vat  = base.with_entities(func.sum(Invoice.vat_amount)).scalar() or 0
    by_cat     = base.with_entities(
        Invoice.category,
        func.count(Invoice.id).label("count"),
        func.sum(Invoice.total_amount).label("total"),
    ).group_by(Invoice.category).limit(10).all()

    cat_lines = "\n".join(
        f"  - {r.category or 'Uncategorized'}: {r.count} invoices, €{r.total or 0:.2f}"
        for r in by_cat
    ) or "  (no invoices yet)"

    return (
        f"{settings.AI_CHAT_SYSTEM_PROMPT}\n\n"
        f"=== USER CONTEXT ===\n"
        f"User: {user.full_name} ({user.email})\n"
        f"Total invoices: {total_inv}\n"
        f"Total amount:   €{total_amt:.2f}\n"
        f"Total VAT:      €{total_vat:.2f}\n"
        f"By category:\n{cat_lines}\n"
        f"==================="
    )


def _get_history(user_id: int, db: Session) -> list[dict]:
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(msgs)]


def _save_message(user_id: int, role: str, content: str, db: Session) -> ChatMessage:
    msg = ChatMessage(user_id=user_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


async def chat(user_message: str, user: User, db: Session) -> tuple[str, int]:
    """
    Send message, get AI reply. Returns (reply_text, saved_message_id).
    Falls back to rule-based replies if Anthropic key not set.
    """
    # Input validation
    user_message = user_message.strip()
    if not user_message:
        return "Please enter a message.", 0
    if len(user_message) > MAX_MESSAGE_LENGTH:
        user_message = user_message[:MAX_MESSAGE_LENGTH]

    # Save user message
    _save_message(user.id, "user", user_message, db)

    # Fallback if no API key
    if not settings.ANTHROPIC_API_KEY:
        reply = _fallback_reply(user_message)
        saved = _save_message(user.id, "assistant", reply, db)
        return reply, saved.id

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        system_prompt = _build_context_prompt(user, db)
        history       = _get_history(user.id, db)

        # Add current message to history
        messages = history + [{"role": "user", "content": user_message}]

        response = client.messages.create(
            model=settings.AI_CHAT_MODEL,
            max_tokens=settings.AI_CHAT_MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text

    except ImportError:
        logger.warning("anthropic package not installed — using fallback")
        reply = _fallback_reply(user_message)
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        reply = "I'm having trouble connecting right now. Please try again in a moment."

    saved = _save_message(user.id, "assistant", reply, db)
    return reply, saved.id


def _fallback_reply(message: str) -> str:
    """Rule-based fallback when AI is unavailable."""
    msg = message.lower()
    if any(w in msg for w in ["vat", "mwst", "kdv", "tax"]):
        return (
            "VAT (Value Added Tax) is automatically extracted from your invoices. "
            "You can see your total VAT in the Dashboard stats. "
            "Standard EU VAT rates: DE 19%, FR 20%, IT 22%, ES 21%."
        )
    if any(w in msg for w in ["how", "help", "what", "?", "explain"]):
        return (
            "I'm your AutoTax-HUB assistant! I can help you with:\n"
            "• Understanding your invoice data\n"
            "• VAT and tax questions\n"
            "• Invoice categories\n"
            "• Export and accounting tips\n\n"
            "To enable full AI: set ANTHROPIC_API_KEY in your .env file."
        )
    if any(w in msg for w in ["total", "spend", "amount", "cost", "euro", "€"]):
        return (
            "Check your Dashboard for total spending by month and category. "
            "The Stats panel shows total invoices, total amount, and total VAT."
        )
    return (
        "Thanks for your message! For full AI-powered answers, "
        "set your ANTHROPIC_API_KEY in the .env file. "
        "I can answer questions about your invoices, VAT, and accounting."
    )
