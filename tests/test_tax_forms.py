"""
tests/test_tax_forms.py — Steuerformular endpoint tests
"""
import pytest


class TestTaxProfile:
    def test_get_profile_creates_default(self, client, auth_headers):
        r = client.get("/api/v1/tax/profile", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "steuernummer" in data
        assert data["tax_country"] == "DE"
        assert data["base_currency"] == "EUR"

    def test_update_profile(self, client, auth_headers):
        r = client.put("/api/v1/tax/profile", json={
            "steuernummer": "12/345/67890",
            "finanzamt": "Saarbrücken",
            "bundesland": "Saarland",
            "betriebsart": "Freiberuf",
            "ist_kleinunternehmer": False,
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["steuernummer"] == "12/345/67890"
        assert r.json()["finanzamt"] == "Saarbrücken"

    def test_profile_requires_auth(self, client):
        r = client.get("/api/v1/tax/profile")
        assert r.status_code == 401


class TestEuerForm:
    def test_auto_fill_creates_form(self, client, auth_headers):
        r = client.post("/api/v1/tax/euer/auto-fill?steuerjahr=2099", headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["steuerjahr"] == 2099
        assert data["auto_filled"] is True
        assert "summe_einnahmen" in data
        assert "gewinn_verlust" in data
        # Clean up
        client.delete(f"/api/v1/tax/euer/{data['id']}", headers=auth_headers)

    def test_auto_fill_duplicate_rejected(self, client, auth_headers):
        r1 = client.post("/api/v1/tax/euer/auto-fill?steuerjahr=2098", headers=auth_headers)
        assert r1.status_code == 201
        r2 = client.post("/api/v1/tax/euer/auto-fill?steuerjahr=2098", headers=auth_headers)
        assert r2.status_code == 409
        client.delete(f"/api/v1/tax/euer/{r1.json()['id']}", headers=auth_headers)

    def test_list_euer(self, client, auth_headers):
        r = client.get("/api/v1/tax/euer", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_update_euer(self, client, auth_headers):
        r1 = client.post("/api/v1/tax/euer/auto-fill?steuerjahr=2097", headers=auth_headers)
        form_id = r1.json()["id"]
        r2 = client.put(f"/api/v1/tax/euer/{form_id}", json={
            "steuerjahr": 2097,
            "ausgaben_raumkosten": 6000.0,
            "ausgaben_telefon_internet": 1200.0,
        }, headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["ausgaben_raumkosten"] == 6000.0
        assert r2.json()["summe_ausgaben"] >= 7200.0
        client.delete(f"/api/v1/tax/euer/{form_id}", headers=auth_headers)

    def test_euer_summary(self, client, auth_headers):
        r1 = client.post("/api/v1/tax/euer/auto-fill?steuerjahr=2096", headers=auth_headers)
        form_id = r1.json()["id"]
        r2 = client.get(f"/api/v1/tax/euer/{form_id}/summary", headers=auth_headers)
        assert r2.status_code == 200
        data = r2.json()
        assert "einnahmen" in data
        assert "ausgaben" in data
        assert "ergebnis" in data
        assert "steuer_schaetzung" in data
        client.delete(f"/api/v1/tax/euer/{form_id}", headers=auth_headers)

    def test_delete_euer(self, client, auth_headers):
        r1 = client.post("/api/v1/tax/euer/auto-fill?steuerjahr=2095", headers=auth_headers)
        form_id = r1.json()["id"]
        r2 = client.delete(f"/api/v1/tax/euer/{form_id}", headers=auth_headers)
        assert r2.status_code == 204
        r3 = client.get(f"/api/v1/tax/euer/{form_id}", headers=auth_headers)
        assert r3.status_code == 404


class TestUstvaForm:
    def test_auto_fill_ustva(self, client, auth_headers):
        r = client.post("/api/v1/tax/ustva/auto-fill?jahr=2099&zeitraum=01", headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["jahr"] == 2099
        assert data["zeitraum"] == "01"
        assert "ust_summe" in data
        assert "vst_summe" in data
        assert "verbleibend" in data
        client.delete(f"/api/v1/tax/ustva/{data['id']}", headers=auth_headers)

    def test_ustva_quarterly(self, client, auth_headers):
        r = client.post("/api/v1/tax/ustva/auto-fill?jahr=2099&zeitraum=Q1", headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["zeitraum"] == "Q1"
        client.delete(f"/api/v1/tax/ustva/{r.json()['id']}", headers=auth_headers)

    def test_list_ustva(self, client, auth_headers):
        r = client.get("/api/v1/tax/ustva", headers=auth_headers)
        assert r.status_code == 200

    def test_ustva_requires_auth(self, client):
        r = client.get("/api/v1/tax/ustva")
        assert r.status_code == 401


class TestHelperEndpoints:
    def test_bundeslaender(self, client):
        r = client.get("/api/v1/tax/bundeslaender")
        assert r.status_code == 200
        assert len(r.json()["bundeslaender"]) == 16

    def test_rechtsformen(self, client):
        r = client.get("/api/v1/tax/rechtsformen")
        assert r.status_code == 200
        assert len(r.json()["rechtsformen"]) >= 7
