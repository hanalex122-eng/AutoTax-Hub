from fastapi import APIRouter
from app.api.v1.endpoints import auth, invoices, chat, export, system, tax_forms

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(invoices.router)
api_router.include_router(chat.router)
api_router.include_router(export.router)
api_router.include_router(system.router)
api_router.include_router(tax_forms.router)
