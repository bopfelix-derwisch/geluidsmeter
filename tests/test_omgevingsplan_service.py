import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import omgevingsplan as op

LOC = {"lat": 52.08, "lon": 5.12}


class _Ozon:
    def __init__(self, regelingen=None, teksten=None, reg_error=False, tekst_error=False):
        self._r, self._t = regelingen, teksten
        self._re, self._te = reg_error, tekst_error
        self.tekst_uri = None

    def regelingen_op_punt(self, geo_rd):
        if self._re:
            raise ConnectorError("down")
        return self._r

    def regelteksten_op_punt(self, uri, geo_rd, max_m=5):
        self.tekst_uri = uri
        if self._te:
            raise ConnectorError("down")
        return (self._t or [])[:max_m]


def _patch_rd(monkeypatch):
    monkeypatch.setattr(op.resolver, "wgs84_naar_rd", lambda lat, lon: (139784.0, 442870.0))


_REGS = [
    {"titel": "Waterschapsverordening X", "type": "Waterschapsverordening", "bevoegd_gezag": "WS X", "uri": "_ws"},
    {"titel": "Omgevingsverordening Utrecht", "type": "Omgevingsverordening", "bevoegd_gezag": "prov", "uri": "_ov"},
    {"titel": "Nationale Omgevingsvisie", "type": "Omgevingsvisie", "bevoegd_gezag": "rijk", "uri": "_novi"},
    {"titel": "Omgevingsplan Z", "type": "Omgevingsplan", "bevoegd_gezag": "gem Z", "uri": "_op"},
]


def test_filtert_types_en_prioriteert_top1(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, teksten=["Bouwregels", "Parkeren"])
    out = op.omgevingsplan_op_locatie(LOC, ozon, max_regelingen=3, max_regelteksten=5)
    # Omgevingsvisie eruit gefilterd; Omgevingsplan heeft hoogste prioriteit
    types = [r["type"] for r in out["regelingen"]]
    assert "Omgevingsvisie" not in types
    assert out["regelingen"][0]["type"] == "Omgevingsplan"
    assert out["top_regeling"] == "Omgevingsplan Z"
    assert ozon.tekst_uri == "_op"                 # regelteksten voor de top-1
    assert out["regelteksten"] == ["Bouwregels", "Parkeren"]
    assert out["locatie_rd"] == [139784.0, 442870.0]
    assert out["bron"].lower().startswith("dso presenteren")


def test_cap_op_regelingen(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, teksten=[])
    out = op.omgevingsplan_op_locatie(LOC, ozon, max_regelingen=2)
    assert len(out["regelingen"]) == 2
    assert out["aantal_beperkt_tot"] == 2


def test_aantal_beperkt_tot_afwezig_zonder_truncatie(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, teksten=[])
    out = op.omgevingsplan_op_locatie(LOC, ozon, max_regelingen=5)
    assert "aantal_beperkt_tot" not in out


def test_geen_relevante_regeling_geeft_none(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=[{"titel": "NOVI", "type": "Omgevingsvisie", "bevoegd_gezag": "rijk", "uri": "_n"}])
    assert op.omgevingsplan_op_locatie(LOC, ozon) is None


def test_regelteksten_fout_blijft_blok(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, tekst_error=True)
    out = op.omgevingsplan_op_locatie(LOC, ozon)
    assert out is not None                         # regelingen blijven staan
    assert out["regelteksten"] == []               # best-effort faalde


def test_regelingen_bron_down_propageert(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(reg_error=True)
    with pytest.raises(ConnectorError):
        op.omgevingsplan_op_locatie(LOC, ozon)
