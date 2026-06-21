from fastapi.testclient import TestClient
import geluidsmeter.api as api


def _client(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "cache_dir": "/tmp/llab_test_cache",
            "dso": {
                "base_url": "https://x/v2",
                "operation_path": "_bepaalToepasbareRegels",
                "api_key_header": "x-api-key",
            },
        }
    }
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_regels_happy(monkeypatch):
    client = _client(monkeypatch)

    class _FakeConn:
        def bepaal_regels(self, activiteit, locatie=None):
            return {"regels": ["X"], "echo": activiteit}

    monkeypatch.setattr(api, "_dso_connector", lambda: _FakeConn())
    r = client.post("/api/regels", json={"activiteit": "kappen van een boom",
                                         "locatie": {"lat": 52.0, "lon": 4.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["beschikbaar"] is True
    assert body["regels_ruw"]["echo"] == "kappen van een boom"
    assert "bevoegd gezag" in body["vangnet"]
    assert body["disclaimer"]


def test_regels_bron_down_returns_200_unavailable(monkeypatch):
    from leefomgevinglab.connectors.base import ConnectorError
    client = _client(monkeypatch)

    class _FakeConn:
        def bepaal_regels(self, activiteit, locatie=None):
            raise ConnectorError("geen key")

    monkeypatch.setattr(api, "_dso_connector", lambda: _FakeConn())
    r = client.post("/api/regels", json={"activiteit": "activiteit X", "locatie": None})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
