# DSO-regels live: resolver + connector-rewrite + diepere inhoud (UC-03a vervolg)

**Datum:** 2026-06-22
**Status:** ontwerp goedgekeurd, klaar voor implementatieplan
**Voorganger:** `docs/superpowers/plans/2026-06-21-leefomgevinglab-uc03a-dso-regels.md` (connector + `/api/regels` op mocks; Step 0 live geverifieerd 2026-06-22)

## Probleem

`POST /api/regels` degradeert nu altijd naar `beschikbaar:false`. De bestaande `DsoConnector`
bouwt een `GET {activiteit, lat, lon}` die niet bestaat. Het live geverifieerde DSO-contract
wijkt fundamenteel af:

- Keys werken alleen op **pre-productie** (`service.pre.omgevingswet.overheid.nl`); productie geeft 401.
- Header `x-api-key` (bevestigd).
- De API neemt **werkzaamheid-concept-URI's** (`functioneleStructuurRef`), geen vrije tekst.
- Geometrie in **RD/EPSG:28992** (GeoJSON Point), niet WGS84 lat/lon.

Er is dus een vertaallaag (resolver) nodig tussen mensentaal en het DSO-contract, plus een
herschreven connector die het echte POST-protocol spreekt.

## Live geverifieerde bronnen (2026-06-22, met `DSO_API_KEY`)

Alle drie op host `service.pre.omgevingswet.overheid.nl`, header `x-api-key`, JSON.

1. **ZoekInterface** — `/publiek/toepasbare-regels/api/zoekinterface/v2`
   `POST /werkzaamheden/_zoek` body `{"zoekterm": "<vrije tekst>"}` (plain string; leeg = alle).
   → HAL-respons `_embedded.werkzaamheden[]` met `urn`, `omschrijving`, `functioneleStructuurRef`,
   `trefwoorden[]`, gerankt op relevantie. Oefen-catalogus: 293 werkzaamheden.
   Spec: `ToepasbareRegels-ZoekInterface-v2.json` (developer portal /publish/pages/235013/).

2. **Samengestelde RTR Services v2** — `/publiek/toepasbare-regels/api/samengestelderegistratietoepasbareregelsservices/v2`
   `POST /werkzaamheden/_bepaalRegelbeheerobjectTyperingen` body
   `{functioneleStructuurRefs:[<ref>], _geo:{intersects:{type:"Point",coordinates:[x,y]}}, datum?}`.
   → `[{functioneleStructuurRef, regelbeheerobjecten:[...], indirecte_regelbeheerobjecten:[...]}]`.
   Bewezen: dakkapel → `["Conclusie","Indieningsvereisten"]`.
   Ook: `_geef-juridisch-gerelateerden`, `_geef-logisch-gerelateerden`, `_bepaalWerkzaamheidCompleet`,
   `GET /activiteiten/algemeen`. Spec: `ToepasbareRegels-SamengesteldeRTRServices-v2.json` (/publish/pages/165401/).

3. **Uitvoeren services v3** — `/publiek/toepasbare-regels/api/toepasbareregelsuitvoerenservices/v3`
   `POST /indieningsvereisten/_bepaal`, `/conclusie/_bepaal`, `/maatregelen/_bepaal`, `/toelichtingen`.
   Stateless. `IndieningsvereistenRequest` vereist `functioneleStructuurRefs`
   (`{functioneleStructuurRef, antwoorden:[]}`) + `_geo` (RD Point). Header `Content-Crs: EPSG:28992`.
   **Constraint:** vraagt een **activiteit/regelbeheerobject-ref** (niet de werkzaamheid-ref) en is
   locatie-afhankelijk; in oefen schaars (lege juridische relaties op willekeurige punten → keten
   levert vaak niets). Accurate vereisten vereisen het beantwoorden van een vragenboom (`antwoorden`).
   Spec: `ToepasbareRegels-UitvoerenServices-v3.json` (/publish/pages/171046/).

## Architectuur

Drie nieuwe, los testbare units; bestaande route/contract-vorm blijft mensvriendelijk.

```
POST /api/regels  {activiteit, locatie:{lat,lon}}
        │
        ▼
 vergunningen/service.regels_opzoeken()          ← orkestratie + conservatief contract
        │
        ├─1► ZoekConnector.zoek_werkzaamheden(tekst)      [ZoekInterface]   PROVEN
        │        → kandidaten [{urn, omschrijving, trefwoorden, ref}]
        ├─2► resolver.kies_werkzaamheid(vraag, kandidaten) [Qwen]
        │        → beste kandidaat + onderbouwing + zekerheid
        ├─3► resolver.wgs84_naar_rd(lat, lon)             [pyproj EPSG:28992]
        ├─4► DsoConnector.bepaal_typeringen([ref], rd)    [Samengestelde RTR] PROVEN
        │        → ["Conclusie","Indieningsvereisten"]
        └─5► DsoConnector.bepaal_indieningsvereisten(...) [Uitvoeren v3]   best-effort, degradeert
```

### Componenten

- `src/leefomgevinglab/connectors/dso_zoek.py` — **`ZoekConnector(BaseConnector)`**
  - `zoek_werkzaamheden(tekst: str, max_n: int = 5) -> list[dict]` — POST `/werkzaamheden/_zoek`,
    geeft `[{urn, omschrijving, functioneleStructuurRef, trefwoorden}]` (top-N, gerankt).
  - Raise `ConnectorError` zonder key of bij bron-fout.
- `src/leefomgevinglab/connectors/dso.py` — **herschreven `DsoConnector(BaseConnector)`**
  - `bepaal_typeringen(refs: list[str], geo_rd: tuple[float,float], datum: str|None=None) -> list[dict]`
    — POST `_bepaalRegelbeheerobjectTyperingen`.
  - `bepaal_indieningsvereisten(refs: list[str], geo_rd, datum=None) -> list[dict]`
    — POST Uitvoeren v3 `/indieningsvereisten/_bepaal` met `Content-Crs`-header; best-effort.
  - Config-gedreven base-URLs per service (de drie hierboven).
- `src/leefomgevinglab/usecases/vergunningen/resolver.py` — **pure helpers**
  - `kies_werkzaamheid(vraag, kandidaten, llm) -> dict` — Qwen kiest beste match + onderbouwing +
    `zekerheid_match` (hoog/midden/laag). Bij 1 kandidaat: direct, geen LLM-call. Bij 0: leeg.
  - `wgs84_naar_rd(lat, lon) -> tuple[float,float]` — pyproj-transformatie naar EPSG:28992.
- `src/leefomgevinglab/connectors/base.py` — **`post_json(url, json_body, headers)` toevoegen**
  - Analoog aan `get_json`: on-disk cache (cache-key op url + body), timeout, degradatie naar
    `ConnectorError`, cache-fallback bij 5xx. Bestaande `get_json`-callers ongewijzigd.

## Antwoordcontract (`POST /api/regels`)

```jsonc
{
  "vraag": "dakkapel plaatsen",
  "gekozen_werkzaamheid": {
    "urn": "DakkapelPlaatsen",
    "omschrijving": "Dakkapel plaatsen, vervangen of veranderen",
    "match_onderbouwing": "...",            // Qwen-redenering
    "zekerheid_match": "hoog"               // hoog | midden | laag
  },
  "alternatieven": [ {"urn": "...", "omschrijving": "..."} ],  // NOOIT verborgen
  "typeringen": ["Conclusie","Indieningsvereisten"],
  "indieningsvereisten": null,              // gevuld bij succes, anders null
  "indieningsvereisten_status": "niet_beschikbaar_op_locatie",
  "locatie_rd": [121000, 487000],
  "bron": "DSO Toepasbare Regels (Zoek + RTR + Uitvoeren)",
  "onzekerheid": true,
  "disclaimer": "Indicatief, geen juridisch besluit ...",
  "vangnet": "Raadpleeg het bevoegd gezag / Omgevingsloket ...",
  "beschikbaar": true
}
```

**Principes:**
- `alternatieven` blijft altijd zichtbaar — Qwen kan misgrijpen; geen verborgen verkeerde keuze.
- Elke laag degradeert **onafhankelijk**: faalt laag 5, dan blijven laag 1–4 staan met `beschikbaar:true`.
- Faalt de resolver zelf (laag 1/2: geen kandidaten of bron down) → `beschikbaar:false`,
  `gekozen_werkzaamheid:null`, contract (disclaimer/vangnet) blijft staan.
- Ontbreekt `locatie` → 422 (locatie is verplicht voor typeringen/`_geo`).

## Laag 5 — degradatie-model

Best-effort met expliciete status; nooit een harde fout naar de client.

| Situatie | `indieningsvereisten` | `indieningsvereisten_status` |
|---|---|---|
| Keten lukt, vereisten terug | de lijst | `beschikbaar` |
| Geen juridische relatie op locatie | `null` | `niet_beschikbaar_op_locatie` |
| Vragenboom vereist antwoorden | `null` | `vereist_nadere_vragen` |
| Uitvoeren-service faalt (5xx) | `null` | `bron_tijdelijk_niet_beschikbaar` |

**Expliciet buiten scope (YAGNI):** de interactieve vragenboom-conversatie (`antwoorden` heen-en-weer).
Eén stateless call met lege antwoorden; meer is een eigen toekomstig subsysteem.

## Config

`core/config.yaml` onder `leefomgevinglab.dso` uitbreiden met drie service-base-URLs
(`rtr_base_url`, `zoek_base_url`, `uitvoeren_base_url`) + `api_key_header`. Bestaande
`base_url`/`operation_path` migreren naar deze structuur. Key blijft `DSO_API_KEY` uit `.env`.

## Error-handling & testen (TDD, mocks)

- Connectors degraderen via `ConnectorError`; service vangt per laag. Cache als 5xx-vangnet.
- Unit-tests op mocks:
  - `ZoekConnector` — mock HAL-respons → top-N parsing, lege/zonder-key gevallen.
  - `DsoConnector` — mock typeringen + indieningsvereisten; body/headers/`Content-Crs` correct;
    geen-key raise.
  - `resolver` — Qwen-mock → deterministische keuze + zekerheid; 0/1/meer kandidaten; pyproj-transform
    tegen bekende RD-referentiewaarde.
  - `regels_opzoeken` — laag-degradatie: elke laag los uit laten vallen, contract blijft staan.
  - API-route `/api/regels` — gemockte connectors + Qwen; happy path, resolver-down, laag-5-degradatie,
    ontbrekende locatie (422).
- Eén optionele live-smoke-test achter `@pytest.mark.live` (skip zonder `DSO_API_KEY`): bewezen keten
  dakkapel → typeringen. Maakt regressie op het echte contract zichtbaar zonder CI hard te koppelen aan DSO.

## Buiten scope (vervolg)

- Interactieve vragenboom (`antwoorden`-flow) en `conclusie/_bepaal`/`maatregelen/_bepaal`.
- Chatbot-integratie (rules-as-code naast RAG op `/chatbot`) — aparte iteratie.
- Frontend voor `/api/regels`.
- WGS84→RD edge-cases buiten Nederland.

## Self-review-checklist (in te vullen na schrijven plan)

- Spec-dekking: resolver (laag 1+2) → ZoekConnector + resolver; connector-rewrite (laag 3+4) →
  DsoConnector + post_json; diepere inhoud (laag 5) → bepaal_indieningsvereisten + degradatie-model;
  conservatief contract → antwoordcontract + alternatieven-principe.
- Geen placeholders/TBD.
- Type-consistentie connector→service→route.
