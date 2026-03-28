import os
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header

logger = logging.getLogger("autotax")

SECRET = os.getenv("JWT_SECRET", "")
if not SECRET:
    import secrets as _s
    SECRET = _s.token_urlsafe(32)
    logger.critical("JWT_SECRET is not set! Using random secret. Tokens will NOT survive restart. Set JWT_SECRET in environment variables!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60       # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 7          # 7 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: int, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "email": email, "exp": exp, "type": "access"}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: int, email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "email": email, "exp": exp, "type": "refresh"}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def create_token(user_id: int, email: str) -> str:
    """Backward compatible — returns access token."""
    return create_access_token(user_id, email)


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        data = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        if data.get("type") != expected_type:
            raise ValueError(f"Expected {expected_type} token")
        return data
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return decode_token(authorization[7:], expected_type="access")
