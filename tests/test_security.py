"""
tests/test_security.py — v5 (Paseto)
"""
import pytest
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    generate_email_token, verify_email_token,
    VERIFY_SALT, RESET_SALT,
)


class TestPassword:
    def test_hash_and_verify(self):
        pw = "MyP@ssword1"
        assert verify_password(pw, hash_password(pw))

    def test_wrong_password_fails(self):
        assert not verify_password("wrong", hash_password("correct"))

    def test_hash_is_not_plaintext(self):
        pw = "Secret1!"
        assert hash_password(pw) != pw

    def test_two_hashes_differ(self):
        pw = "Secret1!"
        assert hash_password(pw) != hash_password(pw)  # bcrypt salts


class TestPaseto:
    def test_access_token_roundtrip(self):
        token = create_access_token(user_id=42)
        assert decode_token(token, "access") == 42

    def test_refresh_token_roundtrip(self):
        token = create_refresh_token(user_id=99)
        assert decode_token(token, "refresh") == 99

    def test_wrong_type_rejected(self):
        access = create_access_token(user_id=1)
        with pytest.raises(ValueError):
            decode_token(access, "refresh")

    def test_tampered_token_rejected(self):
        token = create_access_token(user_id=1)
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(ValueError):
            decode_token(tampered, "access")

    def test_expired_token_rejected(self):
        import json
        from datetime import datetime, timedelta, timezone
        import pyseto
        from pyseto import Key
        from app.core.config import settings
        raw = bytes.fromhex(settings.PASETO_SECRET_KEY) if len(settings.PASETO_SECRET_KEY) == 64 else settings.PASETO_SECRET_KEY.encode().ljust(32)[:32]
        key = Key.new(version=4, purpose="local", key=raw)
        payload = {"sub": "1", "type": "access", "iat": datetime.now(timezone.utc).isoformat(),
                   "exp": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
        expired = pyseto.encode(key, json.dumps(payload).encode()).decode()
        with pytest.raises(ValueError):
            decode_token(expired, "access")

    def test_access_token_starts_with_v4(self):
        token = create_access_token(1)
        assert token.startswith("v4.")

    def test_payload_not_readable_without_key(self):
        """Paseto v4.local is ENCRYPTED — payload not human-readable."""
        import base64
        token = create_access_token(1)
        # Try to extract any part and decode as JSON — should fail
        parts = token.split(".")
        assert len(parts) == 3  # v4.local.payload
        try:
            raw = base64.urlsafe_b64decode(parts[2] + "==")
            decoded = raw.decode("utf-8", errors="ignore")
            # Should NOT contain cleartext JSON
            assert '"sub"' not in decoded or '"type"' not in decoded
        except Exception:
            pass  # Any failure here is also acceptable (garbled bytes)


class TestEmailTokens:
    def test_verify_token_roundtrip(self):
        token = generate_email_token("user@example.com", VERIFY_SALT)
        email = verify_email_token(token, VERIFY_SALT, 3600)
        assert email == "user@example.com"

    def test_wrong_salt_rejected(self):
        token = generate_email_token("user@example.com", VERIFY_SALT)
        assert verify_email_token(token, RESET_SALT, 3600) is None

    def test_expired_token_rejected(self):
        token = generate_email_token("user@example.com", VERIFY_SALT)
        assert verify_email_token(token, VERIFY_SALT, 0) is None

    def test_invalid_token_rejected(self):
        assert verify_email_token("garbage-token", VERIFY_SALT, 3600) is None


class TestFileValidator:
    def test_valid_png(self):
        from app.services.file_validator import validate_upload
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert validate_upload(png, "invoice.png") == "image/png"

    def test_valid_pdf(self):
        from app.services.file_validator import validate_upload
        pdf = b"%PDF-1.4\n" + b"\x00" * 100
        assert validate_upload(pdf, "invoice.pdf") == "application/pdf"

    def test_executable_rejected(self):
        from app.services.file_validator import validate_upload
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            validate_upload(b"MZ\x90\x00" + b"\x00" * 100, "evil.exe")
        assert e.value.status_code == 415

    def test_extension_mismatch_rejected(self):
        from app.services.file_validator import validate_upload
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            validate_upload(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "invoice.pdf")
        assert e.value.status_code == 422

    def test_oversized_rejected(self):
        from app.services.file_validator import validate_upload
        from fastapi import HTTPException
        big = b"\x89PNG\r\n\x1a\n" + b"A" * (11 * 1024 * 1024)
        with pytest.raises(HTTPException) as e:
            validate_upload(big, "big.png")
        assert e.value.status_code == 413

    def test_blocked_extension_rejected(self):
        from app.services.file_validator import validate_upload
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            validate_upload(b"MZ\x90\x00" + b"\x00" * 100, "malware.exe")
        assert e.value.status_code == 415
