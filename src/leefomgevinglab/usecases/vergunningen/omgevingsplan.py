"""UC: 'wat geldt hier' — geldende omgevingsplan-regels op een punt via Ozon.

Type-gefilterd op de relevante regel-soorten; top-1 best-effort regelteksten; begrensd.
"""
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import resolver

RELEVANTE_TYPES = ("Omgevingsplan", "Omgevingsverordening", "Waterschapsverordening")
_PRIORITEIT = {"Omgevingsplan": 0, "Omgevingsverordening": 1, "Waterschapsverordening": 2}
BRON = "DSO Presenteren (Ozon)"


def omgevingsplan_op_locatie(locatie: dict, ozon_connector, max_regelingen: int = 3,
                             max_regelteksten: int = 5) -> dict | None:
    rd = resolver.wgs84_naar_rd(locatie["lat"], locatie["lon"])
    regelingen = ozon_connector.regelingen_op_punt(rd)   # ConnectorError propageert
    relevant = [r for r in regelingen if r.get("type") in RELEVANTE_TYPES]
    if not relevant:
        return None
    relevant.sort(key=lambda r: _PRIORITEIT.get(r.get("type"), 99))
    top = relevant[0]
    regelteksten = []
    try:
        regelteksten = ozon_connector.regelteksten_op_punt(top["uri"], rd, max_regelteksten)
    except ConnectorError:
        regelteksten = []
    return {
        "regelingen": [{"titel": r["titel"], "type": r["type"], "bevoegd_gezag": r["bevoegd_gezag"]}
                       for r in relevant[:max_regelingen]],
        "top_regeling": top["titel"],
        "regelteksten": regelteksten,
        "locatie_rd": list(rd),
        "aantal_beperkt_tot": max_regelingen,
        "bron": BRON,
    }
