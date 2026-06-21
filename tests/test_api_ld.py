from fastapi.testclient import TestClient
import geluidsmeter.api as api
import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld.rev_to_rdf import LL, GEO, REV_CLASS


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {"ld": {"store_dir": "/tmp/llab_ld"}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def _graph():
    g = rdflib.Graph(); s = URIRef(LL["a1"])
    g.add((s, RDF.type, REV_CLASS)); g.add((s, RDFS.label, Literal("A")))
    return g


def test_ld_sparql_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_ld_graph", lambda: _graph())
    r = client.post("/api/ld/sparql", json={"query":
        "PREFIX ll: <https://leefomgevinglab.local/rev/> SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"})
    assert r.status_code == 200
    assert r.json()["rows"][0]["n"] == "1"


def test_ld_sparql_no_graph(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_ld_graph", lambda: None)
    r = client.post("/api/ld/sparql", json={"query": "SELECT * WHERE { ?s ?p ?o }"})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
