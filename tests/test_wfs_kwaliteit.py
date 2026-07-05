from datetime import datetime, timezone

import httpx

from leefomgevinglab.usecases import wfs_kwaliteit as wk

NU = datetime(2026, 7, 4, tzinfo=timezone.utc)
_VALID = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
_INVALID = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


def _feat(props, geom=_VALID):
    return {"type": "Feature", "properties": props, "geometry": geom}


def _metrics(feats):
    return wk._metrics_uit_sample(feats, NU, set(), set())


def test_metrics_geometrie_en_bron_null():
    m = _metrics([
        _feat({"bedrijfsnaam": "A", "identificatie": "1"}, _VALID),
        _feat({"naamexploitant": "B", "identificatie": "2"}, _INVALID),
        _feat({"identificatie": "3"}, None),
    ])
    assert (m["geom_valid"], m["geom_invalid"], m["geom_null"], m["bron_null"]) == (1, 1, 1, 1)
    assert m["geom_invalid_pct"] == round(100 / 3, 1)


def test_metrics_verlopen_duplicaten_bronhouders():
    m = _metrics([
        _feat({"bronhouder": "RWS", "identificatie": "x", "eind_geldigheid": "2020-01-01T00:00:00Z"}),
        _feat({"bronhouder": "RWS", "identificatie": "x"}),
        _feat({"bronhouder": "Gem", "identificatie": "y", "eind_geldigheid": "2099-01-01T00:00:00Z"}),
    ])
    assert (m["verlopen"], m["duplicaten"], m["n_bronhouders"]) == (1, 1, 2)


def test_metrics_verzamelt_facetten():
    bronh, act = set(), set()
    wk._metrics_uit_sample([_feat({"bronhouder": "OD Regio", "evactiviteit": "OpslagPropaan", "identificatie": "1"})],
                           NU, bronh, act)
    assert bronh == {"OD Regio"} and act == {"OpslagPropaan"}


_IMEV4 = ("identificatie", "bronhoudercode", "begin_geldigheid", "tijdstip_registratie")


def test_imev_conformiteit_telt_ontbrekende_verplichte_velden():
    feats = [
        _feat({"identificatie": "1", "bronhoudercode": "b", "begin_geldigheid": "2020", "tijdstip_registratie": "2020"}, _VALID),
        _feat({"identificatie": "2", "begin_geldigheid": "2020"}, _VALID),   # mist bronhoudercode + tijdstip -> 2
        _feat({"identificatie": "3", "bronhoudercode": "b", "begin_geldigheid": "2020", "tijdstip_registratie": "2020"}, None),  # mist geometrie -> 1
    ]
    m = wk._metrics_uit_sample(feats, NU, set(), set(), imev_velden=_IMEV4)
    assert m["imev_ontbrekend"] == 3
    assert m["imev_incompleet"] == 2
    assert m["imev_incompleet_pct"] == round(200 / 3, 1)
    assert m["imev_veld_null"] == {"bronhoudercode": 1, "tijdstip_registratie": 1}
    assert m["imev_velden_niet_in_schema"] == []


def test_imev_veld_alleen_geteld_waar_ontsloten():
    # bevoegdgezag is aanwezig-maar-leeg in de één, gevuld in de ander -> geteld waar ontsloten
    feats = [
        _feat({"identificatie": "1", "bevoegdgezag": "gemeente"}),
        _feat({"identificatie": "2", "bevoegdgezag": None}),      # leeg-maar-aanwezig -> telt
    ]
    m = wk._metrics_uit_sample(feats, NU, set(), set(),
                               imev_velden=("identificatie", "bevoegdgezag"), geometrie_verplicht=False)
    assert m["imev_veld_null"] == {"bevoegdgezag": 1}
    assert m["imev_velden_niet_in_schema"] == []


def test_imev_verplicht_veld_niet_in_schema_wordt_niet_geteld():
    # bevoegdgezag zit in GEEN enkele feature -> niet_in_schema, telt niet mee als leeg
    m = wk._metrics_uit_sample([_feat({"identificatie": "1"}, _VALID)], NU, set(), set(),
                               imev_velden=("identificatie", "bevoegdgezag"), geometrie_verplicht=False)
    assert m["imev_velden_niet_in_schema"] == ["bevoegdgezag"]
    assert m["imev_veld_null"] == {}
    assert m["imev_ontbrekend"] == 0


def test_bouw_cql():
    assert wk.bouw_cql() is None
    assert wk.bouw_cql(bronhouder="OD X") == "bronhouder='OD X'"
    assert wk.bouw_cql(activiteit="A") == "evactiviteit='A'"
    assert wk.bouw_cql("OD X", "A") == "bronhouder='OD X' AND evactiviteit='A'"
    assert wk.bouw_cql(bronhouder="d'Arc") == "bronhouder='d''Arc'"       # quote-escape


def test_lagen_uit_capabilities(monkeypatch):
    caps = '<X><Name>rev_public:ev_brandaandachtsgebieden</Name><Name>rev_public:ev_activiteiten</Name>' \
           '<Name>rev_public:ev_brandaandachtsgebieden</Name><Name>ander:iets</Name></X>'
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, params=None: httpx.Response(200, text=caps))
    lagen = wk.lagen_uit_capabilities("https://x/wfs")
    assert lagen == ["rev_public:ev_brandaandachtsgebieden", "rev_public:ev_activiteiten"]


def test_scan_lagen_met_cql_en_degradatie(monkeypatch):
    def fake_get(self, url, params=None):
        laag = params.get("typeNames")
        if params.get("resultType") == "hits":
            if laag == "kapot":
                raise httpx.ConnectError("veld bestaat niet")
            assert params.get("cql_filter") == "bronhouder='OD X'"      # filter doorgegeven
            return httpx.Response(200, text='numberMatched="7" x')
        return httpx.Response(200, json={"features": [
            _feat({"bronhouder": "OD X", "evactiviteit": "A", "identificatie": "1"})]})

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    out = wk.scan_lagen("https://x/wfs", ["goed", "kapot"], sample_n=10, cql="bronhouder='OD X'")
    rows = {r["laag"]: r for r in out["lagen"]}
    assert rows["goed"]["totaal"] == 7 and rows["goed"]["geom_valid"] == 1
    assert rows["kapot"]["error"] is not None and rows["kapot"]["totaal"] is None
    assert out["bronhouders"] == ["OD X"] and out["activiteiten"] == ["A"]
    assert out["cql"] == "bronhouder='OD X'"
