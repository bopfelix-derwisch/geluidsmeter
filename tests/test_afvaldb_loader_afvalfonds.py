from pathlib import Path
from leefomgevinglab.afvaldb.loaders import afvalfonds as af

FIX = Path(__file__).parent / "fixtures" / "afval" / "afvalfonds_recycling.csv"


def test_parse_rows_canoniseert_en_slaat_onbekend_over():
    recs = af.parse_rows([
        {"materiaal": "Glas", "recycling_pct": 86.0},
        {"materiaal": "Kunststof", "recycling_pct": 55.0},
        {"materiaal": "Onbekend materiaal", "recycling_pct": 10.0},
    ], jaar=2023)
    stromen = {r["afvalstroom_canoniek"]: r for r in recs}
    assert "Verpakkingsglas" in stromen
    assert stromen["Verpakkingsglas"]["hoeveelheid"] == 86.0
    assert stromen["Verpakkingsglas"]["indicator_type"] == "recyclingpercentage"
    assert stromen["Verpakkingsglas"]["eenheid"] == "pct"
    assert stromen["Verpakkingsglas"]["regio_code"] == "NL"
    assert stromen["Verpakkingsglas"]["bron_id"] == "afvalfonds-2023"
    assert "Kunststof verpakkingen" in stromen
    # onbekend materiaal levert geen record
    assert len(recs) == 2


def test_parse_csv():
    recs = af.parse_csv(str(FIX), jaar=2023)
    assert any(r["afvalstroom_canoniek"] == "Oud papier en karton" for r in recs)
