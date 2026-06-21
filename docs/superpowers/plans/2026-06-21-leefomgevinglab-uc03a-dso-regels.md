# LeefomgevingLab — UC-03a: DSO-connector + regels-opzoeken endpoint (Plan 2a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een DSO-connector op de Registratie Toepasbare Regels + een gestructureerd `/api/regels`-endpoint dat per activiteit (+locatie) teruggeeft wat de regels zeggen, ingepakt in een conservatief antwoordcontract (bronverwijzing, onzekerheid, vangnet). Geen LLM, geen RAG — dat is Plan 2b.

**Architecture:** Nieuwe `DsoConnector` (erft van `BaseConnector`) leest de API-key uit `.env`, bouwt het verzoek naar de DSO RTR-service en geeft de respons door. Een `vergunningen`-service wikkelt het resultaat in het antwoordcontract. Een nieuwe route `POST /api/regels` op de bestaande app (8792) ontsluit het. Live DSO-calls zijn buiten scope tot er een key is; alle tests draaien op mocks.

**Tech Stack:** Python 3.10, FastAPI, httpx, pytest. Bron: DSO Registratie Toepasbare Regels (Samengestelde RTR Services v2).

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src moet op het pad).
- App draait via `uvicorn geluidsmeter.api:app --app-dir src` op poort **8792**; service = `geluidsmeter-api` (systemd). Bestaande routes/gedrag niet wijzigen; bestaande tests blijven groen.
- Nieuwe logica onder `src/leefomgevinglab/`; `src/geluidsmeter/*` alleen additief (één route + helper).
- **DSO-key staat in `.env`** als `DSO_API_KEY` (niet committen; `.env.example` wel bijwerken). Geen key in de repo of config.yaml.
- **Conservatief antwoordcontract is een harde eis:** elk antwoord bevat de regels, een **bronverwijzing**, expliciete **onzekerheid**, en het **vangnet** "raadpleeg het bevoegd gezag — indicatief, geen juridisch besluit". Geen stellige ja/nee-vergunninguitspraak.
- **Bron-eigenaardigheid (onbevestigd):** exacte operatie-pad én de naam van de API-key-header staan in de OpenAPI-spec en zijn nog niet geverifieerd (geen key/spec beschikbaar). Daarom zijn pad + header **config-gedreven** met defaults, en is er een expliciete verify-stap (Task 1, Step 0) voor zodra de key er is. De respons wordt **niet** op gegokte veldnamen genormaliseerd — de connector geeft de JSON door; de veld-mapping is een vervolgstap in Plan 2b.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/
  connectors/
    dso.py                         # DsoConnector(BaseConnector)
  usecases/
    vergunningen/
      __init__.py
      service.py                   # regels_opzoeken() + DISCLAIMER/VANGNET
core/config.yaml                   # + leefomgevinglab.dso-sectie (MODIFY)
.env.example                       # + DSO_API_KEY (MODIFY)
src/geluidsmeter/api.py            # + POST /api/regels + helper (MODIFY)
tests/test_dso_connector.py
tests/test_vergunningen_service.py
tests/test_api_regels.py
```

---

### Task 1: DsoConnector + config + .env

**Files:**
- Create: `src/leefomgevinglab/connectors/dso.py`
- Modify: `core/config.yaml` (voeg `leefomgevinglab.dso` toe)
- Modify: `.env.example` (voeg `DSO_API_KEY` toe)
- Test: `tests/test_dso_connector.py`

**Interfaces:**
- Consumes: `BaseConnector`, `ConnectorError` uit `leefomgevinglab.connectors.base`.
- Produces:
  - `class DsoConnector(BaseConnector)` met constructor
    `DsoConnector(base_url: str, operation_path: str, api_key: str | None, api_key_header: str = "x-api-key", cache_dir: str = ..., timeout: float = 10.0, cache_ttl: int = 3600)`
  - methode `bepaal_regels(activiteit: str, locatie: dict | None = None) -> dict` die de DSO-respons (JSON) teruggeeft. Raise `ConnectorError` als er geen API-key is.

- [ ] **Step 0: Verify-aantekening (geen code, vereist key/spec)**

De exacte `operation_path` en `api_key_header` moeten bevestigd worden tegen de OpenAPI-spec
("ToepasbareRegels-SamengesteldeRTRServices-v2.json") of een live respons zodra `DSO_API_KEY`
beschikbaar is. Base-URL is geverifieerd (zie config). Tot die tijd zijn pad/header configdefaults.
Deze stap levert geen code; noteer 'm in het taakrapport als open punt.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_dso_connector.py`:

```python
import pytest
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.base import ConnectorError


def test_bepaal_regels_builds_request_with_key(tmp_path):
    captured = {}

    class _Dso(DsoConnector):
        def get_json(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return {"resultaat": "ok"}

    c = _Dso(base_url="https://service.omgevingswet.overheid.nl/x/v2/",
             operation_path="_bepaalToepasbareRegels",
             api_key="SECRET", api_key_header="x-api-key", cache_dir=str(tmp_path))
    out = c.bepaal_regels("kappen van een boom", {"lat": 52.0, "lon": 4.0})

    assert captured["url"] == "https://service.omgevingswet.overheid.nl/x/v2/_bepaalToepasbareRegels"
    assert captured["headers"]["x-api-key"] == "SECRET"
    assert captured["params"]["activiteit"] == "kappen van een boom"
    assert out == {"resultaat": "ok"}


def test_bepaal_regels_without_key_raises(tmp_path):
    c = DsoConnector(base_url="https://x/v2/", operation_path="op",
                     api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.bepaal_regels("activiteit X")
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_dso_connector.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.connectors.dso'`

- [ ] **Step 3: Breid `BaseConnector.get_json` uit met optionele headers**

In `src/leefomgevinglab/connectors/base.py`: voeg een `headers`-parameter toe zodat connectors
auth-headers kunnen meesturen. Pas alleen de signatuur + de `httpx.get`-aanroep aan; cache-gedrag
blijft gelijk (headers zitten al in de cache-key via niets — auth verandert de data niet, dus laat
de cache-key ongewijzigd op url+params).

```python
    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        cp = self._cache_path(url, params)
        if cp.exists() and (time.time() - cp.stat().st_mtime) < self.cache_ttl:
            return json.loads(cp.read_text())
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            if cp.exists():
                return json.loads(cp.read_text())
            raise ConnectorError(f"Bron niet beschikbaar: {url}") from exc
        cp.write_text(json.dumps(data))
        return data
```

- [ ] **Step 4: Schrijf de DsoConnector**

`src/leefomgevinglab/connectors/dso.py`:

```python
"""DSO Registratie Toepasbare Regels via de Samengestelde RTR Services.

Live calls vereisen een API-key (DSO_API_KEY in .env). Operatie-pad en
api-key-header zijn config-gedreven; bevestig ze tegen de OpenAPI-spec zodra
de key beschikbaar is. De connector geeft de DSO-respons ongewijzigd door;
veld-mapping gebeurt in Plan 2b.
"""
from .base import BaseConnector, ConnectorError


class DsoConnector(BaseConnector):
    def __init__(self, base_url: str, operation_path: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.operation_path = operation_path.strip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def bepaal_regels(self, activiteit: str, locatie: dict | None = None) -> dict:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.base_url}/{self.operation_path}"
        params = {"activiteit": activiteit}
        if locatie:
            params["lat"] = locatie.get("lat")
            params["lon"] = locatie.get("lon")
        headers = {self.api_key_header: self.api_key}
        return self.get_json(url, params=params, headers=headers)
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_dso_connector.py tests/test_base_connector.py -q`
Expected: PASS (de base-connector-tests blijven groen; de nieuwe DSO-tests slagen)

- [ ] **Step 6: Config + .env.example bijwerken**

Voeg aan `core/config.yaml` onder `leefomgevinglab:` toe (naast `rev:` / `llm:`):

```yaml
  dso:
    # DSO Registratie Toepasbare Regels (Samengestelde RTR Services v2). Base-URL
    # geverifieerd 2026-06-21. operation_path en api_key_header bevestigen tegen
    # de OpenAPI-spec zodra DSO_API_KEY beschikbaar is (zie plan Task 1 Step 0).
    base_url: "https://service.omgevingswet.overheid.nl/publiek/toepasbare-regels/api/samengestelderegistratietoepasbareregelsservices/v2"
    operation_path: "_bepaalToepasbareRegels"
    api_key_header: "x-api-key"
```

Voeg aan `.env.example` toe:

```
# DSO Ontwikkelaarsportaal API-key (vrij aan te vragen). Niet committen in .env.
DSO_API_KEY=
```

- [ ] **Step 7: Commit**

```bash
git add src/leefomgevinglab/connectors/dso.py src/leefomgevinglab/connectors/base.py core/config.yaml .env.example tests/test_dso_connector.py
git commit -m "feat(llab): DsoConnector op Registratie Toepasbare Regels (key uit .env)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Vergunningen-service (antwoordcontract)

**Files:**
- Create: `src/leefomgevinglab/usecases/vergunningen/__init__.py` (leeg)
- Create: `src/leefomgevinglab/usecases/vergunningen/service.py`
- Test: `tests/test_vergunningen_service.py`

**Interfaces:**
- Consumes: `ConnectorError` uit `leefomgevinglab.connectors.base`; een connector-object met
  `bepaal_regels(activiteit, locatie) -> dict` (de `DsoConnector` uit Task 1, maar de service
  hangt alleen af van die methode — dependency injection, makkelijk te mocken).
- Produces:
  - `DISCLAIMER: str`, `VANGNET: str`
  - `regels_opzoeken(activiteit: str, locatie: dict | None, connector) -> dict` met sleutels:
    `vraag`, `regels_ruw` (de DSO-respons of `None`), `bron`, `onzekerheid` (bool), `disclaimer`,
    `vangnet`, `beschikbaar` (bool — False bij ConnectorError).

- [ ] **Step 1: Maak de lege package-marker**

Maak `src/leefomgevinglab/usecases/vergunningen/__init__.py` als leeg bestand.

- [ ] **Step 2: Schrijf de falende test**

`tests/test_vergunningen_service.py`:

```python
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import service


class _FakeConnector:
    def __init__(self, payload=None, error=False):
        self._payload = payload
        self._error = error

    def bepaal_regels(self, activiteit, locatie=None):
        if self._error:
            raise ConnectorError("down")
        return self._payload


def test_regels_opzoeken_bevat_contract():
    conn = _FakeConnector(payload={"regels": ["X"]})
    out = service.regels_opzoeken("kappen van een boom", {"lat": 52.0, "lon": 4.0}, conn)
    assert out["vraag"] == "kappen van een boom"
    assert out["regels_ruw"] == {"regels": ["X"]}
    assert out["beschikbaar"] is True
    assert out["onzekerheid"] is True            # altijd indicatief
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"] == service.DISCLAIMER
    assert "toepasbare regels" in out["bron"].lower()


def test_regels_opzoeken_bron_down_degradeert():
    conn = _FakeConnector(error=True)
    out = service.regels_opzoeken("activiteit X", None, conn)
    assert out["beschikbaar"] is False
    assert out["regels_ruw"] is None
    # contract blijft staan, ook als de bron faalt
    assert out["disclaimer"] == service.DISCLAIMER
    assert "bevoegd gezag" in out["vangnet"]
```

- [ ] **Step 3: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_service.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.vergunningen.service'`

- [ ] **Step 4: Schrijf de service**

`src/leefomgevinglab/usecases/vergunningen/service.py`:

```python
"""UC-03a: regels opzoeken bij de DSO, ingepakt in een conservatief antwoordcontract."""
from leefomgevinglab.connectors.base import ConnectorError

DISCLAIMER = (
    "Indicatief, geen juridisch besluit. De getoonde regels zijn een ruwe weergave "
    "van de Registratie Toepasbare Regels."
)
VANGNET = (
    "Raadpleeg het bevoegd gezag of het Omgevingsloket (omgevingswet.overheid.nl) "
    "voor de officiele vergunning- of meldingsplicht."
)
BRON = "DSO Registratie Toepasbare Regels (Samengestelde RTR Services)"


def regels_opzoeken(activiteit: str, locatie: dict | None, connector) -> dict:
    base = {
        "vraag": activiteit,
        "bron": BRON,
        "onzekerheid": True,
        "disclaimer": DISCLAIMER,
        "vangnet": VANGNET,
    }
    try:
        regels = connector.bepaal_regels(activiteit, locatie)
    except ConnectorError:
        return {**base, "regels_ruw": None, "beschikbaar": False}
    return {**base, "regels_ruw": regels, "beschikbaar": True}
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_service.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/ tests/test_vergunningen_service.py
git commit -m "feat(llab): vergunningen-service met conservatief antwoordcontract

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: REST-route POST /api/regels

**Files:**
- Modify: `src/geluidsmeter/api.py` (imports + helper + route)
- Test: `tests/test_api_regels.py`

**Interfaces:**
- Consumes: `DsoConnector` (Task 1), `vergunningen.service` (Task 2), `ConnectorError`, `os`/`dotenv`
  voor de key uit het milieu.
- Produces (HTTP):
  - `POST /api/regels` body `{"activiteit": str, "locatie": {"lat": float, "lon": float} | null}` →
    het antwoordcontract uit Task 2 (HTTP 200, ook als `beschikbaar=False`).
  - Helper `_dso_connector() -> DsoConnector` (monkeypatchbaar in tests), die de key uit
    `os.environ["DSO_API_KEY"]` leest.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_api_regels.py`:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api


def _client(monkeypatch):
    api._config = {
        "leefomgevinglab": {
            "cache_dir": "/tmp/llab_test_cache",
            "dso": {
                "base_url": "https://x/v2",
                "operation_path": "_bepaalToepasbareRegels",
                "api_key_header": "x-api-key",
            },
        }
    }
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_regels_happy(monkeypatch):
    client = _client(monkeypatch)

    class _FakeConn:
        def bepaal_regels(self, activiteit, locatie=None):
            return {"regels": ["X"], "echo": activiteit}

    monkeypatch.setattr(api, "_dso_connector", lambda: _FakeConn())
    r = client.post("/api/regels", json={"activiteit": "kappen van een boom",
                                         "locatie": {"lat": 52.0, "lon": 4.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["beschikbaar"] is True
    assert body["regels_ruw"]["echo"] == "kappen van een boom"
    assert "bevoegd gezag" in body["vangnet"]
    assert body["disclaimer"]


def test_regels_bron_down_returns_200_unavailable(monkeypatch):
    from leefomgevinglab.connectors.base import ConnectorError
    client = _client(monkeypatch)

    class _FakeConn:
        def bepaal_regels(self, activiteit, locatie=None):
            raise ConnectorError("geen key")

    monkeypatch.setattr(api, "_dso_connector", lambda: _FakeConn())
    r = client.post("/api/regels", json={"activiteit": "activiteit X", "locatie": None})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_regels.py -q`
Expected: FAIL (`AttributeError: module 'geluidsmeter.api' has no attribute '_dso_connector'`)

- [ ] **Step 3: Voeg imports toe bovenaan `src/geluidsmeter/api.py`**

Na de bestaande leefomgevinglab-imports toevoegen:

```python
import os
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.usecases.vergunningen import service as vergunningen_service
```

- [ ] **Step 4: Voeg helper + route toe aan het eind van `src/geluidsmeter/api.py`**

```python
def _dso_connector() -> DsoConnector:
    ll = _config.get("leefomgevinglab", {})
    dso = ll.get("dso", {})
    return DsoConnector(
        base_url=dso.get("base_url", ""),
        operation_path=dso.get("operation_path", ""),
        api_key=os.environ.get("DSO_API_KEY"),
        api_key_header=dso.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


class RegelsRequest(BaseModel):
    activiteit: str
    locatie: dict | None = None


@app.post("/api/regels")
def api_regels(req: RegelsRequest):
    return vergunningen_service.regels_opzoeken(req.activiteit, req.locatie, _dso_connector())
```

- [ ] **Step 5: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_regels.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Run de volledige suite (regressie)**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alle bestaande tests + de nieuwe groen.

- [ ] **Step 7: Commit**

```bash
git add src/geluidsmeter/api.py tests/test_api_regels.py
git commit -m "feat(llab): POST /api/regels (DSO toepasbare regels, conservatief contract)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (Plan 2b en later)

- RAG-pijplijn op IPLO (ingest → chunk → embed via llama.cpp `/v1/embeddings` → lokale vectorstore).
- Conversationele chatbot (LLM die het contract in natuurlijke taal verwoordt) + eval-set.
- Veld-mapping op de echte DSO-respons (vergunningplicht/meldingsplicht/indieningsvereisten) — kan pas zinvol zodra `DSO_API_KEY` + OpenAPI-spec bevestigd zijn.
- Stelselcatalogus / begrippen-verkenner (UC-09): endpoint nog te bevestigen, apart plan.
- Frontend voor de chatbot.

## Self-Review

- **Spec-dekking (ontwerp sectie D):** DSO Toepasbare Regels-bron → Task 1; conservatief antwoordcontract (bron/onzekerheid/vangnet/geen stellige uitspraak) → Task 2 + Task 3; key uit `.env`, mocks, live-deferred → Global Constraints + Task 1 Step 0. RAG/chatbot/eval → expliciet Plan 2b. Stelselcatalogus → expliciet uit scope.
- **Placeholders:** geen TODO/TBD in code; `operation_path`/`api_key_header` zijn concrete config-waarden met een gemarkeerde verify-stap (geen gegokte respons-normalisatie).
- **Type-consistentie:** `DsoConnector.bepaal_regels(activiteit, locatie)`, `get_json(url, params, headers)`, `regels_opzoeken(activiteit, locatie, connector)`, `_dso_connector()` consistent over Task 1→3. `BaseConnector.get_json` krijgt in Task 1 Step 3 de `headers`-param die Task 1 Step 4 gebruikt — bestaande callers (RevConnector) geven geen headers mee en blijven werken (default `None`).
