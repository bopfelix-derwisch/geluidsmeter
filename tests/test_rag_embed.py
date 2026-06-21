import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.rag import embed as emb


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=None, response=None)
    def json(self): return self._p


def test_embed_texts_returns_vectors_in_order(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        assert url.endswith("/embeddings")
        assert json["input"] == ["a", "b"]
        return _Resp({"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    out = emb.embed_texts(["a", "b"], base_url="http://localhost:8082/v1", model="bge")
    assert out == [[1.0, 0.0], [0.0, 1.0]]


def test_embed_texts_error_raises(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(ConnectorError):
        emb.embed_texts(["a"], base_url="http://localhost:8082/v1", model="bge")
