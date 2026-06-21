# Data-chatbot Plan B — de chatbot (NL→SPARQL + nabijheid) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een data-chatbot die een natuurlijke-taalvraag beantwoordt door (RAG-grounded) SPARQL te genereren over de linked-data-laag (eigen REV-LD + Kadaster KKG) en ruimtelijke nabijheid met shapely te berekenen — met cijfers, bronverwijzing, onzekerheid én de gebruikte query.

**Architecture:** Een grounding-bouwer levert de ontologie/SHACL + voorbeeldqueries als context. De LLM (Qwen) genereert SPARQL; bij ongeldige/lege output valt het terug op een vast sjabloon. SPARQL draait op de lokale REV-graph (Plan A) en de KKG (scholen/provincie). Nabijheid ("binnen R m van een school") gebeurt met shapely + pyproj (projectie naar RD/28992). Een service stelt het antwoordcontract samen; een `/datavraag`-pagina ontsluit het.

**Tech Stack:** Python 3.10, rdflib, shapely + pyproj (via geopandas), httpx, FastAPI, pytest, Qwen (`/v1/chat/completions`).

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src op het pad). Alle tests mocken LLM + KKG (geen netwerk).
- App op poort **8792**, service `geluidsmeter-api`. Bestaande routes/gedrag niet wijzigen; `src/geluidsmeter/api.py` alleen additief.
- Nieuwe logica onder `src/leefomgevinglab/usecases/datavraag/`.
- **Bouwt op Plan A** (al gemerged): `leefomgevinglab.ld.store` (`load_graph`, `run_sparql`), `leefomgevinglab.ld.kkg` (`sparql`), `leefomgevinglab.ld.rev_to_rdf` (`REV_CLASS = LL.REVProductiefaciliteit`), config `leefomgevinglab.ld`.
- **Conservatief contract (harde eis):** elk antwoord bevat de **cijfers**, **bronnen**, expliciete **onzekerheid**, een **vangnet** ("indicatief; raadpleeg het bevoegd gezag / de bronhouder"), én de **gebruikte SPARQL** (transparantie/leerwaarde). De LLM verzint geen aantallen — die komen uit de query.
- **Eerlijk over Seveso:** de open REV-laag heeft geen Seveso-vlag → de telling gaat over **REV-productiefaciliteiten**; antwoord vermeldt dit.
- **Verify-stap:** de KKG-scholen-query (BAG-onderwijs) moet tijdens de bouw tegen het live endpoint fijngeslepen worden (zware Virtuoso-query). Connector is query-gedreven; tests mocken KKG.
- **Externe afhankelijkheden, gemockt in tests, deferred live:** Qwen op `localhost:8080` (draait); KKG-endpoint; gebouwde REV-LD-graph (Plan A build-script).
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/usecases/datavraag/
  __init__.py
  grounding.py     # build_grounding() -> contexttekst (ontologie/SHACL + voorbeeldqueries)
  nl2sparql.py     # genereer_sparql(), FALLBACK_SPARQL, is_geldige_sparql(), kies_sparql()
  nabijheid.py     # scholen_in_provincie() (KKG) + nabij() (shapely+pyproj, meters)
  service.py       # beantwoord() -> antwoordcontract
src/leefomgevinglab/static/datavraag.html
src/geluidsmeter/api.py   # + POST /api/datavraag + GET /datavraag (MODIFY)
tests/test_datavraag_grounding.py
tests/test_datavraag_nl2sparql.py
tests/test_datavraag_nabijheid.py
tests/test_api_datavraag.py
```

---

### Task 1: Grounding-context

**Files:**
- Create: `src/leefomgevinglab/usecases/datavraag/__init__.py` (leeg)
- Create: `src/leefomgevinglab/usecases/datavraag/grounding.py`
- Test: `tests/test_datavraag_grounding.py`

**Interfaces:**
- Produces:
  - `VOORBEELDEN: list[dict]` — paren `{"vraag": str, "sparql": str}` (NL → SPARQL).
  - `build_grounding(shapes_ttl: str) -> str` — bouwt één contexttekst uit de SHACL-shape-tekst +
    de voorbeeldqueries + een korte schema-uitleg (klasse `ll:REVProductiefaciliteit`, `rdfs:label`,
    `geo:asWKT`). Deze tekst gaat als RAG-grounding naar de LLM.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_datavraag_grounding.py`:

```python
from leefomgevinglab.usecases.datavraag import grounding as G


def test_build_grounding_bevat_schema_en_voorbeeld():
    txt = G.build_grounding("ll:REVProductiefaciliteitShape a sh:NodeShape .")
    assert "ll:REVProductiefaciliteit" in txt
    assert "geo:asWKT" in txt
    assert "SELECT" in txt                      # minstens één voorbeeldquery
    assert "NodeShape" in txt                   # de meegegeven shape-tekst zit erin


def test_voorbeelden_zijn_geldig_gevormd():
    assert G.VOORBEELDEN and all("vraag" in v and "sparql" in v for v in G.VOORBEELDEN)
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_datavraag_grounding.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.datavraag.grounding'`

- [ ] **Step 3: Schrijf de implementatie**

Maak `src/leefomgevinglab/usecases/datavraag/__init__.py` leeg. `grounding.py`:

```python
"""RAG-grounding voor NL->SPARQL: schema, SHACL-shape en voorbeeldqueries als context."""

SCHEMA = """\
Lokale linked-data (rdflib), prefixes:
  ll:  <https://leefomgevinglab.local/rev/>
  geo: <http://www.opengis.net/ont/geosparql#>
  rdfs:<http://www.w3.org/2000/01/rdf-schema#>
Klasse ll:REVProductiefaciliteit (REV-productiefaciliteiten; let op: geen Seveso-vlag in de bron).
Elk object heeft: rdfs:label (naam), geo:asWKT (geometrie als WKT-literal)."""

VOORBEELDEN = [
    {"vraag": "hoeveel productiefaciliteiten zijn er?",
     "sparql": "PREFIX ll: <https://leefomgevinglab.local/rev/> "
               "SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"},
    {"vraag": "geef de namen van de productiefaciliteiten",
     "sparql": "PREFIX ll: <https://leefomgevinglab.local/rev/> "
               "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
               "SELECT ?label WHERE { ?s a ll:REVProductiefaciliteit ; rdfs:label ?label }"},
]


def build_grounding(shapes_ttl: str) -> str:
    blokken = [SCHEMA, "SHACL-shape:\n" + shapes_ttl.strip(), "Voorbeelden (vraag -> SPARQL):"]
    for v in VOORBEELDEN:
        blokken.append(f"V: {v['vraag']}\nQ: {v['sparql']}")
    return "\n\n".join(blokken)
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_datavraag_grounding.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/datavraag/__init__.py src/leefomgevinglab/usecases/datavraag/grounding.py tests/test_datavraag_grounding.py
git commit -m "feat(llab): datavraag-grounding (schema + SHACL + voorbeeldqueries)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: NL→SPARQL met fallback

**Files:**
- Create: `src/leefomgevinglab/usecases/datavraag/nl2sparql.py`
- Test: `tests/test_datavraag_nl2sparql.py`

**Interfaces:**
- Consumes: `ConnectorError` (`leefomgevinglab.connectors.base`), `rdflib` (validatie), httpx (Qwen).
- Produces:
  - `FALLBACK_SPARQL: str` — telt `ll:REVProductiefaciliteit` (de demo-fallback).
  - `is_geldige_sparql(query: str) -> bool` — True als rdflib de query kan prepareren.
  - `genereer_sparql(vraag, grounding, llm_base_url, model, timeout_s=60.0) -> str` — Qwen schrijft
    SPARQL (alleen de query als tekst). Raise `ConnectorError` bij LLM-fout.
  - `kies_sparql(vraag, grounding, llm_base_url, model, timeout_s=60.0) -> tuple[str, str]` — geeft
    `(sparql, herkomst)` waarbij herkomst `"llm"` of `"fallback"` is. Probeert de LLM; valt terug op
    `FALLBACK_SPARQL` bij fout of ongeldige query.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_datavraag_nl2sparql.py`:

```python
import httpx
import pytest
from leefomgevinglab.usecases.datavraag import nl2sparql as N


class _Resp:
    def __init__(self, content):
        self._c = content; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": self._c}}]}


def test_is_geldige_sparql():
    assert N.is_geldige_sparql("SELECT ?s WHERE { ?s ?p ?o }")
    assert not N.is_geldige_sparql("dit is geen sparql {{{")


def test_kies_sparql_gebruikt_llm_als_geldig(monkeypatch):
    q = "PREFIX ll: <https://leefomgevinglab.local/rev/> SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"
    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: _Resp("```sparql\n" + q + "\n```"))
    sparql, herkomst = N.kies_sparql("hoeveel?", "ground", "http://x/v1", "qwen")
    assert herkomst == "llm"
    assert "COUNT" in sparql and "```" not in sparql


def test_kies_sparql_valt_terug_bij_ongeldig(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, json=None, timeout=None: _Resp("sorry geen idee {{{"))
    sparql, herkomst = N.kies_sparql("iets vaags", "ground", "http://x/v1", "qwen")
    assert herkomst == "fallback"
    assert sparql == N.FALLBACK_SPARQL


def test_kies_sparql_valt_terug_bij_llm_fout(monkeypatch):
    def boom(url, json=None, timeout=None): raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    sparql, herkomst = N.kies_sparql("iets", "ground", "http://x/v1", "qwen")
    assert herkomst == "fallback"
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_datavraag_nl2sparql.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.datavraag.nl2sparql'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/usecases/datavraag/nl2sparql.py`:

```python
"""NL-vraag -> SPARQL via Qwen, met een veilige fallback-query."""
import re

import httpx
import rdflib

from leefomgevinglab.connectors.base import ConnectorError

FALLBACK_SPARQL = (
    "PREFIX ll: <https://leefomgevinglab.local/rev/> "
    "SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"
)


def is_geldige_sparql(query: str) -> bool:
    try:
        rdflib.plugins.sparql.prepareQuery(query)
        return True
    except Exception:
        return False


def _strip_codeblok(tekst: str) -> str:
    m = re.search(r"```(?:sparql)?\s*(.+?)```", tekst, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else tekst).strip()


def genereer_sparql(vraag: str, grounding: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> str:
    prompt = (
        "Schrijf één SPARQL-query (alleen de query, geen uitleg) die de vraag beantwoordt, "
        "uitsluitend met de gegeven prefixes/klassen.\n\n"
        f"{grounding}\n\nVraag: {vraag}"
    )
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return _strip_codeblok(resp.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("LLM niet beschikbaar voor SPARQL-generatie") from exc


def kies_sparql(vraag: str, grounding: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> tuple[str, str]:
    try:
        q = genereer_sparql(vraag, grounding, llm_base_url, model, timeout_s)
        if is_geldige_sparql(q):
            return q, "llm"
    except ConnectorError:
        pass
    return FALLBACK_SPARQL, "fallback"
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_datavraag_nl2sparql.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/datavraag/nl2sparql.py tests/test_datavraag_nl2sparql.py
git commit -m "feat(llab): NL->SPARQL via Qwen met validatie + fallback-query

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Scholen (KKG) + nabijheid (shapely/pyproj)

**Files:**
- Create: `src/leefomgevinglab/usecases/datavraag/nabijheid.py`
- Test: `tests/test_datavraag_nabijheid.py`

**Interfaces:**
- Consumes: `leefomgevinglab.ld.kkg.sparql` (Plan A), `shapely`, `pyproj` (via geopandas).
- Produces:
  - `SCHOLEN_Q: str` — KKG-SPARQL voor scholen-punten in een provincie (BAG-onderwijs). **Verify-stap.**
  - `scholen_in_provincie(provincie, kkg_endpoint, sparql_fn=...) -> list[tuple[str, float, float]]` —
    lijst `(label, lon, lat)`. `sparql_fn` injecteerbaar (default `kkg.sparql`) voor tests.
  - `nabij(object_wkts: list[str], scholen: list[tuple[str, float, float]], straal_m: float) -> list[str]` —
    de WKT's die binnen `straal_m` meter van minstens één school liggen (projectie naar EPSG:28992).

- [ ] **Step 0: Verify-aantekening (geen code, vereist live KKG)**

Stem `SCHOLEN_Q` af op het live KKG-endpoint: scholen = BAG-verblijfsobjecten met gebruiksdoel
"onderwijsfunctie", met provincie-filter en geometrie (centroïde/punt). Zware Virtuoso-query — beperk
met `LIMIT`/gebied. Tests mocken `sparql_fn`, dus dit blokkeert de taak niet; noteer als open punt.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_datavraag_nabijheid.py`:

```python
from leefomgevinglab.usecases.datavraag import nabijheid as NB


def test_scholen_parse(monkeypatch):
    fake_rows = [{"label": "School A", "lon": "4.30", "lat": "51.90"}]
    out = NB.scholen_in_provincie("Zuid-Holland", "http://x", sparql_fn=lambda q, ep, **k: fake_rows)
    assert out == [("School A", 4.30, 51.90)]


def test_nabij_meters():
    # school op (4.30, 51.90); object ~30 m ernaast vs object ~5 km verderop
    scholen = [("S", 4.30, 51.90)]
    dichtbij = "POINT(4.3004 51.9000)"     # ~27 m
    verweg = "POINT(4.40 51.90)"           # ~6-7 km
    res = NB.nabij([dichtbij, verweg], scholen, straal_m=200)
    assert dichtbij in res and verweg not in res
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_datavraag_nabijheid.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.datavraag.nabijheid'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/usecases/datavraag/nabijheid.py`:

```python
"""Scholen ophalen uit de KKG + nabijheid (in meters) met shapely/pyproj."""
from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.ops import transform as shp_transform

from leefomgevinglab.ld import kkg

# Scholen-punten in een provincie (BAG-onderwijs). LET OP: tegen het live KKG-endpoint
# fijnslijpen (gebruiksdoel onderwijsfunctie + provincie-filter + geometrie). Verify-stap.
SCHOLEN_Q = """PREFIX imx: <http://modellen.geostandaarden.nl/def/imx-geo#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
SELECT ?label ?lon ?lat WHERE {{
  ?s imx:naam ?label ; imx:gebruiksdoel "onderwijsfunctie" ; geo:hasGeometry/geo:asWKT ?wkt .
}} LIMIT 2000"""

_TO_RD = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def scholen_in_provincie(provincie: str, kkg_endpoint: str, sparql_fn=kkg.sparql) -> list[tuple[str, float, float]]:
    rows = sparql_fn(SCHOLEN_Q.format(prov=provincie), kkg_endpoint)
    out = []
    for r in rows:
        try:
            out.append((r.get("label") or "school", float(r["lon"]), float(r["lat"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _to_rd(geom):
    return shp_transform(lambda x, y, z=None: _TO_RD.transform(x, y), geom)


def nabij(object_wkts: list[str], scholen: list[tuple[str, float, float]], straal_m: float) -> list[str]:
    from shapely.geometry import Point
    school_rd = [_to_rd(Point(lon, lat)) for _, lon, lat in scholen]
    treffers = []
    for w in object_wkts:
        try:
            g_rd = _to_rd(shapely_wkt.loads(w))
        except Exception:
            continue
        if any(g_rd.distance(s) <= straal_m for s in school_rd):
            treffers.append(w)
    return treffers
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_datavraag_nabijheid.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/datavraag/nabijheid.py tests/test_datavraag_nabijheid.py
git commit -m "feat(llab): scholen uit KKG + nabijheid in meters (shapely/pyproj)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Service + REST + frontend

**Files:**
- Create: `src/leefomgevinglab/usecases/datavraag/service.py`
- Create: `src/leefomgevinglab/static/datavraag.html`
- Modify: `src/geluidsmeter/api.py` (imports + helper + 2 routes)
- Modify: `src/leefomgevinglab/static/index.html` (nav-link)
- Test: `tests/test_api_datavraag.py`

**Interfaces:**
- Consumes: `grounding`, `nl2sparql`, `ld.store` (`load_graph`/`run_sparql`), `_config`.
- Produces:
  - `service.beantwoord(vraag, graph, grounding_txt, llm_base_url, model, timeout_s=60.0) -> dict` met
    sleutels: `vraag`, `antwoord` (str|None), `sparql`, `herkomst` ("llm"/"fallback"), `rijen` (list),
    `onzekerheid` (True), `disclaimer`, `vangnet`, `beschikbaar` (bool). Degradeert (beschikbaar=False)
    als er geen graph is of de query faalt.
  - HTTP: `POST /api/datavraag` body `{"vraag": str}` → het contract (HTTP 200, ook bij degradatie).
    `GET /datavraag` → de chat-pagina. Helpers `_dv_graph()` + `_dv_grounding()` (monkeypatchbaar).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_api_datavraag.py`:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api
import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from leefomgevinglab.ld.rev_to_rdf import LL, REV_CLASS


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {
        "ld": {"store_dir": "/tmp/llab_dv"},
        "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def _graph():
    g = rdflib.Graph()
    for i in (1, 2):
        s = URIRef(LL[f"x{i}"]); g.add((s, RDF.type, REV_CLASS)); g.add((s, RDFS.label, Literal(f"F{i}")))
    return g


def test_datavraag_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_dv_graph", lambda: _graph())
    monkeypatch.setattr(api, "_dv_grounding", lambda: "ground")
    monkeypatch.setattr(api.dv_service, "beantwoord",
        lambda vraag, graph, grounding_txt, **kw: {"vraag": vraag, "antwoord": "2 gevonden",
            "sparql": "SELECT ...", "herkomst": "fallback", "rijen": [{"n": "2"}],
            "onzekerheid": True, "disclaimer": "indicatief", "vangnet": "bevoegd gezag", "beschikbaar": True})
    r = client.post("/api/datavraag", json={"vraag": "hoeveel?"})
    assert r.status_code == 200
    assert r.json()["rijen"][0]["n"] == "2"
    assert r.json()["sparql"]


def test_datavraag_no_graph(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_dv_graph", lambda: None)
    r = client.post("/api/datavraag", json={"vraag": "hoeveel?"})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_datavraag.py -q`
Expected: FAIL (`AttributeError: ... has no attribute '_dv_graph'`)

- [ ] **Step 3: Schrijf de service**

`src/leefomgevinglab/usecases/datavraag/service.py`:

```python
"""Data-chatbot service: NL-vraag -> SPARQL -> antwoord met conservatief contract."""
from leefomgevinglab.ld.store import run_sparql
from leefomgevinglab.usecases.datavraag.nl2sparql import kies_sparql

DISCLAIMER = ("Indicatief, geen juridisch/officieel cijfer. De telling betreft REV-productiefaciliteiten "
             "(de open REV-laag kent geen Seveso-vlag).")
VANGNET = "Raadpleeg de bronhouder (REV/PDOK, Kadaster) of het bevoegd gezag voor officiele cijfers."


def beantwoord(vraag: str, graph, grounding_txt: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    base = {"vraag": vraag, "onzekerheid": True, "disclaimer": DISCLAIMER, "vangnet": VANGNET,
            "bron": "eigen REV-LD (PDOK) + Kadaster KKG"}
    if graph is None:
        return {**base, "antwoord": None, "sparql": None, "herkomst": None, "rijen": [], "beschikbaar": False}
    sparql, herkomst = kies_sparql(vraag, grounding_txt, llm_base_url, model, timeout_s)
    try:
        rijen = run_sparql(graph, sparql)
    except Exception:
        return {**base, "antwoord": None, "sparql": sparql, "herkomst": herkomst, "rijen": [], "beschikbaar": False}
    # Eenvoudige verwoording: toon de eerste rij/telling
    if rijen and "n" in rijen[0]:
        antwoord = f"Gevonden: {rijen[0]['n']} (REV-productiefaciliteiten)."
    else:
        antwoord = f"{len(rijen)} resultaten."
    return {**base, "antwoord": antwoord, "sparql": sparql, "herkomst": herkomst,
            "rijen": rijen, "beschikbaar": True}
```

- [ ] **Step 4: Voeg imports + helpers + routes toe aan `src/geluidsmeter/api.py`**

Imports (na de bestaande leefomgevinglab-imports):

```python
from pathlib import Path as _Path  # reeds Path aanwezig; gebruik bestaande Path
from leefomgevinglab.usecases.datavraag import grounding as dv_grounding
from leefomgevinglab.usecases.datavraag import service as dv_service
```

(Gebruik de al-geïmporteerde `Path` en `ld_store`; voeg geen dubbele toe.)

Helpers + routes aan het eind:

```python
def _dv_graph():
    ld = _config.get("leefomgevinglab", {}).get("ld", {})
    return ld_store.load_graph(ld.get("store_dir", ""))


def _dv_grounding():
    shapes = Path(__file__).parent.parent / "leefomgevinglab" / "ld" / "shapes.ttl"
    txt = shapes.read_text() if shapes.exists() else ""
    return dv_grounding.build_grounding(txt)


class DatavraagRequest(BaseModel):
    vraag: str


@app.post("/api/datavraag")
def api_datavraag(req: DatavraagRequest):
    g = _dv_graph()
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    return dv_service.beantwoord(
        req.vraag, g, _dv_grounding(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"), timeout_s=llm.get("timeout_s", 60))


@app.get("/datavraag", response_class=HTMLResponse)
def datavraag_page():
    return (Path(__file__).parent.parent / "leefomgevinglab" / "static" / "datavraag.html").read_text()
```

- [ ] **Step 5: Maak de frontend**

`src/leefomgevinglab/static/datavraag.html`:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LeefomgevingLab — Datavraag</title>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #080c14; color: #e0e6ed; }
    header { background: #0d1b2a; border-bottom: 1px solid #1a3a5c; padding: 12px 18px; }
    header a { color: #2ecc8f; text-decoration: none; font-size: 13px; }
    main { max-width: 800px; margin: 0 auto; padding: 18px; }
    h1 { font-size: 18px; color: #eafff6; margin: 0 0 4px; }
    .muted { color: #8aa0b2; font-size: 12px; }
    form { display: flex; gap: 8px; margin: 16px 0; }
    input { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #1a3a5c; background: #0a1220; color: #e0e6ed; }
    button { padding: 10px 16px; border: none; border-radius: 8px; background: #2ecc8f; color: #042; font-weight: 700; cursor: pointer; }
    .voorb { font-size: 12px; }
    .voorb a { color: #4fc3f7; cursor: pointer; }
    .ans { background: #0d1b2a; border: 1px solid #1a3a5c; border-radius: 10px; padding: 14px; margin-top: 14px; }
    .ans .big { font-size: 22px; color: #2ecc8f; font-weight: 800; }
    .tag { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 10px; border: 1px solid #1a3a5c; color: #8aa0b2; }
    pre { background: #0a1220; border: 1px solid #1a3a5c; border-radius: 8px; padding: 10px; overflow-x: auto; font-size: 12px; color: #b8c7d6; }
    .disc { font-size: 11px; color: #b89; margin-top: 8px; }
  </style>
</head>
<body>
  <header><a href="/">← LeefomgevingLab</a> · <a href="/poc">over deze POC</a></header>
  <main>
    <h1>Datavraag</h1>
    <p class="muted">Stel een vraag over de linked-data-laag. De gegenereerde SPARQL wordt getoond; cijfers komen uit de data.</p>
    <form id="f">
      <input id="q" placeholder="bv. hoeveel productiefaciliteiten zijn er?" autocomplete="off" />
      <button>Vraag</button>
    </form>
    <p class="voorb muted">Voorbeelden:
      <a data-q="hoeveel productiefaciliteiten zijn er?">hoeveel productiefaciliteiten?</a> ·
      <a data-q="geef de namen van de productiefaciliteiten">geef de namen</a></p>
    <div id="out"></div>
  </main>
  <script>
    const out = document.getElementById("out");
    async function vraag(q) {
      out.innerHTML = '<div class="ans">Bezig…</div>';
      try {
        const r = await fetch("/api/datavraag", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vraag: q }) });
        const d = await r.json();
        if (!d.beschikbaar) { out.innerHTML = '<div class="ans"><p class="muted">Geen antwoord (graaf/LLM offline). ' + (d.vangnet||"") + '</p></div>'; return; }
        const big = (d.rijen && d.rijen[0] && d.rijen[0].n != null) ? '<div class="big">' + d.rijen[0].n + '</div>' : '';
        const rows = (d.rijen||[]).slice(0,15).map(x => Object.values(x).join(" · ")).join("<br>");
        out.innerHTML = '<div class="ans">' + big +
          '<p>' + (d.antwoord||"").replace(/</g,"&lt;") + ' <span class="tag">SPARQL: ' + d.herkomst + '</span></p>' +
          (rows ? '<div class="muted" style="margin:6px 0">' + rows + '</div>' : '') +
          '<pre>' + (d.sparql||"").replace(/</g,"&lt;") + '</pre>' +
          '<div class="disc">' + d.disclaimer + '<br>' + d.vangnet + '</div></div>';
      } catch (e) { out.innerHTML = '<div class="ans">Er ging iets mis.</div>'; }
    }
    document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); const q = document.getElementById("q").value.trim(); if (q) vraag(q); });
    document.querySelectorAll(".voorb a").forEach(a => a.onclick = () => { document.getElementById("q").value = a.dataset.q; vraag(a.dataset.q); });
  </script>
</body>
</html>
```

- [ ] **Step 6: Nav-link op de landing**

In `src/leefomgevinglab/static/index.html`, voeg in het header-`<nav>` na de POC-link toe:

```html
      <a href="/datavraag">Datavraag</a>
```

- [ ] **Step 7: Run tests + volledige suite**

Run: `PYTHONPATH=src python -m pytest tests/test_api_datavraag.py -q`
Expected: PASS (2 passed)
Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen.

- [ ] **Step 8: Commit**

```bash
git add src/leefomgevinglab/usecases/datavraag/service.py src/leefomgevinglab/static/datavraag.html src/geluidsmeter/api.py src/leefomgevinglab/static/index.html tests/test_api_datavraag.py
git commit -m "feat(llab): data-chatbot service + POST /api/datavraag + /datavraag frontend

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (later)

- De nabijheid-vraag ("bij een school") volledig conversationeel: `service.beantwoord` toont nu de SPARQL-telling; het koppelen van `nabijheid.scholen_in_provincie` + `nabij` aan een herkende "nabij school"-intentie is een vervolgstap (de bouwstenen staan klaar in Task 3).
- Federatieve SPARQL (KKG-SERVICE) en GeoSPARQL-afstand in de query.
- Fijnslijpen van `SCHOLEN_Q` tegen het live KKG-endpoint (verify-stap).
- Echte Seveso-telling (vereist BRZO-bron).

## Self-Review

- **Spec-dekking (design sectie Plan B):** RAG-grounding → Task 1; NL→SPARQL met fallback → Task 2; scholen + nabijheid (shapely) → Task 3; service met antwoordcontract + getoonde SPARQL + frontend → Task 4. Conservatief contract → Task 4 service. Verify-stap KKG-scholen → Task 3 Step 0. Echte Seveso/nabijheid-intentie → expliciet out of scope.
- **Placeholders:** geen TODO/TBD in code; `SCHOLEN_Q` is een concrete query met gemarkeerde verify-stap.
- **Type-consistentie:** `build_grounding(shapes_ttl)`, `kies_sparql(...) -> (sparql, herkomst)`, `FALLBACK_SPARQL`, `scholen_in_provincie(...) -> [(label,lon,lat)]`, `nabij(wkts, scholen, straal_m)`, `beantwoord(...) -> contract`, `_dv_graph()/_dv_grounding()`, `REV_CLASS`/`LL` (Plan A) consistent over Task 1→4. Antwoord-dict-sleutels identiek tussen service en frontend/api-test.
```
