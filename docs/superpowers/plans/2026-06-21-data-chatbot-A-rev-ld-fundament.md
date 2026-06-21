# Data-chatbot Plan A — REV→LD-fundament Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een lokale, met SPARQL bevraagbare linked-data-laag van REV-Seveso-objecten (Zuid-Holland) + een connector naar de Kadaster Knowledge Graph (KKG), als fundament voor de latere data-chatbot.

**Architecture:** Een KKG-SPARQL-connector bevraagt het publieke Kadaster-endpoint (provincie/scholen). Een converter zet REV-features (uit de bestaande `RevConnector`) om naar RDF met GeoSPARQL-WKT, gefilterd op de Zuid-Holland-polygon (shapely) en een Seveso-filter. Een lokale rdflib-triple-store bewaart de graph als Turtle op NVMe en draait lokale SPARQL. Een build-script bouwt de graph.

**Tech Stack:** Python 3.10, rdflib (SPARQL + Turtle), shapely (al aanwezig via geopandas), httpx, pytest.

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src op het pad).
- App/services blijven werken; nieuwe logica onder `src/leefomgevinglab/ld/`; `src/geluidsmeter/*` alleen additief.
- **Open data, geen key.** KKG-endpoint (publiek, geverifieerd HTTP 200):
  `https://api.labs.kadaster.nl/datasets/kadaster/kkg/services/kkg/sparql`. REV via de bestaande `RevConnector`.
- **Rolzuiverheid:** de eigen REV-LD is een **lokale** representatie voor eigen bevraging (NVMe, niet als extern register gepubliceerd).
- LD-cache/graph op **NVMe**: `/mnt/nvme/geluidsmeter/data/ld/` (niet in git).
- **Verify-stappen (in de bouw, geen gok):** exacte Seveso-filter-property in REV; KKG-URIs voor provinciegebied + BAG-onderwijsfunctie. Connectors zijn config-/parameter-gedreven met die als open punt.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/ld/
  __init__.py
  kkg.py            # KKG SPARQL-connector: sparql(query) -> list[dict]
  rev_to_rdf.py     # REV-features -> rdflib Graph (GeoSPARQL WKT, ZH-filter, Seveso-filter)
  store.py          # save/load Turtle op NVMe + lokale sparql(graph, query) -> list[dict]
  shapes.ttl        # SHACL-shape voor het Seveso-objecttype
scripts/10_build_rev_ld.py
core/config.yaml    # + leefomgevinglab.ld-sectie (MODIFY)
src/geluidsmeter/api.py   # + GET /api/ld/sparql (lokale graph, inspectie) (MODIFY)
tests/test_ld_kkg.py
tests/test_ld_rev_to_rdf.py
tests/test_ld_store.py
tests/test_api_ld.py
```

## Naamruimten (vast in dit plan)

- `LL = "https://leefomgevinglab.local/rev/"` (lokale REV-resources + klasse `LL.SevesoInrichting`)
- `GEO = "http://www.opengis.net/ont/geosparql#"` (`GEO.asWKT`, datatype `GEO.wktLiteral`)
- `RDFS = "http://www.w3.org/2000/01/rdf-schema#"`

---

### Task 1: KKG SPARQL-connector + config

**Files:**
- Create: `src/leefomgevinglab/ld/__init__.py` (leeg)
- Create: `src/leefomgevinglab/ld/kkg.py`
- Modify: `core/config.yaml` (voeg `leefomgevinglab.ld` toe)
- Test: `tests/test_ld_kkg.py`

**Interfaces:**
- Consumes: `ConnectorError` uit `leefomgevinglab.connectors.base`.
- Produces:
  - `sparql(query: str, endpoint: str, timeout_s: float = 30.0) -> list[dict]` — POST naar het
    SPARQL-endpoint met `Accept: application/sparql-results+json`; geeft per rij een dict
    `{var: waarde}` (alleen de `.value`-strings). Raise `ConnectorError` bij fout/onverwacht antwoord.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_ld_kkg.py`:

```python
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
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_ld_kkg.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.ld.kkg'`

- [ ] **Step 3: Schrijf de implementatie**

Maak `src/leefomgevinglab/ld/__init__.py` leeg. `src/leefomgevinglab/ld/kkg.py`:

```python
"""Connector naar de Kadaster Knowledge Graph (KKG) via SPARQL."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError


def sparql(query: str, endpoint: str, timeout_s: float = 30.0) -> list[dict]:
    try:
        resp = httpx.post(
            endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise ConnectorError("KKG SPARQL niet beschikbaar") from exc
    return [{k: v.get("value") for k, v in row.items()} for row in bindings]
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_ld_kkg.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Config-sectie toevoegen**

Voeg aan `core/config.yaml` onder `leefomgevinglab:` toe:

```yaml
  ld:
    kkg_endpoint: "https://api.labs.kadaster.nl/datasets/kadaster/kkg/services/kkg/sparql"
    store_dir: "/mnt/nvme/geluidsmeter/data/ld"
    provincie: "Zuid-Holland"
    # REV-bron + Seveso-filter. Bevestig de exacte property/waarde tegen een REV-respons
    # (zie Task 2 Step 0) voordat je hierop leunt; null = (voorlopig) alle productiefaciliteiten.
    seveso_property: null
    seveso_values: []
```

- [ ] **Step 6: Verify-aantekening (geen code)**

Noteer in het taakrapport als open punt: de KKG-URIs voor `Provinciegebied` en BAG-onderwijsfunctie
moeten in de bouw bevestigd worden tegen het live endpoint (`kkg_endpoint`). De connector zelf is
query-agnostisch.

- [ ] **Step 7: Commit**

```bash
git add src/leefomgevinglab/ld/__init__.py src/leefomgevinglab/ld/kkg.py core/config.yaml tests/test_ld_kkg.py
git commit -m "feat(llab): KKG SPARQL-connector + ld-config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: REV→RDF converter (ZH-filter + Seveso-filter)

**Files:**
- Create: `src/leefomgevinglab/ld/rev_to_rdf.py`
- Test: `tests/test_ld_rev_to_rdf.py`

**Interfaces:**
- Consumes: `shapely` (`shapely.geometry.shape`), `rdflib`.
- Produces:
  - `LL`, `GEO` (rdflib `Namespace`-objecten) + `SEVESO_CLASS = LL.SevesoInrichting`.
  - `build_rev_graph(features: dict, gebied_wkt: str | None = None, seveso_filter=None) -> rdflib.Graph`
    waarbij `features` een GeoJSON FeatureCollection is (zoals `RevConnector.features` teruggeeft),
    `gebied_wkt` een WKT-polygon (alleen features die hierin liggen blijven; None = geen geo-filter),
    en `seveso_filter` een callable `(properties: dict) -> bool` (None = alles). Elke feature wordt:
    `LL[id] a SEVESO_CLASS ; rdfs:label <naam> ; geo:asWKT "<wkt>"^^geo:wktLiteral`.

- [ ] **Step 0: Verify-aantekening (geen code, vereist live REV-respons)**

Bekijk één REV-feature (`production_facility_*`) en bepaal welke property + waarde een **Seveso**-
inrichting markeert (vgl. "Conversietabel E6 Seveso Inrichtingen"). Zet die in `core/config.yaml`
(`seveso_property`/`seveso_values`). Tot dat bevestigd is werkt de converter met `seveso_filter=None`
(alle productiefaciliteiten) — noteer dit als open punt. Geen code in deze stap.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_ld_rev_to_rdf.py`:

```python
from leefomgevinglab.ld import rev_to_rdf as R
from rdflib import RDF, RDFS

def _fc():
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Fabriek A", "seveso": "ja"},
         "geometry": {"type": "Point", "coordinates": [4.30, 51.90]}},   # binnen
        {"type": "Feature", "properties": {"name": "Fabriek B", "seveso": "nee"},
         "geometry": {"type": "Point", "coordinates": [6.90, 52.20]}},   # buiten ZH
    ]}

# vierkant rond [4.30,51.90]
ZH = "POLYGON((4.0 51.6, 4.6 51.6, 4.6 52.1, 4.0 52.1, 4.0 51.6))"


def test_build_graph_filtert_gebied_en_seveso():
    g = R.build_rev_graph(_fc(), gebied_wkt=ZH, seveso_filter=lambda p: p.get("seveso") == "ja")
    klassen = list(g.subjects(RDF.type, R.SEVESO_CLASS))
    assert len(klassen) == 1                      # alleen Fabriek A (binnen + seveso=ja)
    s = klassen[0]
    assert str(next(g.objects(s, RDFS.label))) == "Fabriek A"
    wkt = str(next(g.objects(s, R.GEO.asWKT)))
    assert wkt.upper().startswith("POINT")


def test_geen_filters_neemt_alles():
    g = R.build_rev_graph(_fc())
    assert len(list(g.subjects(RDF.type, R.SEVESO_CLASS))) == 2
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_ld_rev_to_rdf.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.ld.rev_to_rdf'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/ld/rev_to_rdf.py`:

```python
"""Zet REV-features (GeoJSON) om naar een lokale RDF-graph (GeoSPARQL WKT)."""
import hashlib

import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from shapely.geometry import shape
from shapely import wkt as shapely_wkt

LL = rdflib.Namespace("https://leefomgevinglab.local/rev/")
GEO = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
SEVESO_CLASS = LL.SevesoInrichting


def _feature_id(props: dict, geom_wkt: str) -> str:
    raw = str(props.get("gml_id") or props.get("identifier") or props.get("local_id") or geom_wkt)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_rev_graph(features: dict, gebied_wkt: str | None = None, seveso_filter=None) -> rdflib.Graph:
    g = rdflib.Graph()
    g.bind("ll", LL)
    g.bind("geo", GEO)
    gebied = shapely_wkt.loads(gebied_wkt) if gebied_wkt else None
    for feat in features.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if not geom:
            continue
        if seveso_filter is not None and not seveso_filter(props):
            continue
        shp = shape(geom)
        if gebied is not None and not shp.intersects(gebied):
            continue
        geom_wkt = shp.wkt
        s = URIRef(LL[_feature_id(props, geom_wkt)])
        g.add((s, RDF.type, SEVESO_CLASS))
        naam = props.get("name") or props.get("naam") or "REV-object"
        g.add((s, RDFS.label, Literal(naam)))
        g.add((s, GEO.asWKT, Literal(geom_wkt, datatype=GEO.wktLiteral)))
    return g
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_ld_rev_to_rdf.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/ld/rev_to_rdf.py tests/test_ld_rev_to_rdf.py
git commit -m "feat(llab): REV->RDF converter (GeoSPARQL WKT, gebied- + Seveso-filter)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Lokale triple-store (save/load/sparql) + SHACL-shape

**Files:**
- Create: `src/leefomgevinglab/ld/store.py`
- Create: `src/leefomgevinglab/ld/shapes.ttl`
- Test: `tests/test_ld_store.py`

**Interfaces:**
- Consumes: `rdflib`.
- Produces:
  - `save_graph(graph: rdflib.Graph, store_dir: str, naam: str = "rev.ttl") -> None`
  - `load_graph(store_dir: str, naam: str = "rev.ttl") -> rdflib.Graph | None` (None als bestand ontbreekt)
  - `run_sparql(graph: rdflib.Graph, query: str) -> list[dict]` (rijen als `{var: str}`).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_ld_store.py`:

```python
import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld import store
from leefomgevinglab.ld.rev_to_rdf import LL, GEO, SEVESO_CLASS


def _g():
    g = rdflib.Graph()
    s = URIRef(LL["a1"])
    g.add((s, RDF.type, SEVESO_CLASS))
    g.add((s, RDFS.label, Literal("Fabriek A")))
    g.add((s, GEO.asWKT, Literal("POINT(4.3 51.9)", datatype=GEO.wktLiteral)))
    return g


def test_save_load_roundtrip(tmp_path):
    store.save_graph(_g(), str(tmp_path))
    g2 = store.load_graph(str(tmp_path))
    assert g2 is not None
    assert len(list(g2.subjects(RDF.type, SEVESO_CLASS))) == 1
    assert store.load_graph(str(tmp_path / "leeg")) is None


def test_run_sparql_count():
    rows = store.run_sparql(_g(),
        "PREFIX ll: <https://leefomgevinglab.local/rev/> "
        "SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:SevesoInrichting }")
    assert rows[0]["n"] == "1"
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_ld_store.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.ld.store'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/ld/store.py`:

```python
"""Lokale rdflib triple-store: Turtle op NVMe + lokale SPARQL."""
from pathlib import Path

import rdflib


def save_graph(graph: rdflib.Graph, store_dir: str, naam: str = "rev.ttl") -> None:
    d = Path(store_dir)
    d.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(d / naam), format="turtle")


def load_graph(store_dir: str, naam: str = "rev.ttl") -> rdflib.Graph | None:
    p = Path(store_dir) / naam
    if not p.exists():
        return None
    g = rdflib.Graph()
    g.parse(str(p), format="turtle")
    return g


def run_sparql(graph: rdflib.Graph, query: str) -> list[dict]:
    res = graph.query(query)
    rows = []
    for row in res:
        rows.append({str(var): (str(row[var]) if row[var] is not None else None) for var in res.vars})
    return rows
```

`src/leefomgevinglab/ld/shapes.ttl` (SHACL-shape voor het Seveso-objecttype):

```turtle
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix ll:   <https://leefomgevinglab.local/rev/> .
@prefix geo:  <http://www.opengis.net/ont/geosparql#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ll:SevesoInrichtingShape
    a sh:NodeShape ;
    sh:targetClass ll:SevesoInrichting ;
    sh:property [ sh:path rdfs:label ; sh:minCount 1 ; sh:datatype rdfs:Literal ] ;
    sh:property [ sh:path geo:asWKT ; sh:minCount 1 ; sh:datatype geo:wktLiteral ] .
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_ld_store.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/ld/store.py src/leefomgevinglab/ld/shapes.ttl tests/test_ld_store.py
git commit -m "feat(llab): lokale triple-store (Turtle + SPARQL) + SHACL-shape

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Build-script + /api/ld/sparql + docs

**Files:**
- Create: `scripts/10_build_rev_ld.py`
- Modify: `src/geluidsmeter/api.py` (import + helper + route)
- Test: `tests/test_api_ld.py`

**Interfaces:**
- Consumes: `kkg` (Task 1), `rev_to_rdf` (Task 2), `store` (Task 3), bestaande `RevConnector`.
- Produces (HTTP):
  - `POST /api/ld/sparql` body `{"query": str}` → `{"rows": [...]}` (lokale REV-graph). Ontbreekt de
    graph → `{"rows": [], "beschikbaar": false}`. Helper `_ld_graph()` (monkeypatchbaar) laadt de graph.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_api_ld.py`:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api
import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld.rev_to_rdf import LL, GEO, SEVESO_CLASS


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {"ld": {"store_dir": "/tmp/llab_ld"}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def _graph():
    g = rdflib.Graph(); s = URIRef(LL["a1"])
    g.add((s, RDF.type, SEVESO_CLASS)); g.add((s, RDFS.label, Literal("A")))
    return g


def test_ld_sparql_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_ld_graph", lambda: _graph())
    r = client.post("/api/ld/sparql", json={"query":
        "PREFIX ll: <https://leefomgevinglab.local/rev/> SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:SevesoInrichting }"})
    assert r.status_code == 200
    assert r.json()["rows"][0]["n"] == "1"


def test_ld_sparql_no_graph(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_ld_graph", lambda: None)
    r = client.post("/api/ld/sparql", json={"query": "SELECT * WHERE { ?s ?p ?o }"})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_ld.py -q`
Expected: FAIL (`AttributeError: ... has no attribute '_ld_graph'`)

- [ ] **Step 3: Voeg imports toe bovenaan `src/geluidsmeter/api.py`**

Na de bestaande leefomgevinglab-imports:

```python
from leefomgevinglab.ld import store as ld_store
```

- [ ] **Step 4: Voeg helper + route toe aan het eind van `src/geluidsmeter/api.py`**

```python
def _ld_graph():
    ld = _config.get("leefomgevinglab", {}).get("ld", {})
    return ld_store.load_graph(ld.get("store_dir", ""))


class LdSparqlRequest(BaseModel):
    query: str


@app.post("/api/ld/sparql")
def api_ld_sparql(req: LdSparqlRequest):
    g = _ld_graph()
    if g is None:
        return {"rows": [], "beschikbaar": False}
    try:
        return {"rows": ld_store.run_sparql(g, req.query), "beschikbaar": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ongeldige SPARQL: {exc}")
```

- [ ] **Step 5: Schrijf het build-script**

`scripts/10_build_rev_ld.py`:

```python
#!/usr/bin/env python3
"""Bouw de lokale REV-LD-graph: REV-Seveso in Zuid-Holland -> RDF op NVMe."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from leefomgevinglab.connectors.rev import RevConnector
from leefomgevinglab.ld import kkg
from leefomgevinglab.ld.rev_to_rdf import build_rev_graph
from leefomgevinglab.ld.store import save_graph

PROV_WKT_Q = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
SELECT ?wkt WHERE {{
  ?p rdfs:label "{prov}" ; geo:hasGeometry/geo:asWKT ?wkt .
}} LIMIT 1"""


def main():
    root = Path(__file__).parent.parent
    cfg = yaml.safe_load(open(root / "core" / "config.yaml"))["leefomgevinglab"]
    ld = cfg["ld"]
    # Provincie-polygon uit KKG (verify de exacte URI/structuur indien leeg)
    rows = kkg.sparql(PROV_WKT_Q.format(prov=ld["provincie"]), ld["kkg_endpoint"])
    gebied_wkt = rows[0]["wkt"] if rows else None
    # REV-features (ruime bbox rond Zuid-Holland), daarna geo-filter in build_rev_graph
    rev = cfg["rev"]
    conn = RevConnector(base_url=rev["ogc_base_url"], collections=rev["collections"],
                        max_features=rev["max_features"], cache_dir=cfg["cache_dir"])
    fc = {"type": "FeatureCollection", "features": []}
    for bbox in ["3.9,51.6,4.9,52.2"]:   # Zuid-Holland (lon,lat)
        fc["features"].extend(conn.features(bbox).get("features", []))
    sev_prop, sev_vals = ld.get("seveso_property"), ld.get("seveso_values") or []
    filt = (lambda p: str(p.get(sev_prop)) in [str(v) for v in sev_vals]) if sev_prop else None
    g = build_rev_graph(fc, gebied_wkt=gebied_wkt, seveso_filter=filt)
    save_graph(g, ld["store_dir"])
    print(f"REV-LD: {len(list(g.subjects(None, None)))} triples-subj, opgeslagen in {ld['store_dir']}; gebied={'ja' if gebied_wkt else 'geen'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests + volledige suite**

Run: `PYTHONPATH=src python -m pytest tests/test_api_ld.py -q`
Expected: PASS (2 passed)
Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen.

- [ ] **Step 7: Optionele live-build (best-effort, vereist netwerk)**

Run: `PYTHONPATH=src python scripts/10_build_rev_ld.py`
Verwacht: een regel met opgeslagen triples + `gebied=ja`. Bij geen netwerk / afwijkende KKG-structuur:
noteer als concern (provincie-query/Seveso-filter fijnslijpen), niet blokkeren.

- [ ] **Step 8: Commit**

```bash
git add scripts/10_build_rev_ld.py src/geluidsmeter/api.py tests/test_api_ld.py
git commit -m "feat(llab): REV-LD build-script + POST /api/ld/sparql

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (Plan B en later)

- De data-chatbot (NL→SPARQL via RAG + fallback, nabijheid met shapely, frontend `/datavraag`).
- Federatieve SPARQL (SERVICE) en GeoSPARQL-afstandsfuncties in de store.
- Fijnslijpen van de exacte Seveso-property en de KKG-URIs (provinciegebied/BAG-onderwijs) — verify-stappen.

## Self-Review

- **Spec-dekking:** KKG-connector → Task 1; eigen REV-LD (converter, ZH-filter, Seveso-filter, GeoSPARQL-WKT) → Task 2; lokale triple-store + SHACL → Task 3; build-script + bevraagbaar endpoint → Task 4. Verify-stappen (Seveso-property, KKG-URIs) expliciet in Task 1/2. Chatbot → expliciet Plan B.
- **Placeholders:** geen TODO/TBD in code; `seveso_property` is een bewuste config-null met verify-stap; KKG-provincie-query staat concreet in het script met een verify-noot.
- **Type-consistentie:** `kkg.sparql(query, endpoint)`, `build_rev_graph(features, gebied_wkt, seveso_filter)`, `LL`/`GEO`/`SEVESO_CLASS`, `save_graph/load_graph/run_sparql`, `_ld_graph()` consistent over Task 1→4. RDF-vorm (`a SEVESO_CLASS`, `rdfs:label`, `geo:asWKT`) identiek in converter, store-test en api-test.
```
