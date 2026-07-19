from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api

_GRAPH = {
    "nodes": [
        {"data": {"id": "imx:straatnaam", "label": "straatnaam", "bron": "IMX-Geo", "definitie": "weg"}},
        {"data": {"id": "bag:Naam", "label": "Naam", "bron": "BAG", "definitie": None}},
    ],
    "edges": [{"data": {"id": "imx:straatnaam|closeMatch|bag:Naam",
                        "source": "imx:straatnaam", "target": "bag:Naam", "relatie": "closeMatch"}}],
    "bronnen": ["BAG", "IMX-Geo"],
}


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {"semantiek": {"store_dir": "/tmp/llab_sem"}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_graph_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_semantiek_graph", lambda: _GRAPH)
    r = client.get("/api/semantiek/graph")
    assert r.status_code == 200
    b = r.json()
    assert b["beschikbaar"] is True
    assert len(b["elements"]["nodes"]) == 2
    assert b["bronnen"] == ["BAG", "IMX-Geo"]


def test_graph_zoekterm_filtert(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_semantiek_graph", lambda: _GRAPH)
    r = client.get("/api/semantiek/graph", params={"zoekTerm": "straat"})
    ids = {n["data"]["id"] for n in r.json()["elements"]["nodes"]}
    assert "imx:straatnaam" in ids and "bag:Naam" in ids  # match + buur


def test_graph_missing(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_semantiek_graph", lambda: None)
    r = client.get("/api/semantiek/graph")
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False


def test_node_buren(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_semantiek_graph", lambda: _GRAPH)
    r = client.get("/api/semantiek/node", params={"uri": "imx:straatnaam"})
    assert r.status_code == 200
    buren = r.json()["buren"]
    assert buren[0]["node"]["data"]["id"] == "bag:Naam"
    assert buren[0]["relatie"] == "closeMatch"
