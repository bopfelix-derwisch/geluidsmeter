"""Crosswalk: bron-specifieke sleutels -> canonieke afvalstroom (CBS↔AMICE-brug)."""
from leefomgevinglab.usecases.afval.transform import AFVALSTROMEN

# CBS-topic -> canoniek: exact de bestaande AFVALSTROMEN-mapping (key->label omgedraaid).
_CBS = [{"bron_type": "cbs_topic", "bron_sleutel": key, "afvalstroom_canoniek": label}
        for label, key in AFVALSTROMEN.items()]

# Afvalfonds-materiaal -> canoniek.
_AFVALFONDS = [
    {"bron_type": "afvalfonds_materiaal", "bron_sleutel": "Glas", "afvalstroom_canoniek": "Verpakkingsglas"},
    {"bron_type": "afvalfonds_materiaal", "bron_sleutel": "Papier en karton", "afvalstroom_canoniek": "Oud papier en karton"},
    {"bron_type": "afvalfonds_materiaal", "bron_sleutel": "Kunststof", "afvalstroom_canoniek": "Kunststof verpakkingen"},
]

# Euralcode -> canoniek (AMICE-aansluiting; selectie relevant voor de curated stromen).
_EURAL = [
    {"bron_type": "euralcode", "bron_sleutel": "200108", "afvalstroom_canoniek": "GFT-afval"},
    {"bron_type": "euralcode", "bron_sleutel": "200101", "afvalstroom_canoniek": "Oud papier en karton"},
    {"bron_type": "euralcode", "bron_sleutel": "200102", "afvalstroom_canoniek": "Verpakkingsglas"},
    {"bron_type": "euralcode", "bron_sleutel": "200301", "afvalstroom_canoniek": "Huishoudelijk restafval"},
]

# CLO-indicator -> canoniek.
_CLO = [
    {"bron_type": "clo_indicator", "bron_sleutel": "afval-huishoudens-per-inwoner", "afvalstroom_canoniek": "Totaal huishoudelijk afval"},
]

CROSSWALK = _CBS + _AFVALFONDS + _EURAL + _CLO


def canoniek(bron_type: str, bron_sleutel: str) -> str | None:
    for row in CROSSWALK:
        if row["bron_type"] == bron_type and row["bron_sleutel"] == bron_sleutel:
            return row["afvalstroom_canoniek"]
    return None
