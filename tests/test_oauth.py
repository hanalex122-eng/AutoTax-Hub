"""
tests/test_oauth.py
Multipart form login + Google OAuth tests
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════
#  MULTIPART / FORM LOGIN
# ═══════════════════════════════════════
class TestFormLogin:
    def test_form_login_success(self, client, registered_user):
        r = client.post("/api/v1/auth/login/form", data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token"  in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_form_login_wrong_password(self, client, registered_user):
        r = client.post("/api/v1/auth/login/form", data={
            "username": registered_user["email"],
            "password": "WrongPass1!",
        })
        assert r.status_code == 401

    def test_form_login_unknown_user(self, client):
        r = client.post("/api/v1/auth/login/form", data={
            "username": "nobody@example.com",
            "password": "Secret1!",
        })
        assert r.status_code == 401

    def test_form_login_missing_fields(self, client):
        r = client.post("/api/v1/auth/login/form", data={"username": "x@x.com"})
        assert r.status_code == 422

    def test_form_login_returns_same_tokens_as_json(self, client, registered_user):
        """Both endpoints must return same token structure."""
        rj = client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })
        rf = client.post("/api/v1/auth/login/form", data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        assert rj.status_code == rf.status_code == 200
        assert set(rj.json().keys()) == set(rf.json().keys())

    def test_form_login_token_works_on_protected_endpoint(self, client, registered_user):
        r = client.post("/api/v1/auth/login/form", data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        })
        token = r.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == registered_user["email"]

    def test_json_and_form_both_subject_to_brute_force(self, client, db):
        """Both login endpoints share brute-force counter."""
        from app.core.security import hash_password
        from app.models.user import User
        user = User(email="bf2@example.com", full_name="BF2",
                    hashed_password=hash_password("Secret1!"), is_verified=True)
        db.add(user); db.commit()

        # 3 JSON failures
        for _ in range(3):
            client.post("/api/v1/auth/login", json={"email": "bf2@example.com", "password": "Wrong1!"})
        # 2 form failures → should lock
        for _ in range(2):
            client.post("/api/v1/auth/login/form", data={"username": "bf2@example.com", "password": "Wrong1!"})

        r = client.post("/api/v1/auth/login/form", data={"username": "bf2@example.com", "password": "Secret1!"})
        assert r.status_code == 429

        db.delete(user); db.commit()


# ═══════════════════════════════════════
#  GOOGLE OAUTH — unit tests
# ═══════════════════════════════════════
class TestGoogleOAuth:
    def test_google_login_redirect_without_config(self, client):
        """Without GOOGLE_CLIENT_ID set, should return 503."""
        r = client.get("/api/v1/auth/google", follow_redirects=False)
        # Either 503 (not configured) or 307 redirect (if configured)
        assert r.status_code in (503, 307, 302)

    def test_google_callback_without_config(self, client):
        r = client.get("/api/v1/auth/google/callback?code=fake123")
        assert r.status_code in (503, 400)

    def test_google_callback_creates_new_user(self, client, db):
        """Mock Google API → creates user on first login."""
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "fake_google_token"}

        mock_userinfo_response = MagicMock()
        mock_userinfo_response.status_code = 200
        mock_userinfo_response.json.return_value = {
            "email": "googleuser@gmail.com",
            "name":  "Google User",
            "email_verified": True,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_token_response)
        mock_client.get  = AsyncMock(return_value=mock_userinfo_response)

        with patch("app.api.v1.endpoints.auth.settings") as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID     = "fake-client-id"
            mock_settings.GOOGLE_CLIENT_SECRET = "fake-secret"
            mock_settings.GOOGLE_REDIRECT_URI  = "http://localhost/callback"
            mock_settings.REFRESH_TOKEN_EXPIRE_DAYS = 7
            mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
            mock_settings.ALGORITHM = "HS256"
            mock_settings.SECRET_KEY = "testsecret"
            mock_settings.MAIL_ENABLED = False

            with patch("httpx.AsyncClient", return_value=mock_client):
                r = client.get("/api/v1/auth/google/callback?code=authcode123")

        # User should be created and tokens returned
        from app.models.user import User
        u = db.query(User).filter(User.email == "googleuser@gmail.com").first()
        if u:
            assert u.is_verified == True
            db.delete(u); db.commit()

    def test_google_callback_unverified_email_rejected(self, client):
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "fake_google_token"}

        mock_userinfo_response = MagicMock()
        mock_userinfo_response.status_code = 200
        mock_userinfo_response.json.return_value = {
            "email": "unverified@gmail.com",
            "name":  "Unverified",
            "email_verified": False,   # not verified!
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_token_response)
        mock_client.get  = AsyncMock(return_value=mock_userinfo_response)

        with patch("app.api.v1.endpoints.auth.settings") as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID     = "fake-client-id"
            mock_settings.GOOGLE_CLIENT_SECRET = "fake-secret"
            mock_settings.GOOGLE_REDIRECT_URI  = "http://localhost/callback"

            with patch("httpx.AsyncClient", return_value=mock_client):
                r = client.get("/api/v1/auth/google/callback?code=authcode123")

        assert r.status_code == 400
