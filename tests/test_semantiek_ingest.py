import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.semantiek import ingest


class _Resp:
    def __init__(self, text, status=200):
        self.text = text; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=None, response=None)


def test_fetch_ttl_ok(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, follow_redirects=None: _Resp("@prefix x."))
    assert ingest.fetch_ttl("https://x/a.ttl") == "@prefix x."


def test_fetch_ttl_error_raises(monkeypatch):
    def boom(url, timeout=None, follow_redirects=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(ConnectorError):
        ingest.fetch_ttl("https://x/a.ttl")


def test_fetch_all_skips_failures(monkeypatch):
    def get(url, timeout=None, follow_redirects=None):
        if "bad" in url:
            raise httpx.ConnectError("down")
        return _Resp("ok:" + url)
    monkeypatch.setattr(httpx, "get", get)
    out = ingest.fetch_all(["https://x/bad.ttl", "https://x/good.ttl"])
    assert out == ["ok:https://x/good.ttl"]
