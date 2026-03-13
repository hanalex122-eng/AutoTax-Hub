"""
app/core/security.py — v5
Paseto v4.local (symmetric, AES-256-GCM + BLAKE2b)
replaces JWT entirely.

Why Paseto over JWT:
- No "alg:none" attack possible
- No RS256/HS256 confusion
- Encrypted payload (v4.local) — claims not readable without key
- Built-in expiration in spec
- Type-safe token purpose ("access" / "refresh")
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

import pyseto
from pyseto import Key
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer  = URLSafeTimedSerializer(settings.PASETO_SECRET_KEY)

# Paseto symmetric key (v4.local = AES-256-GCM encrypted)
_RAW_KEY = bytes.fromhex(settings.PASETO_SECRET_KEY) if len(settings.PASETO_SECRET_KEY) == 64 else settings.PASETO_SECRET_KEY.encode().ljust(32)[:32]
_PASETO_KEY = Key.new(version=4, purpose="local", key=_RAW_KEY)


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Paseto tokens ─────────────────────────────────────────────────────────────

def _create_paseto_token(subject: str, token_type: Literal["access", "refresh"], expires: timedelta) -> str:
    now    = datetime.now(timezone.utc)
    expire = now + expires
    payload = {
        "sub":  subject,
        "type": token_type,
        "iat":  now.isoformat(),
        "exp":  expire.isoformat(),
    }
    token = pyseto.encode(_PASETO_KEY, json.dumps(payload).encode())
    return token.decode() if isinstance(token, bytes) else token


def create_access_token(user_id: int) -> str:
    return _create_paseto_token(str(user_id), "access",
                                timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

def create_refresh_token(user_id: int) -> str:
    return _create_paseto_token(str(user_id), "refresh",
                                timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> int:
    """
    Decodes Paseto token. Raises ValueError on any failure.
    """
    try:
        decoded = pyseto.decode(_PASETO_KEY, token)
        payload = json.loads(decoded.payload)
    except Exception as e:
        raise ValueError(f"Invalid token: {e}")

    # Check expiry
    exp_str = payload.get("exp")
    if not exp_str:
        raise ValueError("Missing expiry")
    exp = datetime.fromisoformat(exp_str)
    if datetime.now(timezone.utc) > exp:
        raise ValueError("Token expired")

    # Check type
    if payload.get("type") != expected_type:
        raise ValueError(f"Wrong token type: expected {expected_type}")

    sub = payload.get("sub")
    if not sub:
        raise ValueError("Missing subject")
    return int(sub)


# ── Email / Password-reset tokens ─────────────────────────────────────────────

def generate_email_token(email: str, salt: str) -> str:
    return _serializer.dumps(email, salt=salt)

def verify_email_token(token: str, salt: str, max_age_seconds: int) -> str | None:
    try:
        return _serializer.loads(token, salt=salt, max_age=max_age_seconds)
    except (SignatureExpired, BadSignature):
        return None

VERIFY_SALT = "email-verification"
RESET_SALT  = "password-reset"
