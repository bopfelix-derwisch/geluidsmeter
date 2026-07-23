from pathlib import Path
from leefomgevinglab.afvaldb.loaders import clo

FIX = Path(__file__).parent / "fixtures" / "afval" / "clo_huishoudelijk.csv"


def test_parse_csv():
    recs = clo.parse_csv(str(FIX))
    assert {r["jaar"] for r in recs} >= {2000, 2020}
    r2020 = next(r for r in recs if r["jaar"] == 2020)
    assert r2020["regio_code"] == "NL"
    assert r2020["afvalstroom_canoniek"] == "Totaal huishoudelijk afval"
    assert r2020["indicator_type"] == "per_inwoner"
    assert r2020["eenheid"] == "kg_per_inwoner"
    assert r2020["hoeveelheid"] == 495.0
    assert r2020["bron_id"] == "clo-nl014437"
