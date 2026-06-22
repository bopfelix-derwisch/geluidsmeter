from fastapi.testclient import TestClient
import geluidsmeter.api as api


def _client(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "cache_dir": "/tmp/llab_test_cache",
            "llm": {"base_url": "http://llm/v1", "model": "qwen", "timeout_s": 5},
            "dso": {
                "api_key_header": "x-api-key",
                "zoek_base_url": "https://x/zoek/v2",
                "rtr_base_url": "https://x/rtr/v2",
                "uitvoeren_base_url": "https://x/uitv/v3",
            },
        }
    }
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_regels_happy(monkeypatch):
    client = _client(monkeypatch)

    class _Zoek:
        def zoek_werkzaamheden(self, tekst, max_n=5):
            return [{"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen",
                     "trefwoorden": ["dakkapel"], "functioneleStructuurRef": "http://x/DakkapelPlaatsen"}]

    class _Dso:
        def bepaal_typeringen(self, refs, geo_rd, datum=None):
            return [{"regelbeheerobjecten": ["Conclusie"]}]

        def bepaal_indieningsvereisten(self, refs, geo_rd, datum=None):
            return []

    monkeypatch.setattr(api, "_zoek_connector", lambda: _Zoek())
    monkeypatch.setattr(api, "_dso_connector", lambda: _Dso())
    r = client.post("/api/regels", json={"activiteit": "dakkapel", "locatie": {"lat": 52.0, "lon": 5.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["beschikbaar"] is True
    assert body["gekozen_werkzaamheid"]["urn"] == "DakkapelPlaatsen"
    assert body["typeringen"] == ["Conclusie"]
    assert body["indieningsvereisten_status"] == "niet_beschikbaar_op_locatie"
    assert "bevoegd gezag" in body["vangnet"]


def test_regels_locatie_verplicht(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/api/regels", json={"activiteit": "dakkapel", "locatie": None})
    assert r.status_code == 422
    r2 = client.post("/api/regels", json={"activiteit": "dakkapel", "locatie": {"lat": 52.0}})
    assert r2.status_code == 422


def test_regels_zoekbron_down_200_unavailable(monkeypatch):
    from leefomgevinglab.connectors.base import ConnectorError
    client = _client(monkeypatch)

    class _Zoek:
        def zoek_werkzaamheden(self, tekst, max_n=5):
            raise ConnectorError("geen key")

    monkeypatch.setattr(api, "_zoek_connector", lambda: _Zoek())
    monkeypatch.setattr(api, "_dso_connector", lambda: object())
    r = client.post("/api/regels", json={"activiteit": "x", "locatie": {"lat": 52.0, "lon": 5.0}})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
