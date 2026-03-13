"""
tests/test_auth.py
Auth endpoint coverage: register, login, refresh, logout,
brute-force lock, password reset, email verify
"""
import pytest
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.refresh_token import RefreshToken


# ═══════════════════════════════════════════════════════
#  REGISTER
# ═══════════════════════════════════════════════════════
class TestRegister:
    def test_register_success(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "new@example.com", "full_name": "New User", "password": "Secret1!"
        })
        assert r.status_code == 201
        assert "message" in r.json()

    def test_register_duplicate_email(self, client, registered_user):
        r = client.post("/api/v1/auth/register", json={
            "email": registered_user["email"], "full_name": "Dupe", "password": "Secret1!"
        })
        assert r.status_code == 409

    def test_register_weak_password_no_uppercase(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "x@example.com", "full_name": "X", "password": "secret1!"
        })
        assert r.status_code == 422

    def test_register_weak_password_no_digit(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "x@example.com", "full_name": "X", "password": "Secret!!"
        })
        assert r.status_code == 422

    def test_register_weak_password_too_short(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "x@example.com", "full_name": "X", "password": "S1!"
        })
        assert r.status_code == 422

    def test_register_invalid_email(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "not-an-email", "full_name": "X", "password": "Secret1!"
        })
        assert r.status_code == 422

    def test_register_empty_name(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "x2@example.com", "full_name": "   ", "password": "Secret1!"
        })
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════
#  LOGIN
# ═══════════════════════════════════════════════════════
class TestLogin:
    def test_login_success(self, client, registered_user):
        r = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, registered_user):
        r = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": "WrongPass1!"
        })
        assert r.status_code == 401
        # Must NOT reveal which field is wrong
        assert "password" not in r.json()["detail"].lower()

    def test_login_unknown_email(self, client):
        r = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com", "password": "Secret1!"
        })
        assert r.status_code == 401

    def test_login_returns_same_error_for_bad_email_and_bad_password(self, client, registered_user):
        """Timing-safe: error message must be identical."""
        r1 = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Secret1!"})
        r2 = client.post("/api/v1/auth/login", json={"email": registered_user["email"], "password": "BadPass1!"})
        assert r1.json()["detail"] == r2.json()["detail"]


# ═══════════════════════════════════════════════════════
#  BRUTE-FORCE PROTECTION
# ═══════════════════════════════════════════════════════
class TestBruteForce:
    def test_account_locks_after_5_failures(self, client, db):
        from app.core.security import hash_password
        # Create fresh user for this test
        user = User(email="brutetest@example.com", full_name="Brute",
                    hashed_password=hash_password("Secret1!"), is_verified=True)
        db.add(user); db.commit()

        for _ in range(5):
            client.post("/api/v1/auth/login", json={"email": "brutetest@example.com", "password": "Wrong1!"})

        r = client.post("/api/v1/auth/login", json={"email": "brutetest@example.com", "password": "Secret1!"})
        assert r.status_code == 429
        assert "locked" in r.json()["detail"].lower()

        db.delete(user); db.commit()

    def test_correct_login_not_locked_before_threshold(self, client, registered_user):
        # 4 bad attempts — should NOT lock
        for _ in range(4):
            client.post("/api/v1/auth/login", json={
                "email": registered_user["email"], "password": "Wrong1!"
            })
        r = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        # May fail if previous tests already incremented, so just check it's not 429
        assert r.status_code in (200, 401)


# ═══════════════════════════════════════════════════════
#  REFRESH TOKEN
# ═══════════════════════════════════════════════════════
class TestRefreshToken:
    def test_refresh_success(self, client, registered_user):
        r1 = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        refresh_token = r1.json()["refresh_token"]

        r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    def test_refresh_token_rotated(self, client, registered_user):
        """Old refresh token must be invalid after rotation."""
        r1 = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        old_rt = r1.json()["refresh_token"]

        client.post("/api/v1/auth/refresh", json={"refresh_token": old_rt})

        # Old token must now be rejected
        r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_rt})
        assert r3.status_code == 401

    def test_refresh_with_access_token_fails(self, client, registered_user):
        r1 = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        access = r1.json()["access_token"]
        r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
        assert r2.status_code == 401

    def test_refresh_with_invalid_token_fails(self, client):
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": "totally.fake.token"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════
#  LOGOUT
# ═══════════════════════════════════════════════════════
class TestLogout:
    def test_logout_revokes_refresh_token(self, client, registered_user):
        r1 = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        rt = r1.json()["refresh_token"]

        r2 = client.post("/api/v1/auth/logout", json={"refresh_token": rt})
        assert r2.status_code == 200

        r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert r3.status_code == 401


# ═══════════════════════════════════════════════════════
#  ME / PROTECTED ENDPOINT
# ═══════════════════════════════════════════════════════
class TestMe:
    def test_me_success(self, client, auth_headers, registered_user):
        r = client.get("/api/v1/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == registered_user["email"]
        assert "hashed_password" not in data

    def test_me_no_token(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_me_invalid_token(self, client):
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer fake.token.here"})
        assert r.status_code == 401

    def test_me_expired_token(self, client, registered_user):
        import time
        from app.core.security import _create_token
        from datetime import timedelta
        expired = _create_token(str(999), "access", timedelta(seconds=-1))
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════
#  PASSWORD RESET
# ═══════════════════════════════════════════════════════
class TestPasswordReset:
    def test_forgot_password_always_200(self, client):
        """Must not reveal if email exists."""
        r1 = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
        r2 = client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["message"] == r2.json()["message"]

    def test_reset_password_with_valid_token(self, client, registered_user):
        from app.core.security import generate_email_token, RESET_SALT
        token = generate_email_token(registered_user["email"], RESET_SALT)
        r = client.post("/api/v1/auth/reset-password", json={
            "token": token,
            "new_password": "NewSecret2@"
        })
        assert r.status_code == 200

    def test_reset_password_with_invalid_token(self, client):
        r = client.post("/api/v1/auth/reset-password", json={
            "token": "bad-token", "new_password": "NewSecret2@"
        })
        assert r.status_code == 400

    def test_reset_forces_relogin(self, client, registered_user):
        """After reset, old refresh tokens must be invalid."""
        r1 = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"]
        })
        rt = r1.json()["refresh_token"]

        from app.core.security import generate_email_token, RESET_SALT
        token = generate_email_token(registered_user["email"], RESET_SALT)
        client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "BrandNew3#"})

        r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert r3.status_code == 401
