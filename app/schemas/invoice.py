"""
app/schemas/invoice.py
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class InvoiceOut(BaseModel):
    id: int
    vendor: Optional[str]
    invoice_number: Optional[str]
    date: Optional[str]
    total_amount: float
    vat_rate: Optional[str]
    vat_amount: float
    currency: str
    category: Optional[str]
    payment_method: Optional[str]
    filename: Optional[str]
    ocr_mode: str
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[InvoiceOut]


class StatsResponse(BaseModel):
    total_invoices: int
    total_amount: float
    total_vat: float
    by_category: list[dict]
