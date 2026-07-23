# Afval — brondata-uitleg & data-chatbot (NL→SQL) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een linkerpaneel in `/afval` met een brondata-uitleg (uit de `bron`-tabel) en een data-chatbot die natuurlijke-taalvragen via de lokale Qwen naar een read-only DuckDB `SELECT` vertaalt, valideert, uitvoert en samenvat.

**Architecture:** Store-helpers voor read-only queries + bron-lijst; een chat-module (`usecases/afval/chat.py`) met SQL-validatie, dynamische grounding uit de DB, NL→SQL en samenvatting via Qwen (twee calls) met een conservatief contract dat het `datavraag`-patroon spiegelt; twee routes; en een driekoloms frontend.

**Tech Stack:** Python 3.10, DuckDB (read-only), httpx, FastAPI, lokale Qwen (`/chat/completions`), MapLibre/HTML.

## Global Constraints

- Testrunner: **`python3 -m pytest`** vanuit repo-root (`tests/conftest.py` zet `src/` op het pad; `duckdb` geïnstalleerd).
- DuckDB-bestand: **`/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb`** (via config `leefomgevinglab.afvaldb.db_path`).
- **Alleen lezen:** de chatbot opent DuckDB met `read_only=True`. Naast read-only geldt een SQL-guard: precies één statement, moet met `select`/`with` beginnen, geen `;`, verboden trefwoorden geweigerd, `LIMIT` afgedwongen (max 200).
- Verboden trefwoorden (woordgrens, case-insensitief): `insert, update, delete, drop, alter, create, attach, copy, pragma, install`.
- Conservatief contract voor de chat (spiegelt `usecases/datavraag`): keys `vraag, antwoord, sql, rijen, beschikbaar, disclaimer, vangnet, bron`.
- Provincie-map (geverifieerd, authoritatief): `PV20`=Groningen, `PV21`=Fryslân, `PV22`=Drenthe, `PV23`=Overijssel, `PV24`=Flevoland, `PV25`=Gelderland, `PV26`=Utrecht, `PV27`=Noord-Holland, `PV28`=Zuid-Holland, `PV29`=Zeeland, `PV30`=Noord-Brabant, `PV31`=Limburg.
- LLM-config uit `_config["leefomgevinglab"]["llm"]` (base_url default `http://localhost:8080/v1`, model `qwen2.5-32b`, timeout 60).
- Server-strings in de frontend via `textContent`/escaping (geen raw innerHTML van bron-/antwoord-/SQL-velden).
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Vaste feiten (geverifieerd 2026-07-23)

- `duckdb.connect(path, read_only=True)` → een `DELETE`/mutatie werpt `duckdb.InvalidInputException`; `SELECT` werkt. De live DB heeft 3012 feiten, 4 bronnen, 910 forecast-rijen.
- `bron`-tabel kolommen: `bron_id, naam, url, licentie, type, opgehaald_op`.
- `afval_feit`-kolommen: `bron_id, regio_code, jaar, afvalstroom_canoniek, euralcode, verwerking, indicator_type, hoeveelheid, eenheid`.
- Bestaande store: `leefomgevinglab.afvaldb.store` (`open_db`, `insert_feiten`, `insert_bron`/`upsert_bron`, `series`, `forecast_rows`).
- api.py heeft al `_afvaldb_path()`, `afval_service`, `afval_duiding`, `HTTPException`, `BaseModel`, `Path`, `ConnectorError`, en `_config`.

## File Structure

- Modify: `src/leefomgevinglab/afvaldb/store.py` — `bronnen(con)`, `open_readonly(db_path)`, `run_select(con, sql)`.
- Create: `src/leefomgevinglab/usecases/afval/chat.py` — `OngeldigeSQL`, `valideer_sql`, `PROVINCIE_NAMEN`, `bouw_grounding`, `genereer_sql`, `vat_samen`, `beantwoord`, constanten.
- Modify: `src/leefomgevinglab/geluidsmeter/api.py` — `GET /api/afval/bronnen`, `POST /api/afval/chat`.
- Modify: `src/leefomgevinglab/static/afval.html` — driekoloms layout + brondata-paneel + chatbot.
- Modify: `CLAUDE.md` — sprintstatus.
- Test: `tests/test_afvaldb_store_select.py`, `tests/test_afval_chat_validatie.py`, `tests/test_afval_chat_grounding.py`, `tests/test_afval_chat.py`, `tests/test_api_afval_chat.py`.

---

### Task 1: Store — read-only helpers + bron-lijst

**Files:**
- Modify: `src/leefomgevinglab/afvaldb/store.py`
- Test: `tests/test_afvaldb_store_select.py`

**Interfaces:**
- Consumes: bestaande `store.open_db`, `insert_feiten`, `upsert_bron`.
- Produces:
  - `bronnen(con) -> list[dict]` — rijen `{bron_id, naam, url, licentie, type, opgehaald_op}` (opgehaald_op als string), gesorteerd op `bron_id`.
  - `open_readonly(db_path: str)` — `duckdb.connect(db_path, read_only=True)`.
  - `run_select(con, sql: str) -> list[dict]` — voert `sql` uit, geeft rijen als dicts (kolomnamen uit `con.description`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afvaldb_store_select.py
import duckdb
import pytest
from leefomgevinglab.afvaldb import store


def _seed(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.upsert_bron(con, {"bron_id": "cbs-83558NED", "naam": "CBS", "url": "u",
                            "licentie": "CC-BY 4.0", "type": "api", "opgehaald_op": "2026-07-23"})
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"}])
    con.close()
    return p


def test_bronnen(tmp_path):
    p = _seed(tmp_path)
    con = store.open_db(p)
    b = store.bronnen(con)
    assert b[0]["bron_id"] == "cbs-83558NED"
    assert b[0]["licentie"] == "CC-BY 4.0"
    assert set(b[0]) == {"bron_id", "naam", "url", "licentie", "type", "opgehaald_op"}


def test_run_select_geeft_dicts(tmp_path):
    p = _seed(tmp_path)
    con = store.open_readonly(p)
    rijen = store.run_select(con, "SELECT regio_code, hoeveelheid FROM afval_feit")
    assert rijen == [{"regio_code": "PV24", "hoeveelheid": 12.0}]


def test_open_readonly_weigert_schrijven(tmp_path):
    p = _seed(tmp_path)
    con = store.open_readonly(p)
    with pytest.raises(duckdb.Error):
        con.execute("DELETE FROM afval_feit")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_store_select.py -v`
Expected: FAIL — `AttributeError: module ...store has no attribute 'bronnen'`.

- [ ] **Step 3: Write minimal implementation**

Voeg aan het eind van `src/leefomgevinglab/afvaldb/store.py` toe:

```python
def open_readonly(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def bronnen(con) -> list[dict]:
    cols = ["bron_id", "naam", "url", "licentie", "type", "opgehaald_op"]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM bron ORDER BY bron_id").fetchall()
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["opgehaald_op"] = None if d["opgehaald_op"] is None else str(d["opgehaald_op"])
        out.append(d)
    return out


def run_select(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afvaldb_store_select.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/afvaldb/store.py tests/test_afvaldb_store_select.py
git commit -m "feat(afvaldb): store read-only helpers (open_readonly/run_select) + bronnen-lijst

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: SQL-validatie (security-guard)

**Files:**
- Create: `src/leefomgevinglab/usecases/afval/chat.py`
- Test: `tests/test_afval_chat_validatie.py`

**Interfaces:**
- Produces:
  - `class OngeldigeSQL(Exception)`.
  - `valideer_sql(sql: str) -> str` — geeft opgeschoonde SQL met afgedwongen `LIMIT`; werpt `OngeldigeSQL` bij ongeldige/gevaarlijke input.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_chat_validatie.py
import pytest
from leefomgevinglab.usecases.afval import chat


def test_select_krijgt_limit():
    out = chat.valideer_sql("SELECT * FROM afval_feit")
    assert out.lower().endswith("limit 200")


def test_bestaande_limit_te_hoog_wordt_verlaagd():
    out = chat.valideer_sql("SELECT * FROM afval_feit LIMIT 9999")
    assert "200" in out and "9999" not in out


def test_with_is_toegestaan():
    out = chat.valideer_sql("WITH x AS (SELECT 1 AS n) SELECT n FROM x")
    assert out.lower().startswith("with")


def test_trailing_semicolon_gestript():
    out = chat.valideer_sql("SELECT 1 AS n;")
    assert ";" not in out


@pytest.mark.parametrize("bad", [
    "DELETE FROM afval_feit",
    "DROP TABLE afval_feit",
    "INSERT INTO afval_feit VALUES (1)",
    "UPDATE afval_feit SET jaar=0",
    "ATTACH 'x.db'",
    "COPY afval_feit TO 'out.csv'",
    "PRAGMA database_list",
    "SELECT 1; DROP TABLE afval_feit",
    "CREATE TABLE t (x int)",
])
def test_gevaarlijke_sql_wordt_geweigerd(bad):
    with pytest.raises(chat.OngeldigeSQL):
        chat.valideer_sql(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_chat_validatie.py -v`
Expected: FAIL — `ModuleNotFoundError: ...afval.chat`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/leefomgevinglab/usecases/afval/chat.py
"""Afval data-chatbot: NL-vraag -> read-only DuckDB SELECT -> samenvatting.

Conservatief contract (spiegelt usecases/datavraag). Read-only + SQL-guard.
"""
import re

_VERBODEN = ("insert", "update", "delete", "drop", "alter", "create",
             "attach", "copy", "pragma", "install")
_MAX_LIMIT = 200


class OngeldigeSQL(Exception):
    """De gegenereerde SQL is leeg, geen enkele SELECT, of bevat verboden constructies."""


def valideer_sql(sql: str) -> str:
    s = (sql or "").strip()
    while s.endswith(";"):
        s = s[:-1].strip()
    if not s:
        raise OngeldigeSQL("lege query")
    if ";" in s:
        raise OngeldigeSQL("meerdere statements niet toegestaan")
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise OngeldigeSQL("alleen SELECT/WITH toegestaan")
    for kw in _VERBODEN:
        if re.search(rf"\b{kw}\b", low):
            raise OngeldigeSQL(f"verboden trefwoord: {kw}")
    m = re.search(r"\blimit\s+(\d+)\b", low)
    if m:
        if int(m.group(1)) > _MAX_LIMIT:
            s = re.sub(r"\blimit\s+\d+\b", f"LIMIT {_MAX_LIMIT}", s, flags=re.IGNORECASE)
    else:
        s = f"{s} LIMIT {_MAX_LIMIT}"
    return s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_chat_validatie.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/chat.py tests/test_afval_chat_validatie.py
git commit -m "feat(afval-chat): SQL-validatie (SELECT-only, verboden trefwoorden, LIMIT-guard)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Grounding + provincie-map

**Files:**
- Modify: `src/leefomgevinglab/usecases/afval/chat.py`
- Test: `tests/test_afval_chat_grounding.py`

**Interfaces:**
- Consumes: een DuckDB-connectie (leest distinct-waarden uit `afval_feit`).
- Produces:
  - `PROVINCIE_NAMEN: dict[str, str]` — de 12 geverifieerde codes→namen.
  - `bouw_grounding(con) -> str` — schema-beschrijving + distinct afvalstromen/regio's/indicator_types/bron_ids + jaar-bereik + provincie-map + instructie "uitsluitend één SELECT".

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_chat_grounding.py
from leefomgevinglab.afvaldb import store
from leefomgevinglab.usecases.afval import chat


def test_provincie_map_volledig():
    assert chat.PROVINCIE_NAMEN["PV24"] == "Flevoland"
    assert chat.PROVINCIE_NAMEN["PV28"] == "Zuid-Holland"
    assert len(chat.PROVINCIE_NAMEN) == 12


def test_bouw_grounding_bevat_schema_en_distinct(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"}])
    g = chat.bouw_grounding(con)
    assert "afval_feit" in g and "forecast" in g
    assert "GFT-afval" in g              # distinct afvalstroom
    assert "cbs-83558NED" in g           # distinct bron
    assert "Flevoland" in g              # provincie-map
    assert "2020" in g                   # jaar-bereik
    assert "select" in g.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_chat_grounding.py -v`
Expected: FAIL — `AttributeError: module ...chat has no attribute 'PROVINCIE_NAMEN'`.

- [ ] **Step 3: Write minimal implementation**

Voeg aan `src/leefomgevinglab/usecases/afval/chat.py` toe (na `valideer_sql`):

```python
PROVINCIE_NAMEN = {
    "PV20": "Groningen", "PV21": "Fryslân", "PV22": "Drenthe", "PV23": "Overijssel",
    "PV24": "Flevoland", "PV25": "Gelderland", "PV26": "Utrecht", "PV27": "Noord-Holland",
    "PV28": "Zuid-Holland", "PV29": "Zeeland", "PV30": "Noord-Brabant", "PV31": "Limburg",
}


def bouw_grounding(con) -> str:
    def distinct(kolom):
        return [r[0] for r in con.execute(
            f"SELECT DISTINCT {kolom} FROM afval_feit ORDER BY 1").fetchall()]
    stromen = distinct("afvalstroom_canoniek")
    regios = distinct("regio_code")
    indicatoren = distinct("indicator_type")
    bron_ids = distinct("bron_id")
    jmin, jmax = con.execute("SELECT MIN(jaar), MAX(jaar) FROM afval_feit").fetchone()
    prov = ", ".join(f"{c}={n}" for c, n in PROVINCIE_NAMEN.items())
    return (
        "Je genereert precies één DuckDB SQL SELECT over onderstaande database.\n"
        "Tabel afval_feit(bron_id, regio_code, jaar, afvalstroom_canoniek, euralcode, "
        "verwerking, indicator_type, hoeveelheid, eenheid).\n"
        "Tabel forecast(regio_code, afvalstroom_canoniek, jaar, verwacht, ondergrens, "
        "bovengrens, methode).\n"
        f"regio_code is 'NL' of een provinciecode. Provincies: {prov}.\n"
        f"afvalstroom_canoniek in: {stromen}.\n"
        f"regio_code-waarden aanwezig: {regios}.\n"
        f"indicator_type in: {indicatoren} (volume in kton of ton; recyclingpercentage in "
        "pct; per_inwoner in kg per inwoner).\n"
        f"bron_id in: {bron_ids}. jaar loopt van {jmin} t/m {jmax}.\n"
        "Geef UITSLUITEND de SELECT-query terug: geen uitleg, geen puntkomma, geen ```-fences."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_chat_grounding.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/chat.py tests/test_afval_chat_grounding.py
git commit -m "feat(afval-chat): dynamische grounding uit de DB + provincie-map

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Chatbot — genereer_sql, vat_samen, beantwoord

**Files:**
- Modify: `src/leefomgevinglab/usecases/afval/chat.py`
- Test: `tests/test_afval_chat.py`

**Interfaces:**
- Consumes: `valideer_sql`, `bouw_grounding`, `OngeldigeSQL`, `store.open_readonly`, `store.run_select`; `ConnectorError`.
- Produces:
  - `genereer_sql(vraag, grounding, llm_base_url, model, timeout_s=60.0) -> str` — één Qwen-call, strip code-fences; `ConnectorError` bij LLM-fout.
  - `vat_samen(vraag, rijen, llm_base_url, model, timeout_s=60.0) -> str` — Qwen vat de rijen samen; `ConnectorError` bij fout.
  - `beantwoord(vraag, db_path, llm_base_url, model, timeout_s=60.0) -> dict` — contract `{vraag, antwoord, sql, rijen, beschikbaar, disclaimer, vangnet, bron}`.
  - constanten `DISCLAIMER`, `VANGNET`, `BRON`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_afval_chat.py
from leefomgevinglab.afvaldb import store
from leefomgevinglab.usecases.afval import chat


def _db(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"}])
    con.close()
    return p


def test_beantwoord_happy(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "SELECT hoeveelheid FROM afval_feit")
    monkeypatch.setattr(chat, "vat_samen",
                        lambda vraag, rijen, **kw: "In 2020 was het 12 kton.")
    out = chat.beantwoord("hoeveel GFT in Flevoland 2020?", p,
                          llm_base_url="x", model="m")
    assert out["beschikbaar"] is True
    assert out["rijen"] == [{"hoeveelheid": 12.0}]
    assert out["antwoord"] == "In 2020 was het 12 kton."
    assert "limit 200" in out["sql"].lower()   # LIMIT afgedwongen
    assert "disclaimer" in out and "bron" in out


def test_beantwoord_gevaarlijke_sql_niet_uitgevoerd(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "DROP TABLE afval_feit")
    out = chat.beantwoord("verwijder alles", p, llm_base_url="x", model="m")
    assert out["beschikbaar"] is False
    assert out["rijen"] == []
    # DB is intact
    con = store.open_db(p)
    assert con.execute("SELECT COUNT(*) FROM afval_feit").fetchone()[0] == 1


def test_beantwoord_lege_resultaten(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "SELECT * FROM afval_feit WHERE jaar=1900")
    out = chat.beantwoord("iets", p, llm_base_url="x", model="m")
    assert out["beschikbaar"] is True and out["rijen"] == []
    assert "geen resultaten" in out["antwoord"].lower()


def test_beantwoord_db_afwezig(tmp_path):
    out = chat.beantwoord("iets", str(tmp_path / "bestaat_niet.duckdb"),
                          llm_base_url="x", model="m")
    assert out["beschikbaar"] is False
    assert out["antwoord"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_chat.py -v`
Expected: FAIL — `AttributeError: module ...chat has no attribute 'beantwoord'`.

- [ ] **Step 3: Write minimal implementation**

Voeg boven in `chat.py` bij de imports toe:
```python
from pathlib import Path

import httpx

from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.afvaldb import store
```

Voeg aan het eind van `chat.py` toe:

```python
DISCLAIMER = ("Indicatief; open cijfers als proxy voor het gesloten LMA/AMICE, geen officieel cijfer.")
VANGNET = "Raadpleeg de bronhouder (CBS, Afvalfonds, RWS/LMA) voor officiele cijfers."
BRON = "Afvaldatabase: CBS 83558NED, CLO, Afvalfonds, LMA/RWS (open bronnen)."


def _chat(prompt: str, llm_base_url: str, model: str, timeout_s: float) -> str:
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.0},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("AI tijdelijk niet beschikbaar") from exc


def genereer_sql(vraag: str, grounding: str, llm_base_url: str, model: str,
                 timeout_s: float = 60.0) -> str:
    tekst = _chat(f"{grounding}\n\nVraag: {vraag}\nSQL:", llm_base_url, model, timeout_s)
    tekst = tekst.strip()
    if tekst.startswith("```"):
        tekst = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", tekst).strip()
    return tekst


def vat_samen(vraag: str, rijen: list[dict], llm_base_url: str, model: str,
              timeout_s: float = 60.0) -> str:
    prompt = (
        "Je bent een feitelijke data-assistent. Beantwoord de vraag in 2-3 zinnen op basis van "
        "UITSLUITEND de gegeven queryresultaten. Verzin niets; noem concrete getallen. Geen beleidsoordeel.\n\n"
        f"Vraag: {vraag}\nResultaten (JSON): {rijen}"
    )
    return _chat(prompt, llm_base_url, model, timeout_s)


def beantwoord(vraag: str, db_path: str, llm_base_url: str, model: str,
               timeout_s: float = 60.0) -> dict:
    base = {"vraag": vraag, "disclaimer": DISCLAIMER, "vangnet": VANGNET, "bron": BRON}
    if not Path(db_path).exists():
        return {**base, "antwoord": None, "sql": None, "rijen": [], "beschikbaar": False}
    con = store.open_readonly(db_path)
    try:
        grounding = bouw_grounding(con)
        try:
            ruwe = genereer_sql(vraag, grounding, llm_base_url=llm_base_url, model=model, timeout_s=timeout_s)
        except ConnectorError:
            return {**base, "antwoord": "AI tijdelijk niet beschikbaar.", "sql": None, "rijen": [], "beschikbaar": False}
        try:
            sql = valideer_sql(ruwe)
        except OngeldigeSQL:
            return {**base, "antwoord": "Deze vraag kon niet veilig naar een query worden vertaald.",
                    "sql": ruwe, "rijen": [], "beschikbaar": False}
        try:
            rijen = store.run_select(con, sql)
        except Exception:
            return {**base, "antwoord": "De query kon niet worden uitgevoerd.", "sql": sql,
                    "rijen": [], "beschikbaar": False}
    finally:
        con.close()
    if not rijen:
        return {**base, "antwoord": "Geen resultaten voor deze vraag.", "sql": sql, "rijen": [], "beschikbaar": True}
    try:
        antwoord = vat_samen(vraag, rijen, llm_base_url=llm_base_url, model=model, timeout_s=timeout_s)
    except ConnectorError:
        antwoord = f"{len(rijen)} resultaten (AI-samenvatting tijdelijk niet beschikbaar)."
    return {**base, "antwoord": antwoord, "sql": sql, "rijen": rijen, "beschikbaar": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_afval_chat.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/afval/chat.py tests/test_afval_chat.py
git commit -m "feat(afval-chat): NL->SQL + samenvatting met conservatief contract (read-only)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Routes — /api/afval/bronnen + /api/afval/chat

**Files:**
- Modify: `src/leefomgevinglab/geluidsmeter/api.py`
- Test: `tests/test_api_afval_chat.py`

**Interfaces:**
- Consumes: `store.open_readonly`/`store.bronnen`, `chat.beantwoord`, `_afvaldb_path()`, `_config`.
- Produces:
  - `GET /api/afval/bronnen` → `list[{...bron..., omschrijving}]`; 503 als DB-file ontbreekt.
  - `POST /api/afval/chat` (body `AfvalChatRequest{vraag: str}`) → `chat.beantwoord(...)`-contract.
  - module-imports `from leefomgevinglab.usecases.afval import chat as afval_chat` en `from leefomgevinglab.afvaldb import store as afvaldb_store`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_afval_chat.py
from fastapi.testclient import TestClient
import leefomgevinglab.geluidsmeter.api as api


def _client(monkeypatch, tmp_path):
    api._config = {"leefomgevinglab": {
        "afvaldb": {"db_path": str(tmp_path / "afval.duckdb")},
        "llm": {"base_url": "x", "model": "m", "timeout_s": 1}}}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_bronnen_ok(monkeypatch, tmp_path):
    (tmp_path / "afval.duckdb").touch()
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(api.afvaldb_store, "open_readonly", lambda p: "CON")
    monkeypatch.setattr(api.afvaldb_store, "bronnen",
                        lambda con: [{"bron_id": "cbs-83558NED", "naam": "CBS", "url": "u",
                                      "licentie": "CC-BY 4.0", "type": "api", "opgehaald_op": "2026-07-23"}])
    r = client.get("/api/afval/bronnen")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["bron_id"] == "cbs-83558NED"
    assert "omschrijving" in body[0] and body[0]["omschrijving"]


def test_bronnen_db_absent_503(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    r = client.get("/api/afval/bronnen")
    assert r.status_code == 503


def test_chat_route(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(api.afval_chat, "beantwoord",
                        lambda vraag, db_path, **kw:
                        {"vraag": vraag, "antwoord": "ok", "sql": "SELECT 1 LIMIT 200",
                         "rijen": [], "beschikbaar": True, "disclaimer": "d", "vangnet": "v", "bron": "b"})
    r = client.post("/api/afval/chat", json={"vraag": "hoeveel GFT?"})
    assert r.status_code == 200
    assert r.json()["antwoord"] == "ok"
    assert r.json()["sql"] == "SELECT 1 LIMIT 200"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_api_afval_chat.py -v`
Expected: FAIL — `AttributeError: module ...api has no attribute 'afval_chat'`.

- [ ] **Step 3: Write minimal implementation**

Voeg bij de imports in `api.py` (bij de andere afval-imports, rond regel 45) toe:
```python
from leefomgevinglab.usecases.afval import chat as afval_chat
from leefomgevinglab.afvaldb import store as afvaldb_store
```

Voeg onderaan `api.py` toe:

```python
_AFVAL_BRON_OMSCHRIJVING = {
    "cbs-": "Gemeentelijke afvalstoffen per provincie en jaar (CBS StatLine 83558NED).",
    "clo-": "Huishoudelijk afval per inwoner, lange tijdreeks (Compendium voor de Leefomgeving).",
    "afvalfonds-": "Recyclingpercentages per verpakkingsmateriaal (Afvalfonds Verpakkingen/Verpact).",
    "lma-rws-": "Nationale afvalcijfers per Euralcode en verwerking (LMA/RWS, openbaar).",
}


def _afval_bron_omschrijving(bron_id: str) -> str:
    for prefix, tekst in _AFVAL_BRON_OMSCHRIJVING.items():
        if bron_id.startswith(prefix):
            return tekst
    return ""


@app.get("/api/afval/bronnen")
def api_afval_bronnen():
    if not Path(_afvaldb_path()).exists():
        raise HTTPException(status_code=503, detail="Afval-database nog niet gevuld")
    con = afvaldb_store.open_readonly(_afvaldb_path())
    try:
        rows = afvaldb_store.bronnen(con)
    finally:
        if hasattr(con, "close"):
            con.close()
    for r in rows:
        r["omschrijving"] = _afval_bron_omschrijving(r["bron_id"])
    return rows


class AfvalChatRequest(BaseModel):
    vraag: str


@app.post("/api/afval/chat")
def api_afval_chat(req: AfvalChatRequest):
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    return afval_chat.beantwoord(
        req.vraag, _afvaldb_path(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"),
        timeout_s=llm.get("timeout_s", 60),
    )
```

*(Noot: de test monkeypatcht `open_readonly` naar een stub die geen `.close()` heeft; de `hasattr(con, "close")`-guard voorkomt dat de stub crasht.)*

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest tests/test_api_afval_chat.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/geluidsmeter/api.py tests/test_api_afval_chat.py
git commit -m "feat(afval-chat): routes /api/afval/bronnen + /api/afval/chat

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Frontend — driekoloms layout + brondata + chatbot

**Files:**
- Modify: `src/leefomgevinglab/static/afval.html`

**Interfaces:**
- Consumes: `GET /api/afval/bronnen`, `POST /api/afval/chat`.
- Produces: linkerpaneel met brondata-lijst en chatbot; driekoloms layout. Geen unit-test; live smoke-test.

- [ ] **Step 1: Voeg CSS voor de driekoloms layout + linkerpaneel toe**

Vervang in `src/leefomgevinglab/static/afval.html` de regel:
```css
  .wrap { display: flex; height: calc(100vh - 62px); }
```
door:
```css
  .wrap { display: flex; height: calc(100vh - 62px); }
  aside.left { width: 300px; padding: 14px; box-sizing: border-box; overflow-y: auto; border-right: 1px solid #ddd; display: flex; flex-direction: column; }
  aside.left h2 { font-size: 13px; margin: 0 0 6px; color: #0b4f6c; }
  .bronitem { font-size: 12px; margin-bottom: 8px; }
  .bronitem .lic { color: #789; }
  .chat { margin-top: 14px; display: flex; flex-direction: column; flex: 1; min-height: 220px; }
  #chatlog { flex: 1; overflow-y: auto; border: 1px solid #e3e3e3; border-radius: 6px; padding: 8px; font-size: 13px; background: #fafcfd; }
  #chatlog .q { font-weight: 600; margin-top: 8px; }
  #chatlog .a { white-space: pre-wrap; margin: 2px 0 4px; }
  #chatlog details { font-size: 11px; color: #789; }
  #chatlog pre { white-space: pre-wrap; background: #eef3f5; padding: 6px; border-radius: 4px; }
  .chatbar { display: flex; gap: 6px; margin-top: 8px; }
  .chatbar input { flex: 1; padding: 6px; }
  @media (max-width: 900px) { .wrap { flex-direction: column; height: auto; } aside.left, aside { width: auto; } #map { height: 60vh; } }
```

- [ ] **Step 2: Voeg het linkerpaneel-HTML toe**

Vervang in `afval.html`:
```html
<div class="wrap">
  <div id="map"></div>
```
door:
```html
<div class="wrap">
  <aside class="left">
    <h2>Brondata</h2>
    <div style="font-size:12px;color:#789;margin-bottom:8px">Deze cijfers komen uit open bronnen:</div>
    <div id="bronnen">Laden…</div>
    <div class="chat">
      <h2>Vraag het de data</h2>
      <div id="chatlog"></div>
      <div class="chatbar">
        <input id="chatinput" placeholder="bijv. hoeveel GFT in Flevoland in 2020?" />
        <button id="chatsend">Vraag</button>
      </div>
    </div>
  </aside>
  <div id="map"></div>
```

- [ ] **Step 3: Voeg de JS voor brondata + chat toe**

Voeg vlak vóór `map.on("load", loadMeta);` (onderaan het script) toe:

```javascript
async function laadBronnen() {
  const box = document.getElementById("bronnen");
  try {
    const bronnen = await (await fetch("/api/afval/bronnen")).json();
    box.innerHTML = "";
    bronnen.forEach(b => {
      const d = document.createElement("div");
      d.className = "bronitem";
      const naam = document.createElement("b"); naam.textContent = b.naam;
      const oms = document.createElement("div"); oms.textContent = b.omschrijving || "";
      const lic = document.createElement("div"); lic.className = "lic";
      lic.textContent = `Licentie: ${b.licentie} · ${b.type}`;
      d.appendChild(naam); d.appendChild(oms); d.appendChild(lic);
      if (b.url) {
        const a = document.createElement("a");
        a.href = b.url; a.target = "_blank"; a.rel = "noopener";
        a.textContent = "bron ↗"; a.style.fontSize = "11px";
        d.appendChild(a);
      }
      box.appendChild(d);
    });
  } catch (e) { box.textContent = "Brondata niet beschikbaar."; }
}

async function stelVraag() {
  const inp = document.getElementById("chatinput");
  const vraag = inp.value.trim();
  if (!vraag) return;
  const log = document.getElementById("chatlog");
  const q = document.createElement("div"); q.className = "q"; q.textContent = "▸ " + vraag;
  const a = document.createElement("div"); a.className = "a"; a.textContent = "denkt na…";
  log.appendChild(q); log.appendChild(a); log.scrollTop = log.scrollHeight;
  inp.value = "";
  try {
    const r = await fetch("/api/afval/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vraag })
    });
    const d = await r.json();
    a.textContent = d.antwoord || "Geen antwoord.";
    if (d.sql) {
      const det = document.createElement("details");
      const sum = document.createElement("summary"); sum.textContent = "toon query";
      const pre = document.createElement("pre"); pre.textContent = d.sql;
      det.appendChild(sum); det.appendChild(pre);
      log.insertBefore(det, a.nextSibling);
    }
    if (!d.beschikbaar && d.vangnet) {
      const v = document.createElement("div"); v.className = "lic"; v.style.fontSize = "11px";
      v.textContent = d.vangnet; log.appendChild(v);
    }
  } catch (e) { a.textContent = "Chatbot tijdelijk niet beschikbaar."; }
  log.scrollTop = log.scrollHeight;
}

document.getElementById("chatsend").addEventListener("click", stelVraag);
document.getElementById("chatinput").addEventListener("keydown", e => { if (e.key === "Enter") stelVraag(); });
laadBronnen();
```

- [ ] **Step 4: Live smoke-test (poort 8799; 8792 is bezet)**

Run:
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab
[ -d .venv ] && source .venv/bin/activate
uvicorn leefomgevinglab.geluidsmeter.api:app --host 127.0.0.1 --port 8799 --app-dir src &
sleep 4
curl -s "http://127.0.0.1:8799/api/afval/bronnen" | python3 -c "import sys,json; b=json.load(sys.stdin); print('bronnen:', [x['bron_id'] for x in b]); print('omschrijving[0]:', b[0]['omschrijving'][:40])"
curl -s -o /dev/null -w "GET /afval -> %{http_code}\n" "http://127.0.0.1:8799/afval"
curl -s "http://127.0.0.1:8799/afval" | grep -c "stelVraag"
kill %1
```
Expected: 4 bronnen met omschrijving; `/afval` → 200; grep vindt `stelVraag`. *(Een echte chat-vraag vereist dat de Qwen-server op 8080 draait; dat is optioneel voor deze smoke-test.)*

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/static/afval.html
git commit -m "feat(afval-chat): linkerpaneel met brondata-uitleg + data-chatbot

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Docs + volledige suite

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Voeg de sprintstatus toe aan CLAUDE.md**

Voeg onder "## Sprint status", na de UC-08b-regel, toe:
```markdown
- 🚧 **UC-08c — Brondata & data-chatbot:** linkerpaneel op `/afval` met brondata-uitleg (`GET /api/afval/bronnen`) en een NL→SQL-chatbot (`POST /api/afval/chat`, `usecases/afval/chat.py`) die read-only DuckDB-SELECT's genereert (Qwen), valideert (SELECT-only, verboden trefwoorden, LIMIT) en samenvat. Toont de uitgevoerde SQL + bron/disclaimer.
```

- [ ] **Step 2: Volledige afval-suite draaien**

Run:
```bash
cd /mnt/nvme/workspaces/LeefomgevingLab && python3 -m pytest \
  tests/test_afvaldb_store_select.py tests/test_afval_chat_validatie.py tests/test_afval_chat_grounding.py \
  tests/test_afval_chat.py tests/test_api_afval_chat.py tests/test_afvaldb_store.py \
  tests/test_api_afval_forecast.py tests/test_afval_service.py tests/test_api_afval.py -q
```
Expected: alle tests PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(afval-chat): sprintstatus brondata + data-chatbot

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review (uitgevoerd)

**Spec-dekking:**
- §2 driekoloms layout + linkerpaneel → Task 6. ✓
- §3.1 `/api/afval/bronnen` + `bronnen(con)` + omschrijving → Task 1 (store) + Task 5 (route/omschrijving). ✓
- §3.2 chat-module (grounding, NL→SQL, validatie, run_select, samenvatten, contract) → Tasks 2/3/4. ✓
- §3.3 `/api/afval/chat` → Task 5. ✓
- §4 SQL-veiligheid (read-only, één-statement, verboden trefwoorden, LIMIT) → Task 1 (open_readonly) + Task 2 (valideer_sql). ✓
- §5 frontend-gedrag (brondata render, chat met toon-query, escaping) → Task 6. ✓
- §6 foutafhandeling (DB weg → 503/`beschikbaar:false`, Qwen offline, ongeldige SQL, lege resultaten) → Tasks 4/5. ✓
- §7 tests (validatie, run_select read-only, grounding, contract incl. gevaarlijke SQL + DB-afwezig, endpoints) → alle Task-tests. ✓
- §9 herkomst (licentie in paneel, SQL + bron + disclaimer in antwoord) → Tasks 4/5/6. ✓

**Placeholder-scan:** geen TBD/TODO; alle code-stappen bevatten volledige code.

**Type-consistentie:** `beantwoord(vraag, db_path, llm_base_url, model, timeout_s)`-contract identiek gedefinieerd (Task 4) en aangeroepen (Task 5-route, gemockt in tests); `valideer_sql`/`OngeldigeSQL`/`bouw_grounding`/`store.open_readonly`/`store.run_select`/`store.bronnen`-signaturen komen overeen tussen definitie (Tasks 1–3) en gebruik (Task 4/5). Route-namen `afval_chat`/`afvaldb_store` matchen de test-referenties. `sql`/`rijen`/`beschikbaar`/`antwoord` consistent in service (Task 4), route (Task 5) en frontend (Task 6).
