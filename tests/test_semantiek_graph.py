from leefomgevinglab.semantiek import graph as G

FIXTURE = """
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix : <https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/> .
:straatnaam a skos:Concept ;
   skos:prefLabel "straatnaam"@nl ;
   skos:definition "De benaming van een weg."@nl ;
   skos:inScheme <https://staging-definities.geostandaarden.nl/imx-geo/> ;
   skos:closeMatch <http://bag.basisregistraties.overheid.nl/id/begrip/Naam> ;
   skos:broader :adres .
:adres a skos:Concept ;
   skos:prefLabel "adres"@nl ;
   skos:inScheme <https://staging-definities.geostandaarden.nl/imx-geo/> .
"""


def test_bron_from_uri():
    imx = {"https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/straatnaam"}
    assert G.bron_from_uri("https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/straatnaam", imx) == "IMX-Geo"
    assert G.bron_from_uri("http://bag.basisregistraties.overheid.nl/id/begrip/Naam", imx) == "BAG"


def test_build_graph_nodes_edges_bron():
    g = G.build_graph([FIXTURE])
    ids = {n["data"]["id"] for n in g["nodes"]}
    # IMX-Geo concepten + externe BAG-node als losse node
    assert any(i.endswith("/straatnaam") for i in ids)
    assert "http://bag.basisregistraties.overheid.nl/id/begrip/Naam" in ids
    bron = {n["data"]["id"]: n["data"]["bron"] for n in g["nodes"]}
    assert bron["http://bag.basisregistraties.overheid.nl/id/begrip/Naam"] == "BAG"
    straat = next(n for n in g["nodes"] if n["data"]["id"].endswith("/straatnaam"))
    assert straat["data"]["bron"] == "IMX-Geo"
    assert straat["data"]["label"] == "straatnaam"
    assert "weg" in (straat["data"]["definitie"] or "")
    relaties = {e["data"]["relatie"] for e in g["edges"]}
    assert "closeMatch" in relaties and "broader" in relaties
    assert "BAG" in g["bronnen"] and "IMX-Geo" in g["bronnen"]


def test_save_load_roundtrip(tmp_path):
    g = G.build_graph([FIXTURE])
    G.save_graph(g, str(tmp_path))
    g2 = G.load_graph(str(tmp_path))
    assert g2["bronnen"] == g["bronnen"]
    assert G.load_graph(str(tmp_path / "leeg")) is None
