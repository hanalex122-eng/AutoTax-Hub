from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, Text, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=True)
    vendor = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True)
    invoice_type = Column(String, default="expense")
    total_amount = Column(Float, nullable=True)
    vat_amount = Column(Float, nullable=True)
    vat_rate = Column(String, nullable=True)
    date = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    category = Column(String, nullable=True)
    processed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CashEntry(Base):
    __tablename__ = "cash_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    description = Column(String, nullable=False)
    vendor = Column(String, nullable=True)
    gross_amount = Column(Float, nullable=True)
    vat_amount = Column(Float, nullable=True)
    vat_rate = Column(String, nullable=True)
    entry_type = Column(String, nullable=False)
    category = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    reference = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_reconciled = Column(Boolean, default=False)
    invoice_id = Column(Integer, nullable=True)
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
