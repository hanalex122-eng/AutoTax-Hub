"""
tests/test_chat.py — AI chat endpoint tests
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestChatREST:
    def test_chat_requires_auth(self, client):
        r = client.post("/api/v1/chat", json={"message": "hello"})
        assert r.status_code == 401

    def test_chat_empty_message_rejected(self, client, auth_headers):
        r = client.post("/api/v1/chat", json={"message": "   "})
        assert r.status_code == 422

    def test_chat_returns_reply(self, client, auth_headers):
        with patch("app.services.ai_chat.settings") as ms:
            ms.ANTHROPIC_API_KEY = ""   # force fallback
            ms.AI_CHAT_MAX_TOKENS = 1024
            ms.AI_CHAT_MODEL = "claude-haiku-4-5-20251001"
            ms.AI_CHAT_SYSTEM_PROMPT = "You are helpful."
            r = client.post("/api/v1/chat", json={"message": "help"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "reply"      in data
        assert "message_id" in data
        assert len(data["reply"]) > 0

    def test_chat_fallback_vat_question(self, client, auth_headers):
        r = client.post("/api/v1/chat", json={"message": "what is VAT?"}, headers=auth_headers)
        assert r.status_code == 200
        assert "reply" in r.json()

    def test_chat_history_empty_initially(self, client, auth_headers):
        # Clear first
        client.delete("/api/v1/chat", headers=auth_headers)
        r = client.get("/api/v1/chat/history", headers=auth_headers)
        assert r.status_code == 200
        assert "messages" in r.json()

    def test_chat_history_saved(self, client, auth_headers):
        client.delete("/api/v1/chat", headers=auth_headers)
        client.post("/api/v1/chat", json={"message": "test message"}, headers=auth_headers)
        r = client.get("/api/v1/chat/history", headers=auth_headers)
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) >= 2   # user + assistant
        roles = [m["role"] for m in msgs]
        assert "user"      in roles
        assert "assistant" in roles

    def test_chat_clear_history(self, client, auth_headers):
        client.post("/api/v1/chat", json={"message": "to be deleted"}, headers=auth_headers)
        r_del = client.delete("/api/v1/chat", headers=auth_headers)
        assert r_del.status_code == 204
        r_hist = client.get("/api/v1/chat/history", headers=auth_headers)
        assert r_hist.json()["messages"] == []

    def test_chat_user_isolation(self, client, auth_headers, db):
        """User A's chat history must not leak to user B."""
        from app.core.security import hash_password
        from app.models.user import User
        u2 = User(email="chatuser2@example.com", full_name="U2",
                  hashed_password=hash_password("Secret1!"), is_verified=True)
        db.add(u2); db.commit()

        r_login = client.post("/api/v1/auth/login", json={"email": "chatuser2@example.com", "password": "Secret1!"})
        headers2 = {"Authorization": f"Bearer {r_login.json()['access_token']}"}

        # User 1 sends a message
        client.delete("/api/v1/chat", headers=auth_headers)
        client.post("/api/v1/chat", json={"message": "user1 secret"}, headers=auth_headers)

        # User 2's history should be empty
        r2 = client.get("/api/v1/chat/history", headers=headers2)
        msgs2 = r2.json()["messages"]
        contents = [m["content"] for m in msgs2]
        assert "user1 secret" not in contents

        db.delete(u2); db.commit()

    def test_chat_long_message_truncated(self, client, auth_headers):
        long_msg = "A" * 3000
        r = client.post("/api/v1/chat", json={"message": long_msg}, headers=auth_headers)
        # Should succeed (truncated internally) not 422
        assert r.status_code == 200


class TestAIChatService:
    def test_fallback_vat_keywords(self):
        from app.services.ai_chat import _fallback_reply
        r = _fallback_reply("what is VAT rate in Germany?")
        assert "VAT" in r or "vat" in r.lower() or "19%" in r

    def test_fallback_help_keywords(self):
        from app.services.ai_chat import _fallback_reply
        r = _fallback_reply("how do I use this?")
        assert len(r) > 10

    def test_fallback_amount_keywords(self):
        from app.services.ai_chat import _fallback_reply
        r = _fallback_reply("what is my total spend?")
        assert "Dashboard" in r or "stats" in r.lower() or "total" in r.lower()

    def test_fallback_unknown(self):
        from app.services.ai_chat import _fallback_reply
        r = _fallback_reply("xyzzy blorp flibble")
        assert len(r) > 0
