# LeefomgevingLab — Fundering + UC-04 REV-viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een open-source MapLibre REV-viewer met AI-duiding bouwen op een nieuwe, herbruikbare connector- + REST-fundering, zonder de draaiende geluid-services te breken.

**Architecture:** Nieuwe Python-package `src/leefomgevinglab/` met een `BaseConnector` (timeout + on-disk NVMe-cache + nette degradatie) en een `RevConnector` op PDOK's REV OGC API Features. De bestaande FastAPI-app (`geluidsmeter.api:app` op poort 8792) wordt uitgebreid met drie routes (`/api/rev/features`, `/api/duiding`, `/viewer`) die de nieuwe package aanroepen. De geluid-pijplijn en -services blijven volledig ongemoeid. AI-duiding loopt via de lokale Qwen2.5 (OpenAI-compatible) op `localhost:8080`.

**Tech Stack:** Python 3.10, FastAPI, httpx, pytest, MapLibre GL JS (CDN), PDOK BRT-achtergrond (WMTS), REV via PDOK OGC API Features, Qwen2.5 lokaal.

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src staat niet op het pad zonder dit).
- App draait met: `uvicorn geluidsmeter.api:app --host 0.0.0.0 --port 8792 --app-dir src` (bestaand script `scripts/05_run_api.sh`).
- **Geluid-services niet breken:** `src/geluidsmeter/*` blijft bestaan en importeerbaar; bestaande routes en tests blijven groen. Nieuwe logica komt onder `src/leefomgevinglab/`.
- Poort blijft **8792** (8791 is bezet door felix-nazaten). Geen nieuwe poort.
- Cache en alle data op NVMe: `/mnt/nvme/geluidsmeter/data/...` (niet in de repo; staat in `.gitignore`).
- Kwaliteitslabel/disclaimer overal: indicatief, geen juridisch oordeel.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Geen DSO/eHerkenning/RAG in dit plan — dat is Plan 2 (UC-03).

## File Structure

```
src/leefomgevinglab/
  __init__.py                       # leeg, markeert package
  connectors/
    __init__.py
    base.py                         # BaseConnector + ConnectorError
    rev.py                          # RevConnector (OGC API Features)
  usecases/
    __init__.py
    rev_viewer/
      __init__.py
      service.py                    # build_prompt() + duiding() via Qwen
  viewer/
    static/
      viewer.html                   # MapLibre-viewer (CDN, geen buildstap)
core/config.yaml                    # + leefomgevinglab-sectie (MODIFY)
src/geluidsmeter/api.py             # + 3 routes (MODIFY)
tests/test_base_connector.py
tests/test_rev_connector.py
tests/test_rev_viewer_service.py
tests/test_api_rev.py
```

**Integratiekeuze (bewust):** nieuwe logica leeft volledig onder `leefomgevinglab`; alleen `geluidsmeter/api.py` krijgt dunne route-wrappers die ernaar verwijzen. De volledige repo/package-rename naar `LeefomgevingLab` en het verhuizen van geluid naar `usecases/geluid/` is een latere, expliciete stap (buiten dit plan) — zo blijven de services tijdens deze bouw draaien.

---

### Task 1: BaseConnector + package-skelet + config-sectie

**Files:**
- Create: `src/leefomgevinglab/__init__.py` (leeg)
- Create: `src/leefomgevinglab/connectors/__init__.py` (leeg)
- Create: `src/leefomgevinglab/connectors/base.py`
- Modify: `core/config.yaml` (voeg `leefomgevinglab`-sectie toe aan het eind)
- Test: `tests/test_base_connector.py`

**Interfaces:**
- Produces:
  - `class ConnectorError(Exception)`
  - `class BaseConnector(cache_dir: str, timeout: float = 10.0, cache_ttl: int = 3600)`
    met methode `get_json(url: str, params: dict | None = None) -> dict|list`.
    Bij netwerkfout én lege cache: raise `ConnectorError`. Bij netwerkfout mét cache: geef (stale) cache terug.

- [ ] **Step 1: Maak de lege package-bestanden**

Maak `src/leefomgevinglab/__init__.py` en `src/leefomgevinglab/connectors/__init__.py` als lege bestanden.

- [ ] **Step 2: Schrijf de falende test**

`tests/test_base_connector.py`:

```python
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
```

- [ ] **Step 3: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_base_connector.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.connectors.base'`

- [ ] **Step 4: Schrijf de minimale implementatie**

`src/leefomgevinglab/connectors/base.py`:

```python
"""Basis-connector: HTTP met timeout, on-disk cache en nette degradatie."""
import json
import time
import hashlib
from pathlib import Path

import httpx


class ConnectorError(Exception):
    """Externe bron tijdelijk niet beschikbaar."""


class BaseConnector:
    def __init__(self, cache_dir: str, timeout: float = 10.0, cache_ttl: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.cache_ttl = cache_ttl

    def _cache_path(self, url: str, params: dict | None) -> Path:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.json"

    def get_json(self, url: str, params: dict | None = None):
        cp = self._cache_path(url, params)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < self.cache_ttl:
            return json.loads(cp.read_text())
        try:
            resp = httpx.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            if cp.exists():
                return json.loads(cp.read_text())
            raise ConnectorError(f"Bron niet beschikbaar: {url}") from exc
        cp.write_text(json.dumps(data))
        return data
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_base_connector.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Voeg de config-sectie toe**

Voeg aan het eind van `core/config.yaml` toe:

```yaml
leefomgevinglab:
  cache_dir: "/mnt/nvme/geluidsmeter/data/cache"
  rev:
    # REV (externe veiligheid) op PDOK als OGC API Features. Geverifieerd 2026-06-20:
    # INSPIRE-geharmoniseerde "Productiefaciliteiten". Let op: deze service levert
    # geometrie in EPSG:4258 (lat,lon-asvolgorde) en negeert bbox-crs — de connector
    # zet bbox en coordinaten om (zie Task 2).
    ogc_base_url: "https://api.pdok.nl/rws/productie-en-industrie-productiefaciliteiten/ogc/v1"
    collection: "production_facility_f"
    max_features: 500
  llm:
    base_url: "http://localhost:8080/v1"
    model: "qwen2.5-32b"
    timeout_s: 60
  viewer:
    center_lat: 52.08
    center_lon: 4.29
    zoom: 13
```

- [ ] **Step 7: Commit**

```bash
git add src/leefomgevinglab/__init__.py src/leefomgevinglab/connectors/ core/config.yaml tests/test_base_connector.py
git commit -m "feat(llab): BaseConnector met cache + degradatie + config-sectie

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: RevConnector (REV via OGC API Features)

**Files:**
- Create: `src/leefomgevinglab/connectors/rev.py`
- Test: `tests/test_rev_connector.py`

**Interfaces:**
- Consumes: `BaseConnector`, `ConnectorError` uit Task 1.
- Produces:
  - `class RevConnector(BaseConnector)` met constructor
    `RevConnector(base_url: str, collection: str, max_features: int = 500, cache_dir: str = ..., timeout: float = 10.0, cache_ttl: int = 3600)`
  - methode `features(bbox: str) -> dict` die een **schone** GeoJSON FeatureCollection
    (CRS84, lon,lat) teruggeeft. `bbox`-invoer = `"minLon,minLat,maxLon,maxLat"` (CRS84,
    zoals MapLibre `getBounds()` levert).

**Bron-eigenaardigheid (geverifieerd 2026-06-20, must-handle):** de REV-service levert
geometrie in **EPSG:4258 met lat,lon-asvolgorde** en negeert `bbox-crs`. Daarom moet de
connector:
1. de inkomende lon,lat-bbox omzetten naar lat,lon vóór de API-call
   (`minLon,minLat,maxLon,maxLat` → `minLat,minLon,maxLat,maxLon`);
2. in elke teruggegeven geometrie de coördinaten van [lat,lon] naar [lon,lat] omdraaien
   (recursief; geometrieën zijn Polygon/MultiPolygon).

Zo blijft de quirk binnen de connector en krijgt de viewer standaard CRS84-GeoJSON.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_rev_connector.py`:

```python
from leefomgevinglab.connectors.rev import RevConnector


def test_features_reorders_bbox_and_swaps_coords(tmp_path):
    captured = {}

    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            # bron levert lat,lon (EPSG:4258)
            return {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Polygon",
                                 "coordinates": [[[52.0, 4.0], [52.1, 4.0], [52.1, 4.2], [52.0, 4.0]]]},
                    "properties": {"name": "X"},
                }],
            }

    c = _Rev(base_url="https://api.pdok.nl/rws/x/ogc/v1/",
             collection="production_facility_f", max_features=250, cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")

    assert captured["url"] == "https://api.pdok.nl/rws/x/ogc/v1/collections/production_facility_f/items"
    # lon,lat-bbox omgezet naar lat,lon voor de bron
    assert captured["params"] == {"bbox": "52.0,4.0,52.5,4.5", "f": "json", "limit": 250}
    # teruggegeven coordinaten omgedraaid naar lon,lat
    assert fc["features"][0]["geometry"]["coordinates"] == [[[4.0, 52.0], [4.0, 52.1], [4.2, 52.1], [4.0, 52.0]]]
    assert fc["features"][0]["properties"]["name"] == "X"


def test_features_non_fc_returns_empty(tmp_path):
    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            return {"type": "Something", "code": "x"}

    c = _Rev(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")
    assert fc == {"type": "FeatureCollection", "features": []}


def test_features_handles_missing_geometry(tmp_path):
    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            return {"type": "FeatureCollection",
                    "features": [{"type": "Feature", "geometry": None, "properties": {}}]}

    c = _Rev(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")
    assert fc["features"][0]["geometry"] is None
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_rev_connector.py -q`
Expected: FAIL — assertion-fouten op bbox-volgorde en omgedraaide coördinaten (of `ModuleNotFoundError` als het bestand nog ontbreekt).

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/connectors/rev.py`:

```python
"""REV (externe veiligheid) via PDOK OGC API Features.

De PDOK REV-service (INSPIRE, EPSG:4258) levert lat,lon en negeert bbox-crs.
Deze connector normaliseert naar schone CRS84 GeoJSON (lon,lat) voor de viewer.
"""
from .base import BaseConnector


def _swap_positions(coords):
    """Draai elke positie [lat, lon, ...] om naar [lon, lat, ...] (recursief)."""
    if coords and isinstance(coords[0], (int, float)):
        return [coords[1], coords[0]] + list(coords[2:])
    return [_swap_positions(c) for c in coords]


class RevConnector(BaseConnector):
    def __init__(self, base_url: str, collection: str, max_features: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.max_features = max_features

    def features(self, bbox: str) -> dict:
        parts = [p.strip() for p in bbox.split(",")]
        # invoer minLon,minLat,maxLon,maxLat -> bron wil minLat,minLon,maxLat,maxLon
        api_bbox = ",".join([parts[1], parts[0], parts[3], parts[2]])
        url = f"{self.base_url}/collections/{self.collection}/items"
        params = {"bbox": api_bbox, "f": "json", "limit": self.max_features}
        data = self.get_json(url, params)
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            return {"type": "FeatureCollection", "features": []}
        for feat in data.get("features", []):
            geom = feat.get("geometry")
            if geom and geom.get("coordinates") is not None:
                geom["coordinates"] = _swap_positions(geom["coordinates"])
        return data
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_rev_connector.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Optionele live-rooktest (best-effort, vereist netwerk)**

Run:
`PYTHONPATH=src python -c "from leefomgevinglab.connectors.rev import RevConnector; c=RevConnector(base_url='https://api.pdok.nl/rws/productie-en-industrie-productiefaciliteiten/ogc/v1', collection='production_facility_f', max_features=2, cache_dir='/tmp/llab_rev'); fc=c.features('6.45,51.85,6.50,51.87'); print('n=', len(fc['features']), 'eerste coord=', fc['features'][0]['geometry']['coordinates'][0][0] if fc['features'] else None)"`
Verwacht: `n=` > 0 en de eerste coördinaat in lon,lat-volgorde (lon ~6.x, lat ~51.x). Bij geen netwerk: noteer als concern, niet blokkeren.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/connectors/rev.py tests/test_rev_connector.py core/config.yaml
git commit -m "feat(llab): RevConnector op PDOK OGC API Features

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: REV-viewer duidingservice (Qwen)

**Files:**
- Create: `src/leefomgevinglab/usecases/__init__.py` (leeg)
- Create: `src/leefomgevinglab/usecases/rev_viewer/__init__.py` (leeg)
- Create: `src/leefomgevinglab/usecases/rev_viewer/service.py`
- Test: `tests/test_rev_viewer_service.py`

**Interfaces:**
- Consumes: `ConnectorError` uit Task 1 (`leefomgevinglab.connectors.base`).
- Produces:
  - `DISCLAIMER: str`
  - `build_prompt(properties: dict) -> str`
  - `duiding(properties: dict, llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict`
    geeft `{"duiding": str, "bron": str, "disclaimer": str}`. Bij LLM-fout: raise `ConnectorError`.

- [ ] **Step 1: Maak de lege package-bestanden**

Maak `src/leefomgevinglab/usecases/__init__.py` en `src/leefomgevinglab/usecases/rev_viewer/__init__.py` als lege bestanden.

- [ ] **Step 2: Schrijf de falende test**

`tests/test_rev_viewer_service.py`:

```python
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
```

- [ ] **Step 3: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_rev_viewer_service.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.rev_viewer.service'`

- [ ] **Step 4: Schrijf de minimale implementatie**

`src/leefomgevinglab/usecases/rev_viewer/service.py`:

```python
"""UC-04: AI-duiding van een REV-object via lokale Qwen."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

DISCLAIMER = (
    "Indicatief, geen juridisch oordeel. Raadpleeg het bevoegd gezag en "
    "registerexterneveiligheid.nl voor de officiele situatie."
)


def build_prompt(properties: dict) -> str:
    velden = "\n".join(f"- {k}: {v}" for k, v in properties.items() if v not in (None, ""))
    return (
        "Je bent een feitelijke assistent voor externe veiligheid. "
        "Vat onderstaand REV-object in 2-3 zinnen begrijpelijk samen voor een burger. "
        "Verzin niets; gebruik uitsluitend de gegeven velden. Trek geen juridische conclusies.\n\n"
        f"REV-object:\n{velden}"
    )


def duiding(properties: dict, llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    prompt = build_prompt(properties)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("AI-duiding tijdelijk niet beschikbaar") from exc
    return {"duiding": text, "bron": "REV (PDOK OGC API Features)", "disclaimer": DISCLAIMER}
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_rev_viewer_service.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/usecases/ tests/test_rev_viewer_service.py
git commit -m "feat(llab): REV-viewer duidingservice via lokale Qwen

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: REST-routes in de bestaande app

**Files:**
- Modify: `src/geluidsmeter/api.py` (imports bovenaan + drie routes onderaan)
- Test: `tests/test_api_rev.py`

**Interfaces:**
- Consumes: `RevConnector` (Task 2), `rev_viewer.service` (Task 3), `ConnectorError` (Task 1).
- Produces (HTTP):
  - `GET /api/rev/features?bbox=minLon,minLat,maxLon,maxLat` → GeoJSON FeatureCollection; bij bronfout HTTP 503.
  - `POST /api/duiding` body `{"properties": {...}}` → `{"duiding","bron","disclaimer"}`; bij LLM-fout HTTP 503.
  - `GET /viewer` → de viewer-HTML (Task 5).
  - Helper `_rev_connector() -> RevConnector` (zodat tests hem kunnen monkeypatchen).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_api_rev.py`:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api
from leefomgevinglab.connectors.base import ConnectorError


def _client_with_config(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "cache_dir": "/tmp/llab_test_cache",
            "rev": {"ogc_base_url": "https://x", "collection": "c", "max_features": 500},
            "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60},
        }
    }
    # voorkom dat startup() de echte config herlaadt
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_rev_features_ok(monkeypatch):
    client = _client_with_config(monkeypatch)

    class _FakeRev:
        def features(self, bbox):
            return {"type": "FeatureCollection", "features": [{"id": 1, "bbox": bbox}]}

    monkeypatch.setattr(api, "_rev_connector", lambda: _FakeRev())
    r = client.get("/api/rev/features", params={"bbox": "4,52,4.5,52.5"})
    assert r.status_code == 200
    assert r.json()["features"][0]["bbox"] == "4,52,4.5,52.5"


def test_rev_features_bron_down_503(monkeypatch):
    client = _client_with_config(monkeypatch)

    class _FakeRev:
        def features(self, bbox):
            raise ConnectorError("down")

    monkeypatch.setattr(api, "_rev_connector", lambda: _FakeRev())
    r = client.get("/api/rev/features", params={"bbox": "4,52,4.5,52.5"})
    assert r.status_code == 503


def test_duiding_ok(monkeypatch):
    client = _client_with_config(monkeypatch)
    monkeypatch.setattr(
        api.rev_service, "duiding",
        lambda properties, **kw: {"duiding": "ok", "bron": "REV", "disclaimer": "d"},
    )
    r = client.post("/api/duiding", json={"properties": {"naam": "X"}})
    assert r.status_code == 200
    assert r.json()["duiding"] == "ok"
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_rev.py -q`
Expected: FAIL (`AttributeError: module 'geluidsmeter.api' has no attribute '_rev_connector'` of import-fout op `rev_service`)

- [ ] **Step 3: Voeg imports toe bovenaan `src/geluidsmeter/api.py`**

Voeg na de bestaande `from .source_match import get_rivm_lden` (regel 16) toe:

```python
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.connectors.rev import RevConnector
from leefomgevinglab.usecases.rev_viewer import service as rev_service
```

- [ ] **Step 4: Voeg de routes toe aan het eind van `src/geluidsmeter/api.py`**

```python
def _rev_connector() -> RevConnector:
    ll = _config.get("leefomgevinglab", {})
    rev = ll.get("rev", {})
    return RevConnector(
        base_url=rev.get("ogc_base_url", ""),
        collection=rev.get("collection", ""),
        max_features=rev.get("max_features", 500),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


@app.get("/api/rev/features")
def api_rev_features(bbox: str):
    try:
        return _rev_connector().features(bbox)
    except ConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class DuidingRequest(BaseModel):
    properties: dict


@app.post("/api/duiding")
def api_duiding(req: DuidingRequest):
    ll = _config.get("leefomgevinglab", {})
    llm = ll.get("llm", {})
    try:
        return rev_service.duiding(
            req.properties,
            llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
            model=llm.get("model", "qwen2.5-32b"),
            timeout_s=llm.get("timeout_s", 60),
        )
    except ConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/viewer", response_class=HTMLResponse)
def viewer_page():
    viewer_html = Path(__file__).parent.parent / "leefomgevinglab" / "viewer" / "static" / "viewer.html"
    return viewer_html.read_text()
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_rev.py -q`
Expected: PASS (3 passed). *Let op:* `/viewer` wordt pas in Task 5 echt bruikbaar (bestand ontbreekt nog); de drie tests raken die route niet.

- [ ] **Step 6: Run de volledige suite (regressie geluid)**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alle bestaande geluid-tests + nieuwe tests groen.

- [ ] **Step 7: Commit**

```bash
git add src/geluidsmeter/api.py tests/test_api_rev.py
git commit -m "feat(llab): REST-routes /api/rev/features, /api/duiding, /viewer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: MapLibre REV-viewer (frontend)

**Files:**
- Create: `src/leefomgevinglab/viewer/__init__.py` (leeg)
- Create: `src/leefomgevinglab/viewer/static/viewer.html`

**Interfaces:**
- Consumes (HTTP, uit Task 4): `GET /api/rev/features?bbox=...`, `POST /api/duiding`.
- Produces: een statische pagina; handmatige verificatie in de browser.

- [ ] **Step 1: Maak de lege package-marker**

Maak `src/leefomgevinglab/viewer/__init__.py` als leeg bestand.

- [ ] **Step 2: Schrijf de viewer**

`src/leefomgevinglab/viewer/static/viewer.html`:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LeefomgevingLab — REV-viewer</title>
  <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
  <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; }
    #map { position: absolute; inset: 0 360px 0 0; }
    #panel { position: absolute; top: 0; right: 0; bottom: 0; width: 360px;
             box-sizing: border-box; padding: 16px; overflow-y: auto;
             background: #f7f7f8; border-left: 1px solid #ddd; }
    h1 { font-size: 16px; margin: 0 0 8px; }
    .muted { color: #666; font-size: 12px; }
    button { margin-top: 8px; padding: 8px 12px; cursor: pointer; }
    pre { white-space: pre-wrap; font-size: 12px; background: #fff; padding: 8px; border: 1px solid #eee; }
    .disc { color: #884; font-size: 11px; margin-top: 8px; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="panel">
    <h1>REV-viewer</h1>
    <p class="muted">Klik op een object voor de details en AI-duiding. Bron: REV via PDOK OGC API Features.</p>
    <div id="info"><p class="muted">Nog niets geselecteerd.</p></div>
  </div>
  <script>
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        sources: {
          brt: {
            type: "raster",
            tiles: ["https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "PDOK BRT-achtergrondkaart"
          }
        },
        layers: [{ id: "brt", type: "raster", source: "brt" }]
      },
      center: [4.29, 52.08],
      zoom: 13
    });

    let selected = null;

    async function loadRev() {
      const b = map.getBounds();
      const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map(n => n.toFixed(5)).join(",");
      let fc;
      try {
        const r = await fetch("/api/rev/features?bbox=" + bbox);
        if (!r.ok) throw new Error("status " + r.status);
        fc = await r.json();
      } catch (e) {
        document.getElementById("info").innerHTML =
          '<p class="muted">REV-bron tijdelijk niet beschikbaar.</p>';
        return;
      }
      if (map.getSource("rev")) {
        map.getSource("rev").setData(fc);
      } else {
        map.addSource("rev", { type: "geojson", data: fc });
        // REV-objecten zijn vlakken (productiefaciliteit-contouren)
        map.addLayer({ id: "rev-fill", type: "fill", source: "rev",
          paint: { "fill-color": "#d7263d", "fill-opacity": 0.35 } });
        map.addLayer({ id: "rev-line", type: "line", source: "rev",
          paint: { "line-color": "#d7263d", "line-width": 1.5 } });
        map.on("click", "rev-fill", (e) => showFeature(e.features[0]));
        map.on("mouseenter", "rev-fill", () => map.getCanvas().style.cursor = "pointer");
        map.on("mouseleave", "rev-fill", () => map.getCanvas().style.cursor = "");
      }
    }

    function showFeature(f) {
      selected = f.properties || {};
      const rows = Object.entries(selected)
        .map(([k, v]) => `<b>${k}</b>: ${v}`).join("<br>");
      document.getElementById("info").innerHTML =
        `<pre>${rows}</pre><button id="duid">AI-duiding</button><div id="duiding"></div>`;
      document.getElementById("duid").onclick = duid;
    }

    async function duid() {
      const out = document.getElementById("duiding");
      out.textContent = "Bezig…";
      try {
        const r = await fetch("/api/duiding", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ properties: selected })
        });
        if (!r.ok) throw new Error("status " + r.status);
        const d = await r.json();
        out.innerHTML = `<p>${d.duiding}</p><p class="muted">${d.bron}</p><p class="disc">${d.disclaimer}</p>`;
      } catch (e) {
        out.innerHTML = '<p class="muted">AI-duiding tijdelijk niet beschikbaar.</p>';
      }
    }

    map.on("load", loadRev);
    map.on("moveend", loadRev);
  </script>
</body>
</html>
```

- [ ] **Step 3: Handmatige verificatie (browser)**

Start de app: `bash scripts/05_run_api.sh` (of `uvicorn geluidsmeter.api:app --port 8792 --app-dir src`).
Open `http://localhost:8792/viewer`. Verwacht: BRT-kaart laadt; rode REV-punten verschijnen na het inzoomen op een gebied met REV-objecten; klik → detailvelden; "AI-duiding" → tekst + bron + disclaimer. Bij uitgeschakelde Qwen: nette "tijdelijk niet beschikbaar"-melding (geen crash).

- [ ] **Step 4: Commit**

```bash
git add src/leefomgevinglab/viewer/
git commit -m "feat(llab): MapLibre REV-viewer met PDOK-basis en AI-duiding

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Documentatie bijwerken

**Files:**
- Modify: `CLAUDE.md` (sprint-status + routes/poort-context)
- Modify: `README.md` (korte LeefomgevingLab-pointer)

**Interfaces:** geen code; alleen docs.

- [ ] **Step 1: Werk `CLAUDE.md` bij**

Voeg onder "Sprint status" een regel toe:
`- 🚧 **LeefomgevingLab fundering:** connector-laag + UC-04 REV-viewer (/viewer, /api/rev/features, /api/duiding)`
En noteer dat geluid één use-case wordt onder `src/leefomgevinglab/usecases/` (gepland), nieuwe code nu onder `src/leefomgevinglab/`.

- [ ] **Step 2: Werk `README.md` bij**

Voeg een korte alinea toe: het project groeit uit tot LeefomgevingLab; geluid is één use-case; REV-viewer op `/viewer`. Verwijs naar `LeefomgevingLab architectuuropzet v0_3.md` en `docs/superpowers/specs/2026-06-20-leefomgevinglab-fundering-design.md`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: LeefomgevingLab fundering + UC-04 in CLAUDE.md/README

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (volgt in Plan 2 — UC-03)

- DSO-connector (Toepasbare Regels + Stelselcatalogus), API-key in `.env`.
- RAG-pijplijn op IPLO (ingest → chunk → embed → lokale vectorstore op NVMe).
- Vergunningen-chatbot met antwoordcontract (bronverwijzing, onzekerheid, vangnet) + eval-set.
- Volledige repo/package-rename naar LeefomgevingLab + `git mv` van geluid naar `usecases/geluid/` met compat-shim, daarna systemd-units omzetten.

## Self-Review

- **Spec-dekking:** Sectie A (repo/structuur, services niet breken) → Tasks 1-4 + integratienotitie + Task 6; Sectie B (BaseConnector + connectors) → Tasks 1-2; Sectie C (UC-04 viewer) → Tasks 3-5; Sectie D (UC-03) → expliciet Plan 2; Sectie E (out of scope) → "Out of scope"-blok. Testen-sectie → elke task heeft TDD-cyclus + Task 4 Step 6 regressie.
- **Placeholders:** geen TODO/TBD in code; REV-endpoint is een concrete config-waarde met een aparte verificatiestap (Task 2 Step 0).
- **Type-consistentie:** `ConnectorError`, `BaseConnector.get_json`, `RevConnector.features(bbox)`, `rev_service.duiding(...)`, `_rev_connector()` consistent gebruikt over Tasks 1→4. Testhelpers (`_FakeResponse`) lokaal per testbestand.
