from leefomgevinglab.afvaldb import forecast as fc
from leefomgevinglab.afvaldb import store


def test_holt_op_lineaire_reeks_extrapoleert():
    jaren = list(range(2010, 2021))            # 11 jaar
    y = [10.0 + 2.0 * i for i in range(11)]     # perfect lineair, helling 2/jaar
    out = fc.forecast_holt(jaren, y, tot_jaar=2023)
    assert [r["jaar"] for r in out] == [2021, 2022, 2023]
    # 2021 ~ 32 (10 + 2*11); tolerantie voor smoothing
    assert abs(out[0]["verwacht"] - 32.0) < 2.0
    assert out[0]["ondergrens"] <= out[0]["verwacht"] <= out[0]["bovengrens"]


def test_te_korte_reeks_geeft_leeg():
    assert fc.forecast_holt([2018, 2019, 2020], [1.0, 2.0, 3.0], tot_jaar=2025) == []


def test_ondergrens_geklemd_op_nul():
    jaren = list(range(2010, 2021))
    y = [100.0 - 9.0 * i for i in range(11)]    # dalend, richting 0
    out = fc.forecast_holt(jaren, y, tot_jaar=2035)
    assert all(r["ondergrens"] >= 0 for r in out)


def test_bouw_forecasts_schrijft_tabel(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2010 + i,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 10.0 + i, "eenheid": "kton"}
        for i in range(8)])
    n = fc.bouw_forecasts(con, tot_jaar=2025)
    assert n == 1
    rows = store.forecast_rows(con, "PV24", "GFT-afval")
    assert rows and rows[0]["methode"] == "holt"
    assert max(r["jaar"] for r in rows) == 2025
