from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api
from leefomgevinglab.connectors.base import ConnectorError


def _client_with_config(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "cache_dir": "/tmp/llab_test_cache",
            "rev": {"ogc_base_url": "https://x", "collections": ["c"], "max_features": 500},
            "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60},
        }
    }
    # voorkom dat startup() de echte config herlaadt
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_rev_features_ok(monkeypatch):
    client = _client_with_config(monkeypatch)

    class _FakeRev:
        def features(self, bbox):
            return {"type": "FeatureCollection", "features": [{"id": 1, "bbox": bbox}]}

    monkeypatch.setattr(api, "_rev_connector", lambda: _FakeRev())
    r = client.get("/api/rev/features", params={"bbox": "4,52,4.5,52.5"})
    assert r.status_code == 200
    assert r.json()["features"][0]["bbox"] == "4,52,4.5,52.5"


def test_rev_features_bron_down_503(monkeypatch):
    client = _client_with_config(monkeypatch)

    class _FakeRev:
        def features(self, bbox):
            raise ConnectorError("down")

    monkeypatch.setattr(api, "_rev_connector", lambda: _FakeRev())
    r = client.get("/api/rev/features", params={"bbox": "4,52,4.5,52.5"})
    assert r.status_code == 503


def test_rev_features_malformed_bbox_400(monkeypatch):
    client = _client_with_config(monkeypatch)
    class _FakeRev:
        def features(self, bbox):
            raise ValueError("bad bbox")
    monkeypatch.setattr(api, "_rev_connector", lambda: _FakeRev())
    r = client.get("/api/rev/features", params={"bbox": "4,52,4.5"})
    assert r.status_code == 400


def test_duiding_ok(monkeypatch):
    client = _client_with_config(monkeypatch)
    monkeypatch.setattr(
        api.rev_service, "duiding",
        lambda properties, **kw: {"duiding": "ok", "bron": "REV", "disclaimer": "d"},
    )
    r = client.post("/api/duiding", json={"properties": {"naam": "X"}})
    assert r.status_code == 200
    assert r.json()["duiding"] == "ok"
