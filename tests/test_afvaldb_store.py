from leefomgevinglab.afvaldb import store


def _con(tmp_path):
    return store.open_db(str(tmp_path / "afval.duckdb"))


def test_schema_en_feiten_roundtrip(tmp_path):
    con = _con(tmp_path)
    store.upsert_bron(con, {"bron_id": "cbs-83558NED", "naam": "CBS", "url": "u",
                            "licentie": "CC-BY 4.0", "type": "api", "opgehaald_op": "2026-07-23"})
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2019,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 10.0, "eenheid": "kton"},
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"},
    ])
    s = store.series(con, "PV24", "GFT-afval")
    assert s == [(2019, 10.0), (2020, 12.0)]


def test_upsert_bron_is_idempotent(tmp_path):
    con = _con(tmp_path)
    b = {"bron_id": "x", "naam": "X", "url": "u", "licentie": "l", "type": "api", "opgehaald_op": "2026-07-23"}
    store.upsert_bron(con, b)
    store.upsert_bron(con, {**b, "naam": "X2"})
    rows = con.execute("SELECT naam FROM bron WHERE bron_id='x'").fetchall()
    assert rows == [("X2",)]


def test_forecast_roundtrip(tmp_path):
    con = _con(tmp_path)
    store.insert_forecasts(con, [
        {"regio_code": "PV24", "afvalstroom_canoniek": "GFT-afval", "jaar": 2030,
         "verwacht": 15.0, "ondergrens": 12.0, "bovengrens": 18.0, "methode": "holt"}])
    fr = store.forecast_rows(con, "PV24", "GFT-afval")
    assert fr[0]["jaar"] == 2030 and fr[0]["verwacht"] == 15.0
