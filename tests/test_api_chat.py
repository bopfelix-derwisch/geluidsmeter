from fastapi.testclient import TestClient
import geluidsmeter.api as api


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {
        "cache_dir": "/tmp/llab_test_cache",
        "rag": {"embed": {"base_url": "http://x/v1", "model": "bge"},
                "store_dir": "/tmp/llab_rag_test", "top_k": 4,
                "chunk_chars": 1200, "chunk_overlap": 200, "iplo_urls": []},
        "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60},
    }}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_chat_happy(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "https://iplo.nl/a", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))
    monkeypatch.setattr(api.chatbot, "beantwoord",
                        lambda vraag, store, embed_fn, **kw: {
                            "vraag": vraag, "antwoord": "ok", "bronnen": ["https://iplo.nl/a"],
                            "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag",
                            "beschikbaar": True})
    r = client.post("/api/chat", json={"vraag": "mag ik kappen?"})
    assert r.status_code == 200
    assert r.json()["antwoord"] == "ok"
    assert r.json()["bronnen"] == ["https://iplo.nl/a"]


def test_chat_no_index_degradeert(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_rag_store", lambda: None)
    r = client.post("/api/chat", json={"vraag": "iets"})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
