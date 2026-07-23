import json
import pandas as pd
import pytest
from leefomgevinglab.usecases.afval import service


@pytest.fixture
def data_dir(tmp_path):
    pd.DataFrame([
        {"regio_code": "PV24", "jaar": 2019, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 10.0},
        {"regio_code": "PV24", "jaar": 2020, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 12.0},
        {"regio_code": "PV30", "jaar": 2020, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 40.0},
    ]).to_parquet(tmp_path / "aggregaat.parquet", index=False)
    pd.DataFrame([
        {"regio_code": "PV24", "jaar": 2019, "nuttige_toepassing_kton": 8.0,
         "verwijderen_kton": 2.0, "circulariteit_pct": 80.0},
        {"regio_code": "PV24", "jaar": 2020, "nuttige_toepassing_kton": 9.0,
         "verwijderen_kton": 3.0, "circulariteit_pct": 75.0},
    ]).to_parquet(tmp_path / "circulariteit.parquet", index=False)
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV24", "naam": "Flevoland"}},
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV30", "naam": "Zuid-Holland"}},
    ]}
    (tmp_path / "provincies.geojson").write_text(json.dumps(geo))
    return str(tmp_path)


def test_meta(data_dir):
    m = service.meta(data_dir)
    assert {"code": "PV24", "naam": "Flevoland"} in m["regios"]
    assert "GFT-afval" in m["afvalstromen"]
    assert m["jaren"] == [2019, 2020]
    assert {"key": "circulariteit", "label": "Circulariteit (%)"} in m["indicatoren"]
    assert "CC-BY" in m["licentie"]


def test_choropleth_volume(data_dir):
    fc = service.choropleth(data_dir, afvalstroom="GFT-afval", jaar=2020, indicator="volume")
    vals = {f["properties"]["identificatie"]: f["properties"]["value"] for f in fc["features"]}
    assert vals["PV24"] == 12.0
    assert vals["PV30"] == 40.0


def test_choropleth_circulariteit_ontbrekend_is_none(data_dir):
    fc = service.choropleth(data_dir, afvalstroom="GFT-afval", jaar=2020, indicator="circulariteit")
    vals = {f["properties"]["identificatie"]: f["properties"]["value"] for f in fc["features"]}
    assert vals["PV24"] == 75.0
    assert vals["PV30"] is None   # geen circulariteit-rij voor PV30


def test_trend(data_dir):
    tr = service.trend(data_dir, regio="PV24", afvalstroom="GFT-afval")
    assert tr["naam"] == "Flevoland"
    jaren = [p["jaar"] for p in tr["reeks"]]
    assert jaren == [2019, 2020]
    assert tr["reeks"][1]["hoeveelheid_kton"] == 12.0
    assert tr["reeks"][1]["circulariteit_pct"] == 75.0


def test_choropleth_circulariteit_nan_wordt_none(tmp_path):
    import math
    import json
    # aggregaat met PV30-rij zodat de regio bestaat
    pd.DataFrame([
        {"regio_code": "PV24", "jaar": 2020, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 12.0},
        {"regio_code": "PV30", "jaar": 2020, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 40.0},
    ]).to_parquet(tmp_path / "aggregaat.parquet", index=False)
    # circulariteit met NaN voor PV30
    pd.DataFrame([
        {"regio_code": "PV24", "jaar": 2020, "nuttige_toepassing_kton": 9.0,
         "verwijderen_kton": 3.0, "circulariteit_pct": 75.0},
        {"regio_code": "PV30", "jaar": 2020, "nuttige_toepassing_kton": 0.0,
         "verwijderen_kton": 0.0, "circulariteit_pct": float("nan")},
    ]).to_parquet(tmp_path / "circulariteit.parquet", index=False)
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV24", "naam": "Flevoland"}},
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV30", "naam": "Zuid-Holland"}},
    ]}
    (tmp_path / "provincies.geojson").write_text(json.dumps(geo))
    fc = service.choropleth(str(tmp_path), afvalstroom="GFT-afval", jaar=2020, indicator="circulariteit")
    vals = {f["properties"]["identificatie"]: f["properties"]["value"] for f in fc["features"]}
    assert vals["PV24"] == 75.0
    assert vals["PV30"] is None  # NaN in parquet moet None worden, niet NaN
