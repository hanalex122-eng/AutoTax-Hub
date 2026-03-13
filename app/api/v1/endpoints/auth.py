"""
app/api/v1/endpoints/auth.py  — v4
POST /login       → JSON
POST /login/form  → multipart/form-data & x-www-form-urlencoded
GET  /google      → Google OAuth2 redirect
GET  /google/callback → Google OAuth2 callback
+ all v3 endpoints
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    RESET_SALT, VERIFY_SALT,
    create_access_token, create_refresh_token,
    decode_token, generate_email_token,
    hash_password, verify_email_token, verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest, LoginRequest, MessageResponse,
    RefreshRequest, RegisterRequest, ResetPasswordRequest,
    TokenResponse, UserOut, VerifyEmailRequest,
)
from app.services.email_service import send_password_reset_email, send_verification_email

router = APIRouter(prefix="/auth", tags=["Auth"])

MAX_FAILED_ATTEMPTS   = 5
LOCK_DURATION_MINUTES = 15
GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO  = "https://www.googleapis.com/oauth2/v3/userinfo"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _check_brute_force(user: User, db: Session) -> None:
    if user.locked_until and datetime.now(timezone.utc) < user.locked_until:
        mins = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
        raise HTTPException(status_code=429, detail=f"Account locked. Try again in {mins} minutes.")
    if user.locked_until and datetime.now(timezone.utc) >= user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

def _record_fail(user: User, db: Session) -> None:
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCK_DURATION_MINUTES)
    db.commit()

def _reset_fail(user: User, db: Session) -> None:
    if user.failed_login_attempts > 0:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()

def _store_refresh(user_id: int, token: str, request: Request, db: Session) -> None:
    active = db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False).count()
    if active >= 5:
        oldest = db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False).order_by(RefreshToken.created_at).first()
        if oldest:
            oldest.is_revoked = True
    rt = RefreshToken(
        user_id=user_id, token_hash=_token_hash(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("user-agent", "")[:500],
        ip_address=request.client.host if request.client else None,
    )
    db.add(rt); db.commit()

def _issue_tokens(user: User, request: Request, db: Session) -> TokenResponse:
    access  = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    _store_refresh(user.id, refresh, request, db)
    return TokenResponse(access_token=access, refresh_token=refresh)

def _authenticate(email: str, password: str, request: Request, db: Session) -> TokenResponse:
    _bad = HTTPException(status_code=401, detail="Invalid email or password")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise _bad
    _check_brute_force(user, db)
    if not verify_password(password, user.hashed_password):
        _record_fail(user, db)
        raise _bad
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if settings.MAIL_ENABLED and not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified. Check your inbox.")
    _reset_fail(user, db)
    return _issue_tokens(user, request, db)


# ═══════════════════════════════════════
#  REGISTER
# ═══════════════════════════════════════
@router.post("/register", response_model=MessageResponse, status_code=201)
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email, full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        is_verified=not settings.MAIL_ENABLED,
    )
    db.add(user); db.commit(); db.refresh(user)
    if settings.MAIL_ENABLED:
        token = generate_email_token(payload.email, VERIFY_SALT)
        await send_verification_email(payload.email, token)
        return {"message": "Account created. Please verify your email."}
    return {"message": "Account created successfully."}


# ═══════════════════════════════════════
#  LOGIN — JSON
# ═══════════════════════════════════════
@router.post("/login", response_model=TokenResponse, summary="Login (JSON)")
async def login_json(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    **JSON login** — Content-Type: application/json
    ```json
    { "email": "you@example.com", "password": "Secret1!" }
    ```
    """
    return _authenticate(payload.email, payload.password, request, db)


# ═══════════════════════════════════════
#  LOGIN — FORM DATA (multipart + urlencoded)
# ═══════════════════════════════════════
@router.post("/login/form", response_model=TokenResponse, summary="Login (Form / Swagger)")
async def login_form(
    request: Request,
    username: str = Form(..., description="Email address (OAuth2 standard naming)"),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    **Form login** — accepts:
    - `multipart/form-data` (HTML forms, mobile apps)
    - `application/x-www-form-urlencoded` (Swagger UI Authorize)

    `username` = email address (OAuth2 spec uses 'username').

    **Example with curl:**
    ```bash
    curl -X POST /api/v1/auth/login/form \\
      -F "username=you@example.com" \\
      -F "password=Secret1!"
    ```
    """
    return _authenticate(username, password, request, db)


# ═══════════════════════════════════════
#  VERIFY EMAIL
# ═══════════════════════════════════════
@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    email = verify_email_token(payload.token, VERIFY_SALT, settings.EMAIL_TOKEN_EXPIRE_HOURS * 3600)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        return {"message": "Email already verified"}
    user.is_verified = True
    db.commit()
    return {"message": "Email verified successfully"}


# ═══════════════════════════════════════
#  REFRESH + LOGOUT
# ═══════════════════════════════════════
@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    _invalid = HTTPException(status_code=401, detail="Invalid or expired refresh token")
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except (ValueError, Exception):
        raise _invalid
    rt = db.query(RefreshToken).filter(
        RefreshToken.token_hash == _token_hash(payload.refresh_token),
        RefreshToken.is_revoked == False,
    ).first()
    if not rt or rt.is_expired:
        raise _invalid
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise _invalid
    rt.is_revoked = True; db.commit()
    return _issue_tokens(user, request, db)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(RefreshToken.token_hash == _token_hash(payload.refresh_token)).first()
    if rt:
        rt.is_revoked = True; db.commit()
    return {"message": "Logged out successfully"}


# ═══════════════════════════════════════
#  FORGOT / RESET PASSWORD
# ═══════════════════════════════════════
@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user and user.is_active:
        token = generate_email_token(payload.email, RESET_SALT)
        await send_password_reset_email(payload.email, token)
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = verify_email_token(payload.token, RESET_SALT, settings.PASSWORD_RESET_EXPIRE_MINUTES * 60)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(payload.new_password)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"is_revoked": True})
    db.commit()
    return {"message": "Password reset successfully. Please log in."}


# ═══════════════════════════════════════
#  ME
# ═══════════════════════════════════════
@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


# ═══════════════════════════════════════
#  GOOGLE OAUTH2
# ═══════════════════════════════════════
@router.get("/google", summary="Google OAuth2 — Login with Google", response_class=RedirectResponse)
async def google_login():
    """
    Redirects user to Google's consent screen.
    After consent → Google calls back `/api/v1/auth/google/callback`.

    **Setup in Google Cloud Console:**
    1. APIs & Services → Credentials → OAuth 2.0 Client ID
    2. Authorized redirect URI: `https://yourdomain.com/api/v1/auth/google/callback`
    3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in .env
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID.")
    import urllib.parse
    params = {
        "client_id":     settings.GOOGLE_CLIENT_ID,
        "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "select_account",
    }
    return RedirectResponse(GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params))


@router.get("/google/callback", response_model=TokenResponse, summary="Google OAuth2 — Callback")
async def google_callback(code: str, request: Request, db: Session = Depends(get_db)):
    """
    Google sends `?code=...` here after user consents.
    Returns JWT tokens — same format as regular login.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        # Step 1: exchange code → access token
        tok = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        if tok.status_code != 200:
            raise HTTPException(status_code=400, detail="Google token exchange failed")
        google_token = tok.json().get("access_token")

        # Step 2: fetch user info
        ui = await client.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {google_token}"})
        if ui.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Google profile")
        info = ui.json()

    email     = info.get("email", "").lower().strip()
    full_name = info.get("name", "")
    verified  = info.get("email_verified", False)

    if not email or not verified:
        raise HTTPException(status_code=400, detail="Google account email not verified")

    # Step 3: find or create user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        import secrets as _s
        user = User(
            email=email, full_name=full_name,
            hashed_password=hash_password(_s.token_hex(32)),  # random — Google users login via OAuth only
            is_verified=True, is_active=True,
        )
        db.add(user); db.commit(); db.refresh(user)
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    else:
        if full_name and user.full_name != full_name:
            user.full_name = full_name; db.commit()

    return _issue_tokens(user, request, db)
