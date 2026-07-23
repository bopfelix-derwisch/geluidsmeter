from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api


def _client(monkeypatch, tmp_path):
    api._config = {"leefomgevinglab": {"afval": {"data_dir": str(tmp_path)},
                                       "afvaldb": {"db_path": str(tmp_path / "afval.duckdb")},
                                       "llm": {"base_url": "x", "model": "m", "timeout_s": 1}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_forecast_endpoint(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(api.afval_service, "forecast",
                        lambda db_path, regio, afvalstroom:
                        {"regio": regio, "afvalstroom": afvalstroom, "historie": [],
                         "forecast": [{"jaar": 2035, "verwacht": 20.0, "ondergrens": 15.0, "bovengrens": 25.0}],
                         "methode": "holt", "label": "indicatief"})
    r = client.get("/api/afval/forecast", params={"regio": "PV24", "afvalstroom": "GFT-afval"})
    assert r.status_code == 200
    assert r.json()["forecast"][0]["jaar"] == 2035
