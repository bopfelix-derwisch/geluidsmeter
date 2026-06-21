import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld import store
from leefomgevinglab.ld.rev_to_rdf import LL, GEO, REV_CLASS


def _g():
    g = rdflib.Graph()
    s = URIRef(LL["a1"])
    g.add((s, RDF.type, REV_CLASS))
    g.add((s, RDFS.label, Literal("Fabriek A")))
    g.add((s, GEO.asWKT, Literal("POINT(4.3 51.9)", datatype=GEO.wktLiteral)))
    return g


def test_save_load_roundtrip(tmp_path):
    store.save_graph(_g(), str(tmp_path))
    g2 = store.load_graph(str(tmp_path))
    assert g2 is not None
    assert len(list(g2.subjects(RDF.type, REV_CLASS))) == 1
    assert store.load_graph(str(tmp_path / "leeg")) is None


def test_run_sparql_count():
    rows = store.run_sparql(_g(),
        "PREFIX ll: <https://leefomgevinglab.local/rev/> "
        "SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }")
    assert rows[0]["n"] == "1"
