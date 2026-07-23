# UC-08 Afval/circulair-dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bouw een provincie-choropleth + trendpaneel + lokale-Qwen-duiding op open CBS-afvalcijfers (83558NED), als open proxy voor het gesloten LMA/AMICE-aggregaat (UC-08).

**Architecture:** Volgt het bestaande LeefomgevingLab-patroon: een dunne HTTP-connector (`CbsAfvalConnector`) haalt CBS OData op; pure transform-functies vormen de ruwe topic-kolommen om naar tidy volumes + circulariteit; een ingest-script schrijft éénmalig Parquet + provincie-GeoJSON naar NVMe; een usecase-service leest die bestanden en levert GeoJSON/tijdreeksen; routes in `geluidsmeter/api.py` ontsluiten alles; een MapLibre-dashboard consumeert het. Na de ingest draait alles offline.

**Tech Stack:** Python 3.10, httpx, pandas, pyarrow, FastAPI, pydantic, MapLibre GL JS (CDN), lokale Qwen via OpenAI-compatibele `/chat/completions`.

## Global Constraints

- Poort API: **8792** (bestaande app `geluidsmeter.api:app`).
- Bron = **CBS 83558NED**, licentie **CC-BY 4.0**; overal gelabeld als **"open proxy voor het gesloten LMA/AMICE-aggregaat — illustratief"**.
- **Eén CBS-tabel** (83558NED). Geen tweede tabel; "kg per inwoner" is buiten scope.
- **Provincie-niveau** (Regiokenmerken-codes met prefix `PV`). Geen gemeenten.
- Indicatoren: **totaal (kton)** en **circulariteit** = nuttige toepassing / (nuttige toepassing + verbranden + storten) × 100.
- Geen eHerkenning/AMICE-BTO.
- Data-dir buiten de repo: `/mnt/nvme/geluidsmeter/data/external/afval/` (staat al onder `.gitignore` via `/mnt/nvme`).
- Tests draaien **offline** (httpx gemockt met `monkeypatch`, of tmp-bestanden).
- Alle nieuwe code onder `src/leefomgevinglab/`; import-pad `leefomgevinglab.*` (uvicorn draait met `--app-dir src`).

## Vaste feiten over de bron (geverifieerd 2026-07-23)

- OData-basis: `https://opendata.cbs.nl/ODataApi/OData/83558NED`; sub-tabellen o.a. `TypedDataSet`, `Regiokenmerken`.
- `TypedDataSet`-rij heeft keys: `Regiokenmerken` (bijv. `"PV24    "`, met trailing spaces), `Perioden` (bijv. `"1993JJ00"`), en topic-kolommen.
- Provincies: Regiokenmerken-code begint met `PV` (`PV20`–`PV31`). `NL01`, `LD0x`, grootteklassen negeren.
- Jaar-perioden eindigen op `JJ00`; jaar = eerste 4 tekens (`int("1993JJ00"[:4])`).
- Volume-topics (in 1000 ton = kton), de curated selectie voor de POC:
  - `TotaalGemeentelijkAfval_1`, `TotaalHuishoudelijkAfval_2`, `HuishoudelijkRestafval_3`, `GFTAfval_6`, `OudPapierEnKarton_7`, `Verpakkingsglas_9`, `KunststofVerpakkingen_10`.
- Verwerking-topics (voor circulariteit, totaal gemeentelijk afval): `NuttigeToepassing_174`, `Verbranden_177`, `Storten_178`.
- PDOK provinciegeometrie: `https://api.pdok.nl/kadaster/bestuurlijkegebieden/ogc/v1/collections/provinciegebied/items?f=json&limit=20`. Feature-property `identificatie` = `"PV24"` (matcht CBS-code na `.strip()`); `naam` = `"Flevoland"`; geometry = MultiPolygon (CRS84).

## File Structure

- Create: `src/leefomgevinglab/usecases/afval/__init__.py` — package-marker (leeg).
- Create: `src/leefomgevinglab/usecases/afval/transform.py` — pure omzetting ruwe OData-rijen → tidy volumes + circulariteit; curated afvalstroom-mapping.
- Create: `src/leefomgevinglab/connectors/cbs_afval.py` — `CbsAfvalConnector(BaseConnector)`; haalt `TypedDataSet` (met paginatie).
- Create: `scripts/11_fetch_afval_aggregaat.py` — ingest: connector + transform → Parquet; PDOK → provincies.geojson.
- Create: `src/leefomgevinglab/usecases/afval/service.py` — leest Parquet/GeoJSON; `meta/choropleth/trend`.
- Create: `src/leefomgevinglab/usecases/afval/duiding.py` — Qwen-trendduiding.
- Create: `src/leefomgevinglab/static/afval.html` — MapLibre-dashboard.
- Modify: `src/leefomgevinglab/geluidsmeter/api.py` — routes + config-factory.
- Modify: `core/config.yaml` — `leefomgevinglab.afval`-blok.
- Test: `tests/test_afval_transform.py`, `tests/test_cbs_afval_connector.py`, `tests/test_afval_service.py`, `tests/test_afval_duiding.py`, `tests/test_api_afval.py`.

---

### Task 1: transform.py — pure omzetting

**Files:**
- Create: `src/leefomgevinglab/usecases/afval/__init__.py`
- Create: `src/leefomgevinglab/usecases/afval/transform.py`
- Test: `tests/test_afval_transform.py`

**Interfaces:**
- Consumes: niets (pure functies op dicts).
- Produces:
  - `AFVALSTROMEN: dict[str, str]` — label → CBS-topic-key.
  - `is_provincie(regio_code: str) -> bool`
  - `periode_to_jaar(periode: str) -> int | None`
  - `tidy_volumes(rows: list[dict]) -> list[dict]` — items `{"regio_code": str, "jaar": int, "afvalstroom": str(label), "hoeveelheid_kton": float}`.
  - `circulariteit_rows(rows: list[dict]) -> list[dict]` — items `{"regio_code": str, "jaar": int, "nuttige_toepassing_kton": float, "verwijderen_kton": float, "circulariteit_pct": float}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_transform.py
from leefomgevinglab.usecases.afval import transform as t


def _row(regio, periode, **topics):
    base = {"Regiokenmerken": regio, "Perioden": periode}
    base.update(topics)
    return base


def test_is_provincie_alleen_pv():
    assert t.is_provincie("PV24    ") is True
    assert t.is_provincie("NL01    ") is False
    assert t.is_provincie("LD03") is False


def test_periode_to_jaar():
    assert t.periode_to_jaar("1993JJ00") == 1993
    assert t.periode_to_jaar("2020KW01") is None


def test_tidy_volumes_alleen_provincie_en_jaar_en_nietnull():
    rows = [
        _row("PV24    ", "2020JJ00", TotaalGemeentelijkAfval_1=100, GFTAfval_6=None),
        _row("PV25    ", "2020JJ00", GFTAfval_6=12.5),
        _row("NL01    ", "2020JJ00", TotaalGemeentelijkAfval_1=9999),   # geen provincie
        _row("PV24    ", "2020KW01", TotaalGemeentelijkAfval_1=1),      # geen jaar
    ]
    out = t.tidy_volumes(rows)
    assert {"regio_code": "PV24", "jaar": 2020,
            "afvalstroom": "Totaal gemeentelijk afval", "hoeveelheid_kton": 100.0} in out
    assert {"regio_code": "PV25", "jaar": 2020,
            "afvalstroom": "GFT-afval", "hoeveelheid_kton": 12.5} in out
    assert all(r["regio_code"].startswith("PV") for r in out)
    assert all("KW" not in str(r["jaar"]) for r in out)
    # None-waarde levert geen rij
    assert not any(r["regio_code"] == "PV24" and r["afvalstroom"] == "GFT-afval" for r in out)


def test_circulariteit_pct():
    rows = [_row("PV24    ", "2020JJ00",
                 NuttigeToepassing_174=75, Verbranden_177=20, Storten_178=5)]
    out = t.circulariteit_rows(rows)
    assert len(out) == 1
    r = out[0]
    assert r["regio_code"] == "PV24" and r["jaar"] == 2020
    assert r["nuttige_toepassing_kton"] == 75.0
    assert r["verwijderen_kton"] == 25.0
    assert round(r["circulariteit_pct"], 1) == 75.0


def test_circulariteit_overslaan_bij_ontbrekende_of_nul():
    rows = [
        _row("PV24    ", "2020JJ00", NuttigeToepassing_174=None, Verbranden_177=1, Storten_178=1),
        _row("PV25    ", "2020JJ00", NuttigeToepassing_174=0, Verbranden_177=0, Storten_178=0),
    ]
    assert t.circulariteit_rows(rows) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_transform.py -v`
Expected: FAIL — `ModuleNotFoundError: leefomgevinglab.usecases.afval`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/usecases/afval/__init__.py
# (leeg — package-marker)
```

```python
# src/leefomgevinglab/usecases/afval/transform.py
"""Pure omzetting van CBS 83558NED TypedDataSet-rijen naar tidy afval-aggregaat.

CBS levert afvalsoorten en verwerkingsmethoden als losse topic-kolommen. Deze
module selecteert een curated set afvalstromen en berekent circulariteit uit de
verwerkingsmethode-kolommen. Alleen provincies (Regiokenmerken-code 'PV..') en
jaarperioden ('..JJ00') worden meegenomen.
"""

# Curated afvalstromen: label -> CBS-topic-key (waarden in 1000 ton = kton).
AFVALSTROMEN: dict[str, str] = {
    "Totaal gemeentelijk afval": "TotaalGemeentelijkAfval_1",
    "Totaal huishoudelijk afval": "TotaalHuishoudelijkAfval_2",
    "Huishoudelijk restafval": "HuishoudelijkRestafval_3",
    "GFT-afval": "GFTAfval_6",
    "Oud papier en karton": "OudPapierEnKarton_7",
    "Verpakkingsglas": "Verpakkingsglas_9",
    "Kunststof verpakkingen": "KunststofVerpakkingen_10",
}

# Verwerking (totaal gemeentelijk afval) voor circulariteit.
_NUTTIG = "NuttigeToepassing_174"
_VERBRANDEN = "Verbranden_177"
_STORTEN = "Storten_178"


def is_provincie(regio_code: str) -> bool:
    return regio_code.strip().startswith("PV")


def periode_to_jaar(periode: str) -> int | None:
    if not periode.endswith("JJ00"):
        return None
    try:
        return int(periode[:4])
    except ValueError:
        return None


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def tidy_volumes(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        code = row.get("Regiokenmerken", "")
        if not is_provincie(code):
            continue
        jaar = periode_to_jaar(row.get("Perioden", ""))
        if jaar is None:
            continue
        for label, key in AFVALSTROMEN.items():
            val = _num(row.get(key))
            if val is None:
                continue
            out.append({"regio_code": code.strip(), "jaar": jaar,
                        "afvalstroom": label, "hoeveelheid_kton": val})
    return out


def circulariteit_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        code = row.get("Regiokenmerken", "")
        if not is_provincie(code):
            continue
        jaar = periode_to_jaar(row.get("Perioden", ""))
        if jaar is None:
            continue
        nuttig = _num(row.get(_NUTTIG))
        verbranden = _num(row.get(_VERBRANDEN))
        storten = _num(row.get(_STORTEN))
        if None in (nuttig, verbranden, storten):
            continue
        verwijderen = verbranden + storten
        noemer = nuttig + verwijderen
        if noemer <= 0:
            continue
        out.append({"regio_code": code.strip(), "jaar": jaar,
                    "nuttige_toepassing_kton": nuttig,
                    "verwijderen_kton": verwijderen,
                    "circulariteit_pct": nuttig / noemer * 100})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_transform.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/__init__.py src/leefomgevinglab/usecases/afval/transform.py tests/test_afval_transform.py
git commit -m "feat(uc08): pure transform CBS-afvalrijen naar tidy volumes + circulariteit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: CbsAfvalConnector

**Files:**
- Create: `src/leefomgevinglab/connectors/cbs_afval.py`
- Test: `tests/test_cbs_afval_connector.py`

**Interfaces:**
- Consumes: `BaseConnector.get_json` (uit `connectors/base.py`).
- Produces: `CbsAfvalConnector(base_url: str, table_id: str, **base_kwargs)`, methode `typed_dataset() -> list[dict]` die alle OData-pagina's samenvoegt (volgt `odata.nextLink`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cbs_afval_connector.py
import httpx
from leefomgevinglab.connectors.cbs_afval import CbsAfvalConnector


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_typed_dataset_volgt_nextlink(tmp_path, monkeypatch):
    pages = {
        "https://cbs/OData/83558NED/TypedDataSet": {
            "value": [{"Regiokenmerken": "PV24    ", "Perioden": "2020JJ00"}],
            "odata.nextLink": "https://cbs/OData/83558NED/TypedDataSet?$skip=1",
        },
        "https://cbs/OData/83558NED/TypedDataSet?$skip=1": {
            "value": [{"Regiokenmerken": "PV25    ", "Perioden": "2020JJ00"}],
        },
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse(pages[url])

    monkeypatch.setattr(httpx, "get", fake_get)
    c = CbsAfvalConnector(base_url="https://cbs/OData", table_id="83558NED",
                          cache_dir=str(tmp_path))
    rows = c.typed_dataset()
    assert [r["Regiokenmerken"].strip() for r in rows] == ["PV24", "PV25"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_cbs_afval_connector.py -v`
Expected: FAIL — `ModuleNotFoundError: ...connectors.cbs_afval`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/connectors/cbs_afval.py
"""CBS StatLine OData-connector voor tabel 83558NED (gemeentelijke afvalstoffen).

Open bron (CC-BY 4.0). Dient als open proxy voor het gesloten LMA/AMICE-aggregaat.
Dunne laag: haalt de TypedDataSet op (met OData-paginatie) en erft caching +
nette degradatie van BaseConnector. Omzetting naar tidy gebeurt in
usecases/afval/transform.py.
"""
from .base import BaseConnector


class CbsAfvalConnector(BaseConnector):
    def __init__(self, base_url: str, table_id: str, **kwargs):
        super().__init__(**kwargs)
        self.table_url = f"{base_url.rstrip('/')}/{table_id}"

    def typed_dataset(self) -> list[dict]:
        url = f"{self.table_url}/TypedDataSet"
        rows: list[dict] = []
        while url:
            data = self.get_json(url)
            rows.extend(data.get("value", []))
            url = data.get("odata.nextLink")
        return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_cbs_afval_connector.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/connectors/cbs_afval.py tests/test_cbs_afval_connector.py
git commit -m "feat(uc08): CbsAfvalConnector (CBS 83558NED OData, paginatie)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Ingest-script + config-blok

**Files:**
- Create: `scripts/11_fetch_afval_aggregaat.py`
- Modify: `core/config.yaml` (blok `leefomgevinglab.afval`)
- Test: `tests/test_afval_ingest.py`

**Interfaces:**
- Consumes: `CbsAfvalConnector.typed_dataset`, `transform.tidy_volumes`, `transform.circulariteit_rows`.
- Produces: functie `bouw_aggregaat(rows, provincie_features) -> tuple[pandas.DataFrame, pandas.DataFrame, dict]` in het script (importeerbaar), die `(volumes_df, circ_df, provincies_geojson)` teruggeeft; en een `main()` die de bestanden wegschrijft. `provincies_geojson` bevat alleen provincies die in de data voorkomen, met properties `identificatie` (= `PVxx`) en `naam`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_ingest.py
import importlib.util
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "11_fetch_afval_aggregaat.py"
_spec = importlib.util.spec_from_file_location("ingest_afval", SPEC)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)


def test_bouw_aggregaat_filtert_en_bouwt_geojson():
    rows = [
        {"Regiokenmerken": "PV24    ", "Perioden": "2020JJ00",
         "TotaalGemeentelijkAfval_1": 100, "GFTAfval_6": 12,
         "NuttigeToepassing_174": 75, "Verbranden_177": 20, "Storten_178": 5},
        {"Regiokenmerken": "NL01    ", "Perioden": "2020JJ00",
         "TotaalGemeentelijkAfval_1": 9999},
    ]
    provincie_features = [
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV24", "naam": "Flevoland", "code": "24"}},
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV30", "naam": "Zuid-Holland", "code": "30"}},
    ]
    vol, circ, geo = ingest.bouw_aggregaat(rows, provincie_features)
    assert set(vol["regio_code"]) == {"PV24"}
    assert set(circ["regio_code"]) == {"PV24"}
    # alleen provincies die in de data voorkomen
    ids = [f["properties"]["identificatie"] for f in geo["features"]]
    assert ids == ["PV24"]
    # GeoJSON-properties beperkt tot identificatie + naam
    assert set(geo["features"][0]["properties"]) == {"identificatie", "naam"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_ingest.py -v`
Expected: FAIL — bestand `scripts/11_fetch_afval_aggregaat.py` bestaat nog niet (`FileNotFoundError` bij `exec_module`).

- [ ] **Step 3: Write minimal implementation**

Voeg eerst het config-blok toe aan `core/config.yaml`, direct ná het `viewer:`-blok onder `leefomgevinglab:` (let op inspringing: 2 spaties, gelijk aan `viewer:`):

```yaml
  afval:
    odata_base_url: "https://opendata.cbs.nl/ODataApi/OData"
    table_id: "83558NED"                       # CBS "Gemeentelijke afvalstoffen; hoeveelheden" (CC-BY 4.0)
    pdok_provincie_url: "https://api.pdok.nl/kadaster/bestuurlijkegebieden/ogc/v1"
    data_dir: "/mnt/nvme/geluidsmeter/data/external/afval"
```

Dan het script:

```python
# scripts/11_fetch_afval_aggregaat.py
"""Ingest UC-08: haalt CBS 83558NED + PDOK-provinciegeometrie op en schrijft het
gebundelde afval-aggregaat (Parquet + GeoJSON) naar de data-dir.

Eenmalig online; daarna draait het dashboard offline op deze bestanden.
Bron: CBS 83558NED (CC-BY 4.0) — open proxy voor het gesloten LMA/AMICE-aggregaat.
"""
import sys
from pathlib import Path

import httpx
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leefomgevinglab.connectors.cbs_afval import CbsAfvalConnector
from leefomgevinglab.usecases.afval import transform


def bouw_aggregaat(rows: list[dict], provincie_features: list[dict]):
    vol = pd.DataFrame(transform.tidy_volumes(rows),
                       columns=["regio_code", "jaar", "afvalstroom", "hoeveelheid_kton"])
    circ = pd.DataFrame(transform.circulariteit_rows(rows),
                        columns=["regio_code", "jaar", "nuttige_toepassing_kton",
                                 "verwijderen_kton", "circulariteit_pct"])
    aanwezige = set(vol["regio_code"]) | set(circ["regio_code"])
    features = []
    for f in provincie_features:
        ident = f["properties"].get("identificatie")
        if ident not in aanwezige:
            continue
        features.append({
            "type": "Feature",
            "geometry": f["geometry"],
            "properties": {"identificatie": ident, "naam": f["properties"].get("naam")},
        })
    geo = {"type": "FeatureCollection", "features": features}
    return vol, circ, geo


def _fetch_provincies(pdok_base: str) -> list[dict]:
    url = f"{pdok_base.rstrip('/')}/collections/provinciegebied/items"
    resp = httpx.get(url, params={"f": "json", "limit": 20}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def main():
    cfg = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "core" / "config.yaml"))
    af = cfg["leefomgevinglab"]["afval"]
    cache_dir = cfg["leefomgevinglab"].get("cache_dir", "/tmp/llab_cache")
    data_dir = Path(af["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)

    conn = CbsAfvalConnector(base_url=af["odata_base_url"], table_id=af["table_id"],
                             cache_dir=cache_dir, timeout=30.0)
    print("CBS 83558NED ophalen...")
    rows = conn.typed_dataset()
    print(f"  {len(rows)} rijen")
    print("PDOK-provinciegeometrie ophalen...")
    provincies = _fetch_provincies(af["pdok_provincie_url"])

    vol, circ, geo = bouw_aggregaat(rows, provincies)
    vol.to_parquet(data_dir / "aggregaat.parquet", index=False)
    circ.to_parquet(data_dir / "circulariteit.parquet", index=False)
    (data_dir / "provincies.geojson").write_text(
        __import__("json").dumps(geo), encoding="utf-8")
    print(f"Geschreven: {len(vol)} volume-rijen, {len(circ)} circulariteit-rijen, "
          f"{len(geo['features'])} provincies -> {data_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_ingest.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Draai de echte ingest éénmalig (online) en verifieer**

Run:
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab
mkdir -p /mnt/nvme/geluidsmeter/data/external/afval
python3 scripts/11_fetch_afval_aggregaat.py
python3 -c "import pandas as pd; d='/mnt/nvme/geluidsmeter/data/external/afval'; \
v=pd.read_parquet(d+'/aggregaat.parquet'); c=pd.read_parquet(d+'/circulariteit.parquet'); \
print('provincies volumes:', sorted(v.regio_code.unique())); \
print('jaren:', v.jaar.min(), '-', v.jaar.max()); \
print('circ rijen:', len(c), 'voorbeeld pct:', round(c.circulariteit_pct.mean(),1))"
```
Expected: 12 provincie-codes (`PV20`–`PV31`), meerdere jaren, circulariteit-percentages tussen 0 en 100. Als CBS/PDOK onbereikbaar is: de connector geeft `ConnectorError` — probeer later opnieuw; deze stap is niet-blokkerend voor de code-commit maar wel voor een werkend dashboard.

- [ ] **Step 6: Commit**

```bash
git add scripts/11_fetch_afval_aggregaat.py core/config.yaml tests/test_afval_ingest.py
git commit -m "feat(uc08): ingest-script CBS-afvalaggregaat + PDOK-provinciegeometrie

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: service.py — meta / choropleth / trend

**Files:**
- Create: `src/leefomgevinglab/usecases/afval/service.py`
- Test: `tests/test_afval_service.py`

**Interfaces:**
- Consumes: Parquet `aggregaat.parquet`, `circulariteit.parquet`, GeoJSON `provincies.geojson` uit `data_dir`; `transform.AFVALSTROMEN`.
- Produces (alle nemen `data_dir: str` als eerste arg):
  - `meta(data_dir) -> dict` met keys `regios` (list `{code, naam}`), `afvalstromen` (list labels), `jaren` (list int, oplopend), `indicatoren` (list `{key, label}`), `bron`, `licentie`, `label`.
  - `choropleth(data_dir, afvalstroom: str, jaar: int, indicator: str) -> dict` — GeoJSON FeatureCollection; elke feature-property krijgt `value: float|None`, `indicator`, `afvalstroom`, `jaar`, `eenheid`.
  - `trend(data_dir, regio: str, afvalstroom: str) -> dict` met `regio`, `naam`, `afvalstroom`, `reeks` (list `{jaar, hoeveelheid_kton, circulariteit_pct}`).
- `indicator` ∈ {`"volume"`, `"circulariteit"`}.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_service.py
import json
import pandas as pd
import pytest
from leefomgevinglab.usecases.afval import service


@pytest.fixture
def data_dir(tmp_path):
    pd.DataFrame([
        {"regio_code": "PV24", "jaar": 2019, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 10.0},
        {"regio_code": "PV24", "jaar": 2020, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 12.0},
        {"regio_code": "PV30", "jaar": 2020, "afvalstroom": "GFT-afval", "hoeveelheid_kton": 40.0},
    ]).to_parquet(tmp_path / "aggregaat.parquet", index=False)
    pd.DataFrame([
        {"regio_code": "PV24", "jaar": 2019, "nuttige_toepassing_kton": 8.0,
         "verwijderen_kton": 2.0, "circulariteit_pct": 80.0},
        {"regio_code": "PV24", "jaar": 2020, "nuttige_toepassing_kton": 9.0,
         "verwijderen_kton": 3.0, "circulariteit_pct": 75.0},
    ]).to_parquet(tmp_path / "circulariteit.parquet", index=False)
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV24", "naam": "Flevoland"}},
        {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []},
         "properties": {"identificatie": "PV30", "naam": "Zuid-Holland"}},
    ]}
    (tmp_path / "provincies.geojson").write_text(json.dumps(geo))
    return str(tmp_path)


def test_meta(data_dir):
    m = service.meta(data_dir)
    assert {"code": "PV24", "naam": "Flevoland"} in m["regios"]
    assert "GFT-afval" in m["afvalstromen"]
    assert m["jaren"] == [2019, 2020]
    assert {"key": "circulariteit", "label": "Circulariteit (%)"} in m["indicatoren"]
    assert "CC-BY" in m["licentie"]


def test_choropleth_volume(data_dir):
    fc = service.choropleth(data_dir, afvalstroom="GFT-afval", jaar=2020, indicator="volume")
    vals = {f["properties"]["identificatie"]: f["properties"]["value"] for f in fc["features"]}
    assert vals["PV24"] == 12.0
    assert vals["PV30"] == 40.0


def test_choropleth_circulariteit_ontbrekend_is_none(data_dir):
    fc = service.choropleth(data_dir, afvalstroom="GFT-afval", jaar=2020, indicator="circulariteit")
    vals = {f["properties"]["identificatie"]: f["properties"]["value"] for f in fc["features"]}
    assert vals["PV24"] == 75.0
    assert vals["PV30"] is None   # geen circulariteit-rij voor PV30


def test_trend(data_dir):
    tr = service.trend(data_dir, regio="PV24", afvalstroom="GFT-afval")
    assert tr["naam"] == "Flevoland"
    jaren = [p["jaar"] for p in tr["reeks"]]
    assert jaren == [2019, 2020]
    assert tr["reeks"][1]["hoeveelheid_kton"] == 12.0
    assert tr["reeks"][1]["circulariteit_pct"] == 75.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_service.py -v`
Expected: FAIL — `ModuleNotFoundError: ...afval.service`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/usecases/afval/service.py
"""UC-08 service: leest het gebundelde afval-aggregaat en levert meta,
choropleth-GeoJSON en tijdreeksen. Geen netwerk — puur bestand-gebaseerd.
"""
import json
from pathlib import Path

import pandas as pd

from .transform import AFVALSTROMEN

BRON = "CBS StatLine 83558NED (Gemeentelijke afvalstoffen; hoeveelheden)"
LICENTIE = "CC-BY 4.0"
LABEL = "Open proxy voor het gesloten LMA/AMICE-aggregaat — illustratief"
INDICATOREN = [
    {"key": "volume", "label": "Hoeveelheid (kton)"},
    {"key": "circulariteit", "label": "Circulariteit (%)"},
]


def _paths(data_dir: str):
    d = Path(data_dir)
    return d / "aggregaat.parquet", d / "circulariteit.parquet", d / "provincies.geojson"


def _load_geo(data_dir: str) -> dict:
    _, _, geo = _paths(data_dir)
    return json.loads(geo.read_text())


def meta(data_dir: str) -> dict:
    vol_p, _, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    geo = _load_geo(data_dir)
    regios = [{"code": f["properties"]["identificatie"], "naam": f["properties"]["naam"]}
              for f in geo["features"]]
    jaren = sorted(int(j) for j in vol["jaar"].unique())
    return {
        "regios": regios,
        "afvalstromen": list(AFVALSTROMEN.keys()),
        "jaren": jaren,
        "indicatoren": INDICATOREN,
        "bron": BRON,
        "licentie": LICENTIE,
        "label": LABEL,
    }


def choropleth(data_dir: str, afvalstroom: str, jaar: int, indicator: str) -> dict:
    vol_p, circ_p, _ = _paths(data_dir)
    geo = _load_geo(data_dir)
    if indicator == "circulariteit":
        df = pd.read_parquet(circ_p)
        df = df[df["jaar"] == int(jaar)]
        lookup = dict(zip(df["regio_code"], df["circulariteit_pct"]))
        eenheid = "%"
    else:
        df = pd.read_parquet(vol_p)
        df = df[(df["jaar"] == int(jaar)) & (df["afvalstroom"] == afvalstroom)]
        lookup = dict(zip(df["regio_code"], df["hoeveelheid_kton"]))
        eenheid = "kton"
    for f in geo["features"]:
        code = f["properties"]["identificatie"]
        val = lookup.get(code)
        f["properties"].update({
            "value": None if val is None else float(val),
            "indicator": indicator,
            "afvalstroom": afvalstroom,
            "jaar": int(jaar),
            "eenheid": eenheid,
        })
    return geo


def trend(data_dir: str, regio: str, afvalstroom: str) -> dict:
    vol_p, circ_p, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    circ = pd.read_parquet(circ_p)
    geo = _load_geo(data_dir)
    naam = next((f["properties"]["naam"] for f in geo["features"]
                 if f["properties"]["identificatie"] == regio), regio)
    v = vol[(vol["regio_code"] == regio) & (vol["afvalstroom"] == afvalstroom)]
    circ_map = dict(zip(circ[circ["regio_code"] == regio]["jaar"],
                        circ[circ["regio_code"] == regio]["circulariteit_pct"]))
    reeks = []
    for _, r in v.sort_values("jaar").iterrows():
        jaar = int(r["jaar"])
        pct = circ_map.get(jaar)
        reeks.append({
            "jaar": jaar,
            "hoeveelheid_kton": float(r["hoeveelheid_kton"]),
            "circulariteit_pct": None if pct is None else float(pct),
        })
    return {"regio": regio, "naam": naam, "afvalstroom": afvalstroom, "reeks": reeks}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_service.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/service.py tests/test_afval_service.py
git commit -m "feat(uc08): afval-service (meta/choropleth/trend) op gebundeld aggregaat

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: duiding.py — lokale Qwen-trendduiding

**Files:**
- Create: `src/leefomgevinglab/usecases/afval/duiding.py`
- Test: `tests/test_afval_duiding.py`

**Interfaces:**
- Consumes: `ConnectorError` (uit `connectors/base.py`); httpx.
- Produces:
  - `build_prompt(regio_naam: str, afvalstroom: str, reeks: list[dict]) -> str`
  - `duiding(regio_naam: str, afvalstroom: str, reeks: list[dict], llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict` met keys `duiding`, `bron`, `disclaimer`. Bij LLM-fout: `ConnectorError`.
- Spiegelt het patroon van `usecases/rev_viewer/service.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_duiding.py
import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.afval import duiding as d


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_REEKS = [{"jaar": 2019, "hoeveelheid_kton": 10.0, "circulariteit_pct": 80.0},
          {"jaar": 2020, "hoeveelheid_kton": 12.0, "circulariteit_pct": 75.0}]


def test_build_prompt_bevat_getallen_en_bron():
    p = d.build_prompt("Flevoland", "GFT-afval", _REEKS)
    assert "Flevoland" in p and "GFT-afval" in p
    assert "2020" in p and "12" in p
    assert "verzin" in p.lower()


def test_duiding_ok(monkeypatch):
    monkeypatch.setattr(httpx, "post",
                        lambda url, json=None, timeout=None:
                        _FakeResponse({"choices": [{"message": {"content": "Stijgende trend."}}]}))
    out = d.duiding("Flevoland", "GFT-afval", _REEKS,
                    llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["duiding"] == "Stijgende trend."
    assert "83558NED" in out["bron"]
    assert "LMA" in out["disclaimer"]


def test_duiding_llm_down_raises(monkeypatch):
    def boom(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(ConnectorError):
        d.duiding("Flevoland", "GFT-afval", _REEKS,
                  llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_duiding.py -v`
Expected: FAIL — `ModuleNotFoundError: ...afval.duiding`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/usecases/afval/duiding.py
"""UC-08: korte AI-duiding van een afval-trend via lokale Qwen.

No-hallucination: gebruikt uitsluitend de meegegeven cijfers, met bronverwijzing.
"""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

BRON = "CBS StatLine 83558NED (CC-BY 4.0)"
DISCLAIMER = (
    "Indicatief. Cijfers zijn een open proxy (CBS) voor het gesloten "
    "LMA/AMICE-aggregaat, geen officiele LMA-meldgegevens."
)


def build_prompt(regio_naam: str, afvalstroom: str, reeks: list[dict]) -> str:
    regels = "\n".join(
        f"- {p['jaar']}: {p['hoeveelheid_kton']} kton"
        + ("" if p.get("circulariteit_pct") is None
           else f", circulariteit {round(p['circulariteit_pct'], 1)}%")
        for p in reeks
    )
    return (
        "Je bent een feitelijke data-assistent. Vat de trend hieronder in 2-3 zinnen "
        "begrijpelijk samen voor een burger. Verzin niets; gebruik uitsluitend de "
        "gegeven getallen. Trek geen beleidsconclusies.\n\n"
        f"Provincie: {regio_naam}\nAfvalstroom: {afvalstroom}\nReeks:\n{regels}"
    )


def duiding(regio_naam: str, afvalstroom: str, reeks: list[dict],
            llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    prompt = build_prompt(regio_naam, afvalstroom, reeks)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("AI-duiding tijdelijk niet beschikbaar") from exc
    return {"duiding": text, "bron": BRON, "disclaimer": DISCLAIMER}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_duiding.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/duiding.py tests/test_afval_duiding.py
git commit -m "feat(uc08): lokale-Qwen trendduiding voor afval-dashboard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Routes in geluidsmeter/api.py

**Files:**
- Modify: `src/leefomgevinglab/geluidsmeter/api.py`
- Test: `tests/test_api_afval.py`

**Interfaces:**
- Consumes: `service.meta/choropleth/trend`, `duiding.duiding`, `_config`.
- Produces routes:
  - `GET /afval` → HTML (`static/afval.html`).
  - `GET /api/afval/meta` → `service.meta(data_dir)`.
  - `GET /api/afval/choropleth?afvalstroom=&jaar=&indicator=` → `service.choropleth(...)`.
  - `GET /api/afval/trend?regio=&afvalstroom=` → `service.trend(...)`.
  - `POST /api/afval/duiding` (body `AfvalDuidingRequest`) → `duiding.duiding(...)`; 503 bij `ConnectorError`.
- Helper `_afval_data_dir() -> str` leest `_config["leefomgevinglab"]["afval"]["data_dir"]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_afval.py
from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api
from leefomgevinglab.connectors.base import ConnectorError


def _client(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "afval": {"data_dir": "/tmp/afval_test"},
            "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60},
        }
    }
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_afval_meta(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "meta",
                        lambda data_dir: {"regios": [], "afvalstromen": ["GFT-afval"],
                                          "jaren": [2020], "indicatoren": [], "bron": "b",
                                          "licentie": "CC-BY 4.0", "label": "l"})
    r = client.get("/api/afval/meta")
    assert r.status_code == 200
    assert r.json()["afvalstromen"] == ["GFT-afval"]


def test_afval_choropleth(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "choropleth",
                        lambda data_dir, afvalstroom, jaar, indicator:
                        {"type": "FeatureCollection", "features": [],
                         "echo": [afvalstroom, jaar, indicator]})
    r = client.get("/api/afval/choropleth",
                   params={"afvalstroom": "GFT-afval", "jaar": 2020, "indicator": "volume"})
    assert r.status_code == 200
    assert r.json()["echo"] == ["GFT-afval", 2020, "volume"]


def test_afval_trend(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_service, "trend",
                        lambda data_dir, regio, afvalstroom:
                        {"regio": regio, "naam": "Flevoland", "afvalstroom": afvalstroom, "reeks": []})
    r = client.get("/api/afval/trend", params={"regio": "PV24", "afvalstroom": "GFT-afval"})
    assert r.status_code == 200
    assert r.json()["naam"] == "Flevoland"


def test_afval_duiding_ok(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api.afval_duiding, "duiding",
                        lambda regio_naam, afvalstroom, reeks, **kw:
                        {"duiding": "ok", "bron": "b", "disclaimer": "d"})
    r = client.post("/api/afval/duiding",
                    json={"regio_naam": "Flevoland", "afvalstroom": "GFT-afval",
                          "reeks": [{"jaar": 2020, "hoeveelheid_kton": 12.0, "circulariteit_pct": 75.0}]})
    assert r.status_code == 200
    assert r.json()["duiding"] == "ok"


def test_afval_duiding_llm_down_503(monkeypatch):
    client = _client(monkeypatch)
    def boom(**kw):
        raise ConnectorError("down")
    monkeypatch.setattr(api.afval_duiding, "duiding", lambda *a, **kw: boom())
    r = client.post("/api/afval/duiding",
                    json={"regio_naam": "Flevoland", "afvalstroom": "GFT-afval", "reeks": []})
    assert r.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_api_afval.py -v`
Expected: FAIL — `AttributeError: module ...api has no attribute 'afval_service'`.

- [ ] **Step 3: Write minimal implementation**

Voeg bij de imports boven in `src/leefomgevinglab/geluidsmeter/api.py` (bij de andere `from leefomgevinglab.usecases...`-regels, rond regel 43) toe:

```python
from leefomgevinglab.usecases.afval import service as afval_service
from leefomgevinglab.usecases.afval import duiding as afval_duiding
```

Voeg onderaan `src/leefomgevinglab/geluidsmeter/api.py` toe (na de bestaande routes):

```python
def _afval_data_dir() -> str:
    return _config.get("leefomgevinglab", {}).get("afval", {}).get(
        "data_dir", "/mnt/nvme/geluidsmeter/data/external/afval")


@app.get("/afval", response_class=HTMLResponse)
def afval_page():
    return (Path(__file__).parent.parent / "static" / "afval.html").read_text()


@app.get("/api/afval/meta")
def api_afval_meta():
    try:
        return afval_service.meta(_afval_data_dir())
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")


@app.get("/api/afval/choropleth")
def api_afval_choropleth(afvalstroom: str, jaar: int, indicator: str = "volume"):
    try:
        return afval_service.choropleth(_afval_data_dir(), afvalstroom, jaar, indicator)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")


@app.get("/api/afval/trend")
def api_afval_trend(regio: str, afvalstroom: str):
    try:
        return afval_service.trend(_afval_data_dir(), regio, afvalstroom)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")


class AfvalDuidingRequest(BaseModel):
    regio_naam: str
    afvalstroom: str
    reeks: list[dict]


@app.post("/api/afval/duiding")
def api_afval_duiding(req: AfvalDuidingRequest):
    ll = _config.get("leefomgevinglab", {})
    llm = ll.get("llm", {})
    try:
        return afval_duiding.duiding(
            req.regio_naam, req.afvalstroom, req.reeks,
            llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
            model=llm.get("model", "qwen2.5-32b"),
            timeout_s=llm.get("timeout_s", 60),
        )
    except ConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_api_afval.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/geluidsmeter/api.py tests/test_api_afval.py
git commit -m "feat(uc08): API-routes /afval + /api/afval/{meta,choropleth,trend,duiding}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Frontend — afval.html (MapLibre choropleth + trend)

**Files:**
- Create: `src/leefomgevinglab/static/afval.html`

**Interfaces:**
- Consumes de routes uit Task 6 (`/api/afval/meta`, `/api/afval/choropleth`, `/api/afval/trend`, `/api/afval/duiding`).
- Produces: interactieve pagina op `/afval`. Geen unit-test; verificatie via een live smoke-test.

- [ ] **Step 1: Schrijf de pagina**

```html
<!-- src/leefomgevinglab/static/afval.html -->
<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Afval &amp; circulariteit — LeefomgevingLab</title>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
  body { margin: 0; font-family: system-ui, sans-serif; color: #1a1a1a; }
  header { padding: 12px 16px; background: #0b4f6c; color: #fff; }
  header h1 { margin: 0; font-size: 18px; }
  header p { margin: 4px 0 0; font-size: 12px; opacity: .85; }
  .wrap { display: flex; height: calc(100vh - 62px); }
  #map { flex: 1; }
  aside { width: 340px; padding: 14px; box-sizing: border-box; overflow-y: auto; border-left: 1px solid #ddd; }
  label { display: block; font-size: 12px; margin: 10px 0 3px; font-weight: 600; }
  select { width: 100%; padding: 6px; }
  .legend { margin-top: 12px; font-size: 12px; }
  .legend i { display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: middle; }
  #trend { margin-top: 14px; }
  #trend h3 { font-size: 14px; margin: 8px 0; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { border-bottom: 1px solid #eee; padding: 3px 4px; text-align: right; }
  th:first-child, td:first-child { text-align: left; }
  button { margin-top: 10px; padding: 8px 10px; background: #0b4f6c; color: #fff; border: 0; border-radius: 4px; cursor: pointer; }
  #duiding { margin-top: 10px; font-size: 13px; background: #f3f7f9; padding: 8px; border-radius: 4px; white-space: pre-wrap; }
  .bron { margin-top: 14px; font-size: 11px; color: #666; }
</style>
</head>
<body>
<header>
  <h1>Afval &amp; circulariteit per provincie</h1>
  <p id="bron">Laden…</p>
</header>
<div class="wrap">
  <div id="map"></div>
  <aside>
    <label>Afvalstroom</label>
    <select id="afvalstroom"></select>
    <label>Jaar</label>
    <select id="jaar"></select>
    <label>Indicator</label>
    <select id="indicator">
      <option value="volume">Hoeveelheid (kton)</option>
      <option value="circulariteit">Circulariteit (%)</option>
    </select>
    <div class="legend" id="legend"></div>
    <div id="trend"><h3>Klik op een provincie</h3></div>
    <div class="bron" id="licentie"></div>
  </aside>
</div>
<script>
const RAMP = ["#f7fbff","#c6dbef","#6baed6","#2171b5","#08306b"];
let META = null, SELECTED = null;
const map = new maplibregl.Map({
  container: "map",
  style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center: [5.3, 52.1], zoom: 6.3
});

function color(v, min, max) {
  if (v === null || v === undefined) return "#e0e0e0";
  const t = max > min ? (v - min) / (max - min) : 0;
  return RAMP[Math.min(RAMP.length - 1, Math.floor(t * RAMP.length))];
}

async function loadMeta() {
  META = await (await fetch("/api/afval/meta")).json();
  document.getElementById("bron").textContent = META.label + " — bron: " + META.bron;
  document.getElementById("licentie").textContent = "Licentie: " + META.licentie;
  const as = document.getElementById("afvalstroom");
  META.afvalstromen.forEach(a => as.add(new Option(a, a)));
  const jr = document.getElementById("jaar");
  META.jaren.slice().reverse().forEach(j => jr.add(new Option(j, j)));
  ["afvalstroom","jaar","indicator"].forEach(id =>
    document.getElementById(id).addEventListener("change", refresh));
  await refresh();
}

async function refresh() {
  const afvalstroom = document.getElementById("afvalstroom").value;
  const jaar = document.getElementById("jaar").value;
  const indicator = document.getElementById("indicator").value;
  const fc = await (await fetch(`/api/afval/choropleth?afvalstroom=${encodeURIComponent(afvalstroom)}&jaar=${jaar}&indicator=${indicator}`)).json();
  const vals = fc.features.map(f => f.properties.value).filter(v => v !== null);
  const min = Math.min(...vals), max = Math.max(...vals);
  fc.features.forEach(f => f.properties._fill = color(f.properties.value, min, max));
  const src = map.getSource("prov");
  if (src) src.setData(fc); else addLayer(fc);
  const eenheid = fc.features[0] ? fc.features[0].properties.eenheid : "";
  document.getElementById("legend").innerHTML =
    `<b>${indicator === "circulariteit" ? "Circulariteit" : afvalstroom} (${eenheid})</b><br>` +
    `<i style="background:${RAMP[0]}"></i>${isFinite(min)?min.toFixed(0):"–"} … ` +
    `<i style="background:${RAMP[4]}"></i>${isFinite(max)?max.toFixed(0):"–"}`;
}

function addLayer(fc) {
  map.addSource("prov", { type: "geojson", data: fc });
  map.addLayer({ id: "prov-fill", type: "fill", source: "prov",
    paint: { "fill-color": ["get","_fill"], "fill-opacity": 0.75, "fill-outline-color": "#fff" } });
  map.on("click", "prov-fill", e => showTrend(e.features[0].properties.identificatie,
                                             e.features[0].properties.naam));
  map.on("mouseenter", "prov-fill", () => map.getCanvas().style.cursor = "pointer");
  map.on("mouseleave", "prov-fill", () => map.getCanvas().style.cursor = "");
}

async function showTrend(code, naam) {
  const afvalstroom = document.getElementById("afvalstroom").value;
  SELECTED = { code, naam, afvalstroom };
  const tr = await (await fetch(`/api/afval/trend?regio=${code}&afvalstroom=${encodeURIComponent(afvalstroom)}`)).json();
  let rows = tr.reeks.map(p =>
    `<tr><td>${p.jaar}</td><td>${p.hoeveelheid_kton.toFixed(0)}</td>` +
    `<td>${p.circulariteit_pct === null ? "–" : p.circulariteit_pct.toFixed(0)}</td></tr>`).join("");
  document.getElementById("trend").innerHTML =
    `<h3>${naam} — ${afvalstroom}</h3>` +
    `<table><thead><tr><th>Jaar</th><th>kton</th><th>circ.%</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<button id="duidBtn">AI-duiding</button><div id="duiding"></div>`;
  document.getElementById("duidBtn").addEventListener("click", () => duiding(tr));
}

async function duiding(tr) {
  const box = document.getElementById("duiding");
  box.textContent = "Duiding ophalen…";
  const r = await fetch("/api/afval/duiding", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regio_naam: tr.naam, afvalstroom: tr.afvalstroom, reeks: tr.reeks })
  });
  if (!r.ok) { box.textContent = "Duiding tijdelijk niet beschikbaar."; return; }
  const d = await r.json();
  box.textContent = d.duiding + "\n\n— " + d.disclaimer;
}

map.on("load", loadMeta);
</script>
</body>
</html>
```

- [ ] **Step 2: Live smoke-test**

Run (start de app op poort 8792 in de achtergrond; vereist dat de ingest uit Task 3 Step 5 gedraaid heeft):
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab
[ -d .venv ] && source .venv/bin/activate
uvicorn geluidsmeter.api:app --host 127.0.0.1 --port 8792 --app-dir src &
sleep 4
curl -s "http://127.0.0.1:8792/api/afval/meta" | python3 -c "import sys,json; m=json.load(sys.stdin); print('jaren:', m['jaren'][:3], '...'); print('afvalstromen:', m['afvalstromen'])"
curl -s "http://127.0.0.1:8792/api/afval/choropleth?afvalstroom=GFT-afval&jaar=2020&indicator=circulariteit" | python3 -c "import sys,json; fc=json.load(sys.stdin); print('features:', len(fc['features'])); print('voorbeeld:', {k:fc['features'][0]['properties'][k] for k in ('identificatie','value','eenheid')})"
curl -s -o /dev/null -w "GET /afval -> %{http_code}\n" "http://127.0.0.1:8792/afval"
kill %1
```
Expected: `meta` toont jaren + afvalstromen; `choropleth` geeft 12 features met een `value`; `/afval` → `200`. (Als de ingest nog niet gedraaid is → `503`; draai eerst Task 3 Step 5.)

- [ ] **Step 3: Commit**

```bash
git add src/leefomgevinglab/static/afval.html
git commit -m "feat(uc08): MapLibre afval/circulariteit-dashboard op /afval

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Documentatie — sprintstatus + CLAUDE.md-pointer

**Files:**
- Modify: `CLAUDE.md` (sectie "Sprint status")

**Interfaces:** documentatie-only.

- [ ] **Step 1: Voeg UC-08-regel toe aan de sprintstatus**

Voeg in `CLAUDE.md` onder "## Sprint status", na de laatste `🚧`-regel, toe:

```markdown
- 🚧 **UC-08 — Afval/circulair-dashboard:** provincie-choropleth + trend + Qwen-duiding op open CBS-afvalcijfers (83558NED, CC-BY 4.0) als open proxy voor het gesloten LMA/AMICE-aggregaat. Routes `/afval`, `/api/afval/{meta,choropleth,trend,duiding}`. Ingest via `scripts/11_fetch_afval_aggregaat.py` → `/mnt/nvme/geluidsmeter/data/external/afval/`. Code onder `src/leefomgevinglab/usecases/afval/` + `connectors/cbs_afval.py`.
```

- [ ] **Step 2: Volledige testsuite draaien**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_transform.py tests/test_cbs_afval_connector.py tests/test_afval_ingest.py tests/test_afval_service.py tests/test_afval_duiding.py tests/test_api_afval.py -v`
Expected: alle tests PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(uc08): sprintstatus afval/circulair-dashboard

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review (uitgevoerd)

**Spec-dekking:**
- §2 connector → Task 2; ingest → Task 3; service → Task 4; duiding → Task 5; routes → Task 6; frontend → Task 7. ✓
- §4 endpoints (`/afval`, meta, choropleth, trend, duiding) → Task 6. ✓
- §5 indicatoren (totaal kton + circulariteit R/D, één CBS-tabel) → Task 1 (`AFVALSTROMEN`, `circulariteit_rows`) + Task 4. ✓
- §6 Qwen no-hallucination + bronverwijzing → Task 5. ✓
- §7 foutafhandeling (BaseConnector-degradatie, Qwen-offline 503, ontbrekende data → `value: None`/`503`) → Tasks 2/4/5/6. ✓
- §8 offline tests op fixtures → alle Task-tests. ✓
- §9 metadata/bron/licentie/label overal → `service.meta`, `duiding`, frontend header. ✓
- Buiten scope (eHerkenning/BTO, per-gemeente, kg/inwoner) → nergens geïmplementeerd. ✓

**Placeholder-scan:** geen TBD/TODO; alle code-stappen bevatten volledige code. ✓

**Type-consistentie:** `regio_code`/`identificatie` = `"PVxx"` (gestript) door alle lagen; `afvalstroom` = label-string uit `AFVALSTROMEN`; `indicator` ∈ {`volume`,`circulariteit`}; `service.meta/choropleth/trend` en `duiding.duiding`-signaturen komen overeen tussen Task 4/5 (definitie) en Task 6 (aanroep/mocks). ✓
