from pathlib import Path
from leefomgevinglab.afvaldb.loaders import lma_rws as lma

FIX = Path(__file__).parent / "fixtures" / "afval" / "lma_rws.csv"


def test_parse_rows_euralcode_en_verwerking():
    recs = lma.parse_rows([
        {"euralcode": "200108", "verwerking": "R", "ton": 1500000},
        {"euralcode": "999999", "verwerking": "D", "ton": 100},   # onbekende eural
    ], jaar=2022)
    gft = next(r for r in recs if r["euralcode"] == "200108")
    assert gft["afvalstroom_canoniek"] == "GFT-afval"
    assert gft["verwerking"] == "R" and gft["eenheid"] == "ton"
    assert gft["regio_code"] == "NL" and gft["bron_id"] == "lma-rws-2022"
    onbekend = next(r for r in recs if r["euralcode"] == "999999")
    assert onbekend["afvalstroom_canoniek"] is None   # eural bewaard, canoniek onbekend


def test_parse_csv():
    recs = lma.parse_csv(str(FIX), jaar=2022)
    assert any(r["afvalstroom_canoniek"] == "Verpakkingsglas" for r in recs)
