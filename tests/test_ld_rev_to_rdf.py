from leefomgevinglab.ld import rev_to_rdf as R
from rdflib import RDF, RDFS

def _fc():
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Fabriek A", "seveso": "ja"},
         "geometry": {"type": "Point", "coordinates": [4.30, 51.90]}},   # binnen
        {"type": "Feature", "properties": {"name": "Fabriek B", "seveso": "nee"},
         "geometry": {"type": "Point", "coordinates": [6.90, 52.20]}},   # buiten ZH
    ]}

# vierkant rond [4.30,51.90]
ZH = "POLYGON((4.0 51.6, 4.6 51.6, 4.6 52.1, 4.0 52.1, 4.0 51.6))"


def test_build_graph_filtert_gebied_en_seveso():
    g = R.build_rev_graph(_fc(), gebied_wkt=ZH, feature_filter=lambda p: p.get("seveso") == "ja")
    klassen = list(g.subjects(RDF.type, R.REV_CLASS))
    assert len(klassen) == 1                      # alleen Fabriek A (binnen + seveso=ja)
    s = klassen[0]
    assert str(next(g.objects(s, RDFS.label))) == "Fabriek A"
    wkt = str(next(g.objects(s, R.GEO.asWKT)))
    assert wkt.upper().startswith("POINT")


def test_geen_filters_neemt_alles():
    g = R.build_rev_graph(_fc())
    assert len(list(g.subjects(RDF.type, R.REV_CLASS))) == 2
