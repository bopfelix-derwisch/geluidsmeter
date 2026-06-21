"""Data-chatbot service: NL-vraag -> SPARQL -> antwoord met conservatief contract."""
from leefomgevinglab.ld.store import run_sparql
from leefomgevinglab.usecases.datavraag.nl2sparql import kies_sparql

DISCLAIMER = ("Indicatief, geen juridisch/officieel cijfer. De telling betreft REV-productiefaciliteiten "
             "(de open REV-laag kent geen Seveso-vlag).")
VANGNET = "Raadpleeg de bronhouder (REV/PDOK, Kadaster) of het bevoegd gezag voor officiele cijfers."


def beantwoord(vraag: str, graph, grounding_txt: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    base = {"vraag": vraag, "onzekerheid": True, "disclaimer": DISCLAIMER, "vangnet": VANGNET,
            "bron": "eigen REV-LD (PDOK) + Kadaster KKG"}
    if graph is None:
        return {**base, "antwoord": None, "sparql": None, "herkomst": None, "rijen": [], "beschikbaar": False}
    sparql, herkomst = kies_sparql(vraag, grounding_txt, llm_base_url, model, timeout_s)
    try:
        rijen = run_sparql(graph, sparql)
    except Exception:
        return {**base, "antwoord": None, "sparql": sparql, "herkomst": herkomst, "rijen": [], "beschikbaar": False}
    # Eenvoudige verwoording: toon de eerste rij/telling
    if rijen and "n" in rijen[0]:
        antwoord = f"Gevonden: {rijen[0]['n']} (REV-productiefaciliteiten)."
    else:
        antwoord = f"{len(rijen)} resultaten."
    return {**base, "antwoord": antwoord, "sparql": sparql, "herkomst": herkomst,
            "rijen": rijen, "beschikbaar": True}
