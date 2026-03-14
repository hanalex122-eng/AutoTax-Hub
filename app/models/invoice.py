"""
app/models/invoice.py
"""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    vendor         = Column(String(255), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    date           = Column(String(20),  nullable=True)
    total_amount   = Column(Float, default=0.0)
    vat_rate       = Column(String(20),  nullable=True)
    vat_amount     = Column(Float, default=0.0)
    currency       = Column(String(10),  default="EUR")
    category       = Column(String(100), nullable=True)
    payment_method = Column(String(100), nullable=True)
    qr_data        = Column(String(500), nullable=True)
    filename       = Column(String(255), nullable=True)
    ocr_mode       = Column(String(50),  default="standard")
    status         = Column(String(50),  default="processed")
    invoice_type   = Column(String(20),  default="expense")   # "income" | "expense"
    # ── Duplicate detection ──────────────────────────────────────────────────
    content_hash   = Column(String(64),  nullable=True, index=True)  # SHA-256 of file
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", backref="invoices")

    # Unique: same file hash per user → duplicate blocked
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_user_content_hash"),
    )
