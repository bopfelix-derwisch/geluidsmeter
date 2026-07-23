"""CBS-loader: 83558NED TypedDataSet -> canonieke afval_feit-records (provincies + NL)."""
from leefomgevinglab.usecases.afval.transform import AFVALSTROMEN, periode_to_jaar

BRON = {"bron_id": "cbs-83558NED", "naam": "CBS StatLine 83558NED (Gemeentelijke afvalstoffen)",
        "url": "https://opendata.cbs.nl/ODataApi/OData/83558NED", "licentie": "CC-BY 4.0",
        "type": "api", "opgehaald_op": None}  # opgehaald_op vult het ingest-script


def _regio(code: str) -> str | None:
    c = code.strip()
    if c.startswith("PV"):
        return c
    if c.startswith("NL"):
        return "NL"
    return None


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def parse(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        regio = _regio(row.get("Regiokenmerken", ""))
        if regio is None:
            continue
        jaar = periode_to_jaar(row.get("Perioden", ""))
        if jaar is None:
            continue
        for label, key in AFVALSTROMEN.items():
            val = _num(row.get(key))
            if val is None:
                continue
            out.append({"bron_id": "cbs-83558NED", "regio_code": regio, "jaar": jaar,
                        "afvalstroom_canoniek": label, "euralcode": None,
                        "verwerking": "onbekend", "indicator_type": "volume",
                        "hoeveelheid": val, "eenheid": "kton"})
    return out
