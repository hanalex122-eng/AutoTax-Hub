# AutoTax-HUB v5.2 — Production-Ready SaaS Backend

Multi-country tax & invoice management API with AI, multi-currency, and multi-language support.

## New in v5.2

- Multi-Currency: 17 currencies with conversion (EUR, USD, GBP, TRY, CHF, etc.)
- Multi-Language: 8 languages (DE, EN, TR, FR, ES, IT, AR, ZH)
- Flexible Tax Engine: Income tax for 11 countries (DE, AT, TR, FR, ES, IT, GB, CH, US, NL, PL)
- VAT rates for 27 countries
- Dashboard with income/expense/tax estimate
- Invoice update (PUT) endpoint
- Income vs Expense tracking
- DATEV SKR03 export (improved)
- JSON export

## Security

| Feature | Status |
|---------|--------|
| Paseto v4 encrypted tokens | Done |
| Refresh token rotation + DB revocation | Done |
| Bcrypt password hashing | Done |
| Brute-force lock (5 attempts, 15 min) | Done |
| Email verification + password reset | Done |
| Google OAuth2 | Done |
| Multi-tenant isolation | Done |
| Rate limiting | Done |
| File magic-bytes + extension validation | Done |
| CORS whitelist | Done |

## Quick Start

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload
```

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/auth/register | Register |
| POST | /api/v1/auth/login | Login (JSON) |
| POST | /api/v1/auth/login/form | Login (form/Swagger) |
| POST | /api/v1/auth/refresh | Rotate tokens |
| POST | /api/v1/auth/logout | Revoke token |
| POST | /api/v1/auth/forgot-password | Send reset email |
| POST | /api/v1/auth/reset-password | Set new password |
| GET | /api/v1/auth/me | Current user |
| GET | /api/v1/auth/google | Google OAuth2 |

### Invoices
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/invoices/upload | Upload single invoice |
| POST | /api/v1/invoices/batch | Batch upload (max 20) |
| GET | /api/v1/invoices | List (paginated, filterable) |
| GET | /api/v1/invoices/stats/summary | Stats summary |
| GET | /api/v1/invoices/dashboard | Full dashboard (multi-currency, multi-country tax) |
| GET | /api/v1/invoices/{id} | Get invoice |
| PUT | /api/v1/invoices/{id} | Update invoice |
| DELETE | /api/v1/invoices/{id} | Delete invoice |

### Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/export/csv | CSV export |
| GET | /api/v1/export/datev | DATEV format (SKR03) |
| GET | /api/v1/export/excel | Excel CSV (BOM) |
| GET | /api/v1/export/json | JSON export |

### System (public)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/v1/system/currencies | List all currencies |
| GET | /api/v1/system/currencies/{code} | Currency detail |
| GET | /api/v1/system/currencies/convert/{from}/{to} | Convert amount |
| GET | /api/v1/system/languages | List all languages |
| GET | /api/v1/system/vat-rates | VAT rates (27 countries) |
| GET | /api/v1/system/vat-rates/{country} | VAT detail |
| GET | /api/v1/system/tax-countries | Tax-supported countries |
| GET | /api/v1/system/tax-estimate | Estimate income tax |

### AI Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/chat | Send message |
| GET | /api/v1/chat/history | Chat history |
| DELETE | /api/v1/chat | Clear history |
| WS | /api/v1/chat/ws | WebSocket chat |

## Testing

```bash
pytest
pytest --cov=app
```

## Deploy (Railway)

1. Push to GitHub
2. Connect Railway to your repo
3. Set env vars: DATABASE_URL, PASETO_SECRET_KEY, APP_ENV=production
4. Deploy
