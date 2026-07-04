from datetime import datetime, timezone

import httpx

from leefomgevinglab.usecases import wfs_kwaliteit as wk

NU = datetime(2026, 7, 4, tzinfo=timezone.utc)

# geldig vierkant vs. self-intersecting "bowtie" (invalide)
_VALID = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
_INVALID = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


def _feat(props, geom=_VALID):
    return {"type": "Feature", "properties": props, "geometry": geom}


def test_metrics_geometrie_en_bron_null():
    feats = [
        _feat({"bedrijfsnaam": "A", "identificatie": "1"}, _VALID),
        _feat({"naamexploitant": "B", "identificatie": "2"}, _INVALID),
        _feat({"identificatie": "3"}, None),                       # bron leeg + geom null
    ]
    m = wk._metrics_uit_sample(feats, NU)
    assert m["sample"] == 3
    assert m["geom_valid"] == 1
    assert m["geom_invalid"] == 1
    assert m["geom_null"] == 1
    assert m["bron_null"] == 1
    assert m["geom_invalid_pct"] == round(100 / 3, 1)


def test_metrics_verlopen_en_duplicaten_en_bronhouders():
    feats = [
        _feat({"bronhouder": "RWS", "identificatie": "x", "eind_geldigheid": "2020-01-01T00:00:00Z"}),
        _feat({"bronhouder": "RWS", "identificatie": "x"}),        # duplicaat (zelfde id+geom)
        _feat({"bronhouder": "Gem", "identificatie": "y", "eind_geldigheid": "2099-01-01T00:00:00Z"}),
    ]
    m = wk._metrics_uit_sample(feats, NU)
    assert m["verlopen"] == 1
    assert m["duplicaten"] == 1
    assert m["n_bronhouders"] == 2


def test_metrics_stof_null():
    feats = [_feat({"bedrijfsnaam": "A", "maatgevende_stof": None, "identificatie": "1"}),
             _feat({"bedrijfsnaam": "B", "maatgevende_stof": "propaan", "identificatie": "2"})]
    m = wk._metrics_uit_sample(feats, NU)
    assert m["stof_null"] == 1


def test_scan_lagen_degradeert_per_laag(monkeypatch):
    def fake_get(self, url, params=None):
        laag = params.get("typeNames")
        if params.get("resultType") == "hits":
            if laag == "kapot":
                raise httpx.ConnectError("down")
            return httpx.Response(200, text='numberMatched="42" numberReturned="0"')
        return httpx.Response(200, json={"features": [_feat({"bedrijfsnaam": "A", "identificatie": "1"})]})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    out = wk.scan_lagen("https://x/wfs", ["goed", "kapot"], sample_n=10)
    rows = {r["laag"]: r for r in out["lagen"]}
    assert rows["goed"]["totaal"] == 42
    assert rows["goed"]["geom_valid"] == 1
    assert rows["kapot"]["error"] is not None          # degradeert, blokkeert de rest niet
    assert rows["kapot"]["totaal"] is None
    assert out["wfs_url"] == "https://x/wfs" and out["sample_n"] == 10
