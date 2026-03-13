# AutoTax-HUB v3 — Production-Ready SaaS Backend

## 🔐 Security Checklist

| Feature | Status |
|---------|--------|
| JWT Access Token (30 min) | ✅ |
| JWT Refresh Token (7 days) | ✅ |
| **Refresh token stored in DB** (revocable) | ✅ |
| **Token rotation** on every refresh | ✅ |
| Bcrypt password hashing | ✅ |
| **Brute-force lock** (5 attempts → 15 min) | ✅ |
| **Email verification** | ✅ |
| **Password reset** (time-limited token) | ✅ |
| **Logout revokes token** | ✅ |
| Multi-tenant isolation | ✅ |
| Rate limiting (60 req/min) | ✅ |
| **File magic-bytes validation** | ✅ |
| **Extension/content mismatch check** | ✅ |
| CORS whitelist | ✅ |
| Generic error messages (no user enumeration) | ✅ |
| Production Swagger hidden | ✅ |

## 🧪 Test Suite — 63 Tests

```
tests/test_auth.py       — 26 tests  (register, login, brute-force, refresh, logout, password reset)
tests/test_invoices.py   — 16 tests  (CRUD, auth guards, multi-tenant, file validation)
tests/test_security.py   — 18 tests  (JWT, bcrypt, email tokens, file validator)
tests/test_health.py     —  3 tests  (health, 404)
```

Run:
```bash
pytest                    # all tests
pytest --cov=app          # with coverage
pytest tests/test_auth.py # single file
```

## 🚀 Quick Start

```bash
cp .env.example .env
# Fill in SECRET_KEY and DATABASE_URL
pip install -r requirements.txt
uvicorn main:app --reload
```

## 📡 API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | /api/v1/auth/register | ❌ | Register |
| POST | /api/v1/auth/verify-email | ❌ | Verify email |
| POST | /api/v1/auth/login | ❌ | Login → tokens |
| POST | /api/v1/auth/refresh | ❌ | Rotate tokens |
| POST | /api/v1/auth/logout | ❌ | Revoke token |
| POST | /api/v1/auth/forgot-password | ❌ | Send reset email |
| POST | /api/v1/auth/reset-password | ❌ | Set new password |
| GET  | /api/v1/auth/me | ✅ | Current user |
| POST | /api/v1/invoices/upload | ✅ | Upload & OCR |
| GET  | /api/v1/invoices | ✅ | List (paginated) |
| GET  | /api/v1/invoices/{id} | ✅ | Detail |
| DELETE | /api/v1/invoices/{id} | ✅ | Delete |
| GET  | /api/v1/invoices/stats/summary | ✅ | Dashboard stats |
