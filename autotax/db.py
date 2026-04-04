import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from autotax.models import Base, Invoice, User, CashEntry, UserCompany, LlmUsage

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
        # Invoice table — file storage columns
        inv_cols = [c["name"] for c in insp.get_columns("invoices")]
        with engine.begin() as conn:
            if "file_data" not in inv_cols:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN file_data BYTEA"))
                logger.info("Added 'file_data' column to invoices")
            if "file_content_type" not in inv_cols:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN file_content_type VARCHAR"))
                logger.info("Added 'file_content_type' column to invoices")
        # --- ADDED START: soft delete columns ---
        inv_cols = [c["name"] for c in insp.get_columns("invoices")]
        with engine.begin() as conn:
            if "is_deleted" not in inv_cols:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
                logger.info("Added 'is_deleted' column to invoices")
            if "deleted_at" not in inv_cols:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN deleted_at TIMESTAMP"))
                logger.info("Added 'deleted_at' column to invoices")
        ce_cols = [c["name"] for c in insp.get_columns("cash_entries")]
        with engine.begin() as conn:
            if "is_deleted" not in ce_cols:
                conn.execute(text("ALTER TABLE cash_entries ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
                logger.info("Added 'is_deleted' column to cash_entries")
            if "deleted_at" not in ce_cols:
                conn.execute(text("ALTER TABLE cash_entries ADD COLUMN deleted_at TIMESTAMP"))
                logger.info("Added 'deleted_at' column to cash_entries")
        # --- ADDED END ---
        # --- ADDED START: company detail columns ---
        uc_cols = [c["name"] for c in insp.get_columns("user_companies")]
        with engine.begin() as conn:
            for col in ["iban", "tax_id", "address", "phone", "fax", "email", "website"]:
                if col not in uc_cols:
                    conn.execute(text(f"ALTER TABLE user_companies ADD COLUMN {col} VARCHAR"))
                    logger.info("Added '%s' column to user_companies", col)
        # --- ADDED END ---
    except Exception as e:
        logger.warning("Column migration skipped: %s", e)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_invoice(data: dict, user_id: int, filename: str = None, file_data: bytes = None, file_content_type: str = None) -> int:
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
            file_data=file_data,
            file_content_type=file_content_type,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice.id
    finally:
        db.close()
