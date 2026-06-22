"""UC-03a: regels opzoeken bij de DSO (Zoek -> Qwen -> typeringen -> indieningsvereisten).

Gelaagd, conservatief antwoordcontract: elke laag degradeert onafhankelijk; alternatieven
blijven altijd zichtbaar; geen stellige vergunninguitspraak.
"""
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import resolver

DISCLAIMER = (
    "Indicatief, geen juridisch besluit. De getoonde regels zijn een ruwe weergave "
    "van de Registratie Toepasbare Regels."
)
VANGNET = (
    "Raadpleeg het bevoegd gezag of het Omgevingsloket (omgevingswet.overheid.nl) "
    "voor de officiele vergunning- of meldingsplicht."
)
BRON = "DSO Toepasbare Regels (Zoek + RTR + Uitvoeren)"


def _contract_basis(activiteit: str) -> dict:
    return {"vraag": activiteit, "bron": BRON, "onzekerheid": True,
            "disclaimer": DISCLAIMER, "vangnet": VANGNET}


def _onbeschikbaar(activiteit: str) -> dict:
    return {**_contract_basis(activiteit), "beschikbaar": False, "gekozen_werkzaamheid": None,
            "alternatieven": [], "typeringen": None, "indieningsvereisten": None,
            "indieningsvereisten_status": "niet_beschikbaar", "locatie_rd": None}


def regels_opzoeken(activiteit: str, locatie: dict, zoek_connector, dso_connector,
                    llm_cfg: dict) -> dict:
    # Laag 1: zoek werkzaamheden
    try:
        kandidaten = zoek_connector.zoek_werkzaamheden(activiteit)
    except ConnectorError:
        return _onbeschikbaar(activiteit)
    if not kandidaten:
        return _onbeschikbaar(activiteit)

    # Laag 2: Qwen kiest
    keuze = resolver.kies_werkzaamheid(activiteit, kandidaten, **llm_cfg)
    gekozen = keuze["gekozen"]
    if gekozen is None:
        return _onbeschikbaar(activiteit)
    alternatieven = [{"urn": k["urn"], "omschrijving": k["omschrijving"]}
                     for k in kandidaten if k["urn"] != gekozen["urn"]]
    ref = gekozen["functioneleStructuurRef"]

    # Laag 3: WGS84 -> RD
    rd = resolver.wgs84_naar_rd(locatie["lat"], locatie["lon"])

    # Laag 4: regelbeheerobject-typeringen
    try:
        typ_resp = dso_connector.bepaal_typeringen([ref], rd)
        typeringen = (typ_resp[0].get("regelbeheerobjecten") if typ_resp else []) or []
    except ConnectorError:
        typeringen = None

    # Laag 5: indieningsvereisten (best-effort)
    # Noot (laag 5): de status `vereist_nadere_vragen` uit de spec wordt nog niet geëmitteerd —
    # dat vereist een geverifieerde 200-respons van `indieningsvereisten/_bepaal` om "open vragen" te
    # herkennen (in oefen niet reproduceerbaar gekregen). De statuswaarde is gereserveerd voor een
    # vervolg; nu geldt: niet-lege respons = `beschikbaar`, lege = `niet_beschikbaar_op_locatie`,
    # bronfout = `bron_tijdelijk_niet_beschikbaar`.
    indieningsvereisten = None
    iv_status = "niet_beschikbaar_op_locatie"
    try:
        iv = dso_connector.bepaal_indieningsvereisten([ref], rd)
        if iv:
            indieningsvereisten = iv
            iv_status = "beschikbaar"
    except ConnectorError:
        iv_status = "bron_tijdelijk_niet_beschikbaar"

    return {**_contract_basis(activiteit), "beschikbaar": True,
            "gekozen_werkzaamheid": {
                "urn": gekozen["urn"], "omschrijving": gekozen["omschrijving"],
                "match_onderbouwing": keuze["match_onderbouwing"],
                "zekerheid_match": keuze["zekerheid_match"]},
            "alternatieven": alternatieven,
            "typeringen": typeringen,
            "indieningsvereisten": indieningsvereisten,
            "indieningsvereisten_status": iv_status,
            "locatie_rd": list(rd)}
