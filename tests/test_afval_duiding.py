import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.afval import duiding as d


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_CONTEXT = {
    "waarde_kton": 12.0,
    "circulariteit_pct": 75.0,
    "landelijk_gemiddelde_kton": 20.0,
    "rang": 8, "aantal_provincies": 12, "boven_gemiddeld": False,
    "meerjaren": {"van_jaar": 2010, "tot_jaar": 2020, "volume_pct": 20.0, "circ_pct_punt": 5.0},
    "aandeel_van_totaal_pct": 8.5,
    "hoogste": {"naam": "Zuid-Holland", "waarde_kton": 80.0},
    "laagste": {"naam": "Zeeland", "waarde_kton": 4.0},
    "achtergrond": "GFT-afval wordt gecomposteerd.",
}


def test_build_prompt_bevat_context_en_no_hallucination():
    p = d.build_prompt("Flevoland", "GFT-afval", 2020, _CONTEXT)
    assert "Flevoland" in p and "GFT-afval" in p and "2020" in p
    assert "12" in p                       # hoeveelheid
    assert "8e van 12" in p                # rang
    assert "8.5%" in p                     # aandeel
    assert "Zuid-Holland" in p and "Zeeland" in p
    assert "gecomposteerd" in p            # achtergrond
    assert "verzin" in p.lower()


def test_build_prompt_verdraagt_lege_context():
    p = d.build_prompt("Flevoland", "GFT-afval", 2020, {})
    assert "Flevoland" in p and "GFT-afval" in p


def test_duiding_ok(monkeypatch):
    monkeypatch.setattr(httpx, "post",
                        lambda url, json=None, timeout=None:
                        _FakeResponse({"choices": [{"message": {"content": "Onder gemiddeld."}}]}))
    out = d.duiding("Flevoland", "GFT-afval", 2020, _CONTEXT,
                    llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["duiding"] == "Onder gemiddeld."
    assert "83558NED" in out["bron"]
    assert "LMA" in out["disclaimer"]


def test_duiding_llm_down_raises(monkeypatch):
    def boom(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(ConnectorError):
        d.duiding("Flevoland", "GFT-afval", 2020, _CONTEXT,
                  llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")


def test_build_prompt_neemt_forecast_en_extra_mee():
    ctx = dict(_CONTEXT)
    ctx["forecast"] = {"jaar": 2035, "verwacht": 20.0, "ondergrens": 15.0, "bovengrens": 25.0}
    ctx["extra"] = {"recyclingpercentage": 86.0, "recycling_bron": "afvalfonds-2023", "per_inwoner": None}
    p = d.build_prompt("Flevoland", "GFT-afval", 2020, ctx)
    assert "2035" in p and "20" in p           # doorkijk
    assert "86" in p                            # recyclingpercentage
    assert "doorkijk" in p.lower() or "extrapol" in p.lower()
