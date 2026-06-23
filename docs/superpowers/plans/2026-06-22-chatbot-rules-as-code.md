# Rules-as-code in de vergunningen-chatbot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De vergunningen-chatbot (`/chatbot`, `POST /api/chat`) laat de feitelijke DSO toepasbare-regels meewegen: bij een meegestuurde locatie zoekt hij via het bestaande `/api/regels`-pad de werkzaamheid + regelsoorten op, geeft Qwen die mee als context voor het proza-antwoord, én toont het structurele DSO-blok ongewijzigd.

**Architecture:** Additief op de bestaande RAG-chatbot. `chatbot.beantwoord()` krijgt twee optionele trailing-params (`locatie`, `regels_fn`); zonder locatie is het exact de huidige RAG-only chatbot. De `/api/chat`-route bouwt een `regels_fn`-closure over het al-gebouwde `regels_opzoeken(...)`-pad. De frontend (`chat.html`) krijgt een maplibre-kaartprik voor de locatie en rendert een DSO-regels-kaartje.

**Tech Stack:** Python 3.10, FastAPI, httpx, pytest. Frontend: maplibre-gl (zelfde als `/viewer`), PDOK BRT-tiles. Lokale Qwen + bge-m3 RAG (bestaand).

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src op het pad; venv `.venv`).
- App draait via `uvicorn geluidsmeter.api:app --app-dir src` op poort **8792**; service `geluidsmeter-api`. **Na een merge moet de service herstart** om nieuwe code te laden: `sudo systemctl restart geluidsmeter-api`.
- **Additief / backwards compatible:** zonder `locatie` is `/api/chat` exact de huidige RAG-only chatbot. Bestaande tests (`test_chatbot.py`, `test_api_chat.py`, `test_chatbot_eval.py`) blijven groen **zonder wijziging** — nieuwe params zijn optioneel met default `None`.
- **Conservatief contract (harde eis):** `onzekerheid:true`, `disclaimer`, `vangnet` op elk pad; geen stellige vergunninguitspraak. Het DSO-blok gaat **ongewijzigd** (niet door de LLM hervormd) mee; `alternatieven` blijven zichtbaar.
- **Onafhankelijke degradatie:** een fout in de regels-laag mag het RAG-antwoord nooit laten vallen (en omgekeerd). Geen locatie of geen werkzaamheid-match → `regels:null`, RAG draait door.
- **Relevantie:** `regels` wordt alleen gevuld als `regels_opzoeken` `beschikbaar:true` **en** een `gekozen_werkzaamheid` teruggeeft.
- Nieuwe/gewijzigde logica onder `src/leefomgevinglab/`; `src/geluidsmeter/api.py` alleen additief (route + ChatRequest-veld). Frontend in `src/leefomgevinglab/static/chat.html`.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/usecases/vergunningen/chatbot.py   # build_prompt + beantwoord (MODIFY, additief)
src/geluidsmeter/api.py                                 # ChatRequest.locatie + /api/chat regels_fn (MODIFY)
src/leefomgevinglab/static/chat.html                    # maplibre-kaartprik + DSO-blok (MODIFY)
tests/test_chatbot.py                                   # + rules-as-code tests (MODIFY, additief)
tests/test_api_chat.py                                  # + locatie-route test (MODIFY, additief)
```

---

### Task 1: `chatbot.py` — rules-as-code in prompt + beantwoord

**Files:**
- Modify: `src/leefomgevinglab/usecases/vergunningen/chatbot.py`
- Test: `tests/test_chatbot.py`

**Interfaces:**
- Consumes: `ConnectorError`; een `regels_fn` callable `(vraag: str, locatie: dict) -> dict` (de
  `regels_opzoeken`-uitkomst; dependency-injected door de route in Task 2).
- Produces:
  - `build_prompt(vraag: str, passages: list[dict], regels: dict | None = None) -> str` — voegt een
    DSO-sectie toe als `regels` bruikbaar is (`beschikbaar` + `gekozen_werkzaamheid`).
  - `beantwoord(vraag, store, embed_fn, llm_base_url, model, top_k=4, timeout_s=60.0, locatie=None, regels_fn=None) -> dict`
    — bestaand contract + nieuw veld `regels` (de regels-dict of `None`).

- [ ] **Step 1: Schrijf de falende tests**

Voeg aan `tests/test_chatbot.py` toe (de bestaande imports `httpx`, `pytest`, `ConnectorError`, `chatbot`, en de helpers `_Resp`, `_Store`, `_embed_ok` zijn al aanwezig en blijven ongewijzigd):

```python
_REGELS_OK = {
    "beschikbaar": True,
    "gekozen_werkzaamheid": {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen",
                             "match_onderbouwing": "Enige kandidaat", "zekerheid_match": "midden"},
    "alternatieven": [],
    "typeringen": ["Conclusie", "Indieningsvereisten"],
    "indieningsvereisten": None,
    "indieningsvereisten_status": "niet_beschikbaar_op_locatie",
    "locatie_rd": [80474.8, 455194.3],
    "bron": "DSO Toepasbare Regels (Zoek + RTR + Uitvoeren)",
}
_REGELS_GEEN_MATCH = {"beschikbaar": False, "gekozen_werkzaamheid": None, "alternatieven": []}
LOC = {"lat": 52.08, "lon": 4.30}


def test_build_prompt_met_regels_voegt_dso_sectie_toe():
    p = chatbot.build_prompt("mag ik een dakkapel plaatsen?",
                             [{"text": "context", "url": "u1"}], _REGELS_OK)
    assert "DSO Toepasbare Regels" in p
    assert "Dakkapel plaatsen" in p
    assert "Conclusie" in p


def test_build_prompt_zonder_regels_geen_dso_sectie():
    p = chatbot.build_prompt("iets", [{"text": "context", "url": "u1"}])
    assert "DSO Toepasbare Regels" not in p


def test_beantwoord_met_locatie_en_match(monkeypatch):
    store = _Store([{"text": "Voor een dakkapel geldt soms een melding.", "url": "https://iplo.nl/a", "score": 0.9}])
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["messages"][0]["content"]
        return _Resp({"choices": [{"message": {"content": "Mogelijk een melding."}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("mag ik een dakkapel plaatsen?", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b",
                             locatie=LOC, regels_fn=lambda v, l: _REGELS_OK)
    assert out["beschikbaar"] is True
    assert out["antwoord"] == "Mogelijk een melding."
    assert out["regels"] == _REGELS_OK
    assert "Dakkapel plaatsen" in captured["prompt"]   # Qwen kreeg de DSO-context mee


def test_beantwoord_zonder_locatie_geen_regels(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])
    called = {"n": 0}

    def regels_fn(v, l):
        called["n"] += 1
        return _REGELS_OK

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen", regels_fn=regels_fn)
    assert out["regels"] is None
    assert called["n"] == 0           # zonder locatie niet aangeroepen
    assert out["beschikbaar"] is True


def test_beantwoord_geen_werkzaamheid_match_geen_regels(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets vaags", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, regels_fn=lambda v, l: _REGELS_GEEN_MATCH)
    assert out["regels"] is None
    assert out["beschikbaar"] is True


def test_beantwoord_regels_bron_down_rag_blijft(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])

    def boom(v, l):
        raise ConnectorError("regels down")

    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, regels_fn=boom)
    assert out["regels"] is None            # regels-laag faalde
    assert out["beschikbaar"] is True       # RAG-antwoord blijft
    assert out["antwoord"] == "ok"


def test_beantwoord_rag_down_regels_blijft(monkeypatch):
    def embed_boom(texts):
        raise ConnectorError("embed down")

    store = _Store([])
    out = chatbot.beantwoord("mag ik een dakkapel plaatsen?", store, embed_boom,
                             llm_base_url="http://x/v1", model="qwen",
                             locatie=LOC, regels_fn=lambda v, l: _REGELS_OK)
    assert out["beschikbaar"] is False      # RAG faalde
    assert out["antwoord"] is None
    assert out["regels"] == _REGELS_OK      # regels overleven onafhankelijk
```

- [ ] **Step 2: Run de tests om te zien dat ze falen**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: de nieuwe tests FALEN (o.a. `TypeError` op onbekende kwargs `locatie`/`regels_fn`, en `KeyError: 'regels'`). De 3 bestaande tests blijven slagen.

- [ ] **Step 3: Pas `build_prompt` + `beantwoord` aan**

Vervang in `src/leefomgevinglab/usecases/vergunningen/chatbot.py` de functies `build_prompt` en `beantwoord` door:

```python
def build_prompt(vraag: str, passages: list[dict], regels: dict | None = None) -> str:
    context = "\n\n".join(f"[bron: {p['url']}]\n{p['text']}" for p in passages)
    dso = ""
    if regels and regels.get("beschikbaar") and regels.get("gekozen_werkzaamheid"):
        wz = regels["gekozen_werkzaamheid"]
        typeringen = ", ".join(regels.get("typeringen") or []) or "geen"
        dso = (
            "\n\nVolgens de DSO Toepasbare Regels geldt voor deze activiteit op de gekozen "
            f"locatie de werkzaamheid '{wz.get('omschrijving')}' met regelsoorten: {typeringen}. "
            "Dit is de best passende werkzaamheid en hoeft niet exact de vraag te zijn. Trek geen "
            "stellige conclusie over vergunningplicht; verwijs naar het bevoegd gezag."
        )
    return (
        "Je bent een feitelijke assistent over de Omgevingswet. Beantwoord de vraag "
        "uitsluitend op basis van onderstaande context. Verzin niets; trek geen juridische "
        "conclusies en doe geen stellige uitspraak over vergunningplicht. Als de context "
        "geen antwoord geeft, zeg dat eerlijk. Verwijs naar de gebruikte bron(nen)."
        f"{dso}\n\nContext:\n{context}\n\nVraag: {vraag}"
    )


def beantwoord(vraag: str, store, embed_fn, llm_base_url: str, model: str,
               top_k: int = 4, timeout_s: float = 60.0,
               locatie: dict | None = None, regels_fn=None) -> dict:
    base = {
        "vraag": vraag,
        "onzekerheid": True,
        "disclaimer": DISCLAIMER,
        "vangnet": VANGNET,
    }
    # DSO-regels (onafhankelijk; mag het RAG-antwoord nooit laten vallen)
    regels = None
    if locatie and regels_fn is not None:
        try:
            r = regels_fn(vraag, locatie)
            if r and r.get("beschikbaar") and r.get("gekozen_werkzaamheid"):
                regels = r
        except ConnectorError:
            regels = None

    # RAG over IPLO
    try:
        qvec = embed_fn([vraag])[0]
        passages = store.search(qvec, top_k)
    except ConnectorError:
        return {**base, "antwoord": None, "bronnen": [], "regels": regels, "beschikbaar": False}
    if not passages:
        return {**base, "antwoord": None, "bronnen": [], "regels": regels, "beschikbaar": False}

    prompt = build_prompt(vraag, passages, regels)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        antwoord = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return {**base, "antwoord": None, "bronnen": [], "regels": regels, "beschikbaar": False}

    bronnen = list(dict.fromkeys(p["url"] for p in passages))
    return {**base, "antwoord": antwoord, "bronnen": bronnen, "regels": regels, "beschikbaar": True}
```

> **Noot:** alleen `ConnectorError` wordt rond de regels-laag gevangen (dat is wat `regels_opzoeken`
> en zijn connectors werpen bij bron-uitval; de service degradeert intern al). Een programmeerfout
> blijft zo zichtbaar i.p.v. stil ingeslikt.

- [ ] **Step 4: Run de tests om te zien dat ze slagen**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: PASS — de 3 bestaande + 7 nieuwe tests groen.

- [ ] **Step 5: Volledige suite (regressie op chatbot-eval e.d.)**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alle bestaande tests (incl. `test_chatbot_eval.py`, `test_api_chat.py`) blijven groen.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/chatbot.py tests/test_chatbot.py
git commit -m "feat(llab): chatbot weegt DSO-regels mee (rules-as-code naast RAG)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `/api/chat` route — optionele locatie + regels_fn

**Files:**
- Modify: `src/geluidsmeter/api.py` (`ChatRequest` + `api_chat`)
- Test: `tests/test_api_chat.py`

**Interfaces:**
- Consumes: `chatbot.beantwoord(...)` met de nieuwe `locatie`/`regels_fn` params (Task 1);
  bestaande helpers `_rag_store()`, `_rag_embed_fn()`, `_zoek_connector()`, `_dso_connector()`,
  `_llm_cfg()`, en `vergunningen_service.regels_opzoeken(...)`.
- Produces (HTTP): `POST /api/chat` body `{"vraag": str, "locatie": {"lat": float, "lon": float} | null}`
  → het chat-contract + veld `regels` (de regels-dict of `null`). Geen locatie → RAG-only (`regels:null`).

- [ ] **Step 1: Schrijf de falende test**

Voeg aan `tests/test_api_chat.py` toe (bestaande `_client` + tests blijven ongewijzigd):

```python
def test_chat_met_locatie_geeft_regels_door(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "https://iplo.nl/a", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        captured.update(kw)
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": {"gekozen_werkzaamheid": {"urn": "X"}},
                "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik een dakkapel?", "locatie": {"lat": 52.0, "lon": 4.3}})
    assert r.status_code == 200
    assert captured["locatie"] == {"lat": 52.0, "lon": 4.3}
    assert callable(captured["regels_fn"])
    assert r.json()["regels"] == {"gekozen_werkzaamheid": {"urn": "X"}}


def test_chat_zonder_locatie_locatie_none(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))

    captured = {}

    def fake_beantwoord(vraag, store, embed_fn, **kw):
        captured.update(kw)
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": None,
                "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "iets"})
    assert r.status_code == 200
    assert captured["locatie"] is None
    assert r.json()["regels"] is None


def test_chat_no_index_regels_none(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_rag_store", lambda: None)
    r = client.post("/api/chat", json={"vraag": "iets", "locatie": {"lat": 52.0, "lon": 4.3}})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
    assert r.json()["regels"] is None
```

- [ ] **Step 2: Run de test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: FAIL — `captured["locatie"]`/`regels_fn` ontbreken (route geeft ze nog niet door) en `regels`-veld mist in het no-index-pad.

- [ ] **Step 3: Pas `ChatRequest` + `api_chat` aan in `src/geluidsmeter/api.py`**

Vervang het bestaande blok (`class ChatRequest` t/m de `return chatbot.beantwoord(...)` in `api_chat`) door:

```python
class ChatRequest(BaseModel):
    vraag: str
    locatie: dict | None = None


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    store = _rag_store()
    if store is None:
        return {
            "vraag": req.vraag, "antwoord": None, "bronnen": [], "regels": None, "onzekerheid": True,
            "disclaimer": chatbot.DISCLAIMER, "vangnet": chatbot.VANGNET, "beschikbaar": False,
        }
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    llm = _config.get("leefomgevinglab", {}).get("llm", {})

    def regels_fn(vraag: str, locatie: dict) -> dict:
        return vergunningen_service.regels_opzoeken(
            vraag, locatie, _zoek_connector(), _dso_connector(), _llm_cfg()
        )

    return chatbot.beantwoord(
        req.vraag, store, _rag_embed_fn(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"),
        top_k=rag.get("top_k", 4), timeout_s=llm.get("timeout_s", 60),
        locatie=req.locatie, regels_fn=regels_fn,
    )
```

- [ ] **Step 4: Run de test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: PASS — de 2 bestaande + 3 nieuwe tests groen.

- [ ] **Step 5: Volledige suite (regressie)**

Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen.

- [ ] **Step 6: Commit**

```bash
git add src/geluidsmeter/api.py tests/test_api_chat.py
git commit -m "feat(llab): /api/chat accepteert optionele locatie + geeft DSO-regels door

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — kaartprik + DSO-regels-kaartje in `chat.html`

**Files:**
- Modify: `src/leefomgevinglab/static/chat.html`

**Interfaces:**
- Consumes (HTTP): `POST /api/chat` met body `{vraag, locatie}`; respons met `regels` (of `null`).
- Produces: een maplibre-kaart (klik = locatie-pin → `locatie:{lat,lon}`) en een "DSO-regels"-kaartje
  onder het antwoord.

> Frontend wordt **handmatig geverifieerd** tegen de draaiende service (geen unit-test voor HTML).
> De data-paden eronder zijn in Task 1/2 wél getest.

- [ ] **Step 1: Vervang de inhoud van `src/leefomgevinglab/static/chat.html`**

Vervang het volledige bestand door (maplibre toegevoegd in `<head>`, kaart + status onder het vraagveld, DSO-blok-rendering in het script):

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LeefomgevingLab — Vergunningen-chatbot</title>
  <link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet" />
  <script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #080c14; color: #e0e6ed; }
    header { background: #0d1b2a; border-bottom: 1px solid #1a3a5c; padding: 12px 18px; }
    header a { color: #2ecc8f; text-decoration: none; font-size: 13px; }
    main { max-width: 760px; margin: 0 auto; padding: 18px; }
    h1 { font-size: 18px; color: #eafff6; margin: 0 0 4px; }
    .muted { color: #8aa0b2; font-size: 12px; }
    #map { height: 220px; border-radius: 8px; border: 1px solid #1a3a5c; margin: 12px 0 6px; }
    .locrow { display: flex; align-items: center; gap: 10px; font-size: 12px; color: #8aa0b2; margin-bottom: 10px; }
    .locrow button { padding: 4px 10px; font-size: 12px; }
    #log { margin: 16px 0; display: flex; flex-direction: column; gap: 12px; }
    .msg { padding: 10px 12px; border-radius: 8px; font-size: 14px; line-height: 1.5; }
    .user { background: #14202e; align-self: flex-end; max-width: 80%; }
    .bot { background: #0d1b2a; border: 1px solid #1a3a5c; }
    .bronnen { font-size: 11px; color: #8aa0b2; margin-top: 8px; }
    .bronnen a { color: #4fc3f7; }
    .disc { font-size: 11px; color: #b89; margin-top: 8px; }
    .regels { margin-top: 10px; padding: 10px; border-radius: 8px; background: #0a1626; border: 1px solid #1f4068; }
    .regels h4 { margin: 0 0 6px; font-size: 13px; color: #7fd8ff; }
    .chip { display: inline-block; background: #14304a; color: #bfe6ff; border-radius: 10px; padding: 2px 8px; font-size: 11px; margin: 2px 4px 2px 0; }
    .regels .alt { font-size: 11px; color: #8aa0b2; margin-top: 6px; }
    .regels .status { font-size: 11px; color: #c9b78a; margin-top: 6px; }
    form { display: flex; gap: 8px; }
    input { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #1a3a5c; background: #0a1220; color: #e0e6ed; }
    button { padding: 10px 16px; border-radius: 8px; border: none; background: #2ecc8f; color: #042; font-weight: 700; cursor: pointer; }
  </style>
</head>
<body>
  <header><a href="/">← LeefomgevingLab</a></header>
  <main>
    <h1>Vergunningen-chatbot</h1>
    <p class="muted">Vraag indicatief wat de regels zeggen over een activiteit. Prik een locatie op de kaart voor de feitelijke DSO-regels op die plek. Geen juridisch besluit.</p>
    <div id="map"></div>
    <div class="locrow">
      <span id="locstat">Geen locatie gekozen — antwoord is dan alleen op basis van IPLO-tekst.</span>
      <button type="button" id="clearloc">wis locatie</button>
    </div>
    <div id="log"></div>
    <form id="f">
      <input id="q" placeholder="bv. mag ik een dakkapel plaatsen?" autocomplete="off" />
      <button>Vraag</button>
    </form>
  </main>
  <script>
    const STATUS_TEKST = {
      beschikbaar: "indieningsvereisten beschikbaar",
      niet_beschikbaar_op_locatie: "geen indieningsvereisten gevonden op deze locatie",
      bron_tijdelijk_niet_beschikbaar: "indieningsvereisten-bron tijdelijk niet beschikbaar",
      niet_beschikbaar: "niet beschikbaar",
    };
    const map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        sources: { brt: { type: "raster",
          tiles: ["https://service.pdok.nl/brt/achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png"],
          tileSize: 256, attribution: "PDOK BRT-achtergrondkaart" } },
        layers: [{ id: "brt", type: "raster", source: "brt" }]
      },
      center: [4.27, 51.885], zoom: 11
    });
    let locatie = null, marker = null;
    const locstat = document.getElementById("locstat");
    map.on("click", (e) => {
      locatie = { lat: e.lngLat.lat, lon: e.lngLat.lng };
      if (marker) marker.remove();
      marker = new maplibregl.Marker({ color: "#2ecc8f" }).setLngLat(e.lngLat).addTo(map);
      locstat.textContent = "Locatie: " + locatie.lat.toFixed(5) + ", " + locatie.lon.toFixed(5);
    });
    document.getElementById("clearloc").addEventListener("click", () => {
      locatie = null; if (marker) { marker.remove(); marker = null; }
      locstat.textContent = "Geen locatie gekozen — antwoord is dan alleen op basis van IPLO-tekst.";
    });

    const log = document.getElementById("log");
    function add(cls, html) { const d = document.createElement("div"); d.className = "msg " + cls; d.innerHTML = html; log.appendChild(d); d.scrollIntoView(); return d; }
    function esc(s) { const t = document.createElement("span"); t.textContent = s == null ? "" : String(s); return t.innerHTML; }

    function regelsHtml(r) {
      if (!r || !r.gekozen_werkzaamheid) return "";
      const wz = r.gekozen_werkzaamheid;
      const chips = (r.typeringen || []).map(t => '<span class="chip">' + esc(t) + "</span>").join("");
      const alts = (r.alternatieven || []).map(a => esc(a.omschrijving)).join(" · ");
      const status = STATUS_TEKST[r.indieningsvereisten_status] || esc(r.indieningsvereisten_status);
      return '<div class="regels"><h4>DSO toepasbare regels (indicatief)</h4>' +
        "<div><strong>" + esc(wz.omschrijving) + "</strong> <span class=\"muted\">(" + esc(wz.zekerheid_match) + " zekerheid)</span></div>" +
        (chips ? "<div style=\"margin-top:6px\">" + chips + "</div>" : "") +
        '<div class="status">Indieningsvereisten: ' + status + "</div>" +
        (alts ? '<div class="alt">Bedoelde je ook: ' + alts + "</div>" : "") +
        '<div class="alt">Bron: ' + esc(r.bron) + "</div></div>";
    }

    document.getElementById("f").addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = document.getElementById("q").value.trim();
      if (!q) return;
      add("user", esc(q));
      document.getElementById("q").value = "";
      const pending = add("bot", "Bezig…");
      try {
        const body = { vraag: q };
        if (locatie) body.locatie = locatie;
        const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const d = await r.json();
        if (!d.beschikbaar && !d.regels) {
          pending.innerHTML = '<p>Geen antwoord beschikbaar (index of model offline).</p><div class="disc">' + esc(d.vangnet) + '</div>';
          return;
        }
        const bronnen = (d.bronnen || []).map(u => '<a href="' + esc(u) + '" target="_blank">' + esc(u) + "</a>").join("<br>");
        pending.innerHTML =
          (d.antwoord ? "<p>" + esc(d.antwoord) + "</p>" : "<p><em>Geen IPLO-antwoord; zie DSO-regels hieronder.</em></p>") +
          regelsHtml(d.regels) +
          (bronnen ? '<div class="bronnen">Bronnen:<br>' + bronnen + "</div>" : "") +
          '<div class="disc">' + esc(d.disclaimer) + "<br>" + esc(d.vangnet) + "</div>";
      } catch (err) { pending.innerHTML = "Er ging iets mis."; }
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Herstart de service en verifieer handmatig**

```bash
sudo systemctl restart geluidsmeter-api
```
Open `http://localhost:8792/chatbot` (of de publieke URL) en controleer:
1. Kaart laadt (PDOK BRT). Klik → groene marker + "Locatie: …" verschijnt.
2. Vraag "mag ik een dakkapel plaatsen?" mét locatie → antwoord + een **DSO-regels-kaartje**
   (werkzaamheid "Dakkapel plaatsen", chips "Conclusie"/"Indieningsvereisten", status-regel, bron).
3. "wis locatie" → vraag opnieuw → géén DSO-kaartje, gewoon RAG-antwoord.
4. Een niet-activiteit-vraag mét locatie → geen (of leeg) DSO-kaartje, RAG-antwoord blijft.

Noteer de uitkomst van elke stap in het taakrapport (handmatige verificatie vervangt hier de unit-test).

- [ ] **Step 3: Commit**

```bash
git add src/leefomgevinglab/static/chat.html
git commit -m "feat(llab): chat-frontend met kaartprik-locatie + DSO-regels-kaartje

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Activiteit-extractie — vraag → kale werkzaamheid-term

**Reden (live bevonden 2026-06-23):** de ZoekInterface matcht niet op een hele vraag
("mag ik een dakkapel plaatsen?" → 0 kandidaten) maar wél op de kale activiteit
("dakkapel plaatsen" → `DakkapelPlaatsen`). Zonder extractie geeft de chatbot daarom op echte
vragen géén regels-blok. Deze taak haalt de kale activiteit uit de vraag vóór de ZoekInterface.

**Files:**
- Modify: `src/leefomgevinglab/usecases/vergunningen/resolver.py` (+ `extract_activiteit`)
- Modify: `src/geluidsmeter/api.py` (regels_fn-closure gebruikt de extractie)
- Test: `tests/test_vergunningen_resolver.py` (+ extractie-tests), `tests/test_api_chat.py` (+ wiring-test)

**Interfaces:**
- Produces: `extract_activiteit(vraag: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> str`
  — Qwen haalt de kale activiteit-woordgroep uit de vraag; bij élke fout val terug op de ruwe `vraag`
  (nooit slechter dan nu).
- Consumes (api.py): de extractie in de `regels_fn`-closure; `vergunningen_resolver.extract_activiteit`.

- [ ] **Step 1: Schrijf de falende resolver-tests**

Voeg toe aan `tests/test_vergunningen_resolver.py` (imports `httpx`, `resolver` zijn al aanwezig):

```python
def test_extract_activiteit_haalt_kale_woordgroep(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(200, json={"choices": [{"message": {"content": "dakkapel plaatsen"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = resolver.extract_activiteit("mag ik een dakkapel plaatsen in mijn tuin?", "http://llm/v1", "qwen")
    assert out == "dakkapel plaatsen"


def test_extract_activiteit_valt_terug_op_vraag_bij_fout(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    vraag = "mag ik een dakkapel plaatsen?"
    assert resolver.extract_activiteit(vraag, "http://llm/v1", "qwen") == vraag


def test_extract_activiteit_lege_output_valt_terug(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    vraag = "iets vaags"
    assert resolver.extract_activiteit(vraag, "http://llm/v1", "qwen") == vraag
```

- [ ] **Step 2: Run om te zien dat ze falen**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_resolver.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'extract_activiteit'`).

- [ ] **Step 3: Implementeer `extract_activiteit` in `resolver.py`**

Voeg toe (onder de bestaande imports/`kies_werkzaamheid`):

```python
def extract_activiteit(vraag: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> str:
    prompt = (
        "Haal uit de volgende vraag de kale activiteit/werkzaamheid als korte zelfstandige "
        "woordgroep, zonder vraagwoorden, locatie of leestekens. Geef UITSLUITEND die woordgroep "
        "terug, niets anders.\n\n"
        f"Vraag: {vraag}\nActiviteit:"
    )
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.0},
            timeout=timeout_s,
        )
        if resp.status_code >= 400:
            raise httpx.HTTPError(f"HTTP {resp.status_code}")
        tekst = resp.json()["choices"][0]["message"]["content"].strip()
        return tekst or vraag
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        return vraag
```

- [ ] **Step 4: Run om te zien dat ze slagen**

Run: `PYTHONPATH=src python -m pytest tests/test_vergunningen_resolver.py -q`
Expected: PASS (bestaande + 3 nieuwe).

- [ ] **Step 5: Schrijf de falende route-wiring-test**

Voeg toe aan `tests/test_api_chat.py`:

```python
def test_chat_locatie_extraheert_activiteit_voor_zoek(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "u", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))
    monkeypatch.setattr(api.vergunningen_resolver, "extract_activiteit", lambda *a, **k: "dakkapel plaatsen")

    captured = {}

    def fake_regels(activiteit, locatie, zc, dc, cfg):
        captured["activiteit"] = activiteit
        return {"beschikbaar": True,
                "gekozen_werkzaamheid": {"urn": "X", "omschrijving": "Dakkapel plaatsen", "zekerheid_match": "midden"},
                "typeringen": ["Conclusie"], "alternatieven": [], "indieningsvereisten_status": "x", "bron": "b"}

    monkeypatch.setattr(api.vergunningen_service, "regels_opzoeken", fake_regels)

    # Laat de echte regels_fn-closure draaien via een beantwoord-mock die hem aanroept:
    def fake_beantwoord(vraag, store, embed_fn, **kw):
        r = kw["regels_fn"](vraag, kw["locatie"])
        return {"vraag": vraag, "antwoord": "ok", "bronnen": [], "regels": r, "onzekerheid": True,
                "disclaimer": "d", "vangnet": "bevoegd gezag", "beschikbaar": True}

    monkeypatch.setattr(api.chatbot, "beantwoord", fake_beantwoord)
    r = client.post("/api/chat", json={"vraag": "mag ik een dakkapel plaatsen?", "locatie": {"lat": 52.0, "lon": 4.3}})
    assert r.status_code == 200
    assert captured["activiteit"] == "dakkapel plaatsen"          # extractie toegepast vóór zoek
    assert r.json()["regels"]["gekozen_werkzaamheid"]["urn"] == "X"
```

- [ ] **Step 6: Run om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: FAIL (`AttributeError: module 'geluidsmeter.api' has no attribute 'vergunningen_resolver'`, of `captured` leeg omdat de extractie nog niet bedraad is).

- [ ] **Step 7: Bedraad de extractie in `src/geluidsmeter/api.py`**

Voeg bij de imports toe (naast de bestaande `from leefomgevinglab.usecases.vergunningen import service as vergunningen_service`):

```python
from leefomgevinglab.usecases.vergunningen import resolver as vergunningen_resolver
```

Vervang in `api_chat` de `regels_fn`-closure door:

```python
    def regels_fn(vraag: str, locatie: dict) -> dict:
        activiteit = vergunningen_resolver.extract_activiteit(
            vraag, llm.get("base_url", "http://localhost:8080/v1"),
            llm.get("model", "qwen2.5-32b"), llm.get("timeout_s", 60),
        )
        return vergunningen_service.regels_opzoeken(
            activiteit, locatie, _zoek_connector(), _dso_connector(), _llm_cfg()
        )
```

- [ ] **Step 8: Run om te zien dat hij slaagt + volledige suite**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py tests/test_vergunningen_resolver.py -q`
Expected: PASS.
Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen.

- [ ] **Step 9: Herstart + live-verificatie**

```bash
sudo systemctl restart geluidsmeter-api
curl -sS -m40 -X POST http://localhost:8792/api/chat -H "Content-Type: application/json" \
  -d '{"vraag":"mag ik een dakkapel plaatsen?","locatie":{"lat":52.08,"lon":4.30}}'
```
Verwacht: `regels` is nu **gevuld** (werkzaamheid `DakkapelPlaatsen`) i.p.v. `null`. Noteer de uitkomst in het taakrapport.

- [ ] **Step 10: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/resolver.py src/geluidsmeter/api.py tests/test_vergunningen_resolver.py tests/test_api_chat.py
git commit -m "feat(llab): extraheer kale activiteit uit chatvraag vóór DSO-zoek

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (vervolg)

- Adres-tekst → geocoding (PDOK Locatieserver); nu alleen kaartprik.
- Gespreksgeschiedenis / multi-turn.
- Interactieve vragenboom / diepere indieningsvereisten-inhoud.

## Self-Review

- **Spec-dekking:** locatie-in (ChatRequest.locatie + kaartprik) → Task 2 + Task 3; rules-as-code
  combineren (Qwen-context + ongewijzigd blok) → Task 1 (`build_prompt`/`beantwoord`) + Task 3
  (rendering); onafhankelijke degradatie → Task 1 (regels vóór RAG, `try/except ConnectorError`) +
  tests `test_beantwoord_regels_bron_down_rag_blijft` / `test_beantwoord_rag_down_regels_blijft`;
  conservatief contract → DSO-sectie-prompt + ongewijzigd blok + vangnet/disclaimer op elk pad;
  relevantie-gating → `beschikbaar` + `gekozen_werkzaamheid`-filter in `beantwoord`.
- **Placeholders:** geen TBD/TODO; alle code-stappen bevatten volledige code. Frontend wordt
  handmatig geverifieerd met concrete checklist (geen vage "test de UI").
- **Type-consistentie:** `build_prompt(vraag, passages, regels=None)`, `beantwoord(vraag, store,
  embed_fn, llm_base_url, model, top_k, timeout_s, locatie, regels_fn)`, `regels_fn(vraag, locatie)`,
  en het respons-veld `regels` consistent over Task 1→3. Bestaande call-sites blijven werken doordat
  `locatie`/`regels_fn` trailing optionals zijn.
