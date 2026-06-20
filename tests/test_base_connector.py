import json
import httpx
import pytest
from leefomgevinglab.connectors.base import BaseConnector, ConnectorError


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload


def test_cache_miss_fetches_and_writes(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(httpx, "get", fake_get)
    c = BaseConnector(cache_dir=str(tmp_path))
    assert c.get_json("https://x/api") == {"ok": True}
    assert len(calls) == 1
    # tweede call binnen TTL -> cache hit, geen extra http
    assert c.get_json("https://x/api") == {"ok": True}
    assert len(calls) == 1


def test_error_without_cache_raises(tmp_path, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fake_get)
    c = BaseConnector(cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.get_json("https://x/api")


def test_error_with_stale_cache_returns_cache(tmp_path, monkeypatch):
    c = BaseConnector(cache_dir=str(tmp_path), cache_ttl=0)
    cp = c._cache_path("https://x/api", None)
    cp.write_text(json.dumps({"stale": True}))

    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert c.get_json("https://x/api") == {"stale": True}
