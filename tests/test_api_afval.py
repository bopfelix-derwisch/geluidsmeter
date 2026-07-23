# tests/test_api_afval.py
from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api
from leefomgevinglab.connectors.base import ConnectorError


def _client(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "afval": {"data_dir": "/tmp/afval_test"},
            "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60},
        }
    }
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_afval_meta(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "meta",
                        lambda data_dir: {"regios": [], "afvalstromen": ["GFT-afval"],
                                          "jaren": [2020], "indicatoren": [], "bron": "b",
                                          "licentie": "CC-BY 4.0", "label": "l"})
    r = client.get("/api/afval/meta")
    assert r.status_code == 200
    assert r.json()["afvalstromen"] == ["GFT-afval"]


def test_afval_choropleth(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "choropleth",
                        lambda data_dir, afvalstroom, jaar, indicator:
                        {"type": "FeatureCollection", "features": [],
                         "echo": [afvalstroom, jaar, indicator]})
    r = client.get("/api/afval/choropleth",
                   params={"afvalstroom": "GFT-afval", "jaar": 2020, "indicator": "volume"})
    assert r.status_code == 200
    assert r.json()["echo"] == ["GFT-afval", 2020, "volume"]


def test_afval_trend(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "trend",
                        lambda data_dir, regio, afvalstroom:
                        {"regio": regio, "naam": "Flevoland", "afvalstroom": afvalstroom, "reeks": []})
    r = client.get("/api/afval/trend", params={"regio": "PV24", "afvalstroom": "GFT-afval"})
    assert r.status_code == 200
    assert r.json()["naam"] == "Flevoland"


def test_afval_duiding_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "stroom_context",
                        lambda data_dir, regio, afvalstroom, jaar:
                        {"naam": "Flevoland", "waarde_kton": 12.0, "rang": 8})
    monkeypatch.setattr(api.afval_duiding, "duiding",
                        lambda regio_naam, afvalstroom, jaar, context, **kw:
                        {"duiding": "ok", "bron": "b", "disclaimer": "d"})
    r = client.post("/api/afval/duiding",
                    json={"regio": "PV24", "afvalstroom": "GFT-afval", "jaar": 2020})
    assert r.status_code == 200
    body = r.json()
    assert body["duiding"] == "ok"
    # context wordt meegeleverd zodat de modal de kerncijfers kan tonen
    assert body["context"]["rang"] == 8


def test_afval_duiding_llm_down_degradeert_met_context(monkeypatch):
    # LLM offline: endpoint blijft 200 en levert de kerncijfers (context), duiding = None.
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "stroom_context",
                        lambda data_dir, regio, afvalstroom, jaar:
                        {"naam": "Flevoland", "waarde_kton": 12.0})
    def boom(*a, **kw):
        raise ConnectorError("down")
    monkeypatch.setattr(api.afval_duiding, "duiding", boom)
    r = client.post("/api/afval/duiding",
                    json={"regio": "PV24", "afvalstroom": "GFT-afval", "jaar": 2020})
    assert r.status_code == 200
    body = r.json()
    assert body["duiding"] is None
    assert body["context"]["waarde_kton"] == 12.0


def test_afval_duiding_data_ontbreekt_503(monkeypatch):
    client = _client(monkeypatch)
    def missing(*a, **kw):
        raise FileNotFoundError()
    monkeypatch.setattr(api.afval_service, "stroom_context", missing)
    r = client.post("/api/afval/duiding",
                    json={"regio": "PV24", "afvalstroom": "GFT-afval", "jaar": 2020})
    assert r.status_code == 503
