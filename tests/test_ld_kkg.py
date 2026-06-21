import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.ld import kkg


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=None, response=None)
    def json(self): return self._p


def test_sparql_parses_rows(monkeypatch):
    payload = {"results": {"bindings": [
        {"p": {"type": "uri", "value": "urn:zh"}, "label": {"type": "literal", "value": "Zuid-Holland"}},
    ]}}
    def fake_post(url, data=None, headers=None, timeout=None):
        assert "sparql" in url
        assert headers["Accept"] == "application/sparql-results+json"
        assert data["query"].startswith("SELECT")
        return _Resp(payload)
    monkeypatch.setattr(httpx, "post", fake_post)
    rows = kkg.sparql("SELECT ?p ?label WHERE {}", endpoint="https://x/sparql")
    assert rows == [{"p": "urn:zh", "label": "Zuid-Holland"}]


def test_sparql_error_raises(monkeypatch):
    def boom(url, data=None, headers=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(ConnectorError):
        kkg.sparql("SELECT * WHERE {}", endpoint="https://x/sparql")
