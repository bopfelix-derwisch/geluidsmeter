import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld.rev_to_rdf import LL, GEO, REV_CLASS
from leefomgevinglab.usecases.datavraag import service as S
from leefomgevinglab.usecases.datavraag import nabijheid as NB


def _graph_met_punten(*lonlat):
    g = rdflib.Graph()
    for i, (lon, lat) in enumerate(lonlat):
        s = URIRef(LL[f"o{i}"])
        g.add((s, RDF.type, REV_CLASS))
        g.add((s, RDFS.label, Literal(f"F{i}")))
        g.add((s, GEO.asWKT, Literal(f"POINT({lon} {lat})", datatype=GEO.wktLiteral)))
    return g


def test_nabijheidsvraag_telt_treffers(monkeypatch):
    # twee REV-objecten; één vlakbij de school, één ver weg
    graph = _graph_met_punten((4.3004, 51.9000), (4.40, 51.90))
    monkeypatch.setattr(NB, "provincie_polygon", lambda prov, ep, **k: "POLYGON((4 51,5 51,5 52,4 52,4 51))")
    monkeypatch.setattr(NB, "scholen_in_gebied", lambda gebied, ep, **k: [("S", 4.30, 51.90)])
    out = S.beantwoord("hoeveel productiefaciliteiten liggen bij een school?", graph, "ground",
                       "http://x/v1", "qwen", kkg_endpoint="http://x", provincie="Zuid-Holland", straal_m=200)
    assert out["beschikbaar"] is True
    assert out["herkomst"] == "nabijheid"
    assert out["rijen"][0] == {"nabij": 1, "totaal": 2, "scholen": 1}
    assert "binnen 200 m van een school" in out["antwoord"]


def test_nabijheid_degradeert_zonder_provincie(monkeypatch):
    graph = _graph_met_punten((4.3, 51.9))
    monkeypatch.setattr(NB, "provincie_polygon", lambda prov, ep, **k: None)
    out = S.beantwoord("scholen in de buurt?", graph, "ground", "http://x/v1", "qwen",
                       kkg_endpoint="http://x", provincie="Zuid-Holland", straal_m=200)
    assert out["beschikbaar"] is False
