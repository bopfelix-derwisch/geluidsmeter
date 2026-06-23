# Omgevingsplan-regels (Ozon) als derde chatbot-bron — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De vergunningen-chatbot weegt bij een geprikte locatie ook de geldende omgevingsplan-regels mee ("wat geldt hier") uit de DSO-bron Ozon (Omgevingsdocument Presenteren v8): welke regelingen (type-gefilterd) op het punt gelden + best-effort de regelteksten van de meest relevante.

**Architecture:** Spiegelt de toepasbare-regels-integratie. Een nieuwe `OzonConnector` (regelingen_op_punt + regelteksten_op_punt), een `omgevingsplan`-service (type-filter + top-1 best-effort + caps), additieve wiring in `chatbot.beantwoord`/`build_prompt` en de `/api/chat`-route, en een "Wat geldt hier"-kaartje in chat.html. Onafhankelijke degradatie en het conservatieve contract blijven gelden.

**Tech Stack:** Python 3.10, FastAPI, httpx, pytest. DSO Ozon Presenteren v8 (pre-prod). Hergebruikt `resolver.wgs84_naar_rd` en `BaseConnector.post_json`.

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (venv `.venv`; src op het pad).
- App op poort **8792** (service `geluidsmeter-api`); **na merge herstarten**: `sudo systemctl restart geluidsmeter-api`.
- **Ozon = pre-productie**, host `service.pre.omgevingswet.overheid.nl`, header `x-api-key` (key uit `.env`), `Accept: application/hal+json`. Geometrie in RD via header **`Content-Crs: http://www.opengis.net/def/crs/EPSG/0/28992`** (OGC-URI-vorm; `EPSG:28992` geeft 400).
- Geo-body: `{"geometrie": {"type": "Point", "coordinates": [x, y]}}` (RD/EPSG:28992).
- **Additief / backwards compatible:** zonder `locatie` of zonder Ozon-data verandert het chat-gedrag niet; bestaande tests blijven groen (nieuwe param `omgevingsplan_fn` default `None`, nieuw veld `omgevingsplan` mag `null` zijn).
- **Conservatief contract (harde eis):** `onzekerheid:true`, `disclaimer`, `vangnet` op elk pad; het structurele `omgevingsplan`-blok gaat ongewijzigd mee; geen stellig juridisch besluit.
- **Onafhankelijke degradatie:** een fout in de Ozon-laag mag het RAG-antwoord of de toepasbare-regels nooit laten vallen.
- **Begrenzing:** filter regelingen op types `Omgevingsplan`, `Omgevingsverordening`, `Waterschapsverordening`; cap `max_regelingen` (3) en `max_regelteksten` (5, alleen voor de top-1 regeling).
- Nieuwe logica onder `src/leefomgevinglab/`; `src/geluidsmeter/api.py` additief; frontend in `chat.html`.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/connectors/ozon.py                 # OzonConnector (CREATE)
src/leefomgevinglab/usecases/vergunningen/omgevingsplan.py  # omgevingsplan_op_locatie (CREATE)
src/leefomgevinglab/usecases/vergunningen/chatbot.py   # beantwoord + build_prompt (MODIFY, additief)
src/geluidsmeter/api.py                                 # _ozon_connector + omgevingsplan_fn (MODIFY)
core/config.yaml                                        # leefomgevinglab.ozon (MODIFY)
src/leefomgevinglab/static/chat.html                   # "Wat geldt hier"-kaartje (MODIFY)
tests/test_ozon_connector.py                            # (CREATE)
tests/test_omgevingsplan_service.py                    # (CREATE)
tests/test_chatbot.py                                   # + omgevingsplan-tests (MODIFY)
tests/test_api_chat.py                                  # + ozon-wiring-test (MODIFY)
tests/test_ozon_live.py                                 # live smoke (skip zonder key) (CREATE)
```

---

### Task 1: `OzonConnector`

**Files:**
- Create: `src/leefomgevinglab/connectors/ozon.py`
- Test: `tests/test_ozon_connector.py`

**Interfaces:**
- Consumes: `BaseConnector`, `ConnectorError`, `post_json`.
- Produces: `OzonConnector(base_url, api_key, api_key_header="x-api-key", **kwargs)` met
  - `regelingen_op_punt(geo_rd: tuple[float,float]) -> list[dict]` → `[{titel, type, bevoegd_gezag, uri}]`.
  - `regelteksten_op_punt(regeling_uri: str, geo_rd, max_m: int = 5) -> list[str]` (best-effort; leeg → `[]`).
  - Beide raise `ConnectorError` zonder key.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_ozon_connector.py`:

```python
import pytest
from leefomgevinglab.connectors.ozon import OzonConnector
from leefomgevinglab.connectors.base import ConnectorError

B = "https://x/ozon/v8"
RD = (139784.0, 442870.0)


def _conn(tmp_path, capture, ret):
    class _O(OzonConnector):
        def post_json(self, url, json_body=None, headers=None):
            capture["url"] = url
            capture["body"] = json_body
            capture["headers"] = headers
            return ret
    return _O(base_url=B, api_key="K", cache_dir=str(tmp_path))


def test_regelingen_op_punt_parst_en_zet_headers(tmp_path):
    cap = {}
    payload = {"_embedded": {"regelingen": [
        {"identificatie": "/akn/nl/act/pv26/2022/ov01", "opschrift": "Omgevingsverordening Utrecht",
         "officieleTitel": "OV Utrecht lang", "type": {"waarde": "Omgevingsverordening"},
         "aangeleverdDoorEen": {"naam": "provincie Utrecht", "bestuurslaag": "provincie"}},
    ]}}
    c = _conn(tmp_path, cap, payload)
    out = c.regelingen_op_punt(RD)
    assert cap["url"] == f"{B}/regelingen/_zoek"
    assert cap["body"] == {"geometrie": {"type": "Point", "coordinates": [139784.0, 442870.0]}}
    assert cap["headers"]["x-api-key"] == "K"
    assert cap["headers"]["Accept"] == "application/hal+json"
    assert cap["headers"]["Content-Crs"] == "http://www.opengis.net/def/crs/EPSG/0/28992"
    assert out == [{"titel": "Omgevingsverordening Utrecht", "type": "Omgevingsverordening",
                    "bevoegd_gezag": "provincie Utrecht", "uri": "_akn_nl_act_pv26_2022_ov01"}]


def test_regelingen_titel_valt_terug_op_officieleTitel(tmp_path):
    cap = {}
    payload = {"_embedded": {"regelingen": [
        {"identificatie": "/akn/x", "officieleTitel": "Alleen officieel", "type": {"waarde": "Omgevingsplan"},
         "aangeleverdDoorEen": {"naam": "gemeente X"}},
    ]}}
    c = _conn(tmp_path, cap, payload)
    assert c.regelingen_op_punt(RD)[0]["titel"] == "Alleen officieel"


def test_regelteksten_op_punt_topM_en_pad(tmp_path):
    cap = {}
    payload = {"_embedded": {"regeltekstannotaties": [
        {"opschrift": "Bouwregels"}, {"opschrift": "Parkeren"}, {"opschrift": "Reclame"}]}}
    c = _conn(tmp_path, cap, payload)
    out = c.regelteksten_op_punt("_akn_nl_act_pv26_2022_ov01", RD, max_m=2)
    assert cap["url"] == f"{B}/regelingen/_akn_nl_act_pv26_2022_ov01/regeltekstannotaties/_zoek"
    assert out == ["Bouwregels", "Parkeren"]


def test_regelteksten_leeg(tmp_path):
    c = _conn(tmp_path, {}, {"_embedded": {}})
    assert c.regelteksten_op_punt("u", RD) == []


def test_zonder_key_raises(tmp_path):
    c = OzonConnector(base_url=B, api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.regelingen_op_punt(RD)
    with pytest.raises(ConnectorError):
        c.regelteksten_op_punt("u", RD)
```

- [ ] **Step 2: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_ozon_connector.py -q`
Expected: FAIL (`ModuleNotFoundError: ... ozon`).

- [ ] **Step 3: Schrijf de connector**

`src/leefomgevinglab/connectors/ozon.py`:

```python
"""DSO Ozon (Omgevingsdocument Presenteren v8): wat geldt hier op een punt.

Pre-productie, x-api-key, HAL. Geometrie in RD via Content-Crs (OGC-URI-vorm).
Live geverifieerd 2026-06-23; zie spec 2026-06-23-omgevingsplan-ozon-chatbot-design.md.
"""
from .base import BaseConnector, ConnectorError

_CRS_RD = "http://www.opengis.net/def/crs/EPSG/0/28992"


def _geo_body(geo_rd: tuple[float, float]) -> dict:
    return {"geometrie": {"type": "Point", "coordinates": [geo_rd[0], geo_rd[1]]}}


class OzonConnector(BaseConnector):
    def __init__(self, base_url: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def _headers(self) -> dict:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        return {self.api_key_header: self.api_key,
                "Accept": "application/hal+json",
                "Content-Crs": _CRS_RD}

    def regelingen_op_punt(self, geo_rd: tuple[float, float]) -> list[dict]:
        headers = self._headers()
        url = f"{self.base_url}/regelingen/_zoek"
        data = self.post_json(url, json_body=_geo_body(geo_rd), headers=headers)
        out = []
        for r in (data.get("_embedded") or {}).get("regelingen") or []:
            bg = r.get("aangeleverdDoorEen") or {}
            out.append({
                "titel": r.get("opschrift") or r.get("officieleTitel"),
                "type": (r.get("type") or {}).get("waarde"),
                "bevoegd_gezag": bg.get("naam"),
                "uri": (r.get("identificatie") or "").replace("/", "_"),
            })
        return out

    def regelteksten_op_punt(self, regeling_uri: str, geo_rd: tuple[float, float],
                             max_m: int = 5) -> list[str]:
        headers = self._headers()
        url = f"{self.base_url}/regelingen/{regeling_uri}/regeltekstannotaties/_zoek"
        data = self.post_json(url, json_body=_geo_body(geo_rd), headers=headers)
        emb = data.get("_embedded") or {}
        items = next(iter(emb.values()), []) if emb else []
        out = []
        for it in items[:max_m]:
            titel = it.get("opschrift") or it.get("titel") or (it.get("regeltekst") or {}).get("opschrift")
            if titel:
                out.append(titel)
        return out
```

> **Noot:** het exacte opschrift-veld van een regeltekstannotatie kon niet tegen een niet-lege
> oefen-respons bevestigd worden (regeltekstannotaties zijn in oefen vrijwel altijd leeg). De parsing
> probeert daarom meerdere kandidaat-velden en degradeert naar `[]`; dit is een best-effort laag.

- [ ] **Step 4: Run om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_ozon_connector.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/connectors/ozon.py tests/test_ozon_connector.py
git commit -m "feat(llab): OzonConnector (regelingen + regelteksten op punt, RD/Content-Crs)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `omgevingsplan`-service

**Files:**
- Create: `src/leefomgevinglab/usecases/vergunningen/omgevingsplan.py`
- Test: `tests/test_omgevingsplan_service.py`

**Interfaces:**
- Consumes: `ConnectorError`; `resolver.wgs84_naar_rd`; een `ozon_connector` met `regelingen_op_punt`
  + `regelteksten_op_punt` (Task 1).
- Produces: `omgevingsplan_op_locatie(locatie: dict, ozon_connector, max_regelingen: int = 3, max_regelteksten: int = 5) -> dict | None`
  — RD-conversie, type-filter, top-1 best-effort regelteksten, caps. `None` bij geen relevante regeling.
  `ConnectorError` uit `regelingen_op_punt` propageert.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_omgevingsplan_service.py`:

```python
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import omgevingsplan as op

LOC = {"lat": 52.08, "lon": 5.12}


class _Ozon:
    def __init__(self, regelingen=None, teksten=None, reg_error=False, tekst_error=False):
        self._r, self._t = regelingen, teksten
        self._re, self._te = reg_error, tekst_error
        self.tekst_uri = None

    def regelingen_op_punt(self, geo_rd):
        if self._re:
            raise ConnectorError("down")
        return self._r

    def regelteksten_op_punt(self, uri, geo_rd, max_m=5):
        self.tekst_uri = uri
        if self._te:
            raise ConnectorError("down")
        return (self._t or [])[:max_m]


def _patch_rd(monkeypatch):
    monkeypatch.setattr(op.resolver, "wgs84_naar_rd", lambda lat, lon: (139784.0, 442870.0))


_REGS = [
    {"titel": "Waterschapsverordening X", "type": "Waterschapsverordening", "bevoegd_gezag": "WS X", "uri": "_ws"},
    {"titel": "Omgevingsverordening Utrecht", "type": "Omgevingsverordening", "bevoegd_gezag": "prov", "uri": "_ov"},
    {"titel": "Nationale Omgevingsvisie", "type": "Omgevingsvisie", "bevoegd_gezag": "rijk", "uri": "_novi"},
    {"titel": "Omgevingsplan Z", "type": "Omgevingsplan", "bevoegd_gezag": "gem Z", "uri": "_op"},
]


def test_filtert_types_en_prioriteert_top1(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, teksten=["Bouwregels", "Parkeren"])
    out = op.omgevingsplan_op_locatie(LOC, ozon, max_regelingen=3, max_regelteksten=5)
    # Omgevingsvisie eruit gefilterd; Omgevingsplan heeft hoogste prioriteit
    types = [r["type"] for r in out["regelingen"]]
    assert "Omgevingsvisie" not in types
    assert out["regelingen"][0]["type"] == "Omgevingsplan"
    assert out["top_regeling"] == "Omgevingsplan Z"
    assert ozon.tekst_uri == "_op"                 # regelteksten voor de top-1
    assert out["regelteksten"] == ["Bouwregels", "Parkeren"]
    assert out["locatie_rd"] == [139784.0, 442870.0]
    assert out["bron"].lower().startswith("dso presenteren")


def test_cap_op_regelingen(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, teksten=[])
    out = op.omgevingsplan_op_locatie(LOC, ozon, max_regelingen=2)
    assert len(out["regelingen"]) == 2
    assert out["aantal_beperkt_tot"] == 2


def test_geen_relevante_regeling_geeft_none(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=[{"titel": "NOVI", "type": "Omgevingsvisie", "bevoegd_gezag": "rijk", "uri": "_n"}])
    assert op.omgevingsplan_op_locatie(LOC, ozon) is None


def test_regelteksten_fout_blijft_blok(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(regelingen=_REGS, tekst_error=True)
    out = op.omgevingsplan_op_locatie(LOC, ozon)
    assert out is not None                         # regelingen blijven staan
    assert out["regelteksten"] == []               # best-effort faalde


def test_regelingen_bron_down_propageert(monkeypatch):
    _patch_rd(monkeypatch)
    ozon = _Ozon(reg_error=True)
    with pytest.raises(ConnectorError):
        op.omgevingsplan_op_locatie(LOC, ozon)
```

- [ ] **Step 2: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_omgevingsplan_service.py -q`
Expected: FAIL (`ModuleNotFoundError: ... omgevingsplan`).

- [ ] **Step 3: Schrijf de service**

`src/leefomgevinglab/usecases/vergunningen/omgevingsplan.py`:

```python
"""UC: 'wat geldt hier' — geldende omgevingsplan-regels op een punt via Ozon.

Type-gefilterd op de relevante regel-soorten; top-1 best-effort regelteksten; begrensd.
"""
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import resolver

RELEVANTE_TYPES = ("Omgevingsplan", "Omgevingsverordening", "Waterschapsverordening")
_PRIORITEIT = {"Omgevingsplan": 0, "Omgevingsverordening": 1, "Waterschapsverordening": 2}
BRON = "DSO Presenteren (Ozon)"


def omgevingsplan_op_locatie(locatie: dict, ozon_connector, max_regelingen: int = 3,
                             max_regelteksten: int = 5) -> dict | None:
    rd = resolver.wgs84_naar_rd(locatie["lat"], locatie["lon"])
    regelingen = ozon_connector.regelingen_op_punt(rd)   # ConnectorError propageert
    relevant = [r for r in regelingen if r.get("type") in RELEVANTE_TYPES]
    if not relevant:
        return None
    relevant.sort(key=lambda r: _PRIORITEIT.get(r.get("type"), 99))
    top = relevant[0]
    regelteksten = []
    try:
        regelteksten = ozon_connector.regelteksten_op_punt(top["uri"], rd, max_regelteksten)
    except ConnectorError:
        regelteksten = []
    return {
        "regelingen": [{"titel": r["titel"], "type": r["type"], "bevoegd_gezag": r["bevoegd_gezag"]}
                       for r in relevant[:max_regelingen]],
        "top_regeling": top["titel"],
        "regelteksten": regelteksten,
        "locatie_rd": list(rd),
        "aantal_beperkt_tot": max_regelingen,
        "bron": BRON,
    }
```

- [ ] **Step 4: Run om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_omgevingsplan_service.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/omgevingsplan.py tests/test_omgevingsplan_service.py
git commit -m "feat(llab): omgevingsplan-service (type-filter + top-1 best-effort regelteksten)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: chatbot — `omgevingsplan_fn` + prompt-sectie

**Files:**
- Modify: `src/leefomgevinglab/usecases/vergunningen/chatbot.py`
- Test: `tests/test_chatbot.py`

**Interfaces:**
- Consumes: `ConnectorError`; een `omgevingsplan_fn` callable `(locatie) -> dict|None`.
- Produces:
  - `build_prompt(vraag, passages, regels=None, omgevingsplan=None)` — voegt een omgevingsplan-sectie
    toe als `omgevingsplan` regelingen bevat.
  - `beantwoord(..., locatie=None, regels_fn=None, omgevingsplan_fn=None)` — berekent `omgevingsplan`
    onafhankelijk (achter `try/except ConnectorError`) en zet het veld `omgevingsplan` op elk return-pad.

- [ ] **Step 1: Schrijf de falende tests**

Voeg toe aan `tests/test_chatbot.py` (helpers `_Store`, `_Resp`, `_embed_ok`, `LOC` bestaan al):

```python
_OP_OK = {
    "regelingen": [{"titel": "Omgevingsplan Z", "type": "Omgevingsplan", "bevoegd_gezag": "gem Z"}],
    "top_regeling": "Omgevingsplan Z", "regelteksten": ["Bouwregels"],
    "locatie_rd": [139784.0, 442870.0], "aantal_beperkt_tot": 3, "bron": "DSO Presenteren (Ozon)",
}


def test_build_prompt_met_omgevingsplan_voegt_sectie_toe():
    p = chatbot.build_prompt("mag ik bouwen?", [{"text": "c", "url": "u1"}], None, _OP_OK)
    assert "omgevingsdocumenten" in p.lower() or "geldt" in p.lower()
    assert "Omgevingsplan Z" in p


def test_build_prompt_zonder_omgevingsplan_geen_sectie():
    p = chatbot.build_prompt("iets", [{"text": "c", "url": "u1"}])
    assert "Omgevingsplan Z" not in p


def test_beantwoord_met_omgevingsplan(monkeypatch):
    store = _Store([{"text": "x", "url": "https://iplo.nl/a", "score": 0.9}])
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["messages"][0]["content"]
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("mag ik bouwen?", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, omgevingsplan_fn=lambda loc: _OP_OK)
    assert out["omgevingsplan"] == _OP_OK
    assert "Omgevingsplan Z" in captured["prompt"]
    assert out["beschikbaar"] is True


def test_beantwoord_zonder_locatie_geen_omgevingsplan(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])
    called = {"n": 0}

    def op_fn(loc):
        called["n"] += 1
        return _OP_OK

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok, llm_base_url="http://x/v1", model="qwen",
                             omgevingsplan_fn=op_fn)
    assert out["omgevingsplan"] is None
    assert called["n"] == 0


def test_beantwoord_ozon_down_rag_blijft(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])

    def op_boom(loc):
        raise ConnectorError("ozon down")

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok, llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, omgevingsplan_fn=op_boom)
    assert out["omgevingsplan"] is None
    assert out["beschikbaar"] is True
    assert out["antwoord"] == "ok"
```

- [ ] **Step 2: Run om te zien dat ze falen**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: de nieuwe tests FALEN (onbekende kwarg `omgevingsplan_fn`, `KeyError: 'omgevingsplan'`); bestaande blijven groen.

- [ ] **Step 3: Pas `build_prompt` + `beantwoord` aan**

In `src/leefomgevinglab/usecases/vergunningen/chatbot.py`: voeg `omgevingsplan=None` toe aan
`build_prompt` en bouw de sectie; voeg `omgevingsplan_fn=None` toe aan `beantwoord`.

In `build_prompt`, ná het opbouwen van `dso` en vóór de `return`, toevoegen:

```python
    op_sectie = ""
    if omgevingsplan and omgevingsplan.get("regelingen"):
        namen = "; ".join(
            f"{r.get('titel')} ({r.get('bevoegd_gezag')})" for r in omgevingsplan["regelingen"]
        )
        teksten = ", ".join(omgevingsplan.get("regelteksten") or [])
        op_sectie = (
            "\n\nOP DE LOCATIE GELDENDE OMGEVINGSDOCUMENTEN (DSO Presenteren): " + namen + "."
            + (f" Relevante regels in {omgevingsplan.get('top_regeling')}: {teksten}." if teksten else "")
            + " Gebruik dit om concreet te zijn over wat er op deze plek geldt."
        )
```

Pas de signatuur en de `return` aan: `def build_prompt(vraag, passages, regels=None, omgevingsplan=None)`
en voeg `op_sectie` in de samenstelling toe direct ná `{dso}`:

```python
    return (
        "Je bent een feitelijke assistent over de Omgevingswet. Geef een nuttig, concreet en "
        "indicatief antwoord op basis van de onderstaande bronnen (IPLO-context en, indien aanwezig, "
        "de DSO toepasbare regels). Verzin niets buiten de bronnen; mis je informatie over een deel, "
        "zeg dat eerlijk. Geef geen stellig juridisch ja/nee-besluit over vergunningplicht, maar wees "
        "wel concreet over wat er geldt en welke stap de gebruiker kan zetten. Sluit kort af met de "
        "notie dat het bevoegd gezag het definitieve besluit neemt. Verwijs naar de gebruikte bron(nen)."
        f"{dso}{op_sectie}\n\nContext:\n{context}\n\nVraag: {vraag}"
    )
```

In `beantwoord`: voeg `omgevingsplan_fn=None` toe aan de signatuur (ná `regels_fn=None`). Bereken het
blok ná de `regels`-berekening en vóór de RAG-`try`:

```python
    # Omgevingsplan ("wat geldt hier") — onafhankelijk; mag het RAG-antwoord nooit laten vallen
    omgevingsplan = None
    if locatie and omgevingsplan_fn is not None:
        try:
            op = omgevingsplan_fn(locatie)
            if op:
                omgevingsplan = op
        except ConnectorError:
            omgevingsplan = None
```

Geef `omgevingsplan` door aan `build_prompt(vraag, passages, regels, omgevingsplan)` en voeg
`"omgevingsplan": omgevingsplan` toe aan **elk** return-dict (de ConnectorError-embed-pad, het
geen-passages-pad, het LLM-fout-pad én het happy-pad), naast het bestaande `"regels": regels`.

- [ ] **Step 4: Run om te zien dat ze slagen**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: PASS (bestaande + 5 nieuwe).

- [ ] **Step 5: Volledige suite**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/chatbot.py tests/test_chatbot.py
git commit -m "feat(llab): chatbot weegt omgevingsplan-regels (Ozon) mee als derde bron

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `/api/chat`-route + config + live smoke

**Files:**
- Modify: `src/geluidsmeter/api.py`
- Modify: `core/config.yaml`
- Test: `tests/test_api_chat.py`
- Test (create): `tests/test_ozon_live.py`

**Interfaces:**
- Consumes: `OzonConnector` (Task 1), `omgevingsplan.omgevingsplan_op_locatie` (Task 2),
  `chatbot.beantwoord(..., omgevingsplan_fn=...)` (Task 3); bestaande `_config`, `os`.
- Produces: helper `_ozon_connector()` + een `omgevingsplan_fn`-closure, doorgegeven aan `beantwoord`.

- [ ] **Step 1: Config — voeg `leefomgevinglab.ozon` toe**

Voeg in `core/config.yaml` onder `leefomgevinglab:` (naast `dso:`/`llm:`) toe:

```yaml
  ozon:
    # DSO Ozon Omgevingsdocument Presenteren v8 (pre-productie; x-api-key; RD via Content-Crs OGC-URI).
    base_url: "https://service.pre.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/presenteren/v8"
    api_key_header: "x-api-key"
    max_regelingen: 3
    max_regelteksten: 5
```

- [ ] **Step 2: Schrijf de falende route-wiring-test**

Voeg toe aan `tests/test_api_chat.py` (`_client` bestaat al; vul de config aan met een `ozon`-blok in
`api._config["leefomgevinglab"]` binnen de test):

```python
def test_chat_locatie_geeft_omgevingsplan_door(monkeypatch):
    client = _client(monkeypatch)
    api._config["leefomgevinglab"]["ozon"] = {
        "base_url": "https://x/ozon/v8", "api_key_header": "x-api-key",
        "max_regelingen": 3, "max_regelteksten": 5}

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_op(locatie, ozon_connector, max_regelingen=3, max_regelteksten=5):
        captured["locatie"] = locatie
        return {"regelingen": [{"titel": "Omgevingsplan Z", "type": "Omgevingsplan", "bevoegd_gezag": "g"}],
                "top_regeling": "Omgevingsplan Z", "regelteksten": [], "locatie_rd": [1.0, 2.0],
                "aantal_beperkt_tot": 3, "bron": "DSO Presenteren (Ozon)"}

    monkeypatch.setattr(api.omgevingsplan_mod, "omgevingsplan_op_locatie", fake_op)

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        op = kw["omgevingsplan_fn"]({"lat": 52.0, "lon": 5.1})   # exerceer de closure
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": None, "omgevingsplan": op,
                "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik bouwen?", "locatie": {"lat": 52.0, "lon": 5.1}})
    assert r.status_code == 200
    assert captured["locatie"] == {"lat": 52.0, "lon": 5.1}
    assert r.json()["omgevingsplan"]["top_regeling"] == "Omgevingsplan Z"
```

- [ ] **Step 3: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: FAIL (`AttributeError: module 'geluidsmeter.api' has no attribute 'omgevingsplan_mod'` / `_ozon_connector`).

- [ ] **Step 4: Bedraad in `src/geluidsmeter/api.py`**

Voeg bij de imports toe (naast `from leefomgevinglab.usecases.vergunningen import resolver as vergunningen_resolver`):

```python
from leefomgevinglab.usecases.vergunningen import omgevingsplan as omgevingsplan_mod
from leefomgevinglab.connectors.ozon import OzonConnector
```

Voeg een helper toe (naast `_dso_connector`):

```python
def _ozon_connector() -> OzonConnector:
    ll = _config.get("leefomgevinglab", {})
    ozon = ll.get("ozon", {})
    return OzonConnector(
        base_url=ozon.get("base_url", ""),
        api_key=os.environ.get("DSO_API_KEY"),
        api_key_header=ozon.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )
```

In `api_chat`, bouw de closure en geef 'm door aan `beantwoord` (naast het bestaande `regels_fn`):

```python
    ozon_cfg = _config.get("leefomgevinglab", {}).get("ozon", {})

    def omgevingsplan_fn(locatie: dict):
        return omgevingsplan_mod.omgevingsplan_op_locatie(
            locatie, _ozon_connector(),
            max_regelingen=ozon_cfg.get("max_regelingen", 3),
            max_regelteksten=ozon_cfg.get("max_regelteksten", 5),
        )
```

en voeg `omgevingsplan_fn=omgevingsplan_fn` toe aan de `chatbot.beantwoord(...)`-aanroep. Werk ook de
`store is None`-vroege return bij: voeg `"omgevingsplan": None` toe (naast `"regels": None`).

- [ ] **Step 5: Run om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: PASS.

- [ ] **Step 6: Schrijf de live smoke-test**

`tests/test_ozon_live.py`:

```python
"""Live smoke tegen Ozon pre-prod. Skipt zonder DSO_API_KEY."""
import os
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DSO_API_KEY"),
                                reason="DSO_API_KEY niet gezet; live-test overgeslagen")

OZON = "https://service.pre.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/presenteren/v8"


def test_live_regelingen_op_punt(tmp_path):
    from leefomgevinglab.connectors.ozon import OzonConnector
    c = OzonConnector(base_url=OZON, api_key=os.environ["DSO_API_KEY"], cache_dir=str(tmp_path))
    regelingen = c.regelingen_op_punt((139784.0, 442870.0))
    assert len(regelingen) >= 1
    assert all("type" in r and "titel" in r for r in regelingen)
```

- [ ] **Step 7: Volledige suite (regressie) + commit**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen; `test_ozon_live.py` draait mét key (of skipt).

```bash
git add src/geluidsmeter/api.py core/config.yaml tests/test_api_chat.py tests/test_ozon_live.py
git commit -m "feat(llab): /api/chat geeft omgevingsplan-regels (Ozon) door + config + live smoke

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — "Wat geldt hier"-kaartje in `chat.html`

**Files:**
- Modify: `src/leefomgevinglab/static/chat.html`

**Interfaces:**
- Consumes (HTTP): `/api/chat`-respons met `omgevingsplan` (of `null`).
- Produces: een tweede kaartje onder het antwoord dat de geldende regelingen (titel + type + bevoegd
  gezag) en eventuele regelteksten toont.

> Handmatige verificatie (geen unit-test voor HTML); de data-paden zijn in Task 1-4 getest.

- [ ] **Step 1: Voeg een `omgevingsplanHtml`-renderer toe en roep 'm aan**

In de `<script>` van `chat.html`, naast de bestaande `regelsHtml(r)`-functie, toevoegen (gebruik de
bestaande `esc()`-helper — geen rauwe innerHTML):

```javascript
    function omgevingsplanHtml(o) {
      if (!o || !(o.regelingen || []).length) return "";
      const items = o.regelingen.map(r =>
        '<li>' + esc(r.titel) + ' <span class="muted">(' + esc(r.type) + ' – ' + esc(r.bevoegd_gezag) + ')</span></li>'
      ).join("");
      const teksten = (o.regelteksten || []).map(t => esc(t)).join(" · ");
      return '<div class="regels"><h4>Wat geldt hier (omgevingsdocumenten)</h4>' +
        '<ul style="margin:4px 0 0;padding-left:18px">' + items + '</ul>' +
        (teksten ? '<div class="alt">Regels in ' + esc(o.top_regeling) + ': ' + teksten + '</div>' : '') +
        '<div class="alt">Bron: ' + esc(o.bron) + '</div></div>';
    }
```

Pas de antwoord-rendering aan zodat het kaartje ná `regelsHtml(d.regels)` verschijnt. Zoek de regel die
`regelsHtml(d.regels)` invoegt en voeg `omgevingsplanHtml(d.omgevingsplan)` direct erna toe, bv.:

```javascript
        pending.innerHTML =
          (d.antwoord ? "<p>" + esc(d.antwoord) + "</p>" : "<p><em>Geen IPLO-antwoord; zie regels hieronder.</em></p>") +
          regelsHtml(d.regels) +
          omgevingsplanHtml(d.omgevingsplan) +
          (bronnen ? '<div class="bronnen">Bronnen:<br>' + bronnen + "</div>" : "") +
          '<div class="disc">' + esc(d.disclaimer) + "<br>" + esc(d.vangnet) + "</div>";
```

Werk ook de degradatie-conditie bij zodat het kaartje ook toont als er alleen omgevingsplan-data is:
de bestaande `if (!d.beschikbaar && !d.regels)`-tak uitbreiden naar `if (!d.beschikbaar && !d.regels && !d.omgevingsplan)`.

- [ ] **Step 2: Herstart + handmatige verificatie**

```bash
sudo systemctl restart geluidsmeter-api
```
Open `/chatbot`, prik een locatie (bv. in een gemeente met omgevingsplan), stel een vraag, en controleer:
1. Onder het antwoord verschijnt "Wat geldt hier (omgevingsdocumenten)" met een lijst regelingen
   (titel + type + bevoegd gezag).
2. Zonder locatie: geen kaartje.
3. Controleer de respons ook met curl:
   `curl -sS -m120 -X POST http://localhost:8792/api/chat -H "Content-Type: application/json" -d '{"vraag":"wat geldt hier?","locatie":{"lat":52.09,"lon":5.12}}'`
   → veld `omgevingsplan` gevuld (of `null` als er geen relevante regeling is).
Noteer de uitkomst in het taakrapport.

- [ ] **Step 3: Commit**

```bash
git add src/leefomgevinglab/static/chat.html
git commit -m "feat(llab): chat-frontend toont 'Wat geldt hier' (omgevingsplan-regelingen)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (vervolg)

- Volledige regeltekst-body (nu alleen opschriften/titels, best-effort).
- Ontwerpregelingen / besluitversies / omgevingsvergunningen.
- Ketenversnelling (parallelle calls), adres→geocoding, multi-turn.

## Self-Review

- **Spec-dekking:** Ozon-connector (regelingen + regelteksten op punt, CRS-URI/headers) → Task 1;
  type-filter + top-1 best-effort + caps → Task 2; derde bron in antwoord (beantwoord/build_prompt) →
  Task 3; route + config + live smoke → Task 4; "Wat geldt hier"-frontend → Task 5; onafhankelijke
  degradatie → Task 2 (regelteksten best-effort) + Task 3 (`try/except ConnectorError`) + tests;
  conservatief contract → prompt-instructie + ongewijzigd blok + vangnet/disclaimer.
- **Placeholders:** geen TBD; alle code-stappen compleet. Het onbevestigde regeltekst-opschrift-veld
  is expliciet als best-effort/robuust gemarkeerd (geen gok die hard faalt).
- **Type-consistentie:** `regelingen_op_punt(geo_rd) -> [{titel,type,bevoegd_gezag,uri}]`,
  `regelteksten_op_punt(uri, geo_rd, max_m) -> [str]`, `omgevingsplan_op_locatie(locatie, ozon, max_regelingen, max_regelteksten) -> dict|None`,
  `beantwoord(..., omgevingsplan_fn)`, `build_prompt(..., omgevingsplan)`, en het respons-veld
  `omgevingsplan` consistent over Task 1→5.
