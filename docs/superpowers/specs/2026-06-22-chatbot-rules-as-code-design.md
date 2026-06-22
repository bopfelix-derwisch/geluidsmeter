# Rules-as-code in de vergunningen-chatbot (UC-03b vervolg)

**Datum:** 2026-06-22
**Status:** ontwerp goedgekeurd, klaar voor implementatieplan
**Voorgangers:**
- `docs/superpowers/specs/2026-06-22-dso-regels-resolver-design.md` (`/api/regels` live: resolver + connectors + gelaagd contract)
- UC-03b RAG-chatbot (`/chatbot`, `POST /api/chat`, IPLO + bge-m3 + Qwen)

## Probleem

De chatbot praat nu *over* regels (RAG-uitleg uit IPLO-teksten) maar zoekt ze niet *op*. De
DSO-regels zijn sinds 2026-06-22 live via `/api/regels`, maar staan los van de chatbot. Doel:
de chatbot laat de feitelijke DSO toepasbare-regels meewegen ("rules-as-code") naast de
RAG-uitleg, zonder de conservatieve, niet-juridische toon te verliezen.

## Beslissingen (uit brainstorm)

1. **Locatie via de UI** als expliciete `lat/lon` (kaartprik, Leaflet — zelfde patroon als `/viewer`;
   geen geocoding-afhankelijkheid). De DSO-regels vereisen een RD-punt; de chat had geen locatie.
2. **Qwen-antwoord + apart structureel DSO-blok**: Qwen schrijft één leesbaar antwoord met BEIDE
   bronnen als context; daarnaast geven we het structurele DSO-blok ongewijzigd terug als
   grondwaarheid voor de UI.
3. **Geen nieuw endpoint**: `/api/chat` wordt additief uitgebreid met optioneel `locatie`. Zonder
   locatie = exact de huidige RAG-only chatbot (niets breekt).
4. **Hergebruik** van het bestaande `regels_opzoeken(...)`-pad; de chat-`vraag` gaat als `activiteit`
   rechtstreeks de ZoekInterface in (fuzzy + gerankt; Qwen kiest de beste match). Geen aparte
   activiteit-extractie nu (YAGNI; snelle vervolgstap als matching tegenvalt).
5. **Relevantie eerlijk**: geen zoek-kandidaten → géén DSO-blok (RAG-only). Wel een match → Qwen
   krijgt die mee met de instructie "best passende werkzaamheid, hoeft niet exact de vraag te zijn";
   het blok toont altijd `alternatieven` + `vangnet`.

## Architectuur & data-flow

```
POST /api/chat  {vraag, locatie?: {lat, lon}}              ← locatie optioneel
        │
        ▼
 chatbot.beantwoord(vraag, locatie, store, embed_fn, regels_fn, llm_cfg, top_k)
        │
        ├─A► RAG: embed(vraag) -> store.search(top_k) -> IPLO-passages          (bestaand)
        ├─B► ALS locatie: regels = regels_fn(vraag, locatie)                     (hergebruik /api/regels-pad)
        │        -> gekozen_werkzaamheid + typeringen + alternatieven + status
        └─C► Qwen krijgt IPLO-passages + (optioneel) DSO-samenvatting als context
                 -> één leesbaar antwoord; DSO-blok gaat ongewijzigd mee in de respons
```

### Componenten

- `src/leefomgevinglab/usecases/vergunningen/chatbot.py` (MODIFY) — `beantwoord()` krijgt:
  - extra params `locatie: dict | None` en `regels_fn` (callable `(vraag, locatie) -> regels-dict`,
    dependency-injected zodat de chatbot niet aan connector-constructie raakt en testbaar blijft).
  - `build_prompt(vraag, passages, regels)` (MODIFY) — voegt een compacte DSO-sectie toe als
    `regels` aanwezig én `beschikbaar` is.
- `src/geluidsmeter/api.py` (MODIFY) — `ChatRequest` krijgt optioneel `locatie: dict | None`; de
  `/api/chat`-route bouwt een `regels_fn` (closure over de bestaande `_zoek_connector()`,
  `_dso_connector()`, `_llm_cfg()` + `vergunningen_service.regels_opzoeken`) en geeft die door.
- `src/leefomgevinglab/static/chat.html` (MODIFY) — Leaflet-kaartprik → `locatie`; render het
  DSO-regels-kaartje onder het antwoord.

## Antwoordcontract (`POST /api/chat`)

Additief op het bestaande contract (bestaande velden ongewijzigd):

```jsonc
{
  "vraag": "mag ik een dakkapel plaatsen?",
  "antwoord": "...",                    // Qwen-proza, nu óók bewust van de DSO-regels
  "bronnen": ["https://iplo.nl/..."],   // RAG-bronnen (bestaand)
  "regels": {                           // NIEUW — null als geen locatie of geen match
    "gekozen_werkzaamheid": {"urn": "DakkapelPlaatsen", "omschrijving": "...",
                             "match_onderbouwing": "...", "zekerheid_match": "midden"},
    "alternatieven": [{"urn": "...", "omschrijving": "..."}],
    "typeringen": ["Conclusie", "Indieningsvereisten"],
    "indieningsvereisten": null,
    "indieningsvereisten_status": "bron_tijdelijk_niet_beschikbaar",
    "locatie_rd": [80474.8, 455194.3],
    "bron": "DSO Toepasbare Regels (Zoek + RTR + Uitvoeren)"
  },
  "onzekerheid": true, "disclaimer": "...", "vangnet": "...", "beschikbaar": true
}
```

`regels` is de volledige `regels_opzoeken`-uitkomst (zonder her-vormen), of `null` wanneer:
geen `locatie` meegestuurd; `regels_opzoeken` gaf `beschikbaar:false` (geen kandidaten / zoekbron down);
of de regels-laag wierp onverwacht. `beschikbaar` (top-level) blijft de RAG-beschikbaarheid.

### Prompt

`build_prompt` voegt, alleen bij een bruikbare `regels` (`beschikbaar` + `gekozen_werkzaamheid`),
een sectie toe vóór de vraag:

> "Volgens de DSO Toepasbare Regels geldt voor deze activiteit op de gekozen locatie de werkzaamheid
> '<omschrijving>' met regelsoorten: <typeringen>. Dit is de best passende werkzaamheid en hoeft niet
> exact de vraag te zijn. Trek geen stellige conclusie over vergunningplicht; verwijs naar het bevoegd
> gezag."

De bestaande no-hallucination/geen-juridische-conclusie-instructie blijft staan.

## Degradatie

Onafhankelijke degradatie, zelfde principe als `/api/regels`:

| Situatie | `antwoord` | `regels` | `beschikbaar` |
|---|---|---|---|
| RAG + regels beide ok | proza | gevuld | true |
| Geen locatie | proza (RAG-only) | null | true |
| Locatie, geen zoek-match | proza (RAG-only) | null | true |
| Regels-bron down | proza (RAG-only) | null | true |
| RAG down (embed/store/LLM) | null | mag gevuld zijn | false |

De regels-laag draait achter een `try/except` in `beantwoord()`: een fout daar mag het
RAG-antwoord nooit laten vallen (`regels=null`, RAG blijft staan).

## Frontend (`chat.html`)

- Kleine **Leaflet-kaart** (hergebruik het `/viewer`-patroon: zelfde tile-laag, centrum uit
  `leefomgevinglab.viewer`); klik plaatst een marker → `locatie:{lat,lon}` in de `/api/chat`-body.
  Knop "zonder locatie vragen" stuurt geen locatie (RAG-only).
- Onder het antwoord een **"DSO-regels"-kaartje** (alleen tonen als `regels` niet null):
  gekozen werkzaamheid + omschrijving; typeringen als chips; uitklap met `alternatieven`
  ("bedoelde je…?"); `indieningsvereisten_status` in gewone taal; het vangnet. Visueel gescheiden
  van het proza-antwoord. Property-waarden via `textContent` (geen HTML-injectie).

## Error-handling & testen (TDD, mocks)

- `beantwoord()`-unit-tests (mock `store`/`embed_fn`/`httpx.post`/`regels_fn`):
  (a) locatie + match → prompt bevat DSO-context, `regels` gevuld, `antwoord` gezet;
  (b) geen locatie → `regels_fn` niet aangeroepen, `regels:null`, puur RAG;
  (c) `regels_fn` geeft `beschikbaar:false` → `regels:null`, RAG-antwoord blijft;
  (d) `regels_fn` werpt → `regels:null`, RAG-antwoord blijft (geen crash);
  (e) RAG down (embed werpt `ConnectorError`) → `antwoord:null, beschikbaar:false`.
- `build_prompt`-test: met/zonder `regels` → DSO-sectie wel/niet aanwezig.
- Route-test `/api/chat`: met `locatie` (regels_fn gemockt) en zonder `locatie` (bestaand gedrag);
  bestaande chat-tests blijven groen (locatie is optioneel, default `None`).
- Frontend: handmatige verificatie op de draaiende service (`sudo systemctl restart geluidsmeter-api`),
  kaartprik → antwoord + DSO-blok.

## Buiten scope (vervolg)

- Activiteit-extractie uit de vraag via een aparte LLM-stap (nu: rauwe vraag → ZoekInterface).
- Adres-tekst → geocoding (PDOK Locatieserver); nu alleen kaartprik.
- Gespreksgeschiedenis / multi-turn (chatbot blijft stateless, één vraag).
- Interactieve vragenboom / diepere indieningsvereisten-inhoud (al buiten scope in het regels-spec).

## Self-review-checklist (na schrijven plan)

- Spec-dekking: locatie-in (frontend + ChatRequest) → frontend + api-taak; rules-as-code combineren
  (Qwen + blok) → `beantwoord`/`build_prompt`-taak; onafhankelijke degradatie → degradatie-tabel +
  tests; conservatief contract behouden → prompt + ongewijzigd blok + vangnet.
- Geen placeholders/TBD.
- Type-consistentie `beantwoord(vraag, locatie, store, embed_fn, regels_fn, llm_cfg, top_k)` ↔ route.
