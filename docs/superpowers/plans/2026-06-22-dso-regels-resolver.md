# DSO-regels live: resolver + connector-rewrite + diepere inhoud — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /api/regels {activiteit, locatie}` geeft live DSO-regels terug: vrije tekst → werkzaamheid (ZoekInterface + Qwen-keuze) → regelbeheerobject-typeringen (Samengestelde RTR) → best-effort indieningsvereisten (Uitvoeren v3), ingepakt in een conservatief, gelaagd-degraderend antwoordcontract.

**Architecture:** Drie nieuwe units bovenop de bestaande connector-laag: een `ZoekConnector` (resolver-bron), een herschreven `DsoConnector` (POST-protocol, twee DSO-services), en pure `resolver`-helpers (Qwen-keuze + WGS84→RD via pyproj). De `vergunningen`-service orkestreert de lagen en laat elke laag onafhankelijk degraderen. `BaseConnector` krijgt `post_json` naast `get_json`.

**Tech Stack:** Python 3.10, FastAPI, httpx, pyproj, pytest. Lokale Qwen (`llama.cpp` OpenAI-compatible op `localhost:8080`). DSO Toepasbare Regels (pre-productie).

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src moet op het pad).
- App draait via `uvicorn geluidsmeter.api:app --app-dir src` op poort **8792**; service `geluidsmeter-api`. Bestaande routes/gedrag (REV, chatbot, datavraag, semantiek) niet wijzigen; hun tests blijven groen.
- **DSO_API_KEY** uit `.env` (gitignored); `api.py` laadt `.env` via `load_dotenv()` (al aanwezig). Geen key in repo/config.
- **DSO = pre-productie**: host `service.pre.omgevingswet.overheid.nl`, header `x-api-key`. Productie geeft 401.
- **Geometrie in RD/EPSG:28992** (GeoJSON Point `[x, y]`), niet WGS84.
- **Conservatief contract (harde eis):** elk antwoord bevat `disclaimer`, `vangnet`, `onzekerheid:true`, en `alternatieven` (andere werkzaamheid-kandidaten) blijven altijd zichtbaar. Geen stellige ja/nee-vergunninguitspraak.
- **Onafhankelijke degradatie:** faalt een diepere laag, dan blijven de ondiepere lagen staan met `beschikbaar:true`.
- Nieuwe logica onder `src/leefomgevinglab/`; `src/geluidsmeter/*` alleen additief (helpers + de bestaande `/api/regels`-route herschrijven).
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/
  connectors/
    base.py                          # + post_json() (MODIFY)
    dso.py                           # DsoConnector HERSCHREVEN (POST-protocol, 2 services)
    dso_zoek.py                      # ZoekConnector (resolver-bron) (CREATE)
  usecases/vergunningen/
    resolver.py                      # wgs84_naar_rd + kies_werkzaamheid (CREATE)
    service.py                       # regels_opzoeken HERSCHREVEN (orkestratie + contract)
src/geluidsmeter/api.py              # _zoek_connector/_dso_connector/_llm_cfg + route (MODIFY)
core/config.yaml                     # leefomgevinglab.dso: 3 service-URLs (MODIFY)
requirements.txt                     # + pyproj expliciet (MODIFY)
tests/test_base_connector.py         # + post_json-tests (MODIFY indien aanwezig, anders deel van Task 1)
tests/test_dso_zoek.py               # (CREATE)
tests/test_dso_connector.py          # HERSCHREVEN naar nieuw protocol
tests/test_vergunningen_resolver.py  # (CREATE)
tests/test_vergunningen_service.py   # HERSCHREVEN naar nieuwe orkestratie
tests/test_api_regels.py             # HERSCHREVEN naar nieuw contract + 422
tests/test_dso_live.py               # optionele live smoke (skip zonder DSO_API_KEY) (CREATE)
```

---

### Task 1: `BaseConnector.post_json`

**Files:**
- Modify: `src/leefomgevinglab/connectors/base.py`
- Test: `tests/test_base_connector.py`

**Interfaces:**
- Consumes: bestaande `BaseConnector` (`cache_dir`, `timeout`, `cache_ttl`, `_cache_path`, `ConnectorError`).
- Produces: `BaseConnector.post_json(url: str, json_body: dict | None = None, headers: dict | None = None) -> dict|list` — POST met on-disk cache (key op url + json_body), degradeert naar `ConnectorError`, valt terug op cache bij fout.

- [ ] **Step 1: Schrijf de falende test**

Voeg toe aan `tests/test_base_connector.py` (maak het bestand als het niet bestaat, met `import json, time` en `from leefomgevinglab.connectors.base import BaseConnector, ConnectorError`):

```python
import httpx
from leefomgevinglab.connectors.base import BaseConnector, ConnectorError


def test_post_json_sends_body_and_caches(tmp_path, monkeypatch):
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    c = BaseConnector(cache_dir=str(tmp_path))
    out = c.post_json("https://x/op", json_body={"a": 1}, headers={"x-api-key": "K"})
    assert out == {"ok": True}
    assert calls["json"] == {"a": 1}
    assert calls["headers"]["x-api-key"] == "K"

    # tweede call met dezelfde body komt uit cache, ook als het netwerk faalt
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    assert c.post_json("https://x/op", json_body={"a": 1}) == {"ok": True}


def test_post_json_raises_without_cache(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    c = BaseConnector(cache_dir=str(tmp_path))
    try:
        c.post_json("https://x/op", json_body={"a": 2})
        assert False, "verwacht ConnectorError"
    except ConnectorError:
        pass
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_base_connector.py -q`
Expected: FAIL met `AttributeError: 'BaseConnector' object has no attribute 'post_json'`

- [ ] **Step 3: Implementeer `post_json`**

Voeg in `src/leefomgevinglab/connectors/base.py` direct ná `get_json` toe:

```python
    def post_json(self, url: str, json_body: dict | None = None, headers: dict | None = None):
        cp = self._cache_path(url, json_body)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < self.cache_ttl:
            return json.loads(cp.read_text())
        try:
            resp = httpx.post(url, json=json_body, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            if cp.exists():
                return json.loads(cp.read_text())
            raise ConnectorError(f"Bron niet beschikbaar: {url}") from exc
        cp.write_text(json.dumps(data))
        return data
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_base_connector.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/connectors/base.py tests/test_base_connector.py
git commit -m "feat(llab): BaseConnector.post_json met cache + degradatie

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `ZoekConnector` (resolver-bron)

**Files:**
- Create: `src/leefomgevinglab/connectors/dso_zoek.py`
- Test: `tests/test_dso_zoek.py`

**Interfaces:**
- Consumes: `BaseConnector`, `ConnectorError`, `post_json` (Task 1).
- Produces: `ZoekConnector(base_url, api_key, api_key_header="x-api-key", **kwargs)` met
  `zoek_werkzaamheden(tekst: str, max_n: int = 5) -> list[dict]` → lijst van
  `{"urn","omschrijving","functioneleStructuurRef","trefwoorden"}` (top-N, gerankt). Raise `ConnectorError` zonder key.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_dso_zoek.py`:

```python
import pytest
from leefomgevinglab.connectors.dso_zoek import ZoekConnector
from leefomgevinglab.connectors.base import ConnectorError


def test_zoek_werkzaamheden_parses_hal(tmp_path):
    captured = {}

    class _Z(ZoekConnector):
        def post_json(self, url, json_body=None, headers=None):
            captured["url"] = url
            captured["body"] = json_body
            captured["headers"] = headers
            return {"_embedded": {"werkzaamheden": [
                {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen",
                 "functioneleStructuurRef": "http://x/werkzaamheden/id/concept/DakkapelPlaatsen",
                 "trefwoorden": ["dakkapel"]},
                {"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden",
                 "functioneleStructuurRef": "http://x/werkzaamheden/id/concept/BouwwerkOnderhouden",
                 "trefwoorden": ["onderhoud"]},
            ]}}

    c = _Z(base_url="https://x/v2/", api_key="K", cache_dir=str(tmp_path))
    out = c.zoek_werkzaamheden("dakkapel")
    assert captured["url"] == "https://x/v2/werkzaamheden/_zoek"
    assert captured["body"] == {"zoekterm": "dakkapel"}
    assert captured["headers"]["x-api-key"] == "K"
    assert out[0]["urn"] == "DakkapelPlaatsen"
    assert out[0]["trefwoorden"] == ["dakkapel"]
    assert len(out) == 2


def test_zoek_respects_max_n(tmp_path):
    class _Z(ZoekConnector):
        def post_json(self, url, json_body=None, headers=None):
            return {"_embedded": {"werkzaamheden": [{"urn": str(i)} for i in range(10)]}}

    c = _Z(base_url="https://x/v2", api_key="K", cache_dir=str(tmp_path))
    assert len(c.zoek_werkzaamheden("x", max_n=3)) == 3


def test_zoek_without_key_raises(tmp_path):
    c = ZoekConnector(base_url="https://x/v2", api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.zoek_werkzaamheden("dakkapel")
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_dso_zoek.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.connectors.dso_zoek'`

- [ ] **Step 3: Schrijf de connector**

`src/leefomgevinglab/connectors/dso_zoek.py`:

```python
"""DSO ZoekInterface: vrije-tekst zoeken naar werkzaamheden (resolver-bron).

POST /werkzaamheden/_zoek met body {"zoekterm": "<vrije tekst>"} (leeg = alle).
Geeft HAL-respons _embedded.werkzaamheden[] gerankt op relevantie.
"""
from .base import BaseConnector, ConnectorError


class ZoekConnector(BaseConnector):
    def __init__(self, base_url: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def zoek_werkzaamheden(self, tekst: str, max_n: int = 5) -> list[dict]:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.base_url}/werkzaamheden/_zoek"
        headers = {self.api_key_header: self.api_key}
        data = self.post_json(url, json_body={"zoekterm": tekst}, headers=headers)
        items = (data.get("_embedded") or {}).get("werkzaamheden") or []
        out = []
        for w in items[:max_n]:
            out.append({
                "urn": w.get("urn"),
                "omschrijving": w.get("omschrijving"),
                "functioneleStructuurRef": w.get("functioneleStructuurRef"),
                "trefwoorden": w.get("trefwoorden") or [],
            })
        return out
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_dso_zoek.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/connectors/dso_zoek.py tests/test_dso_zoek.py
git commit -m "feat(llab): ZoekConnector (DSO ZoekInterface, vrije-tekst werkzaamheden)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `DsoConnector` herschreven (POST-protocol, 2 services)

**Files:**
- Modify (vervangen): `src/leefomgevinglab/connectors/dso.py`
- Test (herschrijven): `tests/test_dso_connector.py`

**Interfaces:**
- Consumes: `BaseConnector`, `ConnectorError`, `post_json` (Task 1).
- Produces: `DsoConnector(rtr_base_url, uitvoeren_base_url, api_key, api_key_header="x-api-key", **kwargs)` met
  - `bepaal_typeringen(refs: list[str], geo_rd: tuple[float,float], datum: str|None=None) -> list[dict]`
    — POST `{rtr_base_url}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen`.
  - `bepaal_indieningsvereisten(refs: list[str], geo_rd: tuple[float,float], datum: str|None=None) -> list[dict]`
    — POST `{uitvoeren_base_url}/indieningsvereisten/_bepaal` met `Content-Crs: EPSG:28992`.
  - Beide raise `ConnectorError` zonder key.

- [ ] **Step 1: Herschrijf de test**

Vervang de inhoud van `tests/test_dso_connector.py` volledig door:

```python
import pytest
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.base import ConnectorError

RTR = "https://x/rtr/v2"
UITV = "https://x/uitv/v3"
REF = "http://x/werkzaamheden/id/concept/DakkapelPlaatsen"


def _conn(tmp_path, capture, ret):
    class _D(DsoConnector):
        def post_json(self, url, json_body=None, headers=None):
            capture["url"] = url
            capture["body"] = json_body
            capture["headers"] = headers
            return ret

    return _D(rtr_base_url=RTR, uitvoeren_base_url=UITV, api_key="K", cache_dir=str(tmp_path))


def test_bepaal_typeringen(tmp_path):
    cap = {}
    c = _conn(tmp_path, cap, [{"functioneleStructuurRef": REF, "regelbeheerobjecten": ["Conclusie"]}])
    out = c.bepaal_typeringen([REF], (155000.0, 463000.0))
    assert cap["url"] == f"{RTR}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen"
    assert cap["body"]["functioneleStructuurRefs"] == [REF]
    assert cap["body"]["_geo"] == {"intersects": {"type": "Point", "coordinates": [155000.0, 463000.0]}}
    assert cap["headers"]["x-api-key"] == "K"
    assert out[0]["regelbeheerobjecten"] == ["Conclusie"]


def test_bepaal_indieningsvereisten_sets_crs_and_antwoorden(tmp_path):
    cap = {}
    c = _conn(tmp_path, cap, [{"indieningsvereisten": []}])
    c.bepaal_indieningsvereisten([REF], (121000.0, 487000.0))
    assert cap["url"] == f"{UITV}/indieningsvereisten/_bepaal"
    assert cap["body"]["functioneleStructuurRefs"] == [{"functioneleStructuurRef": REF, "antwoorden": []}]
    assert cap["body"]["_geo"]["intersects"]["coordinates"] == [121000.0, 487000.0]
    assert cap["headers"]["Content-Crs"] == "EPSG:28992"
    assert cap["headers"]["x-api-key"] == "K"


def test_without_key_raises(tmp_path):
    c = DsoConnector(rtr_base_url=RTR, uitvoeren_base_url=UITV, api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.bepaal_typeringen([REF], (1.0, 2.0))
    with pytest.raises(ConnectorError):
        c.bepaal_indieningsvereisten([REF], (1.0, 2.0))
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_dso_connector.py -q`
Expected: FAIL (`TypeError`: oude `DsoConnector` kent `rtr_base_url` niet / mist methodes)

- [ ] **Step 3: Herschrijf de connector**

Vervang de inhoud van `src/leefomgevinglab/connectors/dso.py` volledig door:

```python
"""DSO Toepasbare Regels via het echte POST-protocol (pre-productie).

Twee services:
- Samengestelde RTR v2: _bepaalRegelbeheerobjectTyperingen (welke regelbeheerobjecten gelden).
- Uitvoeren v3: indieningsvereisten/_bepaal (best-effort diepere inhoud; Content-Crs EPSG:28992).

Geometrie in RD/EPSG:28992 als GeoJSON Point [x, y]. Refs zijn werkzaamheid-concept-URI's.
Live geverifieerd 2026-06-22; zie docs/superpowers/specs/2026-06-22-dso-regels-resolver-design.md.
"""
from .base import BaseConnector, ConnectorError


def _geo_point(geo_rd: tuple[float, float]) -> dict:
    return {"intersects": {"type": "Point", "coordinates": [geo_rd[0], geo_rd[1]]}}


class DsoConnector(BaseConnector):
    def __init__(self, rtr_base_url: str, uitvoeren_base_url: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.rtr_base_url = rtr_base_url.rstrip("/")
        self.uitvoeren_base_url = uitvoeren_base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def _headers(self, extra: dict | None = None) -> dict:
        h = {self.api_key_header: self.api_key}
        if extra:
            h.update(extra)
        return h

    def bepaal_typeringen(self, refs: list[str], geo_rd: tuple[float, float],
                          datum: str | None = None) -> list[dict]:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.rtr_base_url}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen"
        body = {"functioneleStructuurRefs": list(refs), "_geo": _geo_point(geo_rd)}
        if datum:
            body["datum"] = datum
        return self.post_json(url, json_body=body, headers=self._headers())

    def bepaal_indieningsvereisten(self, refs: list[str], geo_rd: tuple[float, float],
                                   datum: str | None = None) -> list[dict]:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.uitvoeren_base_url}/indieningsvereisten/_bepaal"
        body = {
            "functioneleStructuurRefs": [{"functioneleStructuurRef": r, "antwoorden": []} for r in refs],
            "_geo": _geo_point(geo_rd),
        }
        if datum:
            body["datum"] = datum
        return self.post_json(url, json_body=body, headers=self._headers({"Content-Crs": "EPSG:28992"}))
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_dso_connector.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/connectors/dso.py tests/test_dso_connector.py
git commit -m "feat(llab): DsoConnector herschreven naar POST-protocol (typeringen + indieningsvereisten)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `resolver` — WGS84→RD + Qwen-keuze

**Files:**
- Create: `src/leefomgevinglab/usecases/vergunningen/resolver.py`
- Test: `tests/test_vergunningen_resolver.py`

**Interfaces:**
- Consumes: `pyproj.Transformer`, `httpx`, `ConnectorError`.
- Produces:
  - `wgs84_naar_rd(lat: float, lon: float) -> tuple[float, float]` — EPSG:4326 → EPSG:28992 (x, y), afgerond op 0.1 m.
  - `kies_werkzaamheid(vraag: str, kandidaten: list[dict], llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict`
    → `{"gekozen": dict|None, "match_onderbouwing": str, "zekerheid_match": "hoog"|"midden"|"laag"}`.
    0 kandidaten → `gekozen=None`. 1 kandidaat → die, zonder LLM. Meer → Qwen kiest; bij LLM-fout val terug op de hoogst gerankte (`zekerheid_match="laag"`).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_vergunningen_resolver.py`:

```python
import httpx
from leefomgevinglab.usecases.vergunningen import resolver

K1 = {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen", "trefwoorden": ["dakkapel"],
      "functioneleStructuurRef": "http://x/DakkapelPlaatsen"}
K2 = {"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden", "trefwoorden": ["onderhoud"],
      "functioneleStructuurRef": "http://x/BouwwerkOnderhouden"}


def test_wgs84_naar_rd_amersfoort_referentiepunt():
    # OLV-toren Amersfoort = definitiepunt RD (155000, 463000)
    x, y = resolver.wgs84_naar_rd(52.15517440, 5.38720621)
    assert abs(x - 155000) < 1.0
    assert abs(y - 463000) < 1.0


def test_kies_geen_kandidaten():
    out = resolver.kies_werkzaamheid("iets", [], "http://llm/v1", "qwen")
    assert out["gekozen"] is None
    assert out["zekerheid_match"] == "laag"


def test_kies_een_kandidaat_zonder_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM mag niet aangeroepen worden bij 1 kandidaat")

    monkeypatch.setattr(httpx, "post", boom)
    out = resolver.kies_werkzaamheid("dakkapel", [K1], "http://llm/v1", "qwen")
    assert out["gekozen"]["urn"] == "DakkapelPlaatsen"


def test_kies_meer_kandidaten_qwen(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"index": 1, "onderbouwing": "onderhoud past beter", "zekerheid": "hoog"}'}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = resolver.kies_werkzaamheid("onderhoud plegen", [K1, K2], "http://llm/v1", "qwen")
    assert out["gekozen"]["urn"] == "BouwwerkOnderhouden"
    assert out["zekerheid_match"] == "hoog"
    assert "onderhoud" in out["match_onderbouwing"]


def test_kies_valt_terug_bij_llm_fout(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    out = resolver.kies_werkzaamheid("x", [K1, K2], "http://llm/v1", "qwen")
    assert out["gekozen"]["urn"] == "DakkapelPlaatsen"   # hoogst gerankt
    assert out["zekerheid_match"] == "laag"
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_resolver.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.vergunningen.resolver'`

- [ ] **Step 3: Schrijf de resolver**

`src/leefomgevinglab/usecases/vergunningen/resolver.py`:

```python
"""Resolver: vrije tekst -> werkzaamheid (Qwen-keuze) + WGS84 -> RD (EPSG:28992)."""
import json

import httpx
from pyproj import Transformer

# always_xy=True => transform(lon, lat) -> (x, y)
_TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def wgs84_naar_rd(lat: float, lon: float) -> tuple[float, float]:
    x, y = _TRANSFORMER.transform(lon, lat)
    return (round(x, 1), round(y, 1))


def _top_hit(kandidaten: list[dict], onderbouwing: str, zekerheid: str) -> dict:
    return {"gekozen": kandidaten[0], "match_onderbouwing": onderbouwing, "zekerheid_match": zekerheid}


def kies_werkzaamheid(vraag: str, kandidaten: list[dict], llm_base_url: str, model: str,
                      timeout_s: float = 60.0) -> dict:
    if not kandidaten:
        return {"gekozen": None, "match_onderbouwing": "Geen werkzaamheid gevonden",
                "zekerheid_match": "laag"}
    if len(kandidaten) == 1:
        return _top_hit(kandidaten, "Enige kandidaat", "midden")

    opties = "\n".join(
        f"{i}. {k.get('omschrijving')} (trefwoorden: {', '.join(k.get('trefwoorden') or [])})"
        for i, k in enumerate(kandidaten)
    )
    prompt = (
        "Je bent een feitelijke assistent voor de Omgevingswet. Kies welke werkzaamheid het "
        "beste past bij de vraag van de burger. Verzin niets; kies uit de gegeven lijst.\n\n"
        f"Vraag: {vraag}\n\nWerkzaamheden:\n{opties}\n\n"
        'Antwoord UITSLUITEND als JSON: {"index": <nummer>, "onderbouwing": "<kort>", '
        '"zekerheid": "hoog|midden|laag"}'
    )
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        parsed = json.loads(text)
        idx = int(parsed["index"])
        if not 0 <= idx < len(kandidaten):
            raise ValueError("index buiten bereik")
        zekerheid = parsed.get("zekerheid", "midden")
        if zekerheid not in ("hoog", "midden", "laag"):
            zekerheid = "midden"
        return {"gekozen": kandidaten[idx],
                "match_onderbouwing": parsed.get("onderbouwing", ""),
                "zekerheid_match": zekerheid}
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        return _top_hit(kandidaten, "LLM niet beschikbaar; hoogst gerankte gekozen", "laag")
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_resolver.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/resolver.py tests/test_vergunningen_resolver.py
git commit -m "feat(llab): resolver (WGS84->RD via pyproj + Qwen werkzaamheid-keuze)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `vergunningen.service` herschreven (orkestratie + contract)

**Files:**
- Modify (vervangen): `src/leefomgevinglab/usecases/vergunningen/service.py`
- Test (herschrijven): `tests/test_vergunningen_service.py`

**Interfaces:**
- Consumes: `ConnectorError`; `resolver.kies_werkzaamheid` / `resolver.wgs84_naar_rd` (Task 4);
  een `zoek_connector` met `zoek_werkzaamheden(tekst)` (Task 2); een `dso_connector` met
  `bepaal_typeringen(refs, geo_rd)` + `bepaal_indieningsvereisten(refs, geo_rd)` (Task 3).
- Produces: `DISCLAIMER`, `VANGNET`, `BRON`, en
  `regels_opzoeken(activiteit: str, locatie: dict, zoek_connector, dso_connector, llm_cfg: dict) -> dict`
  met het gelaagde antwoordcontract (zie spec). `llm_cfg` = `{"llm_base_url","model","timeout_s"}`.

- [ ] **Step 1: Herschrijf de test**

Vervang de inhoud van `tests/test_vergunningen_service.py` volledig door:

```python
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import service

LOC = {"lat": 52.0, "lon": 5.0}
LLM = {"llm_base_url": "http://llm/v1", "model": "qwen", "timeout_s": 5}
KAND = [
    {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen", "trefwoorden": ["dakkapel"],
     "functioneleStructuurRef": "http://x/DakkapelPlaatsen"},
    {"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden", "trefwoorden": ["onderhoud"],
     "functioneleStructuurRef": "http://x/BouwwerkOnderhouden"},
]


class _Zoek:
    def __init__(self, kand=None, error=False):
        self._kand, self._error = kand, error

    def zoek_werkzaamheden(self, tekst, max_n=5):
        if self._error:
            raise ConnectorError("down")
        return self._kand


class _Dso:
    def __init__(self, typ=None, iv=None, typ_err=False, iv_err=False):
        self._typ, self._iv = typ, iv
        self._typ_err, self._iv_err = typ_err, iv_err

    def bepaal_typeringen(self, refs, geo_rd, datum=None):
        if self._typ_err:
            raise ConnectorError("down")
        return self._typ

    def bepaal_indieningsvereisten(self, refs, geo_rd, datum=None):
        if self._iv_err:
            raise ConnectorError("down")
        return self._iv


def _patch_resolver(monkeypatch, gekozen_idx=0):
    monkeypatch.setattr(service.resolver, "wgs84_naar_rd", lambda lat, lon: (155000.0, 463000.0))
    monkeypatch.setattr(service.resolver, "kies_werkzaamheid",
                        lambda vraag, kand, **cfg: {"gekozen": kand[gekozen_idx],
                                                    "match_onderbouwing": "test", "zekerheid_match": "hoog"})


def test_happy_alle_lagen(monkeypatch):
    _patch_resolver(monkeypatch)
    zoek = _Zoek(kand=KAND)
    dso = _Dso(typ=[{"regelbeheerobjecten": ["Conclusie", "Indieningsvereisten"]}],
               iv=[{"naam": "Tekening"}])
    out = service.regels_opzoeken("dakkapel", LOC, zoek, dso, LLM)
    assert out["beschikbaar"] is True
    assert out["gekozen_werkzaamheid"]["urn"] == "DakkapelPlaatsen"
    assert out["alternatieven"] == [{"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden"}]
    assert out["typeringen"] == ["Conclusie", "Indieningsvereisten"]
    assert out["indieningsvereisten"] == [{"naam": "Tekening"}]
    assert out["indieningsvereisten_status"] == "beschikbaar"
    assert out["locatie_rd"] == [155000.0, 463000.0]
    assert out["onzekerheid"] is True
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"] == service.DISCLAIMER


def test_geen_kandidaten_degradeert(monkeypatch):
    out = service.regels_opzoeken("onzin", LOC, _Zoek(kand=[]), _Dso(), LLM)
    assert out["beschikbaar"] is False
    assert out["gekozen_werkzaamheid"] is None
    assert out["disclaimer"] == service.DISCLAIMER
    assert "bevoegd gezag" in out["vangnet"]


def test_zoekbron_down_degradeert():
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(error=True), _Dso(), LLM)
    assert out["beschikbaar"] is False
    assert out["gekozen_werkzaamheid"] is None


def test_iv_leeg_status_niet_beschikbaar_op_locatie(monkeypatch):
    _patch_resolver(monkeypatch)
    dso = _Dso(typ=[{"regelbeheerobjecten": ["Conclusie"]}], iv=[])
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), dso, LLM)
    assert out["beschikbaar"] is True
    assert out["typeringen"] == ["Conclusie"]
    assert out["indieningsvereisten"] is None
    assert out["indieningsvereisten_status"] == "niet_beschikbaar_op_locatie"


def test_iv_bron_down_degradeert_alleen_laag5(monkeypatch):
    _patch_resolver(monkeypatch)
    dso = _Dso(typ=[{"regelbeheerobjecten": ["Conclusie"]}], iv_err=True)
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), dso, LLM)
    assert out["beschikbaar"] is True                       # laag 1-4 blijven staan
    assert out["typeringen"] == ["Conclusie"]
    assert out["indieningsvereisten_status"] == "bron_tijdelijk_niet_beschikbaar"


def test_typeringen_down_degradeert_alleen_laag4(monkeypatch):
    _patch_resolver(monkeypatch)
    dso = _Dso(typ_err=True, iv=[])
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), dso, LLM)
    assert out["beschikbaar"] is True
    assert out["typeringen"] is None
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_service.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'resolver'` / oude `regels_opzoeken`-signatuur)

- [ ] **Step 3: Herschrijf de service**

Vervang de inhoud van `src/leefomgevinglab/usecases/vergunningen/service.py` volledig door:

```python
"""UC-03a: regels opzoeken bij de DSO (Zoek -> Qwen -> typeringen -> indieningsvereisten).

Gelaagd, conservatief antwoordcontract: elke laag degradeert onafhankelijk; alternatieven
blijven altijd zichtbaar; geen stellige vergunninguitspraak.
"""
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import resolver

DISCLAIMER = (
    "Indicatief, geen juridisch besluit. De getoonde regels zijn een ruwe weergave "
    "van de Registratie Toepasbare Regels."
)
VANGNET = (
    "Raadpleeg het bevoegd gezag of het Omgevingsloket (omgevingswet.overheid.nl) "
    "voor de officiele vergunning- of meldingsplicht."
)
BRON = "DSO Toepasbare Regels (Zoek + RTR + Uitvoeren)"


def _contract_basis(activiteit: str) -> dict:
    return {"vraag": activiteit, "bron": BRON, "onzekerheid": True,
            "disclaimer": DISCLAIMER, "vangnet": VANGNET}


def _onbeschikbaar(activiteit: str) -> dict:
    return {**_contract_basis(activiteit), "beschikbaar": False, "gekozen_werkzaamheid": None,
            "alternatieven": [], "typeringen": None, "indieningsvereisten": None,
            "indieningsvereisten_status": "niet_beschikbaar", "locatie_rd": None}


def regels_opzoeken(activiteit: str, locatie: dict, zoek_connector, dso_connector,
                    llm_cfg: dict) -> dict:
    # Laag 1: zoek werkzaamheden
    try:
        kandidaten = zoek_connector.zoek_werkzaamheden(activiteit)
    except ConnectorError:
        return _onbeschikbaar(activiteit)
    if not kandidaten:
        return _onbeschikbaar(activiteit)

    # Laag 2: Qwen kiest
    keuze = resolver.kies_werkzaamheid(activiteit, kandidaten, **llm_cfg)
    gekozen = keuze["gekozen"]
    if gekozen is None:
        return _onbeschikbaar(activiteit)
    alternatieven = [{"urn": k["urn"], "omschrijving": k["omschrijving"]}
                     for k in kandidaten if k["urn"] != gekozen["urn"]]
    ref = gekozen["functioneleStructuurRef"]

    # Laag 3: WGS84 -> RD
    rd = resolver.wgs84_naar_rd(locatie["lat"], locatie["lon"])

    # Laag 4: regelbeheerobject-typeringen
    try:
        typ_resp = dso_connector.bepaal_typeringen([ref], rd)
        typeringen = (typ_resp[0].get("regelbeheerobjecten") if typ_resp else []) or []
    except ConnectorError:
        typeringen = None

    # Laag 5: indieningsvereisten (best-effort)
    indieningsvereisten = None
    iv_status = "niet_beschikbaar_op_locatie"
    try:
        iv = dso_connector.bepaal_indieningsvereisten([ref], rd)
        if iv:
            indieningsvereisten = iv
            iv_status = "beschikbaar"
    except ConnectorError:
        iv_status = "bron_tijdelijk_niet_beschikbaar"

    return {**_contract_basis(activiteit), "beschikbaar": True,
            "gekozen_werkzaamheid": {
                "urn": gekozen["urn"], "omschrijving": gekozen["omschrijving"],
                "match_onderbouwing": keuze["match_onderbouwing"],
                "zekerheid_match": keuze["zekerheid_match"]},
            "alternatieven": alternatieven,
            "typeringen": typeringen,
            "indieningsvereisten": indieningsvereisten,
            "indieningsvereisten_status": iv_status,
            "locatie_rd": list(rd)}
```

> **Noot (laag 5):** de status `vereist_nadere_vragen` uit de spec wordt nog niet geëmitteerd —
> dat vereist een geverifieerde 200-respons van `indieningsvereisten/_bepaal` om "open vragen" te
> herkennen (in oefen niet reproduceerbaar gekregen). De statuswaarde is gereserveerd voor een
> vervolg; nu geldt: niet-lege respons = `beschikbaar`, lege = `niet_beschikbaar_op_locatie`,
> bronfout = `bron_tijdelijk_niet_beschikbaar`.

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_service.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/service.py tests/test_vergunningen_service.py
git commit -m "feat(llab): vergunningen-service herschreven (gelaagde DSO-orkestratie + contract)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: API-route, config, requirements + regressie

**Files:**
- Modify: `src/geluidsmeter/api.py` (helpers + route)
- Modify: `core/config.yaml` (`leefomgevinglab.dso`: 3 service-URLs)
- Modify: `requirements.txt` (pyproj expliciet)
- Test (herschrijven): `tests/test_api_regels.py`
- Test (create): `tests/test_dso_live.py`

**Interfaces:**
- Consumes: `ZoekConnector` (Task 2), `DsoConnector` (Task 3), `vergunningen_service.regels_opzoeken` (Task 5),
  `os`, bestaande `_config`/`load_config`.
- Produces (HTTP): `POST /api/regels` body `{"activiteit": str, "locatie": {"lat": float, "lon": float}}`
  → het gelaagde contract (HTTP 200; ook bij `beschikbaar:false`). Ontbrekende/incomplete `locatie` → HTTP 422.
  Helpers `_zoek_connector()`, `_dso_connector()`, `_llm_cfg()` (monkeypatchbaar).

- [ ] **Step 1: Werk `core/config.yaml` bij**

Vervang in `core/config.yaml` het hele blok `  dso:` (de huidige `base_url`/`operation_path`/`api_key_header`) door:

```yaml
  dso:
    # DSO Toepasbare Regels (pre-productie). Live geverifieerd 2026-06-22 met DSO_API_KEY.
    # Keys werken alleen op service.pre.* (productie geeft 401). Header x-api-key.
    # Geometrie in RD/EPSG:28992. Zie spec 2026-06-22-dso-regels-resolver-design.md.
    api_key_header: "x-api-key"
    zoek_base_url: "https://service.pre.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/zoekinterface/v2"
    rtr_base_url: "https://service.pre.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/samengestelderegistratietoepasbareregelsservices/v2"
    uitvoeren_base_url: "https://service.pre.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/toepasbareregelsuitvoerenservices/v3"
```

- [ ] **Step 2: Voeg pyproj toe aan `requirements.txt`**

Voeg een regel `pyproj` toe aan `requirements.txt` (alfabetisch nabij `geopandas`). Verifieer dat hij importeert:

Run: `PYTHONPATH=src python -c "import pyproj; print(pyproj.__version__)"`
Expected: een versienummer (bv. `3.7.1`)

- [ ] **Step 3: Herschrijf de route-test**

Vervang de inhoud van `tests/test_api_regels.py` volledig door:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api


def _client(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "cache_dir": "/tmp/llab_test_cache",
            "llm": {"base_url": "http://llm/v1", "model": "qwen", "timeout_s": 5},
            "dso": {
                "api_key_header": "x-api-key",
                "zoek_base_url": "https://x/zoek/v2",
                "rtr_base_url": "https://x/rtr/v2",
                "uitvoeren_base_url": "https://x/uitv/v3",
            },
        }
    }
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_regels_happy(monkeypatch):
    client = _client(monkeypatch)

    class _Zoek:
        def zoek_werkzaamheden(self, tekst, max_n=5):
            return [{"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen",
                     "trefwoorden": ["dakkapel"], "functioneleStructuurRef": "http://x/DakkapelPlaatsen"}]

    class _Dso:
        def bepaal_typeringen(self, refs, geo_rd, datum=None):
            return [{"regelbeheerobjecten": ["Conclusie"]}]

        def bepaal_indieningsvereisten(self, refs, geo_rd, datum=None):
            return []

    monkeypatch.setattr(api, "_zoek_connector", lambda: _Zoek())
    monkeypatch.setattr(api, "_dso_connector", lambda: _Dso())
    r = client.post("/api/regels", json={"activiteit": "dakkapel", "locatie": {"lat": 52.0, "lon": 5.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["beschikbaar"] is True
    assert body["gekozen_werkzaamheid"]["urn"] == "DakkapelPlaatsen"
    assert body["typeringen"] == ["Conclusie"]
    assert body["indieningsvereisten_status"] == "niet_beschikbaar_op_locatie"
    assert "bevoegd gezag" in body["vangnet"]


def test_regels_locatie_verplicht(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/api/regels", json={"activiteit": "dakkapel", "locatie": None})
    assert r.status_code == 422
    r2 = client.post("/api/regels", json={"activiteit": "dakkapel", "locatie": {"lat": 52.0}})
    assert r2.status_code == 422


def test_regels_zoekbron_down_200_unavailable(monkeypatch):
    from leefomgevinglab.connectors.base import ConnectorError
    client = _client(monkeypatch)

    class _Zoek:
        def zoek_werkzaamheden(self, tekst, max_n=5):
            raise ConnectorError("geen key")

    monkeypatch.setattr(api, "_zoek_connector", lambda: _Zoek())
    monkeypatch.setattr(api, "_dso_connector", lambda: object())
    r = client.post("/api/regels", json={"activiteit": "x", "locatie": {"lat": 52.0, "lon": 5.0}})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
```

- [ ] **Step 4: Run route-test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_regels.py -q`
Expected: FAIL (`AttributeError: module 'geluidsmeter.api' has no attribute '_zoek_connector'`)

- [ ] **Step 5: Werk de imports + helpers + route bij in `src/geluidsmeter/api.py`**

Vervang de bestaande import-regel `from leefomgevinglab.connectors.dso import DsoConnector` door:

```python
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.dso_zoek import ZoekConnector
```

Vervang het bestaande blok `def _dso_connector() ... @app.post("/api/regels") ... ` (helper t/m route) door:

```python
def _zoek_connector() -> ZoekConnector:
    ll = _config.get("leefomgevinglab", {})
    dso = ll.get("dso", {})
    return ZoekConnector(
        base_url=dso.get("zoek_base_url", ""),
        api_key=os.environ.get("DSO_API_KEY"),
        api_key_header=dso.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


def _dso_connector() -> DsoConnector:
    ll = _config.get("leefomgevinglab", {})
    dso = ll.get("dso", {})
    return DsoConnector(
        rtr_base_url=dso.get("rtr_base_url", ""),
        uitvoeren_base_url=dso.get("uitvoeren_base_url", ""),
        api_key=os.environ.get("DSO_API_KEY"),
        api_key_header=dso.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


def _llm_cfg() -> dict:
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    return {
        "llm_base_url": llm.get("base_url", "http://localhost:8080/v1"),
        "model": llm.get("model", "qwen2.5-32b"),
        "timeout_s": llm.get("timeout_s", 60),
    }


class RegelsRequest(BaseModel):
    activiteit: str
    locatie: dict | None = None


@app.post("/api/regels")
def api_regels(req: RegelsRequest):
    if not req.locatie or "lat" not in req.locatie or "lon" not in req.locatie:
        raise HTTPException(status_code=422, detail="locatie met lat en lon is verplicht")
    return vergunningen_service.regels_opzoeken(
        req.activiteit, req.locatie, _zoek_connector(), _dso_connector(), _llm_cfg()
    )
```

- [ ] **Step 6: Run route-test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_regels.py -q`
Expected: PASS (3 passed)

- [ ] **Step 7: Schrijf de optionele live smoke-test**

`tests/test_dso_live.py`:

```python
"""Optionele live smoke-test tegen DSO pre-productie. Skipt zonder DSO_API_KEY."""
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DSO_API_KEY"),
                                reason="DSO_API_KEY niet gezet; live-test overgeslagen")

ZOEK = "https://service.pre.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/zoekinterface/v2"
RTR = ("https://service.pre.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/"
       "samengestelderegistratietoepasbareregelsservices/v2")


def test_live_dakkapel_keten(tmp_path):
    from leefomgevinglab.connectors.dso_zoek import ZoekConnector
    from leefomgevinglab.connectors.dso import DsoConnector

    key = os.environ["DSO_API_KEY"]
    zoek = ZoekConnector(base_url=ZOEK, api_key=key, cache_dir=str(tmp_path))
    kand = zoek.zoek_werkzaamheden("dakkapel")
    assert any(k["urn"] == "DakkapelPlaatsen" for k in kand)

    ref = next(k["functioneleStructuurRef"] for k in kand if k["urn"] == "DakkapelPlaatsen")
    dso = DsoConnector(rtr_base_url=RTR, uitvoeren_base_url=RTR, api_key=key, cache_dir=str(tmp_path))
    typ = dso.bepaal_typeringen([ref], (155000.0, 463000.0))
    assert typ and "regelbeheerobjecten" in typ[0]
```

- [ ] **Step 8: Draai de volledige suite (regressie)**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alle bestaande tests (REV, chatbot, datavraag, semantiek, base-connector) + de nieuwe groen; `test_dso_live.py` wordt geskipt zonder gezette key (of slaagt mét key).

- [ ] **Step 9: Commit**

```bash
git add src/geluidsmeter/api.py core/config.yaml requirements.txt tests/test_api_regels.py tests/test_dso_live.py
git commit -m "feat(llab): /api/regels live (resolver + 3 DSO-services + RD-geo), config + pyproj

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (vervolg)

- Interactieve vragenboom (`antwoorden`-flow), `conclusie/_bepaal`, `maatregelen/_bepaal`.
- Chatbot-integratie (rules-as-code naast RAG op `/chatbot`).
- Frontend voor `/api/regels`.
- `vereist_nadere_vragen`-detectie (vereist geverifieerde 200-respons van Uitvoeren v3).
- WGS84→RD buiten Nederland.

## Self-Review

- **Spec-dekking:** ZoekInterface-resolver → Task 2; connector-rewrite POST-protocol + diepere inhoud →
  Task 1 (post_json) + Task 3; Qwen-keuze + WGS84→RD → Task 4; gelaagd contract + onafhankelijke
  degradatie + alternatieven-zichtbaarheid → Task 5; route + config (3 service-URLs) + 422 +
  pyproj + live smoke → Task 6. Vragenboom expliciet out of scope (spec + hierboven).
- **Placeholders:** geen TBD/TODO; alle stappen bevatten concrete code/commando's. De gereserveerde
  status `vereist_nadere_vragen` is expliciet gemarkeerd als niet-geëmitteerd met reden (geen gok).
- **Type-consistentie:** `zoek_werkzaamheden(tekst, max_n)`, `bepaal_typeringen(refs, geo_rd, datum)`,
  `bepaal_indieningsvereisten(refs, geo_rd, datum)`, `kies_werkzaamheid(vraag, kandidaten, llm_base_url,
  model, timeout_s)`, `wgs84_naar_rd(lat, lon)`, `regels_opzoeken(activiteit, locatie, zoek_connector,
  dso_connector, llm_cfg)` consistent over Task 2→6. `llm_cfg`-sleutels (`llm_base_url`/`model`/
  `timeout_s`) matchen `kies_werkzaamheid`-parameters (via `**llm_cfg`). `post_json(url, json_body,
  headers)` consistent in Task 1/2/3.
