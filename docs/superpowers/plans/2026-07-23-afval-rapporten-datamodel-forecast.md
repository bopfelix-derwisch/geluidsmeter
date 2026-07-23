# Afval — rapportcijfers, canoniek datamodel & Holt-forecast — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Meer openbare afvalcijfers per soort in een DuckDB-database volgens een canoniek datamodel (CBS↔AMICE), plus een statistische doorkijk naar de toekomst (Holt), ontsloten in het bestaande afval-dashboard.

**Architecture:** Nieuw pakket `src/leefomgevinglab/afvaldb/` met een DuckDB-store, een crosswalk (bron-vocabulaire → canonieke afvalstroom), vier bron-loaders (CBS live OData; CLO/Afvalfonds/LMA via gebundelde snapshot met pdfplumber-of-curated-CSV), en een zelf-geïmplementeerde Holt-forecast. Een ingest-script vult de database; de bestaande `usecases/afval`-service + `/api/afval/*`-routes + `afval.html` worden uitgebreid met forecast en extra broncijfers.

**Tech Stack:** Python 3.10, DuckDB, pandas, numpy, pdfplumber, httpx, FastAPI, MapLibre + inline SVG.

## Global Constraints

- Testrunner: **`python3 -m pytest`** vanuit de repo-root (systeem-`/usr/bin/python3`; `tests/conftest.py` zet `src/` op het pad). `duckdb`, `pdfplumber`, `pandas`, `numpy` zijn geïnstalleerd.
- DuckDB-bestand: **`/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb`**. Snapshots: **`…/afval/snapshots/`**. Beide buiten de repo (onder `/mnt/nvme`).
- Canonieke afvalstroomnamen sluiten aan op `leefomgevinglab.usecases.afval.transform.AFVALSTROMEN`.
- `afval_feit`-kolommen exact: `bron_id, regio_code, jaar, afvalstroom_canoniek, euralcode, verwerking, indicator_type, hoeveelheid, eenheid`.
- `verwerking` ∈ {`R`, `D`, `onbekend`}; `indicator_type` ∈ {`volume`, `recyclingpercentage`, `per_inwoner`}; `eenheid` ∈ {`kton`, `ton`, `kg_per_inwoner`, `pct`}.
- Rapportbronnen (CLO/Afvalfonds/LMA) zijn **landelijk** (`regio_code = "NL"`); provincie-reeksen (`PVxx`) komen uit CBS.
- Forecast: **Holt** (zelf, numpy), horizon **t/m 2035**, band uit residu-SE, ondergrens geklemd op 0, skip bij < 5 waarnemingen. Overal gelabeld "indicatieve modelmatige extrapolatie (Holt), geen beleidsprognose".
- Elke waarde herleidbaar: elke `afval_feit`-rij heeft een `bron_id` met een `bron`-rij (url/licentie/datum).
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Geen datafiles committen (staan op /mnt/nvme); curated CSV-fixtures wél (klein, in repo onder `tests/fixtures/afval/`).

## Vaste feiten (geverifieerd 2026-07-23)

- `duckdb` 1.5.x en `pdfplumber` 0.11.x zijn geïnstalleerd in systeem-python én `.venv`.
- CBS 83558NED: `Regiokenmerken` (`NL01`, `PV20`–`PV31`, met trailing spaces), `Perioden` (`YYYYJJ00`), topic-kolommen (o.a. `TotaalGemeentelijkAfval_1`, `GFTAfval_6`; verwerking `NuttigeToepassing_174`, `Verbranden_177`, `Storten_178`). Bestaande connector: `leefomgevinglab.connectors.cbs_afval.CbsAfvalConnector(base_url, table_id, **kw).typed_dataset()`.
- Afvalfonds/Verpact recycling per materiaal: PDF-rapporten op `verpact.nl` (glas/papier/metaal 86–95%, kunststof ~55%).
- CLO indicator huishoudelijk afval per inwoner: `https://www.clo.nl/indicatoren/nl014437-afval-van-huishoudens-per-inwoner-1950-2024` (data CBS-afgeleid).

## File Structure

- Create: `src/leefomgevinglab/afvaldb/__init__.py`
- Create: `src/leefomgevinglab/afvaldb/store.py` — DuckDB schema + upsert/query.
- Create: `src/leefomgevinglab/afvaldb/crosswalk.py` — bron-vocabulaire → canoniek.
- Create: `src/leefomgevinglab/afvaldb/loaders/__init__.py`
- Create: `src/leefomgevinglab/afvaldb/loaders/cbs.py`
- Create: `src/leefomgevinglab/afvaldb/loaders/clo.py`
- Create: `src/leefomgevinglab/afvaldb/loaders/afvalfonds.py`
- Create: `src/leefomgevinglab/afvaldb/loaders/lma_rws.py`
- Create: `src/leefomgevinglab/afvaldb/forecast.py` — Holt.
- Create: `scripts/12_fetch_afval_bronnen.py` — ingest-orkestratie.
- Create: `tests/fixtures/afval/clo_huishoudelijk.csv`, `afvalfonds_recycling.csv`, `lma_rws.csv` — curated mini-snapshots.
- Modify: `src/leefomgevinglab/usecases/afval/service.py` — `forecast()` + context-verrijking.
- Modify: `src/leefomgevinglab/geluidsmeter/api.py` — `GET /api/afval/forecast` + duiding-context.
- Modify: `src/leefomgevinglab/static/afval.html` — forecast-grafiek + extra cijfers.
- Modify: `requirements.txt` — `pdfplumber` toevoegen.
- Modify: `core/config.yaml` — `leefomgevinglab.afvaldb`-blok.
- Test: `tests/test_afvaldb_store.py`, `test_afvaldb_crosswalk.py`, `test_afvaldb_loader_cbs.py`, `test_afvaldb_loader_clo.py`, `test_afvaldb_loader_afvalfonds.py`, `test_afvaldb_loader_lma.py`, `test_afvaldb_forecast.py`, `test_afvaldb_ingest.py`, `test_afval_forecast_service.py`, `test_api_afval_forecast.py`.

---

### Task 1: DuckDB-store + schema

**Files:**
- Create: `src/leefomgevinglab/afvaldb/__init__.py` (leeg)
- Create: `src/leefomgevinglab/afvaldb/store.py`
- Test: `tests/test_afvaldb_store.py`

**Interfaces:**
- Produces:
  - `open_db(path: str) -> duckdb.DuckDBPyConnection` — maakt schema als het ontbreekt.
  - `upsert_bron(con, bron: dict)` — keys: `bron_id, naam, url, licentie, type, opgehaald_op`.
  - `insert_feiten(con, records: list[dict])` — keys = `afval_feit`-kolommen.
  - `insert_crosswalk(con, rows: list[dict])` — keys: `bron_type, bron_sleutel, afvalstroom_canoniek`.
  - `insert_forecasts(con, rows: list[dict])` — keys: `regio_code, afvalstroom_canoniek, jaar, verwacht, ondergrens, bovengrens, methode`.
  - `series(con, regio_code, afvalstroom_canoniek, indicator_type="volume", bron_id=None) -> list[tuple[int, float]]` — (jaar, hoeveelheid) oplopend.
  - `forecast_rows(con, regio_code, afvalstroom_canoniek) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_store.py
from leefomgevinglab.afvaldb import store


def _con(tmp_path):
    return store.open_db(str(tmp_path / "afval.duckdb"))


def test_schema_en_feiten_roundtrip(tmp_path):
    con = _con(tmp_path)
    store.upsert_bron(con, {"bron_id": "cbs-83558NED", "naam": "CBS", "url": "u",
                            "licentie": "CC-BY 4.0", "type": "api", "opgehaald_op": "2026-07-23"})
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2019,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 10.0, "eenheid": "kton"},
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"},
    ])
    s = store.series(con, "PV24", "GFT-afval")
    assert s == [(2019, 10.0), (2020, 12.0)]


def test_upsert_bron_is_idempotent(tmp_path):
    con = _con(tmp_path)
    b = {"bron_id": "x", "naam": "X", "url": "u", "licentie": "l", "type": "api", "opgehaald_op": "2026-07-23"}
    store.upsert_bron(con, b)
    store.upsert_bron(con, {**b, "naam": "X2"})
    rows = con.execute("SELECT naam FROM bron WHERE bron_id='x'").fetchall()
    assert rows == [("X2",)]


def test_forecast_roundtrip(tmp_path):
    con = _con(tmp_path)
    store.insert_forecasts(con, [
        {"regio_code": "PV24", "afvalstroom_canoniek": "GFT-afval", "jaar": 2030,
         "verwacht": 15.0, "ondergrens": 12.0, "bovengrens": 18.0, "methode": "holt"}])
    fr = store.forecast_rows(con, "PV24", "GFT-afval")
    assert fr[0]["jaar"] == 2030 and fr[0]["verwacht"] == 15.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_store.py -v`
Expected: FAIL — `ModuleNotFoundError: leefomgevinglab.afvaldb`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/afvaldb/__init__.py
# (leeg — package-marker)
```

```python
# src/leefomgevinglab/afvaldb/store.py
"""DuckDB-store voor het canonieke afval-datamodel (CBS↔AMICE) + forecasts."""
import duckdb

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bron (
    bron_id TEXT PRIMARY KEY, naam TEXT, url TEXT, licentie TEXT, type TEXT, opgehaald_op DATE);
CREATE TABLE IF NOT EXISTS afval_feit (
    bron_id TEXT, regio_code TEXT, jaar INTEGER, afvalstroom_canoniek TEXT,
    euralcode TEXT, verwerking TEXT, indicator_type TEXT, hoeveelheid DOUBLE, eenheid TEXT);
CREATE TABLE IF NOT EXISTS afvalstroom_crosswalk (
    bron_type TEXT, bron_sleutel TEXT, afvalstroom_canoniek TEXT);
CREATE TABLE IF NOT EXISTS forecast (
    regio_code TEXT, afvalstroom_canoniek TEXT, jaar INTEGER,
    verwacht DOUBLE, ondergrens DOUBLE, bovengrens DOUBLE, methode TEXT);
"""

_FEIT_COLS = ["bron_id", "regio_code", "jaar", "afvalstroom_canoniek", "euralcode",
              "verwerking", "indicator_type", "hoeveelheid", "eenheid"]
_FC_COLS = ["regio_code", "afvalstroom_canoniek", "jaar", "verwacht", "ondergrens", "bovengrens", "methode"]


def open_db(path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path)
    con.execute(SCHEMA_SQL)
    return con


def upsert_bron(con, bron: dict) -> None:
    con.execute("DELETE FROM bron WHERE bron_id = ?", [bron["bron_id"]])
    con.execute("INSERT INTO bron VALUES (?, ?, ?, ?, ?, ?)",
                [bron["bron_id"], bron["naam"], bron["url"], bron["licentie"],
                 bron["type"], bron["opgehaald_op"]])


def insert_feiten(con, records: list[dict]) -> None:
    con.executemany(
        f"INSERT INTO afval_feit VALUES ({', '.join(['?'] * len(_FEIT_COLS))})",
        [[r.get(c) for c in _FEIT_COLS] for r in records])


def insert_crosswalk(con, rows: list[dict]) -> None:
    con.executemany("INSERT INTO afvalstroom_crosswalk VALUES (?, ?, ?)",
                    [[r["bron_type"], r["bron_sleutel"], r["afvalstroom_canoniek"]] for r in rows])


def insert_forecasts(con, rows: list[dict]) -> None:
    con.executemany(
        f"INSERT INTO forecast VALUES ({', '.join(['?'] * len(_FC_COLS))})",
        [[r.get(c) for c in _FC_COLS] for r in rows])


def series(con, regio_code, afvalstroom_canoniek, indicator_type="volume", bron_id=None):
    q = ("SELECT jaar, hoeveelheid FROM afval_feit WHERE regio_code = ? "
         "AND afvalstroom_canoniek = ? AND indicator_type = ?")
    params = [regio_code, afvalstroom_canoniek, indicator_type]
    if bron_id:
        q += " AND bron_id = ?"
        params.append(bron_id)
    q += " ORDER BY jaar"
    return [(int(j), float(h)) for j, h in con.execute(q, params).fetchall()]


def forecast_rows(con, regio_code, afvalstroom_canoniek) -> list[dict]:
    rows = con.execute(
        f"SELECT {', '.join(_FC_COLS)} FROM forecast WHERE regio_code = ? "
        "AND afvalstroom_canoniek = ? ORDER BY jaar", [regio_code, afvalstroom_canoniek]).fetchall()
    return [dict(zip(_FC_COLS, r)) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/__init__.py src/leefomgevinglab/afvaldb/store.py tests/test_afvaldb_store.py
git commit -m "feat(afvaldb): DuckDB-store + canoniek schema (bron/afval_feit/crosswalk/forecast)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Crosswalk (bron-vocabulaire → canoniek)

**Files:**
- Create: `src/leefomgevinglab/afvaldb/crosswalk.py`
- Test: `tests/test_afvaldb_crosswalk.py`

**Interfaces:**
- Consumes: `transform.AFVALSTROMEN` (labels).
- Produces:
  - `CROSSWALK: list[dict]` — rows `{bron_type, bron_sleutel, afvalstroom_canoniek}`.
  - `canoniek(bron_type: str, bron_sleutel: str) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_crosswalk.py
from leefomgevinglab.afvaldb import crosswalk as cw


def test_cbs_topic_naar_canoniek():
    assert cw.canoniek("cbs_topic", "GFTAfval_6") == "GFT-afval"
    assert cw.canoniek("cbs_topic", "Verpakkingsglas_9") == "Verpakkingsglas"


def test_afvalfonds_materiaal_naar_canoniek():
    assert cw.canoniek("afvalfonds_materiaal", "Glas") == "Verpakkingsglas"
    assert cw.canoniek("afvalfonds_materiaal", "Papier en karton") == "Oud papier en karton"


def test_euralcode_naar_canoniek():
    assert cw.canoniek("euralcode", "200108") == "GFT-afval"


def test_onbekende_sleutel_is_none():
    assert cw.canoniek("cbs_topic", "BestaatNiet_999") is None


def test_crosswalk_rows_hebben_verplichte_kolommen():
    for row in cw.CROSSWALK:
        assert set(row) == {"bron_type", "bron_sleutel", "afvalstroom_canoniek"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_crosswalk.py -v`
Expected: FAIL — `ModuleNotFoundError: ...afvaldb.crosswalk`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/afvaldb/crosswalk.py
"""Crosswalk: bron-specifieke sleutels -> canonieke afvalstroom (CBS↔AMICE-brug)."""
from leefomgevinglab.usecases.afval.transform import AFVALSTROMEN

# CBS-topic -> canoniek: exact de bestaande AFVALSTROMEN-mapping (key->label omgedraaid).
_CBS = [{"bron_type": "cbs_topic", "bron_sleutel": key, "afvalstroom_canoniek": label}
        for label, key in AFVALSTROMEN.items()]

# Afvalfonds-materiaal -> canoniek.
_AFVALFONDS = [
    {"bron_type": "afvalfonds_materiaal", "bron_sleutel": "Glas", "afvalstroom_canoniek": "Verpakkingsglas"},
    {"bron_type": "afvalfonds_materiaal", "bron_sleutel": "Papier en karton", "afvalstroom_canoniek": "Oud papier en karton"},
    {"bron_type": "afvalfonds_materiaal", "bron_sleutel": "Kunststof", "afvalstroom_canoniek": "Kunststof verpakkingen"},
]

# Euralcode -> canoniek (AMICE-aansluiting; selectie relevant voor de curated stromen).
_EURAL = [
    {"bron_type": "euralcode", "bron_sleutel": "200108", "afvalstroom_canoniek": "GFT-afval"},
    {"bron_type": "euralcode", "bron_sleutel": "200101", "afvalstroom_canoniek": "Oud papier en karton"},
    {"bron_type": "euralcode", "bron_sleutel": "200102", "afvalstroom_canoniek": "Verpakkingsglas"},
    {"bron_type": "euralcode", "bron_sleutel": "200301", "afvalstroom_canoniek": "Huishoudelijk restafval"},
]

# CLO-indicator -> canoniek.
_CLO = [
    {"bron_type": "clo_indicator", "bron_sleutel": "afval-huishoudens-per-inwoner", "afvalstroom_canoniek": "Totaal huishoudelijk afval"},
]

CROSSWALK = _CBS + _AFVALFONDS + _EURAL + _CLO


def canoniek(bron_type: str, bron_sleutel: str) -> str | None:
    for row in CROSSWALK:
        if row["bron_type"] == bron_type and row["bron_sleutel"] == bron_sleutel:
            return row["afvalstroom_canoniek"]
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_crosswalk.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/crosswalk.py tests/test_afvaldb_crosswalk.py
git commit -m "feat(afvaldb): crosswalk bron-vocabulaire naar canonieke afvalstroom

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: CBS-loader (83558NED → afval_feit, provincies + NL)

**Files:**
- Create: `src/leefomgevinglab/afvaldb/loaders/__init__.py` (leeg)
- Create: `src/leefomgevinglab/afvaldb/loaders/cbs.py`
- Test: `tests/test_afvaldb_loader_cbs.py`

**Interfaces:**
- Consumes: `transform.AFVALSTROMEN`, `transform.periode_to_jaar`; `store.insert_feiten`/`upsert_bron`.
- Produces:
  - `parse(rows: list[dict]) -> list[dict]` — CBS TypedDataSet-rijen → `afval_feit`-records voor provincies (`PVxx`) én landelijk (`NL`), `indicator_type="volume"`, `verwerking="onbekend"`, `eenheid="kton"`, `bron_id="cbs-83558NED"`.
  - `BRON: dict` — de `bron`-rij voor CBS.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_loader_cbs.py
from leefomgevinglab.afvaldb.loaders import cbs


def _row(regio, periode, **topics):
    return {"Regiokenmerken": regio, "Perioden": periode, **topics}


def test_parse_provincie_en_nl_volumes():
    rows = [
        _row("PV24    ", "2020JJ00", GFTAfval_6=12, TotaalGemeentelijkAfval_1=100),
        _row("NL01    ", "2020JJ00", GFTAfval_6=800),
        _row("LD03", "2020JJ00", GFTAfval_6=1),   # landsdeel: overslaan
        _row("PV24    ", "2020KW01", GFTAfval_6=3),  # geen jaar: overslaan
    ]
    recs = cbs.parse(rows)
    pv = [r for r in recs if r["regio_code"] == "PV24" and r["afvalstroom_canoniek"] == "GFT-afval"]
    nl = [r for r in recs if r["regio_code"] == "NL" and r["afvalstroom_canoniek"] == "GFT-afval"]
    assert pv and pv[0]["hoeveelheid"] == 12.0 and pv[0]["jaar"] == 2020
    assert pv[0]["indicator_type"] == "volume" and pv[0]["eenheid"] == "kton"
    assert pv[0]["bron_id"] == "cbs-83558NED" and pv[0]["verwerking"] == "onbekend"
    assert nl and nl[0]["hoeveelheid"] == 800.0
    # geen landsdeel/kwartaal
    assert not any(r["regio_code"].startswith("LD") for r in recs)
    assert all(r["jaar"] == 2020 for r in recs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_cbs.py -v`
Expected: FAIL — `ModuleNotFoundError: ...loaders.cbs`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/afvaldb/loaders/__init__.py
# (leeg — package-marker)
```

```python
# src/leefomgevinglab/afvaldb/loaders/cbs.py
"""CBS-loader: 83558NED TypedDataSet -> canonieke afval_feit-records (provincies + NL)."""
from leefomgevinglab.usecases.afval.transform import AFVALSTROMEN, periode_to_jaar

BRON = {"bron_id": "cbs-83558NED", "naam": "CBS StatLine 83558NED (Gemeentelijke afvalstoffen)",
        "url": "https://opendata.cbs.nl/ODataApi/OData/83558NED", "licentie": "CC-BY 4.0",
        "type": "api", "opgehaald_op": None}  # opgehaald_op vult het ingest-script


def _regio(code: str) -> str | None:
    c = code.strip()
    if c.startswith("PV"):
        return c
    if c.startswith("NL"):
        return "NL"
    return None


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def parse(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        regio = _regio(row.get("Regiokenmerken", ""))
        if regio is None:
            continue
        jaar = periode_to_jaar(row.get("Perioden", ""))
        if jaar is None:
            continue
        for label, key in AFVALSTROMEN.items():
            val = _num(row.get(key))
            if val is None:
                continue
            out.append({"bron_id": "cbs-83558NED", "regio_code": regio, "jaar": jaar,
                        "afvalstroom_canoniek": label, "euralcode": None,
                        "verwerking": "onbekend", "indicator_type": "volume",
                        "hoeveelheid": val, "eenheid": "kton"})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_cbs.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/loaders/__init__.py src/leefomgevinglab/afvaldb/loaders/cbs.py tests/test_afvaldb_loader_cbs.py
git commit -m "feat(afvaldb): CBS-loader (83558NED -> canonieke feiten, provincies + NL)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: CLO-loader (huishoudelijk afval per inwoner, curated CSV)

**Files:**
- Create: `src/leefomgevinglab/afvaldb/loaders/clo.py`
- Create: `tests/fixtures/afval/clo_huishoudelijk.csv`
- Test: `tests/test_afvaldb_loader_clo.py`

**Interfaces:**
- Produces:
  - `parse_csv(path: str) -> list[dict]` — CSV met kolommen `jaar,kg_per_inwoner` → `afval_feit`-records (`regio_code="NL"`, `afvalstroom_canoniek="Totaal huishoudelijk afval"`, `indicator_type="per_inwoner"`, `eenheid="kg_per_inwoner"`, `bron_id="clo-nl014437"`).
  - `BRON: dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_loader_clo.py
from pathlib import Path
from leefomgevinglab.afvaldb.loaders import clo

FIX = Path(__file__).parent / "fixtures" / "afval" / "clo_huishoudelijk.csv"


def test_parse_csv():
    recs = clo.parse_csv(str(FIX))
    assert {r["jaar"] for r in recs} >= {2000, 2020}
    r2020 = next(r for r in recs if r["jaar"] == 2020)
    assert r2020["regio_code"] == "NL"
    assert r2020["afvalstroom_canoniek"] == "Totaal huishoudelijk afval"
    assert r2020["indicator_type"] == "per_inwoner"
    assert r2020["eenheid"] == "kg_per_inwoner"
    assert r2020["hoeveelheid"] == 495.0
    assert r2020["bron_id"] == "clo-nl014437"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_clo.py -v`
Expected: FAIL — `ModuleNotFoundError: ...loaders.clo`.

- [ ] **Step 3: Write minimal implementation**

Curated fixture (klein, echte-achtige waarden; bron = CLO nl014437):

```csv
# tests/fixtures/afval/clo_huishoudelijk.csv
jaar,kg_per_inwoner
2000,540
2010,510
2020,495
```

```python
# src/leefomgevinglab/afvaldb/loaders/clo.py
"""CLO-loader: huishoudelijk afval per inwoner (curated CSV-snapshot, CBS-afgeleid)."""
import csv

BRON = {"bron_id": "clo-nl014437", "naam": "Compendium voor de Leefomgeving — afval huishoudens per inwoner",
        "url": "https://www.clo.nl/indicatoren/nl014437-afval-van-huishoudens-per-inwoner-1950-2024",
        "licentie": "CC-BY (CLO)", "type": "report_data", "opgehaald_op": None}


def parse_csv(path: str) -> list[dict]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(r for r in f if not r.startswith("#")):
            out.append({"bron_id": "clo-nl014437", "regio_code": "NL", "jaar": int(row["jaar"]),
                        "afvalstroom_canoniek": "Totaal huishoudelijk afval", "euralcode": None,
                        "verwerking": "onbekend", "indicator_type": "per_inwoner",
                        "hoeveelheid": float(row["kg_per_inwoner"]), "eenheid": "kg_per_inwoner"})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_clo.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/loaders/clo.py tests/fixtures/afval/clo_huishoudelijk.csv tests/test_afvaldb_loader_clo.py
git commit -m "feat(afvaldb): CLO-loader (huishoudelijk afval per inwoner, curated CSV)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Afvalfonds-loader (recyclingpercentage per materiaal)

**Files:**
- Create: `src/leefomgevinglab/afvaldb/loaders/afvalfonds.py`
- Create: `tests/fixtures/afval/afvalfonds_recycling.csv`
- Test: `tests/test_afvaldb_loader_afvalfonds.py`

**Interfaces:**
- Consumes: `crosswalk.canoniek`.
- Produces:
  - `parse_rows(rows: list[dict], jaar: int) -> list[dict]` — rows `{"materiaal": str, "recycling_pct": float}` → `afval_feit` (`regio_code="NL"`, `indicator_type="recyclingpercentage"`, `eenheid="pct"`, canonieke stroom via crosswalk `afvalfonds_materiaal`; onbekend materiaal wordt overgeslagen). `bron_id=f"afvalfonds-{jaar}"`.
  - `parse_csv(path: str, jaar: int) -> list[dict]` — CSV `materiaal,recycling_pct` → via `parse_rows`.
  - `extract_pdf(pdf_path: str) -> list[dict]` — pdfplumber-tabelextractie naar `{"materiaal","recycling_pct"}`-rows (voor het ingest-script; niet unit-getest tegen een echte PDF).
  - `bron(jaar: int) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_loader_afvalfonds.py
from pathlib import Path
from leefomgevinglab.afvaldb.loaders import afvalfonds as af

FIX = Path(__file__).parent / "fixtures" / "afval" / "afvalfonds_recycling.csv"


def test_parse_rows_canoniseert_en_slaat_onbekend_over():
    recs = af.parse_rows([
        {"materiaal": "Glas", "recycling_pct": 86.0},
        {"materiaal": "Kunststof", "recycling_pct": 55.0},
        {"materiaal": "Onbekend materiaal", "recycling_pct": 10.0},
    ], jaar=2023)
    stromen = {r["afvalstroom_canoniek"]: r for r in recs}
    assert "Verpakkingsglas" in stromen
    assert stromen["Verpakkingsglas"]["hoeveelheid"] == 86.0
    assert stromen["Verpakkingsglas"]["indicator_type"] == "recyclingpercentage"
    assert stromen["Verpakkingsglas"]["eenheid"] == "pct"
    assert stromen["Verpakkingsglas"]["regio_code"] == "NL"
    assert stromen["Verpakkingsglas"]["bron_id"] == "afvalfonds-2023"
    assert "Kunststof verpakkingen" in stromen
    # onbekend materiaal levert geen record
    assert len(recs) == 2


def test_parse_csv():
    recs = af.parse_csv(str(FIX), jaar=2023)
    assert any(r["afvalstroom_canoniek"] == "Oud papier en karton" for r in recs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_afvalfonds.py -v`
Expected: FAIL — `ModuleNotFoundError: ...loaders.afvalfonds`.

- [ ] **Step 3: Write minimal implementation**

```csv
# tests/fixtures/afval/afvalfonds_recycling.csv
materiaal,recycling_pct
Glas,86
Papier en karton,92
Kunststof,55
```

```python
# src/leefomgevinglab/afvaldb/loaders/afvalfonds.py
"""Afvalfonds/Verpact-loader: recyclingpercentage per materiaal (NL).

Bron = jaarrapportage (PDF) op verpact.nl. Extractie via pdfplumber met
curated-CSV-fallback; parse_rows is puur en offline testbaar.
"""
import csv

from leefomgevinglab.afvaldb.crosswalk import canoniek


def bron(jaar: int) -> dict:
    return {"bron_id": f"afvalfonds-{jaar}", "naam": f"Afvalfonds Verpakkingen — resultaten recycling {jaar}",
            "url": "https://www.verpact.nl/", "licentie": "open (voorwaarden)",
            "type": "report_pdf", "opgehaald_op": None}


def parse_rows(rows: list[dict], jaar: int) -> list[dict]:
    out = []
    for r in rows:
        stroom = canoniek("afvalfonds_materiaal", str(r["materiaal"]).strip())
        if stroom is None:
            continue
        out.append({"bron_id": f"afvalfonds-{jaar}", "regio_code": "NL", "jaar": jaar,
                    "afvalstroom_canoniek": stroom, "euralcode": None, "verwerking": "R",
                    "indicator_type": "recyclingpercentage", "hoeveelheid": float(r["recycling_pct"]),
                    "eenheid": "pct"})
    return out


def parse_csv(path: str, jaar: int) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(r for r in f if not r.startswith("#")))
    return parse_rows(rows, jaar)


def extract_pdf(pdf_path: str) -> list[dict]:
    """Extraheer {'materiaal','recycling_pct'}-rijen uit een Afvalfonds-PDF-tabel.
    Zoekt regels 'Materiaal ... <getal>%'. Gebruikt door het ingest-script."""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for row in tbl:
                    cells = [c for c in row if c]
                    if len(cells) < 2:
                        continue
                    materiaal = str(cells[0]).strip()
                    pct = str(cells[-1]).replace("%", "").replace(",", ".").strip()
                    try:
                        out.append({"materiaal": materiaal, "recycling_pct": float(pct)})
                    except ValueError:
                        continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_afvalfonds.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/loaders/afvalfonds.py tests/fixtures/afval/afvalfonds_recycling.csv tests/test_afvaldb_loader_afvalfonds.py
git commit -m "feat(afvaldb): Afvalfonds-loader (recyclingpercentage per materiaal, pdf+csv)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: LMA/RWS-loader (nationale cijfers per Euralcode/verwerking)

**Files:**
- Create: `src/leefomgevinglab/afvaldb/loaders/lma_rws.py`
- Create: `tests/fixtures/afval/lma_rws.csv`
- Test: `tests/test_afvaldb_loader_lma.py`

**Interfaces:**
- Consumes: `crosswalk.canoniek`.
- Produces:
  - `parse_rows(rows: list[dict], jaar: int) -> list[dict]` — rows `{"euralcode": str, "verwerking": "R"|"D", "ton": float}` → `afval_feit` (`regio_code="NL"`, `indicator_type="volume"`, `eenheid="ton"`, `afvalstroom_canoniek` via crosswalk `euralcode`; onbekende euralcode → `afvalstroom_canoniek=None` toegestaan maar `euralcode` bewaard). `bron_id=f"lma-rws-{jaar}"`.
  - `parse_csv(path: str, jaar: int) -> list[dict]`.
  - `extract_pdf(pdf_path: str) -> list[dict]`.
  - `bron(jaar: int) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_loader_lma.py
from pathlib import Path
from leefomgevinglab.afvaldb.loaders import lma_rws as lma

FIX = Path(__file__).parent / "fixtures" / "afval" / "lma_rws.csv"


def test_parse_rows_euralcode_en_verwerking():
    recs = lma.parse_rows([
        {"euralcode": "200108", "verwerking": "R", "ton": 1500000},
        {"euralcode": "999999", "verwerking": "D", "ton": 100},   # onbekende eural
    ], jaar=2022)
    gft = next(r for r in recs if r["euralcode"] == "200108")
    assert gft["afvalstroom_canoniek"] == "GFT-afval"
    assert gft["verwerking"] == "R" and gft["eenheid"] == "ton"
    assert gft["regio_code"] == "NL" and gft["bron_id"] == "lma-rws-2022"
    onbekend = next(r for r in recs if r["euralcode"] == "999999")
    assert onbekend["afvalstroom_canoniek"] is None   # eural bewaard, canoniek onbekend


def test_parse_csv():
    recs = lma.parse_csv(str(FIX), jaar=2022)
    assert any(r["afvalstroom_canoniek"] == "Verpakkingsglas" for r in recs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_lma.py -v`
Expected: FAIL — `ModuleNotFoundError: ...loaders.lma_rws`.

- [ ] **Step 3: Write minimal implementation**

```csv
# tests/fixtures/afval/lma_rws.csv
euralcode,verwerking,ton
200108,R,1500000
200102,R,400000
200301,D,3000000
```

```python
# src/leefomgevinglab/afvaldb/loaders/lma_rws.py
"""LMA/RWS-loader: nationale afvalcijfers per Euralcode/verwerking (open jaarrapportage).

Dichtst bij het AMICE-schema (Euralcode + R/D). Extractie via pdfplumber met
curated-CSV-fallback; parse_rows is puur en offline testbaar.
"""
import csv

from leefomgevinglab.afvaldb.crosswalk import canoniek


def bron(jaar: int) -> dict:
    return {"bron_id": f"lma-rws-{jaar}", "naam": f"LMA/RWS afvaloverzicht {jaar} (openbaar)",
            "url": "https://www.lma.nl/", "licentie": "open (voorwaarden)",
            "type": "report_pdf", "opgehaald_op": None}


def parse_rows(rows: list[dict], jaar: int) -> list[dict]:
    out = []
    for r in rows:
        eural = str(r["euralcode"]).strip()
        verwerking = str(r["verwerking"]).strip().upper()
        out.append({"bron_id": f"lma-rws-{jaar}", "regio_code": "NL", "jaar": jaar,
                    "afvalstroom_canoniek": canoniek("euralcode", eural), "euralcode": eural,
                    "verwerking": verwerking if verwerking in ("R", "D") else "onbekend",
                    "indicator_type": "volume", "hoeveelheid": float(r["ton"]), "eenheid": "ton"})
    return out


def parse_csv(path: str, jaar: int) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(r for r in f if not r.startswith("#")))
    return parse_rows(rows, jaar)


def extract_pdf(pdf_path: str) -> list[dict]:
    """Extraheer {'euralcode','verwerking','ton'}-rijen uit een LMA/RWS-PDF-tabel."""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for row in tbl:
                    cells = [str(c).strip() for c in row if c]
                    if len(cells) < 3 or not cells[0].isdigit():
                        continue
                    ton = cells[-1].replace(".", "").replace(",", ".")
                    try:
                        out.append({"euralcode": cells[0], "verwerking": cells[1], "ton": float(ton)})
                    except ValueError:
                        continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_loader_lma.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/loaders/lma_rws.py tests/fixtures/afval/lma_rws.csv tests/test_afvaldb_loader_lma.py
git commit -m "feat(afvaldb): LMA/RWS-loader (nationale cijfers per Euralcode/verwerking)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Holt-forecast

**Files:**
- Create: `src/leefomgevinglab/afvaldb/forecast.py`
- Test: `tests/test_afvaldb_forecast.py`

**Interfaces:**
- Consumes: `store.series`, `store.insert_forecasts`, `store.open_db`.
- Produces:
  - `fit_holt(y: list[float]) -> dict` — `{alpha, beta, level, trend, resid_std}` (grid-search α,β op één-stap-SSE).
  - `forecast_holt(jaren: list[int], y: list[float], tot_jaar: int, z: float = 1.28) -> list[dict]` — per toekomstjaar `{jaar, verwacht, ondergrens, bovengrens}`; leeg bij < 5 waarnemingen; `ondergrens` geklemd op 0.
  - `bouw_forecasts(con, tot_jaar: int = 2035) -> int` — voor elke (regio_code, afvalstroom_canoniek) met `indicator_type='volume'` en ≥ 5 punten: schrijf `forecast`-rijen (`methode="holt"`); geeft het aantal reeksen terug.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_forecast.py
from leefomgevinglab.afvaldb import forecast as fc
from leefomgevinglab.afvaldb import store


def test_holt_op_lineaire_reeks_extrapoleert():
    jaren = list(range(2010, 2021))            # 11 jaar
    y = [10.0 + 2.0 * i for i in range(11)]     # perfect lineair, helling 2/jaar
    out = fc.forecast_holt(jaren, y, tot_jaar=2023)
    assert [r["jaar"] for r in out] == [2021, 2022, 2023]
    # 2021 ~ 32 (10 + 2*11); tolerantie voor smoothing
    assert abs(out[0]["verwacht"] - 32.0) < 2.0
    assert out[0]["ondergrens"] <= out[0]["verwacht"] <= out[0]["bovengrens"]


def test_te_korte_reeks_geeft_leeg():
    assert fc.forecast_holt([2018, 2019, 2020], [1.0, 2.0, 3.0], tot_jaar=2025) == []


def test_ondergrens_geklemd_op_nul():
    jaren = list(range(2010, 2021))
    y = [100.0 - 9.0 * i for i in range(11)]    # dalend, richting 0
    out = fc.forecast_holt(jaren, y, tot_jaar=2035)
    assert all(r["ondergrens"] >= 0 for r in out)


def test_bouw_forecasts_schrijft_tabel(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2010 + i,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 10.0 + i, "eenheid": "kton"}
        for i in range(8)])
    n = fc.bouw_forecasts(con, tot_jaar=2025)
    assert n == 1
    rows = store.forecast_rows(con, "PV24", "GFT-afval")
    assert rows and rows[0]["methode"] == "holt"
    assert max(r["jaar"] for r in rows) == 2025
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_forecast.py -v`
Expected: FAIL — `ModuleNotFoundError: ...afvaldb.forecast`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/afvaldb/forecast.py
"""Holt's lineaire exponential smoothing (zelf-geïmplementeerd, numpy).

Indicatieve modelmatige extrapolatie — geen beleidsprognose.
"""
import numpy as np

from leefomgevinglab.afvaldb import store

MIN_PUNTEN = 5


def _holt_sse(y, alpha, beta):
    level, trend = y[0], y[1] - y[0]
    sse = 0.0
    resid = []
    for t in range(1, len(y)):
        voorspeld = level + trend
        fout = y[t] - voorspeld
        sse += fout * fout
        resid.append(fout)
        level_prev = level
        level = alpha * y[t] + (1 - alpha) * (level + trend)
        trend = beta * (level - level_prev) + (1 - beta) * trend
    return sse, level, trend, resid


def fit_holt(y: list[float]) -> dict:
    y = [float(v) for v in y]
    best = None
    for alpha in np.linspace(0.1, 0.9, 9):
        for beta in np.linspace(0.1, 0.9, 9):
            sse, level, trend, resid = _holt_sse(y, alpha, beta)
            if best is None or sse < best[0]:
                best = (sse, alpha, beta, level, trend, resid)
    sse, alpha, beta, level, trend, resid = best
    resid_std = float(np.std(resid)) if resid else 0.0
    return {"alpha": float(alpha), "beta": float(beta), "level": float(level),
            "trend": float(trend), "resid_std": resid_std}


def forecast_holt(jaren: list[int], y: list[float], tot_jaar: int, z: float = 1.28) -> list[dict]:
    if len(y) < MIN_PUNTEN:
        return []
    f = fit_holt(y)
    laatste = int(jaren[-1])
    out = []
    for h, jaar in enumerate(range(laatste + 1, tot_jaar + 1), start=1):
        verwacht = f["level"] + h * f["trend"]
        band = z * f["resid_std"] * (h ** 0.5)
        out.append({"jaar": jaar, "verwacht": verwacht,
                    "ondergrens": max(0.0, verwacht - band), "bovengrens": verwacht + band})
    return out


def bouw_forecasts(con, tot_jaar: int = 2035) -> int:
    combos = con.execute(
        "SELECT DISTINCT regio_code, afvalstroom_canoniek FROM afval_feit "
        "WHERE indicator_type = 'volume'").fetchall()
    n = 0
    for regio, stroom in combos:
        reeks = store.series(con, regio, stroom, indicator_type="volume")
        if len(reeks) < MIN_PUNTEN:
            continue
        jaren = [j for j, _ in reeks]
        y = [v for _, v in reeks]
        rows = forecast_holt(jaren, y, tot_jaar)
        if not rows:
            continue
        store.insert_forecasts(con, [{"regio_code": regio, "afvalstroom_canoniek": stroom,
                                      "jaar": r["jaar"], "verwacht": r["verwacht"],
                                      "ondergrens": r["ondergrens"], "bovengrens": r["bovengrens"],
                                      "methode": "holt"} for r in rows])
        n += 1
    return n
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_forecast.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/forecast.py tests/test_afvaldb_forecast.py
git commit -m "feat(afvaldb): Holt-forecast (zelf, numpy) met onzekerheidsband

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Ingest-script + config-blok

**Files:**
- Create: `scripts/12_fetch_afval_bronnen.py`
- Modify: `core/config.yaml` (blok `leefomgevinglab.afvaldb`)
- Modify: `requirements.txt` (voeg `pdfplumber` toe)
- Test: `tests/test_afvaldb_ingest.py`

**Interfaces:**
- Consumes: alle loaders, `store`, `crosswalk.CROSSWALK`, `forecast.bouw_forecasts`, `CbsAfvalConnector`.
- Produces: functie `vul_database(con, cbs_rows, clo_csv, afvalfonds_csv, lma_csv, opgehaald_op) -> dict` (importeerbaar, telt inserts per bron); `main()` doet de echte fetch + wegschrijven.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_ingest.py
import importlib.util
from pathlib import Path
from leefomgevinglab.afvaldb import store

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "12_fetch_afval_bronnen.py"
_spec = importlib.util.spec_from_file_location("ingest_bronnen", SPEC)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)

FIX = Path(__file__).parent / "fixtures" / "afval"


def _row(regio, periode, **t):
    return {"Regiokenmerken": regio, "Perioden": periode, **t}


def test_vul_database_laadt_alle_bronnen(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    cbs_rows = [_row("PV24    ", "2020JJ00", GFTAfval_6=12)]
    telling = ingest.vul_database(
        con, cbs_rows=cbs_rows,
        clo_csv=str(FIX / "clo_huishoudelijk.csv"),
        afvalfonds_csv=str(FIX / "afvalfonds_recycling.csv"),
        lma_csv=str(FIX / "lma_rws.csv"),
        opgehaald_op="2026-07-23")
    # feiten uit elke bron aanwezig
    assert store.series(con, "PV24", "GFT-afval")            # CBS
    assert store.series(con, "NL", "Totaal huishoudelijk afval", indicator_type="per_inwoner")  # CLO
    bronnen = {r[0] for r in con.execute("SELECT DISTINCT bron_id FROM afval_feit").fetchall()}
    assert {"cbs-83558NED", "clo-nl014437"}.issubset(bronnen)
    assert any(b.startswith("afvalfonds-") for b in bronnen)
    assert any(b.startswith("lma-rws-") for b in bronnen)
    # crosswalk geladen
    assert con.execute("SELECT COUNT(*) FROM afvalstroom_crosswalk").fetchone()[0] > 0
    assert telling["cbs"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_ingest.py -v`
Expected: FAIL — script bestaat nog niet.

- [ ] **Step 3: Write minimal implementation**

Voeg aan `requirements.txt` (na `pyarrow`) toe:
```
pdfplumber
```

Voeg aan `core/config.yaml` onder `leefomgevinglab:` (2 spaties inspringen, ná het `afval:`-blok) toe:
```yaml
  afvaldb:
    db_path: "/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb"
    snapshots_dir: "/mnt/nvme/geluidsmeter/data/external/afval/snapshots"
    forecast_tot_jaar: 2035
    afvalfonds_jaar: 2023
    lma_jaar: 2022
    # Rapport-snapshots: laat leeg om de curated CSV-fallback in tests/fixtures te gebruiken;
    # vul een pad naar een opgehaalde PDF om pdfplumber-extractie te draaien.
    afvalfonds_pdf: ""
    lma_pdf: ""
```

```python
# scripts/12_fetch_afval_bronnen.py
"""Ingest: vult de DuckDB-afvaldatabase uit alle open bronnen en bouwt de Holt-forecast.

CBS live via OData; CLO/Afvalfonds/LMA via gebundelde snapshot (pdfplumber of curated CSV).
Bron: open/CC-BY — proxy-context naast het gesloten LMA/AMICE.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leefomgevinglab.afvaldb import store, forecast
from leefomgevinglab.afvaldb.crosswalk import CROSSWALK
from leefomgevinglab.afvaldb.loaders import cbs, clo, afvalfonds, lma_rws
from leefomgevinglab.connectors.cbs_afval import CbsAfvalConnector

_ROOT = Path(__file__).resolve().parents[1]
_FIX = _ROOT / "tests" / "fixtures" / "afval"


def vul_database(con, cbs_rows, clo_csv, afvalfonds_csv, lma_csv, opgehaald_op,
                 afvalfonds_jaar=2023, lma_jaar=2022):
    store.insert_crosswalk(con, CROSSWALK)
    telling = {}

    cbs_recs = cbs.parse(cbs_rows)
    store.upsert_bron(con, {**cbs.BRON, "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, cbs_recs)
    telling["cbs"] = len(cbs_recs)

    clo_recs = clo.parse_csv(clo_csv)
    store.upsert_bron(con, {**clo.BRON, "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, clo_recs)
    telling["clo"] = len(clo_recs)

    af_recs = afvalfonds.parse_csv(afvalfonds_csv, jaar=afvalfonds_jaar)
    store.upsert_bron(con, {**afvalfonds.bron(afvalfonds_jaar), "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, af_recs)
    telling["afvalfonds"] = len(af_recs)

    lma_recs = lma_rws.parse_csv(lma_csv, jaar=lma_jaar)
    store.upsert_bron(con, {**lma_rws.bron(lma_jaar), "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, lma_recs)
    telling["lma"] = len(lma_recs)

    return telling


def main():
    from datetime import date
    cfg = yaml.safe_load(open(_ROOT / "core" / "config.yaml"))
    ll = cfg["leefomgevinglab"]
    db = ll["afvaldb"]
    afval = ll["afval"]
    Path(db["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    con = store.open_db(db["db_path"])
    today = date.today().isoformat()

    print("CBS 83558NED ophalen...")
    conn = CbsAfvalConnector(base_url=afval["odata_base_url"], table_id=afval["table_id"],
                             cache_dir=ll.get("cache_dir", "/tmp/llab_cache"), timeout=30.0)
    cbs_rows = conn.typed_dataset()

    # Rapport-snapshots: PDF indien geconfigureerd, anders curated CSV-fallback.
    af_pdf, lma_pdf = db.get("afvalfonds_pdf", ""), db.get("lma_pdf", "")
    af_csv, lma_csv = str(_FIX / "afvalfonds_recycling.csv"), str(_FIX / "lma_rws.csv")
    snap = Path(db["snapshots_dir"]); snap.mkdir(parents=True, exist_ok=True)
    if af_pdf:
        rows = afvalfonds.extract_pdf(af_pdf)
        (snap / "afvalfonds_recycling.csv").write_text(
            "materiaal,recycling_pct\n" + "\n".join(f"{r['materiaal']},{r['recycling_pct']}" for r in rows))
        af_csv = str(snap / "afvalfonds_recycling.csv")
    if lma_pdf:
        rows = lma_rws.extract_pdf(lma_pdf)
        (snap / "lma_rws.csv").write_text(
            "euralcode,verwerking,ton\n" + "\n".join(f"{r['euralcode']},{r['verwerking']},{r['ton']}" for r in rows))
        lma_csv = str(snap / "lma_rws.csv")

    telling = vul_database(con, cbs_rows=cbs_rows,
                           clo_csv=str(_FIX / "clo_huishoudelijk.csv"),
                           afvalfonds_csv=af_csv, lma_csv=lma_csv, opgehaald_op=today,
                           afvalfonds_jaar=db.get("afvalfonds_jaar", 2023),
                           lma_jaar=db.get("lma_jaar", 2022))
    print("Feiten per bron:", telling)
    n = forecast.bouw_forecasts(con, tot_jaar=db.get("forecast_tot_jaar", 2035))
    print(f"Forecast gebouwd voor {n} reeksen -> {db['db_path']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_ingest.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Draai de echte ingest éénmalig (online) en verifieer**

Run:
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab
python3 scripts/12_fetch_afval_bronnen.py
python3 -c "
import duckdb; c=duckdb.connect('/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb')
print('feiten:', c.execute('SELECT COUNT(*) FROM afval_feit').fetchone()[0])
print('bronnen:', [r[0] for r in c.execute('SELECT DISTINCT bron_id FROM afval_feit').fetchall()])
print('forecast-rijen:', c.execute('SELECT COUNT(*) FROM forecast').fetchone()[0])
print('voorbeeld PV24 GFT forecast:', c.execute(\"SELECT jaar,verwacht FROM forecast WHERE regio_code='PV24' AND afvalstroom_canoniek='GFT-afval' ORDER BY jaar DESC LIMIT 1\").fetchall())"
```
Expected: duizenden feiten; bronnen incl. `cbs-83558NED`, `clo-nl014437`, `afvalfonds-2023`, `lma-rws-2022`; forecast-rijen > 0 met een waarde voor 2035. Bij offline CBS: `ConnectorError` — later opnieuw; niet-blokkerend voor de commit.

- [ ] **Step 6: Commit**

```bash
git add scripts/12_fetch_afval_bronnen.py core/config.yaml requirements.txt tests/test_afvaldb_ingest.py
git commit -m "feat(afvaldb): ingest-script (alle bronnen -> DuckDB) + Holt-forecast + config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Service + API — forecast & verrijkte duiding-context

**Files:**
- Modify: `src/leefomgevinglab/usecases/afval/service.py`
- Modify: `src/leefomgevinglab/geluidsmeter/api.py`
- Test: `tests/test_afval_forecast_service.py`, `tests/test_api_afval_forecast.py`

**Interfaces:**
- Consumes: `afvaldb.store`.
- Produces:
  - `service.forecast(db_path, regio, afvalstroom) -> dict` — `{regio, afvalstroom, historie:[{jaar,hoeveelheid_kton}], forecast:[{jaar,verwacht,ondergrens,bovengrens}], methode:"holt", label}`.
  - `service.extra_context(db_path, afvalstroom) -> dict` — landelijke extra cijfers: `{recyclingpercentage: float|None, recycling_bron: str|None, per_inwoner: [{jaar,waarde}]|None}` uit DuckDB.
  - API: `GET /api/afval/forecast?regio=&afvalstroom=`; `POST /api/afval/duiding` reikt `forecast`-samenvatting + `extra` mee in `context`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_forecast_service.py
from leefomgevinglab.afvaldb import store
from leefomgevinglab.usecases.afval import service


def _db(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2018 + i,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 10.0 + i, "eenheid": "kton"} for i in range(3)])
    store.insert_forecasts(con, [
        {"regio_code": "PV24", "afvalstroom_canoniek": "GFT-afval", "jaar": 2030,
         "verwacht": 18.0, "ondergrens": 15.0, "bovengrens": 21.0, "methode": "holt"}])
    store.insert_feiten(con, [
        {"bron_id": "afvalfonds-2023", "regio_code": "NL", "jaar": 2023,
         "afvalstroom_canoniek": "Verpakkingsglas", "euralcode": None, "verwerking": "R",
         "indicator_type": "recyclingpercentage", "hoeveelheid": 86.0, "eenheid": "pct"}])
    con.close()
    return p


def test_forecast_historie_en_toekomst(tmp_path):
    p = _db(tmp_path)
    f = service.forecast(p, "PV24", "GFT-afval")
    assert [h["jaar"] for h in f["historie"]] == [2018, 2019, 2020]
    assert f["forecast"][0]["jaar"] == 2030 and f["forecast"][0]["verwacht"] == 18.0
    assert f["methode"] == "holt"


def test_extra_context_recyclingpercentage(tmp_path):
    p = _db(tmp_path)
    e = service.extra_context(p, "Verpakkingsglas")
    assert e["recyclingpercentage"] == 86.0
    assert "afvalfonds" in (e["recycling_bron"] or "").lower()
```

```python
# tests/test_api_afval_forecast.py
from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api


def _client(monkeypatch, tmp_path):
    api._config = {"leefomgevinglab": {"afval": {"data_dir": str(tmp_path)},
                                       "afvaldb": {"db_path": str(tmp_path / "afval.duckdb")},
                                       "llm": {"base_url": "x", "model": "m", "timeout_s": 1}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_forecast_endpoint(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(api.afval_service, "forecast",
                        lambda db_path, regio, afvalstroom:
                        {"regio": regio, "afvalstroom": afvalstroom, "historie": [],
                         "forecast": [{"jaar": 2035, "verwacht": 20.0, "ondergrens": 15.0, "bovengrens": 25.0}],
                         "methode": "holt", "label": "indicatief"})
    r = client.get("/api/afval/forecast", params={"regio": "PV24", "afvalstroom": "GFT-afval"})
    assert r.status_code == 200
    assert r.json()["forecast"][0]["jaar"] == 2035
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_forecast_service.py tests/test_api_afval_forecast.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'forecast'` / geen `/api/afval/forecast`.

- [ ] **Step 3: Write minimal implementation**

Voeg aan `src/leefomgevinglab/usecases/afval/service.py` toe (onderaan):

```python
from leefomgevinglab.afvaldb import store as _afvaldb_store

FORECAST_LABEL = "Indicatieve modelmatige extrapolatie (Holt) — geen beleidsprognose"


def forecast(db_path: str, regio: str, afvalstroom: str) -> dict:
    con = _afvaldb_store.open_db(db_path)
    try:
        reeks = _afvaldb_store.series(con, regio, afvalstroom, indicator_type="volume")
        fc = _afvaldb_store.forecast_rows(con, regio, afvalstroom)
    finally:
        con.close()
    return {
        "regio": regio, "afvalstroom": afvalstroom,
        "historie": [{"jaar": j, "hoeveelheid_kton": h} for j, h in reeks],
        "forecast": [{"jaar": r["jaar"], "verwacht": r["verwacht"],
                      "ondergrens": r["ondergrens"], "bovengrens": r["bovengrens"]} for r in fc],
        "methode": "holt", "label": FORECAST_LABEL,
    }


def extra_context(db_path: str, afvalstroom: str) -> dict:
    con = _afvaldb_store.open_db(db_path)
    try:
        rec = con.execute(
            "SELECT hoeveelheid, bron_id FROM afval_feit WHERE afvalstroom_canoniek = ? "
            "AND indicator_type = 'recyclingpercentage' ORDER BY jaar DESC LIMIT 1", [afvalstroom]).fetchone()
        pi = con.execute(
            "SELECT jaar, hoeveelheid FROM afval_feit WHERE afvalstroom_canoniek = ? "
            "AND indicator_type = 'per_inwoner' ORDER BY jaar", [afvalstroom]).fetchall()
    finally:
        con.close()
    return {
        "recyclingpercentage": float(rec[0]) if rec else None,
        "recycling_bron": rec[1] if rec else None,
        "per_inwoner": [{"jaar": int(j), "waarde": float(h)} for j, h in pi] or None,
    }
```

Voeg aan `src/leefomgevinglab/geluidsmeter/api.py` toe — een db-path-helper + de route, en verrijk `stroom_context`-gebruik in de duiding-route. Direct ná `_afval_data_dir()`:

```python
def _afvaldb_path() -> str:
    return _config.get("leefomgevinglab", {}).get("afvaldb", {}).get(
        "db_path", "/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb")


@app.get("/api/afval/forecast")
def api_afval_forecast(regio: str, afvalstroom: str):
    try:
        return afval_service.forecast(_afvaldb_path(), regio, afvalstroom)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-database nog niet gevuld")
```

Breid de bestaande `api_afval_duiding` uit: ná het bouwen van `ctx` en vóór de `duiding`-aanroep, verrijk `ctx` met forecast + extra cijfers (best-effort; faalt de DB, dan gewoon zonder):

```python
    try:
        fc = afval_service.forecast(_afvaldb_path(), req.regio, req.afvalstroom)
        ctx["forecast"] = fc["forecast"][-1] if fc["forecast"] else None
        ctx["extra"] = afval_service.extra_context(_afvaldb_path(), req.afvalstroom)
    except Exception:
        ctx["forecast"] = None
        ctx["extra"] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_forecast_service.py tests/test_api_afval_forecast.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/service.py src/leefomgevinglab/geluidsmeter/api.py tests/test_afval_forecast_service.py tests/test_api_afval_forecast.py
git commit -m "feat(afvaldb): forecast-service + /api/afval/forecast + verrijkte duiding-context

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: Frontend — forecast-grafiek + extra cijfers in de modal

**Files:**
- Modify: `src/leefomgevinglab/static/afval.html`

**Interfaces:**
- Consumes: `GET /api/afval/forecast`; `context.forecast` + `context.extra` uit de duiding-response.
- Produces: in de modal een inline-SVG-lijngrafiek (historie + forecast met band) en extra kerncijfers (recyclingpercentage, per-inwoner). Geen unit-test; live smoke-test.

- [ ] **Step 1: Voeg de grafiek + extra cijfers toe**

Voeg in `openDuiding()` (ná het renderen van `statsRows`) toe dat de forecast wordt opgehaald en getekend, en dat extra cijfers uit `d.context.extra` worden getoond. Voeg boven in het `<script>` een SVG-tekenfunctie toe:

```javascript
function forecastSVG(historie, forecast) {
  const H = historie.map(p => ({ x: p.jaar, y: p.hoeveelheid_kton }));
  const F = forecast.map(p => ({ x: p.jaar, y: p.verwacht, lo: p.ondergrens, hi: p.bovengrens }));
  const pts = H.concat(F.map(p => ({ x: p.x, y: p.y })));
  if (pts.length < 2) return "<p style='font-size:12px;color:#789'>Onvoldoende data voor een doorkijk.</p>";
  const W = 500, Hh = 160, pad = 30;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y).concat(F.map(p => p.hi));
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = 0, ymax = Math.max(...ys) * 1.1 || 1;
  const sx = x => pad + (x - xmin) / (xmax - xmin || 1) * (W - 2 * pad);
  const sy = y => Hh - pad - (y - ymin) / (ymax - ymin || 1) * (Hh - 2 * pad);
  const line = a => a.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
  let band = "";
  if (F.length) {
    const top = F.map(p => `${sx(p.x).toFixed(1)},${sy(p.hi).toFixed(1)}`);
    const bot = F.slice().reverse().map(p => `${sx(p.x).toFixed(1)},${sy(p.lo).toFixed(1)}`);
    band = `<polygon points="${top.concat(bot).join(" ")}" fill="#0b4f6c" opacity="0.12"/>`;
  }
  const fLine = F.length ? line([H[H.length - 1], ...F].map(p => ({ x: p.x, y: p.y }))) : "";
  return `<svg viewBox="0 0 ${W} ${Hh}" width="100%" style="margin-top:8px">
    ${band}
    <path d="${line(H)}" fill="none" stroke="#0b4f6c" stroke-width="2"/>
    <path d="${fLine}" fill="none" stroke="#0b4f6c" stroke-width="2" stroke-dasharray="5 4"/>
    <text x="${pad}" y="12" font-size="10" fill="#789">kton — historie (doorgetrokken) + doorkijk (streep) tot ${xmax}</text>
  </svg>`;
}
```

Breid `openDuiding(code, naam, afvalstroom)` uit: ná `document.getElementById("modalStats").innerHTML = statsRows(d.context || {});` voeg toe:

```javascript
  // extra cijfers uit landelijke bronnen
  const extra = (d.context && d.context.extra) || {};
  let extraHtml = "";
  if (extra.recyclingpercentage != null)
    extraHtml += `<dt>Recycling (NL)</dt><dd>${num(extra.recyclingpercentage, 0)}% — ${esc(extra.recycling_bron || "")}</dd>`;
  if (extra.per_inwoner && extra.per_inwoner.length)
    extraHtml += `<dt>Per inwoner (NL)</dt><dd>${num(extra.per_inwoner[extra.per_inwoner.length - 1].waarde, 0)} kg</dd>`;
  if (extraHtml) document.getElementById("modalStats").innerHTML += extraHtml;
  // doorkijk-grafiek
  try {
    const f = await (await fetch(`/api/afval/forecast?regio=${code}&afvalstroom=${encodeURIComponent(afvalstroom)}`)).json();
    document.getElementById("modalChart").innerHTML =
      forecastSVG(f.historie || [], f.forecast || []) +
      `<div style="font-size:10px;color:#789;margin-top:2px">${esc(f.label || "")}</div>`;
  } catch (e) { document.getElementById("modalChart").innerHTML = ""; }
```

Voeg in de modal-HTML (ná `<dl class="stats" id="modalStats"></dl>`) een container toe:
```html
    <div id="modalChart"></div>
```

- [ ] **Step 2: Live smoke-test (poort 8799; 8792 is bezet)**

Run:
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab
[ -d .venv ] && source .venv/bin/activate
uvicorn leefomgevinglab.geluidsmeter.api:app --host 127.0.0.1 --port 8799 --app-dir src &
sleep 4
curl -s "http://127.0.0.1:8799/api/afval/forecast?afvalstroom=GFT-afval&regio=PV24" | python3 -c "import sys,json; f=json.load(sys.stdin); print('historie:', len(f['historie']), '| forecast tot:', (f['forecast'][-1]['jaar'] if f['forecast'] else None), '| methode:', f['methode'])"
curl -s -o /dev/null -w "GET /afval -> %{http_code}\n" "http://127.0.0.1:8799/afval"
curl -s "http://127.0.0.1:8799/afval" | grep -c "forecastSVG"
kill %1
```
Expected: forecast met historie > 0 en een toekomstjaar (t/m 2035); `/afval` → 200; grep vindt `forecastSVG`. (Vereist dat Task 8 Step 5 de database vulde.)

- [ ] **Step 3: Commit**

```bash
git add src/leefomgevinglab/static/afval.html
git commit -m "feat(afvaldb): doorkijk-grafiek (historie+forecast band) + extra cijfers in modal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 11: Docs, duiding-prompt & volledige suite

**Files:**
- Modify: `src/leefomgevinglab/usecases/afval/duiding.py` (forecast + extra in de prompt)
- Modify: `CLAUDE.md` (sprintstatus)
- Test: hergebruik `tests/test_afval_duiding.py`

**Interfaces:**
- `duiding.build_prompt` benoemt de doorkijk (`context.forecast`) en extra cijfers (`context.extra`) als die aanwezig zijn.

- [ ] **Step 1: Uitbreiden build_prompt (test eerst)**

Voeg aan `tests/test_afval_duiding.py` een test toe:

```python
def test_build_prompt_neemt_forecast_en_extra_mee():
    ctx = dict(_CONTEXT)
    ctx["forecast"] = {"jaar": 2035, "verwacht": 20.0, "ondergrens": 15.0, "bovengrens": 25.0}
    ctx["extra"] = {"recyclingpercentage": 86.0, "recycling_bron": "afvalfonds-2023", "per_inwoner": None}
    p = d.build_prompt("Flevoland", "GFT-afval", 2020, ctx)
    assert "2035" in p and "20" in p           # doorkijk
    assert "86" in p                            # recyclingpercentage
    assert "doorkijk" in p.lower() or "extrapol" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_duiding.py::test_build_prompt_neemt_forecast_en_extra_mee -v`
Expected: FAIL (assertion op ontbrekende tekst).

- [ ] **Step 3: Breid build_prompt uit**

Voeg in `src/leefomgevinglab/usecases/afval/duiding.py`, in `build_prompt`, vóór de `body = "\n".join(regels)`-regel toe:

```python
    fc = c.get("forecast")
    if fc and fc.get("verwacht") is not None:
        regels.append(f"- Doorkijk (Holt-extrapolatie, indicatief) {fc['jaar']}: "
                      f"{round(fc['verwacht'], 1)} kton (band {round(fc['ondergrens'], 1)}–{round(fc['bovengrens'], 1)})")
    extra = c.get("extra") or {}
    if extra.get("recyclingpercentage") is not None:
        regels.append(f"- Landelijk recyclingpercentage: {round(extra['recyclingpercentage'], 0)}% "
                      f"(bron: {extra.get('recycling_bron')})")
    if extra.get("per_inwoner"):
        laatste = extra["per_inwoner"][-1]
        regels.append(f"- Landelijk per inwoner ({laatste['jaar']}): {round(laatste['waarde'], 0)} kg")
```

En pas de instructiezin uit `build_prompt` aan zodat de doorkijk benoemd wordt — vervang de bestaande openingszin door:

```python
        "Je bent een feitelijke data-assistent. Vat onderstaande cijfers over deze afvalstroom in "
        "3-5 zinnen begrijpelijk samen voor een burger: benoem hoe de provincie zich verhoudt tot het "
        "landelijk beeld, de meerjarentrend, het aandeel en de doorkijk (extrapolatie) naar de toekomst. "
        "Verzin niets; gebruik uitsluitend de gegeven getallen en achtergrond. Trek geen beleidsconclusies.\n\n"
```

- [ ] **Step 4: Voeg de sprintstatus toe aan CLAUDE.md**

Voeg onder "## Sprint status", na de UC-08-regel, toe:

```markdown
- 🚧 **UC-08b — Afvaldatabase & doorkijk:** DuckDB-database (`afvaldb/`) met canoniek datamodel (CBS↔AMICE: `afval_feit` + `afvalstroom_crosswalk`), gevuld uit CBS (live) + CLO/Afvalfonds/LMA (snapshot: pdfplumber of curated CSV) via `scripts/12_fetch_afval_bronnen.py`. Holt-forecast (`afvaldb/forecast.py`) → `/api/afval/forecast` + doorkijk-grafiek en extra cijfers in de modal. DB op `/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb`.
```

- [ ] **Step 5: Volledige afval-suite draaien**

Run:
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest \
  tests/test_afvaldb_store.py tests/test_afvaldb_crosswalk.py tests/test_afvaldb_loader_cbs.py \
  tests/test_afvaldb_loader_clo.py tests/test_afvaldb_loader_afvalfonds.py tests/test_afvaldb_loader_lma.py \
  tests/test_afvaldb_forecast.py tests/test_afvaldb_ingest.py tests/test_afval_forecast_service.py \
  tests/test_api_afval_forecast.py tests/test_afval_duiding.py tests/test_afval_service.py \
  tests/test_api_afval.py -q
```
Expected: alle tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/duiding.py CLAUDE.md tests/test_afval_duiding.py
git commit -m "feat(afvaldb): duiding benoemt doorkijk + extra cijfers; sprintstatus

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review (uitgevoerd)

**Spec-dekking:**
- §2 DuckDB + canoniek model (bron/afval_feit/crosswalk/forecast) → Task 1. ✓
- §2 crosswalk CBS↔AMICE → Task 2. ✓
- §4 vier bron-loaders (CBS live; CLO/Afvalfonds/LMA snapshot, pdfplumber+curated-CSV-fallback; rapportbronnen = NL) → Tasks 3–6 + ingest Task 8. ✓
- §5 Holt-forecast (zelf, band, horizon 2035, skip<5, klem op 0) → Task 7. ✓
- §6 API `/api/afval/forecast` + verrijkte duiding + modal-grafiek → Tasks 9–11. ✓
- §7 foutafhandeling (DB leeg → 503; forecast te kort → skip; Qwen offline behouden; best-effort verrijking) → Tasks 7/9. ✓
- §8 offline tests op fixtures/synthetische reeksen → alle Task-tests. ✓
- §9 herkomst (bron_id + bron-rij, licentie, labels) → Tasks 1/3–6/9. ✓
- §10 dependencies (pdfplumber toevoegen, duckdb installeren, geen statsmodels) → Task 8 + Global Constraints. ✓

**Placeholder-scan:** geen TBD/TODO; alle code-stappen bevatten volledige code. Config-waarden (PDF-paden leeg → curated CSV) zijn bewuste defaults, geen code-placeholders.

**Type-consistentie:** `afval_feit`-kolommen identiek in store/loaders/tests; `series()`/`forecast_rows()`/`insert_*`-signaturen komen overeen tussen Task 1 (definitie) en Tasks 7/9 (gebruik); `canoniek(bron_type, bron_sleutel)` consistent in Tasks 2/5/6; `forecast()`/`extra_context()`-vormen komen overeen tussen Task 9 (definitie) en Tasks 10/11 (gebruik). `context.forecast` = laatste forecast-punt (dict), `context.extra` = extra_context-dict — consistent gebruikt in api (Task 9), frontend (Task 10) en prompt (Task 11).
