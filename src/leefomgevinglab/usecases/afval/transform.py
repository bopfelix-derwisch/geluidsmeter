"""Pure omzetting van CBS 83558NED TypedDataSet-rijen naar tidy afval-aggregaat.

CBS levert afvalsoorten en verwerkingsmethoden als losse topic-kolommen. Deze
module selecteert een curated set afvalstromen en berekent circulariteit uit de
verwerkingsmethode-kolommen. Alleen provincies (Regiokenmerken-code 'PV..') en
jaarperioden ('..JJ00') worden meegenomen.
"""

# Curated afvalstromen: label -> CBS-topic-key (waarden in 1000 ton = kton).
AFVALSTROMEN: dict[str, str] = {
    "Totaal gemeentelijk afval": "TotaalGemeentelijkAfval_1",
    "Totaal huishoudelijk afval": "TotaalHuishoudelijkAfval_2",
    "Huishoudelijk restafval": "HuishoudelijkRestafval_3",
    "GFT-afval": "GFTAfval_6",
    "Oud papier en karton": "OudPapierEnKarton_7",
    "Verpakkingsglas": "Verpakkingsglas_9",
    "Kunststof verpakkingen": "KunststofVerpakkingen_10",
}

# Verwerking (totaal gemeentelijk afval) voor circulariteit.
_NUTTIG = "NuttigeToepassing_174"
_VERBRANDEN = "Verbranden_177"
_STORTEN = "Storten_178"


def is_provincie(regio_code: str) -> bool:
    return regio_code.strip().startswith("PV")


def periode_to_jaar(periode: str) -> int | None:
    if not periode.endswith("JJ00"):
        return None
    try:
        return int(periode[:4])
    except ValueError:
        return None


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def tidy_volumes(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        code = row.get("Regiokenmerken", "")
        if not is_provincie(code):
            continue
        jaar = periode_to_jaar(row.get("Perioden", ""))
        if jaar is None:
            continue
        for label, key in AFVALSTROMEN.items():
            val = _num(row.get(key))
            if val is None:
                continue
            out.append({"regio_code": code.strip(), "jaar": jaar,
                        "afvalstroom": label, "hoeveelheid_kton": val})
    return out


def circulariteit_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        code = row.get("Regiokenmerken", "")
        if not is_provincie(code):
            continue
        jaar = periode_to_jaar(row.get("Perioden", ""))
        if jaar is None:
            continue
        nuttig = _num(row.get(_NUTTIG))
        verbranden = _num(row.get(_VERBRANDEN))
        storten = _num(row.get(_STORTEN))
        if None in (nuttig, verbranden, storten):
            continue
        verwijderen = verbranden + storten
        noemer = nuttig + verwijderen
        if noemer <= 0:
            continue
        out.append({"regio_code": code.strip(), "jaar": jaar,
                    "nuttige_toepassing_kton": nuttig,
                    "verwijderen_kton": verwijderen,
                    "circulariteit_pct": nuttig / noemer * 100})
    return out
