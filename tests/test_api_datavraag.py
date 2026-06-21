from fastapi.testclient import TestClient
import geluidsmeter.api as api
import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld.rev_to_rdf import LL, REV_CLASS


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {
        "ld": {"store_dir": "/tmp/llab_dv"},
        "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def _graph():
    g = rdflib.Graph()
    for i in (1, 2):
        s = URIRef(LL[f"x{i}"]); g.add((s, RDF.type, REV_CLASS)); g.add((s, RDFS.label, Literal(f"F{i}")))
    return g


def test_datavraag_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_dv_graph", lambda: _graph())
    monkeypatch.setattr(api, "_dv_grounding", lambda: "ground")
    monkeypatch.setattr(api.dv_service, "beantwoord",
        lambda vraag, graph, grounding_txt, **kw: {"vraag": vraag, "antwoord": "2 gevonden",
            "sparql": "SELECT ...", "herkomst": "fallback", "rijen": [{"n": "2"}],
            "onzekerheid": True, "disclaimer": "indicatief", "vangnet": "bevoegd gezag", "beschikbaar": True})
    r = client.post("/api/datavraag", json={"vraag": "hoeveel?"})
    assert r.status_code == 200
    assert r.json()["rijen"][0]["n"] == "2"
    assert r.json()["sparql"]


def test_datavraag_no_graph(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_dv_graph", lambda: None)
    r = client.post("/api/datavraag", json={"vraag": "hoeveel?"})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
