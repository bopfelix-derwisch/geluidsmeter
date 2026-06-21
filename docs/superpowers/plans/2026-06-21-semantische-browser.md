# Semantische browser (IMX-Geo koppelingen-graaf) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een interactieve semantische browser die de informatiemodellen van de leefomgeving als één doorzoekbare graaf toont, met IMX-Geo als crossdomein-spil en de koppelingen (`closeMatch`/`exactMatch`) naar bronregisters (BAG/BGT/BRK/REV…) zichtbaar.

**Architecture:** Een ingest haalt open IMX-Geo TTL's op (GitHub-raw), een graph-builder parseert ze met rdflib tot Cytoscape-elements JSON (gecachet op NVMe), de bestaande FastAPI-app serveert de graaf, en een `/semantiek`-pagina rendert hem met Cytoscape.js. Afnemer/verrijker-rol, volledig open data, geen key.

**Tech Stack:** Python 3.10, rdflib, FastAPI, httpx, pytest, Cytoscape.js (CDN).

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src op het pad).
- App draait via `uvicorn geluidsmeter.api:app --app-dir src` op poort **8792**; service `geluidsmeter-api` (systemd). Bestaande routes/gedrag niet wijzigen; bestaande tests blijven groen.
- Nieuwe logica onder `src/leefomgevinglab/`; `src/geluidsmeter/*` alleen additief.
- **Open data, geen key.** Bron = `github.com/geonovum/IMX-Geo` (raw TTL). De graaf-cache staat op **NVMe** (`/mnt/nvme/geluidsmeter/data/semantiek/`), niet in git.
- **Nieuwe dependency:** `rdflib` (toevoegen aan `requirements.txt`; al geïnstalleerd in de venv).
- **bron-afleiding (geverifieerd):** IMX-Geo-concepten (`skos:inScheme`) → "IMX-Geo"; externe `closeMatch`/`exactMatch`-doelen → bron uit URI-host (`bag.basisregistraties.overheid.nl`→"BAG", enz.).
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/semantiek/
  __init__.py
  ingest.py        # fetch_ttl / fetch_all (ConnectorError per URL, skip-on-fail)
  graph.py         # bron_from_uri, build_graph, save_graph, load_graph
scripts/09_build_semantiek_graph.py
core/config.yaml          # + leefomgevinglab.semantiek (MODIFY)
requirements.txt          # + rdflib (MODIFY)
src/geluidsmeter/api.py   # + /api/semantiek/graph, /api/semantiek/node, /semantiek (MODIFY)
src/leefomgevinglab/static/semantiek.html
tests/test_semantiek_ingest.py
tests/test_semantiek_graph.py
tests/test_api_semantiek.py
```

---

### Task 1: Ingest + rdflib-dependency + config

**Files:**
- Create: `src/leefomgevinglab/semantiek/__init__.py` (leeg)
- Create: `src/leefomgevinglab/semantiek/ingest.py`
- Modify: `requirements.txt` (voeg `rdflib` toe)
- Modify: `core/config.yaml` (voeg `leefomgevinglab.semantiek` toe)
- Test: `tests/test_semantiek_ingest.py`

**Interfaces:**
- Consumes: `ConnectorError` uit `leefomgevinglab.connectors.base`.
- Produces:
  - `fetch_ttl(url: str, timeout_s: float = 25.0) -> str` (raise `ConnectorError` bij fout).
  - `fetch_all(urls: list[str], timeout_s: float = 25.0) -> list[str]` (sla mislukte URL's over).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_semantiek_ingest.py`:

```python
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
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_semantiek_ingest.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.semantiek.ingest'`

- [ ] **Step 3: Schrijf de implementatie**

Maak `src/leefomgevinglab/semantiek/__init__.py` leeg. `src/leefomgevinglab/semantiek/ingest.py`:

```python
"""Ingest van open linked-data TTL-bronnen (IMX-Geo) voor de semantische graaf."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError


def fetch_ttl(url: str, timeout_s: float = 25.0) -> str:
    try:
        resp = httpx.get(url, timeout=timeout_s, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        raise ConnectorError(f"TTL niet beschikbaar: {url}") from exc


def fetch_all(urls: list[str], timeout_s: float = 25.0) -> list[str]:
    texts: list[str] = []
    for url in urls:
        try:
            texts.append(fetch_ttl(url, timeout_s))
        except ConnectorError:
            continue
    return texts
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_semantiek_ingest.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: requirements + config bijwerken**

Voeg `rdflib` toe aan `requirements.txt` (op een eigen regel). Installeer in de venv:
`source .venv/bin/activate && pip install rdflib`

Voeg aan `core/config.yaml` onder `leefomgevinglab:` toe (naast `rev:`/`dso:`/`rag:`/`llm:`):

```yaml
  semantiek:
    store_dir: "/mnt/nvme/geluidsmeter/data/semantiek"
    # Open IMX-Geo linked data (geen key). SKOS-conceptscheme = schone koppelingen;
    # MIM-export = rijker model. Geverifieerd 2026-06-21.
    ttl_urls:
      - "https://raw.githubusercontent.com/geonovum/IMX-Geo/main/conceptscheme/imxgeo-skos.ttl"
      - "https://raw.githubusercontent.com/geonovum/IMX-Geo/main/mim-ld-export/model/imx-geo-mim.ttl"
```

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/semantiek/__init__.py src/leefomgevinglab/semantiek/ingest.py requirements.txt core/config.yaml tests/test_semantiek_ingest.py
git commit -m "feat(llab): semantiek-ingest (IMX-Geo TTL) + rdflib + config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Graph-builder + build-script

**Files:**
- Create: `src/leefomgevinglab/semantiek/graph.py`
- Create: `scripts/09_build_semantiek_graph.py`
- Test: `tests/test_semantiek_graph.py`

**Interfaces:**
- Consumes: `rdflib`; `fetch_all` (Task 1) in het script.
- Produces:
  - `bron_from_uri(uri: str, imxgeo_uris: set[str]) -> str`
  - `build_graph(ttl_texts: list[str]) -> dict` → `{"nodes": [...], "edges": [...], "bronnen": [...]}`
    waarbij node = `{"data": {"id", "label", "bron", "definitie"}}` en
    edge = `{"data": {"id", "source", "target", "relatie"}}`.
  - `save_graph(graph: dict, store_dir: str) -> None` (schrijft `graph.json`).
  - `load_graph(store_dir: str) -> dict | None` (None als `graph.json` ontbreekt).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_semantiek_graph.py`:

```python
from leefomgevinglab.semantiek import graph as G

FIXTURE = """
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix : <https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/> .
:straatnaam a skos:Concept ;
   skos:prefLabel "straatnaam"@nl ;
   skos:definition "De benaming van een weg."@nl ;
   skos:inScheme <https://staging-definities.geostandaarden.nl/imx-geo/> ;
   skos:closeMatch <http://bag.basisregistraties.overheid.nl/id/begrip/Naam> ;
   skos:broader :adres .
:adres a skos:Concept ;
   skos:prefLabel "adres"@nl ;
   skos:inScheme <https://staging-definities.geostandaarden.nl/imx-geo/> .
"""


def test_bron_from_uri():
    imx = {"https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/straatnaam"}
    assert G.bron_from_uri("https://staging-definities.geostandaarden.nl/imx-geo/id/begrip/straatnaam", imx) == "IMX-Geo"
    assert G.bron_from_uri("http://bag.basisregistraties.overheid.nl/id/begrip/Naam", imx) == "BAG"


def test_build_graph_nodes_edges_bron():
    g = G.build_graph([FIXTURE])
    ids = {n["data"]["id"] for n in g["nodes"]}
    # IMX-Geo concepten + externe BAG-node als losse node
    assert any(i.endswith("/straatnaam") for i in ids)
    assert "http://bag.basisregistraties.overheid.nl/id/begrip/Naam" in ids
    bron = {n["data"]["id"]: n["data"]["bron"] for n in g["nodes"]}
    assert bron["http://bag.basisregistraties.overheid.nl/id/begrip/Naam"] == "BAG"
    straat = next(n for n in g["nodes"] if n["data"]["id"].endswith("/straatnaam"))
    assert straat["data"]["bron"] == "IMX-Geo"
    assert straat["data"]["label"] == "straatnaam"
    assert "weg" in (straat["data"]["definitie"] or "")
    relaties = {e["data"]["relatie"] for e in g["edges"]}
    assert "closeMatch" in relaties and "broader" in relaties
    assert "BAG" in g["bronnen"] and "IMX-Geo" in g["bronnen"]


def test_save_load_roundtrip(tmp_path):
    g = G.build_graph([FIXTURE])
    G.save_graph(g, str(tmp_path))
    g2 = G.load_graph(str(tmp_path))
    assert g2["bronnen"] == g["bronnen"]
    assert G.load_graph(str(tmp_path / "leeg")) is None
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_semantiek_graph.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.semantiek.graph'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/semantiek/graph.py`:

```python
"""Bouw een Cytoscape-graaf uit IMX-Geo linked data (rdflib)."""
import json
from pathlib import Path

import rdflib
from rdflib.namespace import SKOS, RDFS

_REL = {
    SKOS.closeMatch: "closeMatch",
    SKOS.exactMatch: "exactMatch",
    SKOS.broader: "broader",
    SKOS.narrower: "narrower",
    SKOS.related: "related",
}

_HOST_BRON = {
    "bag.basisregistraties.overheid.nl": "BAG",
    "bgt.basisregistraties.overheid.nl": "BGT",
    "brk.basisregistraties.overheid.nl": "BRK",
}


def bron_from_uri(uri: str, imxgeo_uris: set[str]) -> str:
    if uri in imxgeo_uris or "imx-geo" in uri:
        return "IMX-Geo"
    host = uri.split("//")[-1].split("/")[0]
    if "rev" in uri or "externe-veiligheid" in uri:
        return "REV"
    return _HOST_BRON.get(host, host)


def _label(g: rdflib.Graph, uri: rdflib.URIRef) -> str:
    for pred in (SKOS.prefLabel, RDFS.label):
        for o in g.objects(uri, pred):
            return str(o)
    return str(uri).rstrip("/").split("/")[-1]


def build_graph(ttl_texts: list[str]) -> dict:
    g = rdflib.Graph()
    for text in ttl_texts:
        try:
            g.parse(data=text, format="turtle")
        except Exception:
            continue
    imxgeo = {str(s) for s in g.subjects(SKOS.inScheme, None)}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(uri: str) -> None:
        if uri in nodes:
            return
        ref = rdflib.URIRef(uri)
        definitie = next((str(o) for o in g.objects(ref, SKOS.definition)), None)
        nodes[uri] = {"data": {
            "id": uri,
            "label": _label(g, ref),
            "bron": bron_from_uri(uri, imxgeo),
            "definitie": definitie,
        }}

    for s, p, o in g:
        if p in _REL and isinstance(o, rdflib.URIRef):
            su, ou = str(s), str(o)
            add_node(su)
            add_node(ou)
            eid = f"{su}|{_REL[p]}|{ou}"
            if eid in seen:
                continue
            seen.add(eid)
            edges.append({"data": {"id": eid, "source": su, "target": ou, "relatie": _REL[p]}})

    bronnen = sorted({n["data"]["bron"] for n in nodes.values()})
    return {"nodes": list(nodes.values()), "edges": edges, "bronnen": bronnen}


def save_graph(graph: dict, store_dir: str) -> None:
    d = Path(store_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "graph.json").write_text(json.dumps(graph))


def load_graph(store_dir: str) -> dict | None:
    p = Path(store_dir) / "graph.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())
```

`scripts/09_build_semantiek_graph.py`:

```python
#!/usr/bin/env python3
"""Bouw de semantiek-graaf uit de geconfigureerde IMX-Geo TTL-URL's."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from leefomgevinglab.semantiek.ingest import fetch_all
from leefomgevinglab.semantiek.graph import build_graph, save_graph


def main():
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "core" / "config.yaml"))["leefomgevinglab"]["semantiek"]
    texts = fetch_all(cfg["ttl_urls"])
    graph = build_graph(texts)
    save_graph(graph, cfg["store_dir"])
    print(f"Semantiek-graaf: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges, "
          f"bronnen {graph['bronnen']} -> {cfg['store_dir']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_semantiek_graph.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Optionele live-build (best-effort, vereist netwerk)**

Run: `PYTHONPATH=src python scripts/09_build_semantiek_graph.py`
Verwacht: een regel met >0 nodes/edges en bronnen incl. "IMX-Geo" en "BAG". Bij geen netwerk: noteer als concern, niet blokkeren.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/semantiek/graph.py scripts/09_build_semantiek_graph.py tests/test_semantiek_graph.py
git commit -m "feat(llab): semantiek graph-builder (rdflib -> cytoscape JSON) + build-script

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: REST-routes /api/semantiek/graph + /node

**Files:**
- Modify: `src/geluidsmeter/api.py` (import + helper + 2 routes)
- Test: `tests/test_api_semantiek.py`

**Interfaces:**
- Consumes: `leefomgevinglab.semantiek.graph` (Task 2), `_config`.
- Produces (HTTP):
  - `GET /api/semantiek/graph` → `{"elements": {"nodes": [...], "edges": [...]}, "bronnen": [...], "beschikbaar": bool}`.
    Optioneel `?zoekTerm=` (nodes met match op label/definitie + directe buren) en `?bron=` (alleen die bron + IMX-Geo). Ontbrekende graaf → `beschikbaar: false`, lege elements, HTTP 200.
  - `GET /api/semantiek/node?uri=` → `{"node": {...}, "buren": [{"node": {...}, "relatie": str}, ...]}`; 404 als graaf/node ontbreekt.
  - Helper `_semantiek_graph()` (monkeypatchbaar) → `load_graph(store_dir)` of None.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_api_semantiek.py`:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api

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
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_semantiek.py -q`
Expected: FAIL (`AttributeError: ... has no attribute '_semantiek_graph'`)

- [ ] **Step 3: Voeg import toe bovenaan `src/geluidsmeter/api.py`**

Na de bestaande leefomgevinglab-imports:

```python
from leefomgevinglab.semantiek import graph as semantiek_graph
```

- [ ] **Step 4: Voeg helper + routes toe aan het eind van `src/geluidsmeter/api.py`**

```python
def _semantiek_graph():
    sem = _config.get("leefomgevinglab", {}).get("semantiek", {})
    return semantiek_graph.load_graph(sem.get("store_dir", ""))


@app.get("/api/semantiek/graph")
def api_semantiek_graph(zoekTerm: str | None = None, bron: str | None = None):
    graph = _semantiek_graph()
    if graph is None:
        return {"elements": {"nodes": [], "edges": []}, "bronnen": [], "beschikbaar": False}
    nodes, edges = graph["nodes"], graph["edges"]
    if bron:
        keep = {n["data"]["id"] for n in nodes if n["data"]["bron"] in (bron, "IMX-Geo")}
        nodes = [n for n in nodes if n["data"]["id"] in keep]
        edges = [e for e in edges if e["data"]["source"] in keep and e["data"]["target"] in keep]
    if zoekTerm:
        z = zoekTerm.lower()
        match = {n["data"]["id"] for n in nodes
                 if z in n["data"]["label"].lower() or z in (n["data"].get("definitie") or "").lower()}
        keep = set(match)
        for e in edges:
            if e["data"]["source"] in match:
                keep.add(e["data"]["target"])
            if e["data"]["target"] in match:
                keep.add(e["data"]["source"])
        nodes = [n for n in nodes if n["data"]["id"] in keep]
        edges = [e for e in edges if e["data"]["source"] in keep and e["data"]["target"] in keep]
    return {"elements": {"nodes": nodes, "edges": edges}, "bronnen": graph["bronnen"], "beschikbaar": True}


@app.get("/api/semantiek/node")
def api_semantiek_node(uri: str):
    graph = _semantiek_graph()
    if graph is None:
        raise HTTPException(status_code=404, detail="Geen graaf beschikbaar")
    by_id = {n["data"]["id"]: n for n in graph["nodes"]}
    node = by_id.get(uri)
    if node is None:
        raise HTTPException(status_code=404, detail="Node niet gevonden")
    buren = []
    for e in graph["edges"]:
        if e["data"]["source"] == uri and e["data"]["target"] in by_id:
            buren.append({"node": by_id[e["data"]["target"]], "relatie": e["data"]["relatie"]})
        elif e["data"]["target"] == uri and e["data"]["source"] in by_id:
            buren.append({"node": by_id[e["data"]["source"]], "relatie": e["data"]["relatie"]})
    return {"node": node, "buren": buren}
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_semantiek.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Run de volledige suite (regressie)**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alle bestaande tests + de nieuwe groen.

- [ ] **Step 7: Commit**

```bash
git add src/geluidsmeter/api.py tests/test_api_semantiek.py
git commit -m "feat(llab): /api/semantiek/graph + /node (filter + buren)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Frontend /semantiek (Cytoscape) + landing/roadmap

**Files:**
- Create: `src/leefomgevinglab/static/semantiek.html`
- Modify: `src/geluidsmeter/api.py` (route `GET /semantiek`)
- Modify: `src/leefomgevinglab/static/index.html` (nav-link)
- Modify: `src/leefomgevinglab/static/roadmap.html` ("Kennisgraaf"-kaart → live link)

**Interfaces:**
- Consumes (HTTP): `GET /api/semantiek/graph` (Task 3).
- Produces: statische pagina + route; handmatige verificatie in de browser.

- [ ] **Step 1: Voeg de route toe aan `src/geluidsmeter/api.py`**

Aan het eind:

```python
@app.get("/semantiek", response_class=HTMLResponse)
def semantiek_page():
    return (Path(__file__).parent.parent / "leefomgevinglab" / "static" / "semantiek.html").read_text()
```

- [ ] **Step 2: Schrijf de frontend**

`src/leefomgevinglab/static/semantiek.html`:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LeefomgevingLab — Semantische browser</title>
  <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #080c14; color: #e0e6ed; }
    header { background: #0d1b2a; border-bottom: 1px solid #1a3a5c; padding: 10px 16px;
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    header a { color: #2ecc8f; font-size: 13px; }
    header input { margin-left: auto; padding: 6px 10px; border-radius: 8px; border: 1px solid #1a3a5c;
      background: #0a1220; color: #e0e6ed; font-size: 13px; }
    #cy { position: absolute; top: 49px; bottom: 0; left: 0; right: 320px; }
    #panel { position: absolute; top: 49px; bottom: 0; right: 0; width: 320px; overflow-y: auto;
      background: #0a1220; border-left: 1px solid #1a3a5c; padding: 14px; font-size: 13px; }
    #panel h3 { color: #eafff6; font-size: 15px; margin-bottom: 6px; }
    .muted { color: #8aa0b2; font-size: 12px; }
    .legend span { display: inline-flex; align-items: center; gap: 5px; margin: 2px 8px 2px 0; font-size: 11px; color: #8aa0b2; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .buur { border-top: 1px solid #14202e; padding: 6px 0; }
    .buur b { color: #4fc3f7; }
  </style>
</head>
<body>
  <header>
    <a href="/">← LeefomgevingLab</a>
    <strong style="color:#2ecc8f">Semantische browser</strong>
    <span class="muted">IMX-Geo · koppelingen tussen modellen</span>
    <input id="zoek" placeholder="zoek begrip…" />
  </header>
  <div id="cy"></div>
  <div id="panel">
    <div id="legend" class="legend"></div>
    <hr style="border-color:#14202e; margin:10px 0" />
    <div id="info"><p class="muted">Klik een begrip in de graaf.</p></div>
  </div>
  <script>
    const palette = ["#2ecc8f","#4fc3f7","#ffb74d","#e57373","#ba68c8","#a1887f","#90a4ae"];
    const bronColor = {};
    function colorFor(bron) {
      if (!(bron in bronColor)) bronColor[bron] = palette[Object.keys(bronColor).length % palette.length];
      return bronColor[bron];
    }
    let cy;

    async function load(zoekTerm) {
      const url = "/api/semantiek/graph" + (zoekTerm ? "?zoekTerm=" + encodeURIComponent(zoekTerm) : "");
      let data;
      try { const r = await fetch(url); data = await r.json(); }
      catch (e) { document.getElementById("info").innerHTML = '<p class="muted">Graaf niet beschikbaar.</p>'; return; }
      if (!data.beschikbaar) {
        document.getElementById("info").innerHTML =
          '<p class="muted">Nog geen graaf gebouwd. Draai <code>scripts/09_build_semantiek_graph.py</code>.</p>';
        return;
      }
      (data.bronnen || []).forEach(colorFor);
      renderLegend(data.bronnen || []);
      const els = data.elements.nodes.map(n => ({ data: n.data })).concat(
                  data.elements.edges.map(e => ({ data: e.data })));
      cy = cytoscape({
        container: document.getElementById("cy"),
        elements: els,
        style: [
          { selector: "node", style: {
              "background-color": (n) => colorFor(n.data("bron")),
              "label": "data(label)", "color": "#cfd8dc", "font-size": "9px",
              "text-valign": "bottom", "width": 16, "height": 16 } },
          { selector: "edge", style: {
              "width": 1, "line-color": "#33506a", "target-arrow-color": "#33506a",
              "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": 0.7 } },
        ],
        layout: { name: "cose", animate: false },
      });
      cy.on("tap", "node", (evt) => showNode(evt.target.data("id")));
    }

    function renderLegend(bronnen) {
      document.getElementById("legend").innerHTML = bronnen.map(b =>
        `<span><span class="dot" style="background:${colorFor(b)}"></span>${b}</span>`).join("");
    }

    async function showNode(uri) {
      const info = document.getElementById("info");
      info.innerHTML = "Bezig…";
      try {
        const r = await fetch("/api/semantiek/node?uri=" + encodeURIComponent(uri));
        if (!r.ok) throw new Error();
        const d = await r.json();
        const n = d.node.data;
        const buren = (d.buren || []).map(b =>
          `<div class="buur"><b>${b.relatie}</b> → ${b.node.data.label} <span class="muted">(${b.node.data.bron})</span></div>`).join("");
        info.innerHTML = `<h3>${n.label}</h3>` +
          `<p class="muted">bron: ${n.bron}</p>` +
          (n.definitie ? `<p>${n.definitie}</p>` : "") +
          `<p class="muted" style="margin-top:8px">${n.id}</p>` +
          (buren ? `<h3 style="font-size:13px;margin-top:12px">Koppelingen</h3>${buren}` : "");
      } catch (e) { info.innerHTML = '<p class="muted">Kon node niet laden.</p>'; }
    }

    let t;
    document.getElementById("zoek").addEventListener("input", (e) => {
      clearTimeout(t);
      t = setTimeout(() => load(e.target.value.trim()), 350);
    });
    load("");
  </script>
</body>
</html>
```

- [ ] **Step 3: Nav-link op de landing**

In `src/leefomgevinglab/static/index.html`, voeg in het `<nav>`-blok (header) een link toe na de "Chatbot"-link:

```html
      <a href="/semantiek">Semantiek</a>
```

- [ ] **Step 4: Roadmap-kaart live maken**

In `src/leefomgevinglab/static/roadmap.html`, in de POC-opties-grid, vervang de niet-klikbare "Kennisgraaf onder de chatbot"-kaart door een live link:

```html
        <a class="card" style="cursor:pointer" href="/semantiek">
          <h3>Semantische browser (live)</h3>
          <p>IMX-Geo als crossdomein-spil: objecttypen/begrippen uit BAG/BGT/BRK/REV… met hun koppelingen in één interactieve graaf.</p>
          <div class="src">IMX-Geo linked data · Cytoscape</div>
        </a>
```

- [ ] **Step 5: Handmatige verificatie (browser)**

Bouw eerst de graaf (`PYTHONPATH=src python scripts/09_build_semantiek_graph.py`), herstart de service (`sudo systemctl restart geluidsmeter-api`) en open `http://localhost:8792/semantiek`. Verwacht: een graaf met gekleurde nodes per bron + legenda; klik een node → definitie + koppelingen; zoekbalk filtert. Zonder gebouwde graaf: nette "nog geen graaf"-melding.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/static/semantiek.html src/geluidsmeter/api.py src/leefomgevinglab/static/index.html src/leefomgevinglab/static/roadmap.html
git commit -m "feat(llab): semantische browser frontend (/semantiek, Cytoscape) + nav/roadmap

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (later)

- Stelselcatalogus-begripsverrijking live (DSO-key); GIR (gesloten model).
- MIM-vocab-extractie (objecttype→attribuut→kardinaliteit) uit de MIM-export — v1 gebruikt de SKOS-relaties; de MIM-TTL wordt wel meegeparset maar levert vooral SKOS-armere triples.
- Losse NEN3610-sectormodellen apart inladen; SHACL-validatie; bewerken; SPARQL-endpoint.

## Self-Review

- **Spec-dekking:** ingest (open TTL) → Task 1; graph-builder + bron-afleiding + build-script → Task 2; API graph/node + filters + degradatie → Task 3; Cytoscape-frontend + nav + roadmap → Task 4; rdflib-dep → Task 1; Stelselcatalogus/GIR/MIM → expliciet out of scope. Testen-sectie van de spec → elke task heeft TDD + Task 3 Step 6 regressie.
- **Placeholders:** geen TODO/TBD; TTL-URL's zijn concrete geverifieerde waarden; live-build is een best-effort stap.
- **Type-consistentie:** `fetch_all(urls)`, `build_graph(ttl_texts)->{"nodes","edges","bronnen"}`, node `data:{id,label,bron,definitie}`, edge `data:{id,source,target,relatie}`, `load_graph(store_dir)`, `_semantiek_graph()`, `semantiek_graph` import-alias consistent over Task 1→4. API-respons `{"elements":{"nodes","edges"},"bronnen","beschikbaar"}` consistent met wat de frontend (Task 4) consumeert.
```
