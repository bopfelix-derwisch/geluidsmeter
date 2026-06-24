"""UC: externe-veiligheid-waarschuwing — REV-EXPLOSIEaandachtsgebieden op een punt.

Per herkomst (inrichting/buisleiding/basisnet) een laag-query op de explosie-laag; verzamelt de
treffers (herkomst + bron + stof) en bouwt een conservatieve waarschuwing. Een laag-fout
(ConnectorError) propageert: liever geen blok dan een onvolledige 'veilig'-indruk.
"""
from leefomgevinglab.usecases.vergunningen import resolver

BRON = "REV (rev-portaal.nl)"


def check_aandachtsgebieden(locatie: dict, ev_connector, lagen: dict, max_n: int = 5) -> dict | None:
    rd = resolver.wgs84_naar_rd(locatie["lat"], locatie["lon"])
    aandachtsgebieden = []
    for herkomst, laag in lagen.items():
        for t in ev_connector.aandachtsgebieden_op_punt(laag, rd, max_n):   # ConnectorError propageert
            aandachtsgebieden.append({"herkomst": herkomst, "bron": t.get("bron"),
                                      "maatgevende_stof": t.get("maatgevende_stof")})
    if not aandachtsgebieden:
        return None
    herkomsten = ", ".join(sorted({a["herkomst"] for a in aandachtsgebieden}))
    bronnen = sorted({a["bron"] for a in aandachtsgebieden if a.get("bron")})
    stoffen = sorted({a["maatgevende_stof"] for a in aandachtsgebieden if a.get("maatgevende_stof")})
    detail = "; ".join(x for x in [
        "herkomst: " + herkomsten,
        ("bron: " + ", ".join(bronnen)) if bronnen else "",
        ("stof: " + ", ".join(stoffen)) if stoffen else "",
    ] if x)
    waarschuwing = (
        f"Let op: deze locatie ligt in een explosieaandachtsgebied ({detail}). Voor een kwetsbaar "
        "gebouw gelden hier aanvullende eisen; raadpleeg het bevoegd gezag."
    )
    return {
        "aandachtsgebieden": aandachtsgebieden,
        "waarschuwing": waarschuwing,
        "locatie_rd": list(rd),
        "bron": BRON,
    }
