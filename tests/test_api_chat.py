from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api


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
    assert r.json()["disclaimer"]
    assert "bevoegd gezag" in r.json()["vangnet"]


def test_chat_met_locatie_geeft_regels_door(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "https://iplo.nl/a", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        captured.update(kw)
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": {"gekozen_werkzaamheid": {"urn": "X"}},
                "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik een dakkapel?", "locatie": {"lat": 52.0, "lon": 4.3}})
    assert r.status_code == 200
    assert captured["locatie"] == {"lat": 52.0, "lon": 4.3}
    assert callable(captured["regels_fn"])
    assert r.json()["regels"] == {"gekozen_werkzaamheid": {"urn": "X"}}


def test_chat_zonder_locatie_locatie_none(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        captured.update(kw)
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": None,
                "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "iets"})
    assert r.status_code == 200
    assert captured["locatie"] is None
    assert r.json()["regels"] is None


def test_chat_no_index_regels_none(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_rag_store", lambda: None)
    r = client.post("/api/chat", json={"vraag": "iets", "locatie": {"lat": 52.0, "lon": 4.3}})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
    assert r.json()["regels"] is None
    assert r.json()["omgevingsplan"] is None


def test_chat_locatie_geeft_omgevingsplan_door(monkeypatch):
    client = _client(monkeypatch)
    api._config["leefomgevinglab"]["ozon"] = {
        "base_url": "https://x/ozon/v8", "api_key_header": "x-api-key",
        "max_regelingen": 3, "max_regelteksten": 5}

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_op(locatie, ozon_connector, max_regelingen=3, max_regelteksten=5):
        captured["locatie"] = locatie
        return {"regelingen": [{"titel": "Omgevingsplan Z", "type": "Omgevingsplan", "bevoegd_gezag": "g"}],
                "top_regeling": "Omgevingsplan Z", "regelteksten": [], "locatie_rd": [1.0, 2.0],
                "aantal_beperkt_tot": 3, "bron": "DSO Presenteren (Ozon)"}

    monkeypatch.setattr(api.omgevingsplan_mod, "omgevingsplan_op_locatie", fake_op)

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        op = kw["omgevingsplan_fn"]({"lat": 52.0, "lon": 5.1})   # exerceer de closure
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": None, "omgevingsplan": op,
                "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik bouwen?", "locatie": {"lat": 52.0, "lon": 5.1}})
    assert r.status_code == 200
    assert captured["locatie"] == {"lat": 52.0, "lon": 5.1}
    assert r.json()["omgevingsplan"]["top_regeling"] == "Omgevingsplan Z"


def test_chat_locatie_geeft_externe_veiligheid_door(monkeypatch):
    client = _client(monkeypatch)
    api._config["leefomgevinglab"]["externe_veiligheid"] = {
        "wfs_url": "https://x/wfs", "max_features": 5,
        "lagen": {"inrichting": "rev_public:ev_explosieaandachtsgebieden"}}

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_check(locatie, ev_connector, lagen, max_n=5):
        captured["locatie"] = locatie
        captured["lagen"] = lagen
        return {"aandachtsgebieden": [{"herkomst": "inrichting", "bron": "X", "maatgevende_stof": "propaan"}],
                "waarschuwing": "Let op", "locatie_rd": [1.0, 2.0], "bron": "REV (rev-portaal.nl)"}

    monkeypatch.setattr(api.externe_veiligheid_mod, "check_aandachtsgebieden", fake_check)

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        ev = kw["ev_fn"]({"lat": 51.0, "lon": 5.0})
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": None, "omgevingsplan": None,
                "externe_veiligheid": ev, "onzekerheid": True, "disclaimer": "d",
                "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik bouwen?", "locatie": {"lat": 51.0, "lon": 5.0}})
    assert r.status_code == 200
    assert captured["locatie"] == {"lat": 51.0, "lon": 5.0}
    assert "inrichting" in captured["lagen"]
    assert r.json()["externe_veiligheid"]["aandachtsgebieden"][0]["herkomst"] == "inrichting"


def test_chat_locatie_extraheert_activiteit_voor_zoek(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))
    monkeypatch.setattr(api.vergunningen_resolver, "extract_activiteit", lambda *a, **k: "dakkapel plaatsen")

    captured = {}

    def fake_regels(activiteit, locatie, zc, dc, cfg):
        captured["activiteit"] = activiteit
        return {"beschikbaar": True,
                "gekozen_werkzaamheid": {"urn": "X", "omschrijving": "Dakkapel plaatsen", "zekerheid_match": "midden"},
                "typeringen": ["Conclusie"], "alternatieven": [], "indieningsvereisten_status": "x", "bron": "b"}

    monkeypatch.setattr(api.vergunningen_service, "regels_opzoeken", fake_regels)

    # Laat de echte regels_fn-closure draaien via een beantwoord-mock die hem aanroept:
    def fake_beantwoord(vraag, store, embed_fn, **kw):
        r = kw["regels_fn"](vraag, kw["locatie"])
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": r, "onzekerheid": True,
                "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik een dakkapel plaatsen?", "locatie": {"lat": 52.0, "lon": 4.3}})
    assert r.status_code == 200
    assert captured["activiteit"] == "dakkapel plaatsen"          # extractie toegepast vóór zoek
    assert r.json()["regels"]["gekozen_werkzaamheid"]["urn"] == "X"
