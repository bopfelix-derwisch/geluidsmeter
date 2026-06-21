import httpx
import pytest
from leefomgevinglab.usecases.vergunningen import chatbot

EVAL_VRAGEN = [
    "mag ik een boom kappen in mijn tuin?",
    "heb ik een vergunning nodig voor een dakkapel?",
    "moet ik een melding doen voor een uitrit?",
]


class _Resp:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return self._p


class _Store:
    def search(self, qv, k): return [{"text": "relevante passage", "url": "https://iplo.nl/x", "score": 0.8}]


def _embed(texts): return [[1.0, 0.0] for _ in texts]


@pytest.mark.parametrize("vraag", EVAL_VRAGEN)
def test_contract_op_eval_vragen(vraag, monkeypatch):
    monkeypatch.setattr(httpx, "post",
                        lambda url, json=None, timeout=None: _Resp(
                            {"choices": [{"message": {"content": "Indicatief antwoord met verwijzing."}}]}))
    out = chatbot.beantwoord(vraag, _Store(), _embed,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    # antwoordcontract afdwingen
    assert out["beschikbaar"] is True
    assert out["bronnen"], "antwoord moet bronnen bevatten"
    assert out["onzekerheid"] is True
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"]
    # geen stellige vergunning-conclusie als gestructureerd veld
    assert "vergunningplichtig" not in out
    assert "conclusie" not in out
