import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import base64

import bcrypt
from fastapi import Depends, HTTPException, Header

SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
ALGORITHM = "HS256"
EXPIRE_HOURS = 48


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_token(user_id: int, email: str) -> str:
    header = _b64encode(json.dumps({"alg": ALGORITHM, "typ": "JWT"}).encode())
    exp = datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS)
    payload = _b64encode(json.dumps({"sub": user_id, "email": email, "exp": exp.timestamp()}).encode())
    sig = _b64encode(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict:
    try:
        header, payload, sig = token.split(".")
        expected = _b64encode(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad sig")
        data = json.loads(_b64decode(payload))
        if datetime.now(timezone.utc).timestamp() > data["exp"]:
            raise ValueError("expired")
        return data
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return decode_token(authorization[7:])
