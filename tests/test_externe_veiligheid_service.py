import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import externe_veiligheid as ev

LOC = {"lat": 51.757, "lon": 5.339}
LAGEN = {"inrichting": "rev_public:ev_explosieaandachtsgebieden",
         "buisleiding": "rev_public:bl_explosieaandachtsgebieden",
         "basisnet": "rev_public:bn_explosieaandachtsgebieden"}


class _Conn:
    def __init__(self, per_laag=None, error_laag=None):
        self._per = per_laag or {}
        self._err = error_laag

    def aandachtsgebieden_op_punt(self, laag, geo_rd, max_n=5):
        if self._err == laag:
            raise ConnectorError("down")
        return self._per.get(laag, [])


def _patch_rd(monkeypatch):
    monkeypatch.setattr(ev.resolver, "wgs84_naar_rd", lambda lat, lon: (151658.2, 418729.5))


def test_treffer_geeft_waarschuwing(monkeypatch):
    _patch_rd(monkeypatch)
    conn = _Conn(per_laag={"rev_public:ev_explosieaandachtsgebieden":
                           [{"bron": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}]})
    out = ev.check_aandachtsgebieden(LOC, conn, LAGEN)
    assert out is not None
    a = out["aandachtsgebieden"][0]
    assert a["herkomst"] == "inrichting"
    assert a["bron"] == "Autobedrijf Mekes"
    assert a["maatgevende_stof"] == "propaan"
    assert "explosieaandachtsgebied" in out["waarschuwing"]
    assert "Autobedrijf Mekes" in out["waarschuwing"]
    assert "kwetsbaar gebouw" in out["waarschuwing"]
    assert out["locatie_rd"] == [151658.2, 418729.5]
    assert out["bron"].startswith("REV")


def test_geen_treffer_geeft_none(monkeypatch):
    _patch_rd(monkeypatch)
    assert ev.check_aandachtsgebieden(LOC, _Conn(), LAGEN) is None


def test_meerdere_herkomsten(monkeypatch):
    _patch_rd(monkeypatch)
    conn = _Conn(per_laag={
        "rev_public:ev_explosieaandachtsgebieden": [{"bron": "A", "maatgevende_stof": "propaan"}],
        "rev_public:bl_explosieaandachtsgebieden": [{"bron": "Gasunie", "maatgevende_stof": "aardgas"}]})
    out = ev.check_aandachtsgebieden(LOC, conn, LAGEN)
    herkomsten = {a["herkomst"] for a in out["aandachtsgebieden"]}
    assert herkomsten == {"inrichting", "buisleiding"}


def test_laag_fout_propageert(monkeypatch):
    _patch_rd(monkeypatch)
    conn = _Conn(error_laag="rev_public:bl_explosieaandachtsgebieden")
    with pytest.raises(ConnectorError):
        ev.check_aandachtsgebieden(LOC, conn, LAGEN)


def test_dubbele_treffers_worden_ontdubbeld(monkeypatch):
    _patch_rd(monkeypatch)
    dup = {"bron": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}
    conn = _Conn(per_laag={"rev_public:ev_explosieaandachtsgebieden": [dup, dict(dup)]})
    out = ev.check_aandachtsgebieden(LOC, conn, LAGEN)
    assert len(out["aandachtsgebieden"]) == 1
