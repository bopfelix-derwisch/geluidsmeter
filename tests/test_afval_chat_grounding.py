from leefomgevinglab.afvaldb import store
from leefomgevinglab.usecases.afval import chat


def test_provincie_map_volledig():
    assert chat.PROVINCIE_NAMEN["PV24"] == "Flevoland"
    assert chat.PROVINCIE_NAMEN["PV28"] == "Zuid-Holland"
    assert len(chat.PROVINCIE_NAMEN) == 12


def test_bouw_grounding_bevat_schema_en_distinct(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"}])
    g = chat.bouw_grounding(con)
    assert "afval_feit" in g and "forecast" in g
    assert "GFT-afval" in g              # distinct afvalstroom
    assert "cbs-83558NED" in g           # distinct bron
    assert "Flevoland" in g              # provincie-map
    assert "2020" in g                   # jaar-bereik
    assert "select" in g.lower()
