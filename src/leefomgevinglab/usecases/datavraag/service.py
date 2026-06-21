"""Data-chatbot service: NL-vraag -> SPARQL/nabijheid -> antwoord met conservatief contract."""
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.ld.store import run_sparql
from leefomgevinglab.usecases.datavraag.nl2sparql import kies_sparql
from leefomgevinglab.usecases.datavraag import nabijheid as NB

DISCLAIMER = ("Indicatief, geen juridisch/officieel cijfer. De telling betreft REV-productiefaciliteiten "
             "(de open REV-laag kent geen Seveso-vlag).")
VANGNET = "Raadpleeg de bronhouder (REV/PDOK, Kadaster) of het bevoegd gezag voor officiele cijfers."

REV_WKT_Q = ("PREFIX ll: <https://leefomgevinglab.local/rev/> "
             "PREFIX geo: <http://www.opengis.net/ont/geosparql#> "
             "SELECT ?wkt WHERE { ?s a ll:REVProductiefaciliteit ; geo:asWKT ?wkt }")


def _is_nabijheidsvraag(vraag: str) -> bool:
    v = vraag.lower()
    return "school" in v or "scholen" in v


def beantwoord(vraag: str, graph, grounding_txt: str, llm_base_url: str, model: str,
               timeout_s: float = 60.0, kkg_endpoint: str = "", provincie: str = "Zuid-Holland",
               straal_m: float = 500.0) -> dict:
    base = {"vraag": vraag, "onzekerheid": True, "disclaimer": DISCLAIMER, "vangnet": VANGNET,
            "bron": "eigen REV-LD (PDOK) + Kadaster KKG"}
    if graph is None:
        return {**base, "antwoord": None, "sparql": None, "herkomst": None, "rijen": [], "beschikbaar": False}

    if _is_nabijheidsvraag(vraag):
        return _beantwoord_nabijheid(vraag, graph, base, kkg_endpoint, provincie, straal_m)

    sparql, herkomst = kies_sparql(vraag, grounding_txt, llm_base_url, model, timeout_s)
    try:
        rijen = run_sparql(graph, sparql)
    except Exception:
        return {**base, "antwoord": None, "sparql": sparql, "herkomst": herkomst, "rijen": [], "beschikbaar": False}
    if rijen and "n" in rijen[0]:
        antwoord = f"Gevonden: {rijen[0]['n']} (REV-productiefaciliteiten)."
    else:
        antwoord = f"{len(rijen)} resultaten."
    return {**base, "antwoord": antwoord, "sparql": sparql, "herkomst": herkomst,
            "rijen": rijen, "beschikbaar": True}


def _beantwoord_nabijheid(vraag, graph, base, kkg_endpoint, provincie, straal_m) -> dict:
    rev_wkts = [r["wkt"] for r in run_sparql(graph, REV_WKT_Q) if r.get("wkt")]
    try:
        gebied = NB.provincie_polygon(provincie, kkg_endpoint)
        if gebied is None:
            return {**base, "antwoord": None, "sparql": REV_WKT_Q, "herkomst": "nabijheid",
                    "rijen": [], "beschikbaar": False}
        scholen = NB.scholen_in_gebied(gebied, kkg_endpoint)
    except ConnectorError:
        return {**base, "antwoord": None, "sparql": REV_WKT_Q, "herkomst": "nabijheid",
                "rijen": [], "beschikbaar": False}
    treffers = NB.nabij(rev_wkts, scholen, straal_m)
    antwoord = (f"{len(treffers)} van de {len(rev_wkts)} REV-productiefaciliteiten in {provincie} "
                f"liggen binnen {straal_m:.0f} m van een school "
                f"({len(scholen)} scholen beschouwd).")
    return {**base, "antwoord": antwoord, "sparql": REV_WKT_Q, "herkomst": "nabijheid",
            "rijen": [{"nabij": len(treffers), "totaal": len(rev_wkts), "scholen": len(scholen)}],
            "beschikbaar": True}
