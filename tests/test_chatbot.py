import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import chatbot


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=None, response=None)
    def json(self): return self._p


class _Store:
    def __init__(self, hits): self._hits = hits
    def search(self, qv, k): return self._hits[:k]


def _embed_ok(texts): return [[1.0, 0.0] for _ in texts]


_REGELS_OK = {
    "beschikbaar": True,
    "gekozen_werkzaamheid": {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen",
                             "match_onderbouwing": "Enige kandidaat", "zekerheid_match": "midden"},
    "alternatieven": [],
    "typeringen": ["Conclusie", "Indieningsvereisten"],
    "indieningsvereisten": None,
    "indieningsvereisten_status": "niet_beschikbaar_op_locatie",
    "locatie_rd": [80474.8, 455194.3],
    "bron": "DSO Toepasbare Regels (Zoek + RTR + Uitvoeren)",
}
_REGELS_GEEN_MATCH = {"beschikbaar": False, "gekozen_werkzaamheid": None, "alternatieven": []}
LOC = {"lat": 52.08, "lon": 4.30}


def test_build_prompt_bevat_context_en_instructie():
    p = chatbot.build_prompt("mag ik een boom kappen?",
                             [{"text": "Voor kappen geldt soms een vergunning.", "url": "u1"}])
    assert "mag ik een boom kappen?" in p
    assert "Voor kappen geldt soms een vergunning." in p
    assert "verzin niets buiten de bronnen" in p.lower()   # no-hallucination-instructie


def test_beantwoord_happy_contract(monkeypatch):
    store = _Store([{"text": "Voor kappen geldt soms een vergunning.", "url": "https://iplo.nl/a", "score": 0.9}])
    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "Mogelijk is een vergunning nodig."}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("mag ik een boom kappen?", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["beschikbaar"] is True
    assert out["antwoord"] == "Mogelijk is een vergunning nodig."
    assert out["bronnen"] == ["https://iplo.nl/a"]
    assert out["onzekerheid"] is True
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"] == chatbot.DISCLAIMER


def test_beantwoord_geen_context_degradeert(monkeypatch):
    store = _Store([])
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["beschikbaar"] is False
    assert out["bronnen"] == []
    assert out["disclaimer"] == chatbot.DISCLAIMER


def test_beantwoord_llm_down_degradeert(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["beschikbaar"] is False
    assert "bevoegd gezag" in out["vangnet"]


def test_build_prompt_met_regels_voegt_dso_sectie_toe():
    p = chatbot.build_prompt("mag ik een dakkapel plaatsen?",
                             [{"text": "context", "url": "u1"}], _REGELS_OK)
    assert "toepasbare regels" in p.lower()
    assert "kern van je antwoord" in p.lower()      # DSO-regels dragen het antwoord
    assert "Dakkapel plaatsen" in p
    assert "Conclusie" in p


def test_build_prompt_zonder_regels_geen_dso_sectie():
    p = chatbot.build_prompt("iets", [{"text": "context", "url": "u1"}])
    assert "kern van je antwoord" not in p.lower()
    assert "Dakkapel plaatsen" not in p


def test_beantwoord_met_locatie_en_match(monkeypatch):
    store = _Store([{"text": "Voor een dakkapel geldt soms een melding.", "url": "https://iplo.nl/a", "score": 0.9}])
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["messages"][0]["content"]
        return _Resp({"choices": [{"message": {"content": "Mogelijk een melding."}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("mag ik een dakkapel plaatsen?", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b",
                             locatie=LOC, regels_fn=lambda v, l: _REGELS_OK)
    assert out["beschikbaar"] is True
    assert out["antwoord"] == "Mogelijk een melding."
    assert out["regels"] == _REGELS_OK
    assert "Dakkapel plaatsen" in captured["prompt"]   # Qwen kreeg de DSO-context mee


def test_beantwoord_zonder_locatie_geen_regels(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])
    called = {"n": 0}

    def regels_fn(v, l):
        called["n"] += 1
        return _REGELS_OK

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen", regels_fn=regels_fn)
    assert out["regels"] is None
    assert called["n"] == 0           # zonder locatie niet aangeroepen
    assert out["beschikbaar"] is True


def test_beantwoord_geen_werkzaamheid_match_geen_regels(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets vaags", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, regels_fn=lambda v, l: _REGELS_GEEN_MATCH)
    assert out["regels"] is None
    assert out["beschikbaar"] is True


def test_beantwoord_regels_bron_down_rag_blijft(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])

    def boom(v, l):
        raise ConnectorError("regels down")

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, regels_fn=boom)
    assert out["regels"] is None            # regels-laag faalde
    assert out["beschikbaar"] is True       # RAG-antwoord blijft
    assert out["antwoord"] == "ok"


def test_beantwoord_rag_down_regels_blijft(monkeypatch):
    def embed_boom(texts):
        raise ConnectorError("embed down")

    store = _Store([])
    out = chatbot.beantwoord("mag ik een dakkapel plaatsen?", store, embed_boom,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, regels_fn=lambda v, l: _REGELS_OK)
    assert out["beschikbaar"] is False      # RAG faalde
    assert out["antwoord"] is None
    assert out["regels"] == _REGELS_OK      # regels overleven onafhankelijk
