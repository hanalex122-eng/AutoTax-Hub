"""
tests/test_health.py
"""


class TestHealth:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "version" in r.json()

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_404(self, client):
        r = client.get("/nonexistent-endpoint")
        assert r.status_code == 404
