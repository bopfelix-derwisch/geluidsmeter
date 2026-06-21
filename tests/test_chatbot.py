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


def test_build_prompt_bevat_context_en_instructie():
    p = chatbot.build_prompt("mag ik een boom kappen?",
                             [{"text": "Voor kappen geldt soms een vergunning.", "url": "u1"}])
    assert "mag ik een boom kappen?" in p
    assert "Voor kappen geldt soms een vergunning." in p
    assert "uitsluitend" in p.lower()      # gebruik alleen de context


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
