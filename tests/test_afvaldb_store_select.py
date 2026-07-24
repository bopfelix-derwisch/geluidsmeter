import duckdb
import pytest
from leefomgevinglab.afvaldb import store


def _seed(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.upsert_bron(con, {"bron_id": "cbs-83558NED", "naam": "CBS", "url": "u",
                            "licentie": "CC-BY 4.0", "type": "api", "opgehaald_op": "2026-07-23"})
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"}])
    con.close()
    return p


def test_bronnen(tmp_path):
    p = _seed(tmp_path)
    con = store.open_db(p)
    b = store.bronnen(con)
    assert b[0]["bron_id"] == "cbs-83558NED"
    assert b[0]["licentie"] == "CC-BY 4.0"
    assert set(b[0]) == {"bron_id", "naam", "url", "licentie", "type", "opgehaald_op"}


def test_run_select_geeft_dicts(tmp_path):
    p = _seed(tmp_path)
    con = store.open_readonly(p)
    rijen = store.run_select(con, "SELECT regio_code, hoeveelheid FROM afval_feit")
    assert rijen == [{"regio_code": "PV24", "hoeveelheid": 12.0}]


def test_open_readonly_weigert_schrijven(tmp_path):
    p = _seed(tmp_path)
    con = store.open_readonly(p)
    with pytest.raises(duckdb.Error):
        con.execute("DELETE FROM afval_feit")


def test_open_readonly_blokkeert_bestandstoegang(tmp_path):
    p = _seed(tmp_path)
    con = store.open_readonly(p)
    with pytest.raises(duckdb.Error):
        con.execute("SELECT content FROM read_text('/etc/hostname')")


def test_run_select_begrenst_rijen(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2018 + i,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 1.0 * i, "eenheid": "kton"} for i in range(3)])
    # zonder LIMIT in de query begrenst run_select toch tot max_rows
    rijen = store.run_select(con, "SELECT * FROM afval_feit", max_rows=2)
    assert len(rijen) == 2
