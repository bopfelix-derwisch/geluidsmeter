"""UC-03a: regels opzoeken bij de DSO, ingepakt in een conservatief antwoordcontract."""
from leefomgevinglab.connectors.base import ConnectorError

DISCLAIMER = (
    "Indicatief, geen juridisch besluit. De getoonde regels zijn een ruwe weergave "
    "van de Registratie Toepasbare Regels."
)
VANGNET = (
    "Raadpleeg het bevoegd gezag of het Omgevingsloket (omgevingswet.overheid.nl) "
    "voor de officiele vergunning- of meldingsplicht."
)
BRON = "DSO Registratie Toepasbare Regels (Samengestelde RTR Services)"


def regels_opzoeken(activiteit: str, locatie: dict | None, connector) -> dict:
    base = {
        "vraag": activiteit,
        "bron": BRON,
        "onzekerheid": True,
        "disclaimer": DISCLAIMER,
        "vangnet": VANGNET,
    }
    try:
        regels = connector.bepaal_regels(activiteit, locatie)
    except ConnectorError:
        return {**base, "regels_ruw": None, "beschikbaar": False}
    return {**base, "regels_ruw": regels, "beschikbaar": True}
