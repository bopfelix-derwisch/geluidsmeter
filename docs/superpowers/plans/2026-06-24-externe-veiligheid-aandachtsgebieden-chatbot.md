# REV-aandachtsgebieden-waarschuwing als 4e chatbot-bron — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De chatbot waarschuwt bij een geprikte locatie als die in een REV-**explosie**aandachtsgebied valt (van inrichtingen, buisleidingen of basisnet) — relevant voor het bouwen van een kwetsbaar gebouw — via de open REV GeoServer WFS.

**Architecture:** Vierde bron, spiegelt het omgevingsplan-patroon. Een `ExterneVeiligheidConnector` (WFS GetFeature met CQL `INTERSECTS` op een RD-punt), een `externe_veiligheid`-service (verzamelt geraakte types + waarschuwing), additieve wiring in `chatbot.beantwoord`/`build_prompt` en de `/api/chat`-route, en een waarschuwingskaartje in chat.html. Onafhankelijke degradatie + conservatief contract.

**Tech Stack:** Python 3.10, FastAPI, httpx, pytest. REV GeoServer WFS (rev-portaal.nl, open). Hergebruikt `resolver.wgs84_naar_rd` + `BaseConnector.get_json`.

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (venv `.venv`; src op het pad).
- App op poort **8792** (service `geluidsmeter-api`); **na merge herstarten**: `sudo systemctl restart geluidsmeter-api`.
- **REV WFS = open** (geen key), host `https://rev-portaal.nl/geoserver/wfs`, GeoJSON-output.
- **SAFETY-KRITISCH:** de CQL-filter-POINT wordt geïnterpreteerd in de **native CRS RD/EPSG:28992**, NIET lon/lat. Een lon/lat-punt geeft stil **0 treffers** (vals-negatief). Locatie dus eerst via `resolver.wgs84_naar_rd` → RD, dan `POINT(rd_x rd_y)`. Geometrie-attribuut heet **`geometrie`** (niet `geom`).
- **Scope: alleen EXPLOSIE-aandachtsgebieden**, over álle bronsoorten — `ev_explosieaandachtsgebieden` (inrichting: propaantanks/tankstations), `bl_explosieaandachtsgebieden` (buisleiding), `bn_explosieaandachtsgebieden` (basisnet). Bron-property verschilt per laag: `bedrijfsnaam` (ev) / `naamexploitant` (bl) / `bronhouder` (bn); alle hebben `maatgevende_stof`. Connector: `bron = bedrijfsnaam || naamexploitant || bronhouder`.
- **Additief / backwards compatible:** zonder `locatie` of zonder treffer verandert het chat-gedrag niet; bestaande tests blijven groen (nieuwe param `ev_fn` default `None`, nieuw veld `externe_veiligheid` mag `null` zijn).
- **Conservatief contract (harde eis):** `onzekerheid:true`, `disclaimer`, `vangnet` op elk pad; het structurele blok gaat ongewijzigd mee; geen stellig juridisch besluit.
- **Onafhankelijke degradatie:** een REV-fout mag het RAG-antwoord of de andere drie bronnen nooit laten vallen.
- Nieuwe logica onder `src/leefomgevinglab/`; `src/geluidsmeter/api.py` additief; frontend in `chat.html`.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/connectors/externe_veiligheid.py               # ExterneVeiligheidConnector (CREATE)
src/leefomgevinglab/usecases/vergunningen/externe_veiligheid.py    # check_aandachtsgebieden (CREATE)
src/leefomgevinglab/usecases/vergunningen/chatbot.py               # beantwoord + build_prompt (MODIFY, additief)
src/geluidsmeter/api.py                                            # _ev_connector + ev_fn (MODIFY)
core/config.yaml                                                   # leefomgevinglab.externe_veiligheid (MODIFY)
src/leefomgevinglab/static/chat.html                              # waarschuwingskaartje (MODIFY)
tests/test_externe_veiligheid_connector.py                        # (CREATE)
tests/test_externe_veiligheid_service.py                          # (CREATE)
tests/test_chatbot.py                                             # + ev-tests (MODIFY)
tests/test_api_chat.py                                            # + ev-wiring-test (MODIFY)
tests/test_ev_live.py                                             # live smoke (CREATE)
```

---

### Task 1: `ExterneVeiligheidConnector`

**Files:**
- Create: `src/leefomgevinglab/connectors/externe_veiligheid.py`
- Test: `tests/test_externe_veiligheid_connector.py`

**Interfaces:**
- Consumes: `BaseConnector`, `get_json`.
- Produces: `ExterneVeiligheidConnector(wfs_url, **kwargs)` met
  `aandachtsgebieden_op_punt(laag: str, geo_rd: tuple[float,float], max_n: int = 5) -> list[dict]`
  → `[{bron, maatgevende_stof}]`. Lege FeatureCollection → `[]`.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_externe_veiligheid_connector.py`:

```python
from leefomgevinglab.connectors.externe_veiligheid import ExterneVeiligheidConnector

WFS = "https://x/geoserver/wfs"
RD = (151658.2, 418729.5)


def _conn(tmp_path, capture, ret):
    class _C(ExterneVeiligheidConnector):
        def get_json(self, url, params=None, headers=None):
            capture["url"] = url
            capture["params"] = params
            return ret
    return _C(wfs_url=WFS, cache_dir=str(tmp_path))


def test_bouwt_wfs_params_met_rd_punt(tmp_path):
    cap = {}
    payload = {"features": [
        {"properties": {"bedrijfsnaam": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}},
    ]}
    c = _conn(tmp_path, cap, payload)
    out = c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD)
    assert cap["url"] == WFS
    p = cap["params"]
    assert p["request"] == "GetFeature"
    assert p["typeNames"] == "rev_public:ev_explosieaandachtsgebieden"
    assert p["outputFormat"] == "application/json"
    assert p["cql_filter"] == "INTERSECTS(geometrie, POINT(151658.2 418729.5))"
    assert out == [{"bron": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}]


def test_bron_valt_terug_op_naamexploitant_en_bronhouder(tmp_path):
    # buisleiding (naamexploitant) en basisnet (bronhouder) hebben geen bedrijfsnaam
    c1 = _conn(tmp_path, {}, {"features": [{"properties": {"naamexploitant": "Gasunie", "maatgevende_stof": "aardgas"}}]})
    assert c1.aandachtsgebieden_op_punt("rev_public:bl_explosieaandachtsgebieden", RD)[0]["bron"] == "Gasunie"
    c2 = _conn(tmp_path, {}, {"features": [{"properties": {"bronhouder": "Rijkswaterstaat", "maatgevende_stof": "LPG"}}]})
    assert c2.aandachtsgebieden_op_punt("rev_public:bn_explosieaandachtsgebieden", RD)[0]["bron"] == "Rijkswaterstaat"


def test_maatgevende_stof_genest_object_pakt_chemischeNaam(tmp_path):
    props = {"bedrijfsnaam": "Bungalowpark Hessenheem",
             "maatgevende_stof": {"categorieNaam": "klasse 2.1: Brandbaar gas", "chemischeNaam": "propaan"}}
    c = _conn(tmp_path, {}, {"features": [{"properties": props}]})
    out = c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD)
    assert out[0]["maatgevende_stof"] == "propaan"


def test_lege_featurecollection_geen_treffer(tmp_path):
    c = _conn(tmp_path, {}, {"features": []})
    assert c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD) == []


def test_respecteert_max_n(tmp_path):
    payload = {"features": [{"properties": {"bedrijfsnaam": str(i)}} for i in range(10)]}
    c = _conn(tmp_path, {}, payload)
    assert len(c.aandachtsgebieden_op_punt("laag", RD, max_n=3)) == 3
```

- [ ] **Step 2: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_externe_veiligheid_connector.py -q`
Expected: FAIL (`ModuleNotFoundError: ... externe_veiligheid`).

- [ ] **Step 3: Schrijf de connector**

`src/leefomgevinglab/connectors/externe_veiligheid.py`:

```python
"""REV externe veiligheid: explosieaandachtsgebieden op een punt via de open REV WFS.

rev-portaal.nl GeoServer WFS, GeoJSON. Het CQL INTERSECTS-filter werkt op de native CRS
RD/EPSG:28992 — het punt MOET in RD (lon/lat geeft stil 0 treffers, vals-negatief).
Geometrie-attribuut: 'geometrie'. De bron-property verschilt per laag (ev=bedrijfsnaam,
bl=naamexploitant, bn=bronhouder); maatgevende_stof zit op alle drie.
Live geverifieerd 2026-06-24; zie spec 2026-06-24-externe-veiligheid-aandachtsgebieden-chatbot-design.md.
"""
from .base import BaseConnector


class ExterneVeiligheidConnector(BaseConnector):
    def __init__(self, wfs_url: str, **kwargs):
        super().__init__(**kwargs)
        self.wfs_url = wfs_url

    def aandachtsgebieden_op_punt(self, laag: str, geo_rd: tuple[float, float],
                                  max_n: int = 5) -> list[dict]:
        x, y = geo_rd
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": laag, "outputFormat": "application/json",
            "srsName": "EPSG:4326", "count": max_n,
            "cql_filter": f"INTERSECTS(geometrie, POINT({x} {y}))",
        }
        data = self.get_json(self.wfs_url, params=params)
        out = []
        for f in (data.get("features") or [])[:max_n]:
            p = f.get("properties") or {}
            stof = p.get("maatgevende_stof")
            if isinstance(stof, dict):   # live: {"categorieNaam": ..., "chemischeNaam": "propaan"}
                stof = stof.get("chemischeNaam") or stof.get("categorieNaam")
            out.append({
                "bron": p.get("bedrijfsnaam") or p.get("naamexploitant") or p.get("bronhouder"),
                "maatgevende_stof": stof,
            })
        return out
```

- [ ] **Step 4: Run om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_externe_veiligheid_connector.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/connectors/externe_veiligheid.py tests/test_externe_veiligheid_connector.py
git commit -m "feat(llab): ExterneVeiligheidConnector (REV-aandachtsgebieden op RD-punt, WFS INTERSECTS)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `externe_veiligheid`-service

**Files:**
- Create: `src/leefomgevinglab/usecases/vergunningen/externe_veiligheid.py`
- Test: `tests/test_externe_veiligheid_service.py`

**Interfaces:**
- Consumes: `ConnectorError`; `resolver.wgs84_naar_rd`; een `ev_connector` met `aandachtsgebieden_op_punt`.
- Produces: `check_aandachtsgebieden(locatie: dict, ev_connector, lagen: dict, max_n: int = 5) -> dict | None`
  — RD-conversie, per (type→laag) een query, verzamelt geraakte types + bronnen + waarschuwing.
  Geen treffer → `None`. `ConnectorError` uit een laag-call propageert.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_externe_veiligheid_service.py`:

```python
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import externe_veiligheid as ev

LOC = {"lat": 51.757, "lon": 5.339}
LAGEN = {"inrichting": "rev_public:ev_explosieaandachtsgebieden",
         "buisleiding": "rev_public:bl_explosieaandachtsgebieden",
         "basisnet": "rev_public:bn_explosieaandachtsgebieden"}


class _Conn:
    def __init__(self, per_laag=None, error_laag=None):
        self._per = per_laag or {}
        self._err = error_laag

    def aandachtsgebieden_op_punt(self, laag, geo_rd, max_n=5):
        if self._err == laag:
            raise ConnectorError("down")
        return self._per.get(laag, [])


def _patch_rd(monkeypatch):
    monkeypatch.setattr(ev.resolver, "wgs84_naar_rd", lambda lat, lon: (151658.2, 418729.5))


def test_treffer_geeft_waarschuwing(monkeypatch):
    _patch_rd(monkeypatch)
    conn = _Conn(per_laag={"rev_public:ev_explosieaandachtsgebieden":
                           [{"bron": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}]})
    out = ev.check_aandachtsgebieden(LOC, conn, LAGEN)
    assert out is not None
    a = out["aandachtsgebieden"][0]
    assert a["herkomst"] == "inrichting"
    assert a["bron"] == "Autobedrijf Mekes"
    assert a["maatgevende_stof"] == "propaan"
    assert "explosieaandachtsgebied" in out["waarschuwing"]
    assert "Autobedrijf Mekes" in out["waarschuwing"]
    assert "kwetsbaar gebouw" in out["waarschuwing"]
    assert out["locatie_rd"] == [151658.2, 418729.5]
    assert out["bron"].startswith("REV")


def test_geen_treffer_geeft_none(monkeypatch):
    _patch_rd(monkeypatch)
    assert ev.check_aandachtsgebieden(LOC, _Conn(), LAGEN) is None


def test_meerdere_herkomsten(monkeypatch):
    _patch_rd(monkeypatch)
    conn = _Conn(per_laag={
        "rev_public:ev_explosieaandachtsgebieden": [{"bron": "A", "maatgevende_stof": "propaan"}],
        "rev_public:bl_explosieaandachtsgebieden": [{"bron": "Gasunie", "maatgevende_stof": "aardgas"}]})
    out = ev.check_aandachtsgebieden(LOC, conn, LAGEN)
    herkomsten = {a["herkomst"] for a in out["aandachtsgebieden"]}
    assert herkomsten == {"inrichting", "buisleiding"}


def test_laag_fout_propageert(monkeypatch):
    _patch_rd(monkeypatch)
    conn = _Conn(error_laag="rev_public:bl_explosieaandachtsgebieden")
    with pytest.raises(ConnectorError):
        ev.check_aandachtsgebieden(LOC, conn, LAGEN)
```

- [ ] **Step 2: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_externe_veiligheid_service.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Schrijf de service**

`src/leefomgevinglab/usecases/vergunningen/externe_veiligheid.py`:

```python
"""UC: externe-veiligheid-waarschuwing — REV-EXPLOSIEaandachtsgebieden op een punt.

Per herkomst (inrichting/buisleiding/basisnet) een laag-query op de explosie-laag; verzamelt de
treffers (herkomst + bron + stof) en bouwt een conservatieve waarschuwing. Een laag-fout
(ConnectorError) propageert: liever geen blok dan een onvolledige 'veilig'-indruk.
"""
from leefomgevinglab.usecases.vergunningen import resolver

BRON = "REV (rev-portaal.nl)"


def check_aandachtsgebieden(locatie: dict, ev_connector, lagen: dict, max_n: int = 5) -> dict | None:
    rd = resolver.wgs84_naar_rd(locatie["lat"], locatie["lon"])
    aandachtsgebieden = []
    for herkomst, laag in lagen.items():
        for t in ev_connector.aandachtsgebieden_op_punt(laag, rd, max_n):   # ConnectorError propageert
            aandachtsgebieden.append({"herkomst": herkomst, "bron": t.get("bron"),
                                      "maatgevende_stof": t.get("maatgevende_stof")})
    if not aandachtsgebieden:
        return None
    herkomsten = ", ".join(sorted({a["herkomst"] for a in aandachtsgebieden}))
    bronnen = sorted({a["bron"] for a in aandachtsgebieden if a.get("bron")})
    stoffen = sorted({a["maatgevende_stof"] for a in aandachtsgebieden if a.get("maatgevende_stof")})
    detail = "; ".join(x for x in [
        "herkomst: " + herkomsten,
        ("bron: " + ", ".join(bronnen)) if bronnen else "",
        ("stof: " + ", ".join(stoffen)) if stoffen else "",
    ] if x)
    waarschuwing = (
        f"Let op: deze locatie ligt in een explosieaandachtsgebied ({detail}). Voor een kwetsbaar "
        "gebouw gelden hier aanvullende eisen; raadpleeg het bevoegd gezag."
    )
    return {
        "aandachtsgebieden": aandachtsgebieden,
        "waarschuwing": waarschuwing,
        "locatie_rd": list(rd),
        "bron": BRON,
    }
```

- [ ] **Step 4: Run om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_externe_veiligheid_service.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/externe_veiligheid.py tests/test_externe_veiligheid_service.py
git commit -m "feat(llab): externe-veiligheid-service (aandachtsgebieden -> waarschuwing)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: chatbot — `ev_fn` + prompt-sectie

**Files:**
- Modify: `src/leefomgevinglab/usecases/vergunningen/chatbot.py`
- Test: `tests/test_chatbot.py`

**Interfaces:**
- Consumes: `ConnectorError`; een `ev_fn` callable `(locatie) -> dict|None`.
- Produces:
  - `build_prompt(vraag, passages, regels=None, omgevingsplan=None, externe_veiligheid=None)` — voegt een
    waarschuwingssectie toe als `externe_veiligheid` aandachtsgebieden bevat.
  - `beantwoord(..., locatie=None, regels_fn=None, omgevingsplan_fn=None, ev_fn=None)` — berekent
    `externe_veiligheid` onafhankelijk (achter `try/except ConnectorError`) en zet het veld op elk return-pad.

- [ ] **Step 1: Schrijf de falende tests**

Voeg toe aan `tests/test_chatbot.py` (helpers `_Store`, `_Resp`, `_embed_ok`, `LOC` bestaan al):

```python
_EV_OK = {
    "aandachtsgebieden": [{"herkomst": "inrichting", "bron": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}],
    "waarschuwing": "Let op: deze locatie ligt in een explosieaandachtsgebied (herkomst: inrichting; "
                    "bron: Autobedrijf Mekes; stof: propaan). Voor een kwetsbaar gebouw gelden hier "
                    "aanvullende eisen; raadpleeg het bevoegd gezag.",
    "locatie_rd": [151658.2, 418729.5], "bron": "REV (rev-portaal.nl)",
}


def test_build_prompt_met_ev_voegt_waarschuwing_toe():
    p = chatbot.build_prompt("mag ik bouwen?", [{"text": "c", "url": "u1"}], None, None, _EV_OK)
    assert "externe veiligheid" in p.lower()
    assert "explosieaandachtsgebied" in p


def test_build_prompt_zonder_ev_geen_waarschuwing():
    p = chatbot.build_prompt("iets", [{"text": "c", "url": "u1"}])
    assert "explosieaandachtsgebied" not in p


def test_beantwoord_met_ev(monkeypatch):
    store = _Store([{"text": "x", "url": "https://iplo.nl/a", "score": 0.9}])
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["messages"][0]["content"]
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("mag ik bouwen?", store, _embed_ok, llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, ev_fn=lambda loc: _EV_OK)
    assert out["externe_veiligheid"] == _EV_OK
    assert "explosieaandachtsgebied" in captured["prompt"]
    assert out["beschikbaar"] is True


def test_beantwoord_zonder_locatie_geen_ev(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])
    called = {"n": 0}

    def ev_fn(loc):
        called["n"] += 1
        return _EV_OK

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok, llm_base_url="http://x/v1", model="qwen", ev_fn=ev_fn)
    assert out["externe_veiligheid"] is None
    assert called["n"] == 0


def test_beantwoord_ev_down_rag_blijft(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])

    def ev_boom(loc):
        raise ConnectorError("rev down")

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok, llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, ev_fn=ev_boom)
    assert out["externe_veiligheid"] is None
    assert out["beschikbaar"] is True
    assert out["antwoord"] == "ok"
```

- [ ] **Step 2: Run om te zien dat ze falen**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: de nieuwe tests FALEN (onbekende kwarg `ev_fn`, `KeyError: 'externe_veiligheid'`); bestaande groen.

- [ ] **Step 3: Pas `build_prompt` + `beantwoord` aan**

In `build_prompt`: voeg `externe_veiligheid=None` toe aan de signatuur. Bouw, ná de bestaande
`op_sectie` (omgevingsplan), een `ev_sectie`:

```python
    ev_sectie = ""
    if externe_veiligheid and externe_veiligheid.get("aandachtsgebieden"):
        ev_sectie = (
            "\n\nLET OP — EXTERNE VEILIGHEID: " + externe_veiligheid.get("waarschuwing", "")
            + " Benoem dit duidelijk in je antwoord; trek geen stellig juridisch besluit."
        )
```

Voeg `{ev_sectie}` toe aan de prompt-samenstelling direct ná `{op_sectie}` (vóór `\n\nContext:`).

In `beantwoord`: voeg `ev_fn=None` toe aan de signatuur (ná `omgevingsplan_fn=None`). Bereken het blok ná
het `omgevingsplan`-blok en vóór de RAG-`try`:

```python
    # Externe veiligheid (REV-aandachtsgebieden) — onafhankelijk; mag het RAG-antwoord nooit laten vallen
    externe_veiligheid = None
    if locatie and ev_fn is not None:
        try:
            ev = ev_fn(locatie)
            if ev:
                externe_veiligheid = ev
        except ConnectorError:
            externe_veiligheid = None
```

Geef `externe_veiligheid` door aan `build_prompt(vraag, passages, regels, omgevingsplan, externe_veiligheid)`
en voeg `"externe_veiligheid": externe_veiligheid` toe aan **elk** return-dict (embed-error, geen-passages,
LLM-fout, happy), naast de bestaande `"omgevingsplan": omgevingsplan`.

- [ ] **Step 4: Run om te zien dat ze slagen**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: PASS (bestaande + 5 nieuwe).

- [ ] **Step 5: Volledige suite**

Run: `PYTHONPATH=src python -m pytest -q --ignore=tests/test_dso_live.py --ignore=tests/test_ozon_live.py --ignore=tests/test_ev_live.py`
Expected: PASS (live-tests apart; netwerk).

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/chatbot.py tests/test_chatbot.py
git commit -m "feat(llab): chatbot waarschuwt voor REV-aandachtsgebieden (4e bron)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `/api/chat`-route + config + live smoke

**Files:**
- Modify: `src/geluidsmeter/api.py`
- Modify: `core/config.yaml`
- Test: `tests/test_api_chat.py`
- Test (create): `tests/test_ev_live.py`

**Interfaces:**
- Consumes: `ExterneVeiligheidConnector` (Task 1), `externe_veiligheid.check_aandachtsgebieden` (Task 2),
  `chatbot.beantwoord(..., ev_fn=...)` (Task 3).
- Produces: helper `_ev_connector()` + een `ev_fn`-closure, doorgegeven aan `beantwoord`.

- [ ] **Step 1: Config — voeg `leefomgevinglab.externe_veiligheid` toe**

Voeg in `core/config.yaml` onder `leefomgevinglab:` (naast `ozon:`) toe:

```yaml
  externe_veiligheid:
    # REV-EXPLOSIEaandachtsgebieden via de open REV GeoServer WFS (rev-portaal.nl). CQL INTERSECTS op
    # RD/EPSG:28992-punt (lon/lat geeft stil 0 treffers). lagen = herkomst -> explosie-laag.
    wfs_url: "https://rev-portaal.nl/geoserver/wfs"
    max_features: 5
    lagen:
      inrichting: "rev_public:ev_explosieaandachtsgebieden"   # propaantanks, tankstations, ...
      buisleiding: "rev_public:bl_explosieaandachtsgebieden"
      basisnet: "rev_public:bn_explosieaandachtsgebieden"
```

- [ ] **Step 2: Schrijf de falende route-wiring-test**

Voeg toe aan `tests/test_api_chat.py`:

```python
def test_chat_locatie_geeft_externe_veiligheid_door(monkeypatch):
    client = _client(monkeypatch)
    api._config["leefomgevinglab"]["externe_veiligheid"] = {
        "wfs_url": "https://x/wfs", "max_features": 5,
        "lagen": {"inrichting": "rev_public:ev_explosieaandachtsgebieden"}}

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_check(locatie, ev_connector, lagen, max_n=5):
        captured["locatie"] = locatie
        captured["lagen"] = lagen
        return {"aandachtsgebieden": [{"herkomst": "inrichting", "bron": "X", "maatgevende_stof": "propaan"}],
                "waarschuwing": "Let op", "locatie_rd": [1.0, 2.0], "bron": "REV (rev-portaal.nl)"}

    monkeypatch.setattr(api.externe_veiligheid_mod, "check_aandachtsgebieden", fake_check)

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        ev = kw["ev_fn"]({"lat": 51.0, "lon": 5.0})
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": None, "omgevingsplan": None,
                "externe_veiligheid": ev, "onzekerheid": True, "disclaimer": "d",
                "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik bouwen?", "locatie": {"lat": 51.0, "lon": 5.0}})
    assert r.status_code == 200
    assert captured["locatie"] == {"lat": 51.0, "lon": 5.0}
    assert "inrichting" in captured["lagen"]
    assert r.json()["externe_veiligheid"]["aandachtsgebieden"][0]["herkomst"] == "inrichting"
```

- [ ] **Step 3: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: FAIL (`AttributeError: ... 'externe_veiligheid_mod'` / `_ev_connector`).

- [ ] **Step 4: Bedraad in `src/geluidsmeter/api.py`**

Voeg bij de imports toe (naast `omgevingsplan as omgevingsplan_mod`):

```python
from leefomgevinglab.usecases.vergunningen import externe_veiligheid as externe_veiligheid_mod
from leefomgevinglab.connectors.externe_veiligheid import ExterneVeiligheidConnector
```

Voeg een helper toe (naast `_ozon_connector`):

```python
def _ev_connector() -> ExterneVeiligheidConnector:
    ll = _config.get("leefomgevinglab", {})
    ev = ll.get("externe_veiligheid", {})
    return ExterneVeiligheidConnector(
        wfs_url=ev.get("wfs_url", ""),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )
```

In `api_chat`, bouw de closure en geef 'm door aan `beantwoord` (naast `omgevingsplan_fn`):

```python
    ev_cfg = _config.get("leefomgevinglab", {}).get("externe_veiligheid", {})

    def ev_fn(locatie: dict):
        return externe_veiligheid_mod.check_aandachtsgebieden(
            locatie, _ev_connector(), ev_cfg.get("lagen", {}), max_n=ev_cfg.get("max_features", 5))
```

en voeg `ev_fn=ev_fn` toe aan de `chatbot.beantwoord(...)`-aanroep. Werk de `store is None`-vroege return
bij: voeg `"externe_veiligheid": None` toe (naast `"omgevingsplan": None`).

- [ ] **Step 5: Run om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: PASS.

- [ ] **Step 6: Schrijf de live smoke-test**

`tests/test_ev_live.py`:

```python
"""Live smoke tegen de open REV WFS. Skipt zonder DSO_API_KEY (live-test-vlag)."""
import os
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DSO_API_KEY"),
                                reason="live-tests uit (DSO_API_KEY niet gezet)")

WFS = "https://rev-portaal.nl/geoserver/wfs"


def test_live_explosieaandachtsgebied_op_rd_punt(tmp_path):
    from leefomgevinglab.connectors.externe_veiligheid import ExterneVeiligheidConnector
    c = ExterneVeiligheidConnector(wfs_url=WFS, cache_dir=str(tmp_path))
    # RD-punt binnen een bekend explosieaandachtsgebied (Bungalowpark Hessenheem, propaan; geverifieerd 2026-06-24)
    treffers = c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", (232003.1, 473064.6))
    assert len(treffers) >= 1
    assert treffers[0]["maatgevende_stof"] == "propaan"
```

- [ ] **Step 7: Volledige suite (regressie) + commit**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen; `test_ev_live.py` draait mét key (of skipt). (Andere live-tests kunnen falen bij een externe DSO-outage — dat is netwerk, niet deze code.)

```bash
git add src/geluidsmeter/api.py core/config.yaml tests/test_api_chat.py tests/test_ev_live.py
git commit -m "feat(llab): /api/chat geeft REV-aandachtsgebied-waarschuwing door + config + live smoke

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — waarschuwingskaartje in `chat.html`

**Files:**
- Modify: `src/leefomgevinglab/static/chat.html`

**Interfaces:**
- Consumes (HTTP): `/api/chat`-respons met `externe_veiligheid` (of `null`).
- Produces: een opvallend waarschuwingskaartje onder het antwoord.

> Handmatige verificatie (geen unit-test voor HTML); de data-paden zijn in Task 1-4 getest.

- [ ] **Step 1: Voeg een `externeVeiligheidHtml`-renderer toe + roep 'm aan**

In de `<script>` van `chat.html`, naast `omgevingsplanHtml(o)`, toevoegen (alle waarden via `esc()`):

```javascript
    function externeVeiligheidHtml(e) {
      if (!e || !(e.aandachtsgebieden || []).length) return "";
      return '<div class="regels" style="border-color:#a33;background:#2a1414">' +
        '<h4 style="color:#ff9a8a">⚠️ Externe veiligheid</h4>' +
        '<div>' + esc(e.waarschuwing) + '</div>' +
        '<div class="alt">Bron: ' + esc(e.bron) + '</div></div>';
    }
```

Voeg de aanroep toe direct ná `omgevingsplanHtml(d.omgevingsplan)` in de antwoord-rendering:

```javascript
          regelsHtml(d.regels) +
          omgevingsplanHtml(d.omgevingsplan) +
          externeVeiligheidHtml(d.externe_veiligheid) +
```

Werk de offline-degradatie-conditie bij zodat het kaartje ook toont als alleen dit blok er is:
breid `if (!d.beschikbaar && !d.regels && !d.omgevingsplan)` uit naar
`if (!d.beschikbaar && !d.regels && !d.omgevingsplan && !d.externe_veiligheid)`.

- [ ] **Step 2: Herstart + handmatige verificatie**

```bash
sudo systemctl restart geluidsmeter-api
```
Open `/chatbot`, prik een locatie in een bekend aandachtsgebied, stel een vraag, en controleer:
1. Een rood/amber **"⚠️ Externe veiligheid"**-kaartje verschijnt met de waarschuwing + bron.
2. Locatie buiten elk aandachtsgebied → geen kaartje.
3. Controleer ook met curl (lat 52.24025, lon 6.5146 ligt in een explosieaandachtsgebied — Bungalowpark Hessenheem, propaan):
   `curl -sS -m150 -X POST http://localhost:8792/api/chat -H "Content-Type: application/json" -d '{"vraag":"mag ik een woning bouwen?","locatie":{"lat":52.24025,"lon":6.5146}}'`
   → veld `externe_veiligheid` gevuld (of `null`). Noteer de uitkomst in het taakrapport.

- [ ] **Step 3: Commit**

```bash
git add src/leefomgevinglab/static/chat.html
git commit -m "feat(llab): chat-frontend toont externe-veiligheid-waarschuwingskaartje

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (vervolg)

- Brand-/gifwolk-aandachtsgebieden en de civiel-/vuurwerk-explosievarianten (nu config-uitbreidbaar; default = alleen explosie ev/bl/bn).
- Kwetsbaarheidscategorieën (`veiligheidszones*`) + juridische eisen per categorie.
- Intentie-detectie "kwetsbaar gebouw"; ketenversnelling; multi-turn.

## Self-Review

- **Spec-dekking:** connector (INTERSECTS op RD-punt, `geometrie`-attr, type-uit-laag) → Task 1;
  type-verzameling + waarschuwing → Task 2; 4e bron in antwoord → Task 3; route + config + live smoke →
  Task 4; waarschuwingskaartje → Task 5; onafhankelijke degradatie → Task 2 (propagatie) + Task 3
  (`try/except ConnectorError`) + tests; conservatief contract → prompt-instructie + ongewijzigd blok.
- **Placeholders:** geen TBD; alle code-stappen compleet. De safety-kritische RD-eis staat in de
  connector-code + Global Constraints.
- **Type-consistentie:** `aandachtsgebieden_op_punt(laag, geo_rd, max_n) -> [{bron,maatgevende_stof}]`,
  `check_aandachtsgebieden(locatie, ev_connector, lagen, max_n) -> dict|None`, `beantwoord(..., ev_fn)`,
  `build_prompt(..., externe_veiligheid)`, en het respons-veld `externe_veiligheid` consistent over Task 1→5.
