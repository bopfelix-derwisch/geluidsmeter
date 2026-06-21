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


VOCAB = [
    {"uri": "http://definities.geostandaarden.nl/imev/id/begrippenkader/IMEV", "@type": "skos:ConceptScheme", "naam": "Begrippenkader IMEV"},
    {"uri": "http://definities.geostandaarden.nl/imev/id/begrip/aandachtsgebied",
     "@type": "skos:Concept", "naam": "aandachtsgebied", "term": "aandachtsgebied",
     "definitie": "Een locatie waar een extern veiligheidsaspect aan de orde is.",
     "isEngerDan": "http://definities.geostandaarden.nl/imev/id/begrip/brandaandachtsgebied"},
]


MIM_FIXTURE = """
@prefix mim: <http://bp4mc2.org/def/mim#> .
<urn:uuid:OT1> a mim:Objecttype ;
   mim:naam "Gebouw" ;
   mim:definitie "Een bouwwerk." ;
   mim:begrip <http://definities.geostandaarden.nl/nen3610-2022/id/begrip/gebouw> .
"""


def test_build_graph_mim_objecttype_en_begripmapping():
    g = G.build_graph([MIM_FIXTURE])
    by_id = {n["data"]["id"]: n["data"] for n in g["nodes"]}
    ot = by_id["urn:uuid:OT1"]
    assert ot["label"] == "Gebouw"
    assert ot["bron"] == "IMX-Geo"
    assert ot["definitie"] == "Een bouwwerk."
    nen = by_id["http://definities.geostandaarden.nl/nen3610-2022/id/begrip/gebouw"]
    assert nen["bron"] == "NEN3610"
    cross = {(e["data"]["source"], e["data"]["relatie"], e["data"]["target"]) for e in g["edges"]}
    assert ("urn:uuid:OT1", "begrip", "http://definities.geostandaarden.nl/nen3610-2022/id/begrip/gebouw") in cross


MIM_ASSOC = """
@prefix mim: <http://bp4mc2.org/def/mim#> .
<urn:uuid:A> a mim:Objecttype ; mim:naam "Gebouw" .
<urn:uuid:B> a mim:Objecttype ; mim:naam "Perceel" .
<urn:uuid:R> mim:naam "ligt op" ; mim:bron <urn:uuid:A> ; mim:doel <urn:uuid:B> .
"""


def test_build_graph_mim_associatie():
    g = G.build_graph([MIM_ASSOC])
    edges = {(e["data"]["source"], e["data"]["relatie"], e["data"]["target"]) for e in g["edges"]}
    assert ("urn:uuid:A", "ligt op", "urn:uuid:B") in edges


def test_bron_from_uri():
    imx = {"https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/straatnaam"}
    assert G.bron_from_uri("https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/straatnaam", imx) == "IMX-Geo"
    assert G.bron_from_uri("http://bag.basisregistraties.overheid.nl/id/begrip/Naam", imx) == "BAG"
    assert G.bron_from_uri("http://definities.geostandaarden.nl/imev/id/begrip/aandachtsgebied", imx) == "IMEV"


def test_build_graph_met_vocab_imev():
    g = G.build_graph([FIXTURE], [VOCAB])
    by_id = {n["data"]["id"]: n["data"] for n in g["nodes"]}
    aand = by_id["http://definities.geostandaarden.nl/imev/id/begrip/aandachtsgebied"]
    assert aand["label"] == "aandachtsgebied"
    assert aand["bron"] == "IMEV"
    assert "veiligheidsaspect" in aand["definitie"]
    # isEngerDan -> narrower edge naar het IMEV-doelbegrip
    rels = {(e["data"]["relatie"], e["data"]["target"]) for e in g["edges"]
            if e["data"]["source"] == "http://definities.geostandaarden.nl/imev/id/begrip/aandachtsgebied"}
    assert ("narrower", "http://definities.geostandaarden.nl/imev/id/begrip/brandaandachtsgebied") in rels
    assert "IMEV" in g["bronnen"] and "IMX-Geo" in g["bronnen"]
    # ConceptScheme-entry wordt geen node
    assert "http://definities.geostandaarden.nl/imev/id/begrippenkader/IMEV" not in by_id


def test_gelijke_naam_koppelt_imxgeo_en_imev():
    # IMX-Geo 'adres' (uit FIXTURE) en een IMEV-begrip met dezelfde naam 'adres'
    vocab = [[
        {"uri": "http://definities.geostandaarden.nl/imev/id/begrip/adres",
         "@type": "skos:Concept", "naam": "adres", "term": "adres",
         "definitie": "Adres in IMEV-context."},
    ]]
    g = G.build_graph([FIXTURE], vocab)
    cross = [e for e in g["edges"] if e["data"]["relatie"] == "gelijkeNaam"]
    paren = {(e["data"]["source"], e["data"]["target"]) for e in cross}
    assert ("https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/adres",
            "http://definities.geostandaarden.nl/imev/id/begrip/adres") in paren


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
