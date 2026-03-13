"""
app/core/config.py — v5
"""
from pydantic_settings import BaseSettings
import secrets


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_TITLE: str = "AutoTax-HUB API"
    APP_VERSION: str = "5.0.0"

    # ── Database ───────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./autotaxhub.db"

    # ── Paseto v4 local (symmetric) ────────────────────────
    # Generate: python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; import base64; k=Ed25519PrivateKey.generate(); print(base64.b64encode(k.private_bytes_raw()).decode())"
    # OR for local symmetric: python -c "import secrets; print(secrets.token_hex(32))"
    PASETO_SECRET_KEY: str = secrets.token_hex(32)   # 32-byte hex → 256-bit
    PASETO_VERSION: str = "v4"                        # v4.local (symmetric AES-256-GCM)

    # Token lifetimes
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Email tokens ───────────────────────────────────────
    EMAIL_TOKEN_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # ── CORS ──────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── Rate Limiting ─────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT: str = "10/minute"    # stricter for auth endpoints

    # ── Email ─────────────────────────────────────────────
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@autotaxhub.com"
    MAIL_FROM_NAME: str = "AutoTax-HUB"
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_PORT: int = 587
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    MAIL_ENABLED: bool = False

    # ── Frontend ──────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Google OAuth2 ─────────────────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── File upload ───────────────────────────────────────
    MAX_UPLOAD_MB: int = 10
    UPLOAD_CHUNK_SIZE: int = 65536          # 64KB streaming chunks
    ALLOWED_MIME_TYPES: list[str] = [
        "application/pdf",
        "image/png", "image/jpeg", "image/webp", "image/tiff",
    ]

    # ── AI Chat ───────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""             # set to enable AI chat
    AI_CHAT_MODEL: str = "claude-haiku-4-5-20251001"
    AI_CHAT_MAX_TOKENS: int = 1024
    AI_CHAT_SYSTEM_PROMPT: str = (
        "You are AutoTax-HUB's AI assistant. "
        "You help users understand their invoices, VAT, tax categories, "
        "and accounting questions. Be concise and professional. "
        "If asked about specific invoice data, say you can see their dashboard data."
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
