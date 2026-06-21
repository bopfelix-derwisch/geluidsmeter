import httpx
import pytest
from leefomgevinglab.usecases.datavraag import nl2sparql as N


class _Resp:
    def __init__(self, content):
        self._c = content; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": self._c}}]}


def test_is_geldige_sparql():
    assert N.is_geldige_sparql("SELECT ?s WHERE { ?s ?p ?o }")
    assert not N.is_geldige_sparql("dit is geen sparql {{{")


def test_kies_sparql_gebruikt_llm_als_geldig(monkeypatch):
    q = "PREFIX ll: <https://leefomgevinglab.local/rev/> SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"
    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: _Resp("```sparql\n" + q + "\n```"))
    sparql, herkomst = N.kies_sparql("hoeveel?", "ground", "http://x/v1", "qwen")
    assert herkomst == "llm"
    assert "COUNT" in sparql and "```" not in sparql


def test_kies_sparql_valt_terug_bij_ongeldig(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: _Resp("sorry geen idee {{{"))
    sparql, herkomst = N.kies_sparql("iets vaags", "ground", "http://x/v1", "qwen")
    assert herkomst == "fallback"
    assert sparql == N.FALLBACK_SPARQL


def test_kies_sparql_valt_terug_bij_llm_fout(monkeypatch):
    def boom(url, json=None, timeout=None): raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    sparql, herkomst = N.kies_sparql("iets", "ground", "http://x/v1", "qwen")
    assert herkomst == "fallback"
