# tests/test_afval_ingest.py
import importlib.util
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "11_fetch_afval_aggregaat.py"
_spec = importlib.util.spec_from_file_location("ingest_afval", SPEC)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


def test_bouw_aggregaat_filtert_en_bouwt_geojson():
    rows = [
        {"Regiokenmerken": "PV24    ", "Perioden": "2020JJ00",
         "TotaalGemeentelijkAfval_1": 100, "GFTAfval_6": 12,
         "NuttigeToepassing_174": 75, "Verbranden_177": 20, "Storten_178": 5},
        {"Regiokenmerken": "NL01    ", "Perioden": "2020JJ00",
         "TotaalGemeentelijkAfval_1": 9999},
    ]
    provincie_features = [
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV24", "naam": "Flevoland", "code": "24"}},
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV30", "naam": "Zuid-Holland", "code": "30"}},
    ]
    vol, circ, geo = ingest.bouw_aggregaat(rows, provincie_features)
    assert set(vol["regio_code"]) == {"PV24"}
    assert set(circ["regio_code"]) == {"PV24"}
    # alleen provincies die in de data voorkomen
    ids = [f["properties"]["identificatie"] for f in geo["features"]]
    assert ids == ["PV24"]
    # GeoJSON-properties beperkt tot identificatie + naam
    assert set(geo["features"][0]["properties"]) == {"identificatie", "naam"}
