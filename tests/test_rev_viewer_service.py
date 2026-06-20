import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.rev_viewer import service


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload


def test_build_prompt_bevat_velden_en_geen_lege():
    p = service.build_prompt({"naam": "Tankstation X", "risico": "LPG", "leeg": None})
    assert "Tankstation X" in p
    assert "LPG" in p
    assert "leeg" not in p


def test_duiding_returnt_tekst_bron_disclaimer(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        assert "chat/completions" in url
        return _FakeResponse(
            {"choices": [{"message": {"content": "Dit is een LPG-tankstation."}}]}
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    out = service.duiding({"naam": "X"}, llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["duiding"] == "Dit is een LPG-tankstation."
    assert "REV" in out["bron"]
    assert out["disclaimer"] == service.DISCLAIMER


def test_duiding_bij_llm_fout_raise_connectorerror(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(ConnectorError):
        service.duiding({"naam": "X"}, llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
