# tests/test_api_afval_chat.py
from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api


def _client(monkeypatch, tmp_path):
    api._config = {"leefomgevinglab": {
        "afvaldb": {"db_path": str(tmp_path / "afval.duckdb")},
        "llm": {"base_url": "x", "model": "m", "timeout_s": 1}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_bronnen_ok(monkeypatch, tmp_path):
    (tmp_path / "afval.duckdb").touch()
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(api.afvaldb_store, "open_readonly", lambda p: "CON")
    monkeypatch.setattr(api.afvaldb_store, "bronnen",
                        lambda con: [{"bron_id": "cbs-83558NED", "naam": "CBS", "url": "u",
                                      "licentie": "CC-BY 4.0", "type": "api", "opgehaald_op": "2026-07-23"}])
    r = client.get("/api/afval/bronnen")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["bron_id"] == "cbs-83558NED"
    assert "omschrijving" in body[0] and body[0]["omschrijving"]


def test_bronnen_db_absent_503(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    r = client.get("/api/afval/bronnen")
    assert r.status_code == 503


def test_chat_route(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(api.afval_chat, "beantwoord",
                        lambda vraag, db_path, **kw:
                        {"vraag": vraag, "antwoord": "ok", "sql": "SELECT 1 LIMIT 200",
                         "rijen": [], "beschikbaar": True, "disclaimer": "d", "vangnet": "v", "bron": "b"})
    r = client.post("/api/afval/chat", json={"vraag": "hoeveel GFT?"})
    assert r.status_code == 200
    assert r.json()["antwoord"] == "ok"
    assert r.json()["sql"] == "SELECT 1 LIMIT 200"
