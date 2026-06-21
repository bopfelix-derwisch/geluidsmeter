"""RAG-grounding voor NL->SPARQL: schema, SHACL-shape en voorbeeldqueries als context."""

SCHEMA = """\
Lokale linked-data (rdflib), prefixes:
  ll:  <https://leefomgevinglab.local/rev/>
  geo: <http://www.opengis.net/ont/geosparql#>
  rdfs:<http://www.w3.org/2000/01/rdf-schema#>
Klasse ll:REVProductiefaciliteit (REV-productiefaciliteiten; let op: geen Seveso-vlag in de bron).
Elk object heeft: rdfs:label (naam), geo:asWKT (geometrie als WKT-literal)."""

VOORBEELDEN = [
    {"vraag": "hoeveel productiefaciliteiten zijn er?",
     "sparql": "PREFIX ll: <https://leefomgevinglab.local/rev/> "
               "SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"},
    {"vraag": "geef de namen van de productiefaciliteiten",
     "sparql": "PREFIX ll: <https://leefomgevinglab.local/rev/> "
               "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
               "SELECT ?label WHERE { ?s a ll:REVProductiefaciliteit ; rdfs:label ?label }"},
]


def build_grounding(shapes_ttl: str) -> str:
    blokken = [SCHEMA, "SHACL-shape:\n" + shapes_ttl.strip(), "Voorbeelden (vraag -> SPARQL):"]
    for v in VOORBEELDEN:
        blokken.append(f"V: {v['vraag']}\nQ: {v['sparql']}")
    return "\n\n".join(blokken)
