from fastapi import APIRouter
from app.api.v1.endpoints import auth, invoices, chat

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(invoices.router)
api_router.include_router(chat.router)
