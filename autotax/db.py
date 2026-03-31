import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from autotax.models import Base, Invoice, User, CashEntry, UserCompany

logger = logging.getLogger("autotax")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///autotax.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}
else:
    engine_args["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    db_type = "PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite"
    logger.info("Database: %s", db_type)
    if db_type == "SQLite":
        logger.warning("Using SQLite fallback — set DATABASE_URL for production")
    Base.metadata.create_all(bind=engine)
    # Add missing columns to existing tables (safe migration)
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    try:
        user_cols = [c["name"] for c in insp.get_columns("users")]
        with engine.begin() as conn:
            if "plan" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN plan VARCHAR DEFAULT 'free'"))
                logger.info("Added 'plan' column to users")
            if "stripe_customer_id" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR"))
                logger.info("Added 'stripe_customer_id' column to users")
            if "registered_at" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN registered_at TIMESTAMP"))
                logger.info("Added 'registered_at' column to users")
    except Exception as e:
        logger.warning("Column migration skipped: %s", e)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_invoice(data: dict, user_id: int, filename: str = None) -> int:
    db = SessionLocal()
    try:
        invoice = Invoice(
            user_id=user_id,
            filename=filename,
            vendor=data.get("vendor") or "Unbekannt",
            total_amount=data.get("total_amount") or 0.0,
            vat_amount=data.get("vat_amount") or 0.0,
            vat_rate=data.get("vat_rate") or "0%",
            date=data.get("date") or "",
            raw_text=data.get("raw_text", ""),
            invoice_type=data.get("invoice_type") or "expense",
            invoice_number=data.get("invoice_number") or "",
            payment_method=data.get("payment_method") or "",
            category=data.get("category") or "other",
            processed=True if data.get("total_amount") else False,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice.id
    finally:
        db.close()
