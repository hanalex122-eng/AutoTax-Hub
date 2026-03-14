"""
tests/test_invoices.py
Invoice endpoint tests: upload, list, get, delete, stats, multi-tenant isolation
"""
import io
import pytest


# ── Minimal valid PNG (1x1 pixel) ────────────────────────────────────────────
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# ── Fake PDF header ───────────────────────────────────────────────────────────
MINIMAL_PDF = b"%PDF-1.4\n%fake content for testing"


def upload_invoice(client, headers, content=None, filename="test.png"):
    file_content = content or MINIMAL_PNG
    return client.post(
        "/api/v1/invoices/upload",
        files={"file": (filename, io.BytesIO(file_content), "image/png")},
        headers=headers,
    )


# ═══════════════════════════════════════════════════════
#  AUTH GUARD
# ═══════════════════════════════════════════════════════
class TestInvoiceAuthGuard:
    def test_list_requires_auth(self, client):
        r = client.get("/api/v1/invoices")
        assert r.status_code == 401

    def test_upload_requires_auth(self, client):
        r = client.post("/api/v1/invoices/upload",
                        files={"file": ("test.png", io.BytesIO(MINIMAL_PNG), "image/png")})
        assert r.status_code == 401

    def test_stats_requires_auth(self, client):
        r = client.get("/api/v1/invoices/stats/summary")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════
#  FILE VALIDATION
# ═══════════════════════════════════════════════════════
class TestFileValidation:
    def test_reject_executable(self, client, auth_headers):
        evil = b"MZ\x90\x00this is an exe"  # Windows PE magic
        r = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("malware.exe", io.BytesIO(evil), "image/png")},
            headers=auth_headers,
        )
        assert r.status_code == 415

    def test_reject_extension_mismatch(self, client, auth_headers):
        """PNG content disguised as PDF."""
        r = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("invoice.pdf", io.BytesIO(MINIMAL_PNG), "application/pdf")},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_reject_empty_file(self, client, auth_headers):
        r = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
            headers=auth_headers,
        )
        assert r.status_code in (415, 422)

    def test_reject_oversized_file(self, client, auth_headers):
        big = b"\x89PNG\r\n\x1a\n" + b"A" * (11 * 1024 * 1024)  # 11MB
        r = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("big.png", io.BytesIO(big), "image/png")},
            headers=auth_headers,
        )
        assert r.status_code == 413


# ═══════════════════════════════════════════════════════
#  MULTI-TENANT ISOLATION
# ═══════════════════════════════════════════════════════
class TestMultiTenantIsolation:
    def _make_second_user(self, client, db):
        from app.core.security import hash_password
        from app.models.user import User
        user2 = User(email="user2@example.com", full_name="User Two",
                     hashed_password=hash_password("Second1!"), is_verified=True)
        db.add(user2); db.commit()
        r = client.post("/api/v1/auth/login", json={"email": "user2@example.com", "password": "Second1!"})
        token = r.json()["access_token"]
        return user2, {"Authorization": f"Bearer {token}"}

    def test_user_cannot_see_other_users_invoices(self, client, auth_headers, db):
        from app.models.invoice import Invoice
        # Create invoice directly for user 1
        from app.models.user import User
        u1 = db.query(User).filter(User.email == "test@example.com").first()
        if not u1:
            pytest.skip("test user not found")
        inv = Invoice(user_id=u1.id, vendor="Secret Vendor", total_amount=999.0, status="processed")
        db.add(inv); db.commit()

        user2, headers2 = self._make_second_user(client, db)

        r = client.get("/api/v1/invoices", headers=headers2)
        assert r.status_code == 200
        vendors = [i["vendor"] for i in r.json()["items"]]
        assert "Secret Vendor" not in vendors

        db.delete(inv); db.delete(user2); db.commit()

    def test_user_cannot_delete_other_users_invoice(self, client, auth_headers, db):
        from app.models.invoice import Invoice
        from app.models.user import User
        u1 = db.query(User).filter(User.email == "test@example.com").first()
        if not u1:
            pytest.skip("test user not found")
        inv = Invoice(user_id=u1.id, vendor="U1 Vendor", total_amount=50.0, status="processed")
        db.add(inv); db.commit()

        user2, headers2 = self._make_second_user(client, db)

        r = client.delete(f"/api/v1/invoices/{inv.id}", headers=headers2)
        assert r.status_code == 404   # must look like it doesn't exist

        db.delete(inv); db.delete(user2); db.commit()


# ═══════════════════════════════════════════════════════
#  INVOICE CRUD
# ═══════════════════════════════════════════════════════
class TestInvoiceCRUD:
    def _seed_invoice(self, db, user_email="test@example.com"):
        from app.models.invoice import Invoice
        from app.models.user import User
        u = db.query(User).filter(User.email == user_email).first()
        if not u:
            return None
        inv = Invoice(user_id=u.id, vendor="Test Vendor", total_amount=42.0,
                      vat_amount=6.72, status="processed", filename="test.png")
        db.add(inv); db.commit(); db.refresh(inv)
        return inv

    def test_list_invoices(self, client, auth_headers, db):
        inv = self._seed_invoice(db)
        r = client.get("/api/v1/invoices", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        if inv:
            db.delete(inv); db.commit()

    def test_get_invoice(self, client, auth_headers, db):
        inv = self._seed_invoice(db)
        if not inv:
            pytest.skip()
        r = client.get(f"/api/v1/invoices/{inv.id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["vendor"] == "Test Vendor"
        db.delete(inv); db.commit()

    def test_get_nonexistent_invoice(self, client, auth_headers):
        r = client.get("/api/v1/invoices/999999", headers=auth_headers)
        assert r.status_code == 404

    def test_delete_invoice(self, client, auth_headers, db):
        inv = self._seed_invoice(db)
        if not inv:
            pytest.skip()
        r = client.delete(f"/api/v1/invoices/{inv.id}", headers=auth_headers)
        assert r.status_code == 204
        r2 = client.get(f"/api/v1/invoices/{inv.id}", headers=auth_headers)
        assert r2.status_code == 404

    def test_stats_endpoint(self, client, auth_headers):
        r = client.get("/api/v1/invoices/stats/summary", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_invoices" in data
        assert "total_amount" in data
        assert "total_vat" in data
        assert "by_category" in data

    def test_list_pagination(self, client, auth_headers):
        r = client.get("/api/v1/invoices?skip=0&limit=5", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 5

    def test_list_limit_max(self, client, auth_headers):
        r = client.get("/api/v1/invoices?limit=200", headers=auth_headers)
        assert r.status_code == 422   # max is 100


# ═══════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════
class TestDashboard:
    def _seed_mixed(self, db, user_email="test@example.com"):
        from app.models.invoice import Invoice
        from app.models.user import User
        u = db.query(User).filter(User.email == user_email).first()
        if not u:
            return []
        inv1 = Invoice(user_id=u.id, vendor="Client A", total_amount=1000.0,
                       vat_amount=190.0, invoice_type="income", date="2026-01-15",
                       status="processed")
        inv2 = Invoice(user_id=u.id, vendor="Office Supply", total_amount=200.0,
                       vat_amount=38.0, invoice_type="expense", date="2026-01-20",
                       category="office", status="processed")
        inv3 = Invoice(user_id=u.id, vendor="Client B", total_amount=2000.0,
                       vat_amount=380.0, invoice_type="income", date="2026-02-10",
                       status="processed")
        db.add_all([inv1, inv2, inv3])
        db.commit()
        return [inv1, inv2, inv3]

    def test_dashboard_endpoint(self, client, auth_headers, db):
        invs = self._seed_mixed(db)
        r = client.get("/api/v1/invoices/dashboard", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_income" in data
        assert "total_expenses" in data
        assert "net_profit" in data
        assert "tax_estimate" in data
        assert "monthly_breakdown" in data
        assert "by_category" in data
        assert data["total_income"] >= 0
        assert data["total_expenses"] >= 0
        for inv in invs:
            db.delete(inv)
        db.commit()

    def test_dashboard_with_year_filter(self, client, auth_headers, db):
        invs = self._seed_mixed(db)
        r = client.get("/api/v1/invoices/dashboard?year=2026", headers=auth_headers)
        assert r.status_code == 200
        for inv in invs:
            db.delete(inv)
        db.commit()

    def test_dashboard_empty(self, client, auth_headers):
        r = client.get("/api/v1/invoices/dashboard?year=1999", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total_income"] == 0
        assert data["total_expenses"] == 0
        assert data["tax_estimate"] == 0


# ═══════════════════════════════════════════════════════
#  INVOICE UPDATE
# ═══════════════════════════════════════════════════════
class TestInvoiceUpdate:
    def _seed_invoice(self, db, user_email="test@example.com"):
        from app.models.invoice import Invoice
        from app.models.user import User
        u = db.query(User).filter(User.email == user_email).first()
        if not u:
            return None
        inv = Invoice(user_id=u.id, vendor="Old Vendor", total_amount=100.0,
                      vat_amount=19.0, invoice_type="expense", status="processed")
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv

    def test_update_vendor(self, client, auth_headers, db):
        inv = self._seed_invoice(db)
        if not inv:
            pytest.skip()
        r = client.put(f"/api/v1/invoices/{inv.id}", json={"vendor": "New Vendor"},
                       headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["vendor"] == "New Vendor"
        db.delete(inv)
        db.commit()

    def test_update_invoice_type(self, client, auth_headers, db):
        inv = self._seed_invoice(db)
        if not inv:
            pytest.skip()
        r = client.put(f"/api/v1/invoices/{inv.id}", json={"invoice_type": "income"},
                       headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["invoice_type"] == "income"
        db.delete(inv)
        db.commit()

    def test_update_invalid_type(self, client, auth_headers, db):
        inv = self._seed_invoice(db)
        if not inv:
            pytest.skip()
        r = client.put(f"/api/v1/invoices/{inv.id}", json={"invoice_type": "invalid"},
                       headers=auth_headers)
        assert r.status_code == 422
        db.delete(inv)
        db.commit()

    def test_update_nonexistent(self, client, auth_headers):
        r = client.put("/api/v1/invoices/999999", json={"vendor": "X"},
                       headers=auth_headers)
        assert r.status_code == 404
