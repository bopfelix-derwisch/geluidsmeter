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


_REEKS = [{"jaar": 2019, "hoeveelheid_kton": 10.0, "circulariteit_pct": 80.0},
          {"jaar": 2020, "hoeveelheid_kton": 12.0, "circulariteit_pct": 75.0}]


def test_build_prompt_bevat_getallen_en_bron():
    p = d.build_prompt("Flevoland", "GFT-afval", _REEKS)
    assert "Flevoland" in p and "GFT-afval" in p
    assert "2020" in p and "12" in p
    assert "verzin" in p.lower()


def test_duiding_ok(monkeypatch):
    monkeypatch.setattr(httpx, "post",
                        lambda url, json=None, timeout=None:
                        _FakeResponse({"choices": [{"message": {"content": "Stijgende trend."}}]}))
    out = d.duiding("Flevoland", "GFT-afval", _REEKS,
                    llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["duiding"] == "Stijgende trend."
    assert "83558NED" in out["bron"]
    assert "LMA" in out["disclaimer"]


def test_duiding_llm_down_raises(monkeypatch):
    def boom(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(ConnectorError):
        d.duiding("Flevoland", "GFT-afval", _REEKS,
                  llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
