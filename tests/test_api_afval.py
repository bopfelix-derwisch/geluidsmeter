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
    monkeypatch.setattr(api.afval_duiding, "duiding",
                        lambda regio_naam, afvalstroom, reeks, **kw:
                        {"duiding": "ok", "bron": "b", "disclaimer": "d"})
    r = client.post("/api/afval/duiding",
                    json={"regio_naam": "Flevoland", "afvalstroom": "GFT-afval",
                          "reeks": [{"jaar": 2020, "hoeveelheid_kton": 12.0, "circulariteit_pct": 75.0}]})
    assert r.status_code == 200
    assert r.json()["duiding"] == "ok"


def test_afval_duiding_llm_down_503(monkeypatch):
    client = _client(monkeypatch)
    def boom(**kw):
        raise ConnectorError("down")
    monkeypatch.setattr(api.afval_duiding, "duiding", lambda *a, **kw: boom())
    r = client.post("/api/afval/duiding",
                    json={"regio_naam": "Flevoland", "afvalstroom": "GFT-afval", "reeks": []})
    assert r.status_code == 503
