from leefomgevinglab.usecases.datavraag import grounding as G


def test_build_grounding_bevat_schema_en_voorbeeld():
    txt = G.build_grounding("ll:REVProductiefaciliteitShape a sh:NodeShape .")
    assert "ll:REVProductiefaciliteit" in txt
    assert "geo:asWKT" in txt
    assert "SELECT" in txt                      # minstens één voorbeeldquery
    assert "NodeShape" in txt                   # de meegegeven shape-tekst zit erin


def test_voorbeelden_zijn_geldig_gevormd():
    assert G.VOORBEELDEN and all("vraag" in v and "sparql" in v for v in G.VOORBEELDEN)
