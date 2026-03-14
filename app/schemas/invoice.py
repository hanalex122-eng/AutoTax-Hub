"""
app/schemas/invoice.py — v5.1
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
    invoice_type: str = "expense"
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


class DashboardResponse(BaseModel):
    total_income: float
    total_expenses: float
    net_profit: float
    tax_estimate: float
    tax_rate_applied: float
    total_vat_paid: float
    total_vat_collected: float
    vat_balance: float
    monthly_breakdown: list[dict]
    by_category: list[dict]
    invoice_count: int
    expense_count: int
    income_count: int


class InvoiceUpdateRequest(BaseModel):
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    total_amount: Optional[float] = None
    vat_rate: Optional[str] = None
    vat_amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    invoice_type: Optional[str] = None
