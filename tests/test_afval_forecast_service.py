from leefomgevinglab.afvaldb import store
from leefomgevinglab.usecases.afval import service


def _db(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2018 + i,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 10.0 + i, "eenheid": "kton"} for i in range(3)])
    store.insert_forecasts(con, [
        {"regio_code": "PV24", "afvalstroom_canoniek": "GFT-afval", "jaar": 2030,
         "verwacht": 18.0, "ondergrens": 15.0, "bovengrens": 21.0, "methode": "holt"}])
    store.insert_feiten(con, [
        {"bron_id": "afvalfonds-2023", "regio_code": "NL", "jaar": 2023,
         "afvalstroom_canoniek": "Verpakkingsglas", "euralcode": None, "verwerking": "R",
         "indicator_type": "recyclingpercentage", "hoeveelheid": 86.0, "eenheid": "pct"}])
    con.close()
    return p


def test_forecast_historie_en_toekomst(tmp_path):
    p = _db(tmp_path)
    f = service.forecast(p, "PV24", "GFT-afval")
    assert [h["jaar"] for h in f["historie"]] == [2018, 2019, 2020]
    assert f["forecast"][0]["jaar"] == 2030 and f["forecast"][0]["verwacht"] == 18.0
    assert f["methode"] == "holt"


def test_extra_context_recyclingpercentage(tmp_path):
    p = _db(tmp_path)
    e = service.extra_context(p, "Verpakkingsglas")
    assert e["recyclingpercentage"] == 86.0
    assert "afvalfonds" in (e["recycling_bron"] or "").lower()
