# Omgevingsplan-regels ("wat geldt hier") als derde chatbot-bron — ontwerp

**Datum:** 2026-06-23
**Status:** ontwerp goedgekeurd, klaar voor implementatieplan
**Voorgangers:**
- `2026-06-22-dso-regels-resolver-design.md` (`/api/regels`: toepasbare regels)
- `2026-06-22-chatbot-rules-as-code-design.md` (toepasbare regels in de chatbot)
- bugfix `d814b88` (chatbot-prompt laat de regels het antwoord dragen)

## Probleem / doel

De chatbot weegt nu IPLO-RAG + DSO toepasbare regels mee, maar niet wat er **juridisch op de
plek geldt** (het omgevingsplan / de omgevingsdocumenten). Doel: bij een geprikte locatie ook de
geldende omgevingsplan-regels ("wat geldt hier") ophalen via de open DSO-bron **Ozon
(Omgevingsdocument Presenteren)** en als **derde bron** meewegen in het antwoord — conservatief en
niet-juridisch, net als de andere lagen.

## Live geverifieerde bron (2026-06-23, met `DSO_API_KEY`)

**Ozon Omgevingsdocument Presenteren v8** — host `service.pre.omgevingswet.overheid.nl`,
pad `/publiek/omgevingsdocumenten/api/presenteren/v8`. Header `x-api-key` (key vereist; "geen
indien-rol" ≠ geen key). HAL-respons (`Accept: application/hal+json`). Geometrie in RD via header
**`Content-Crs: http://www.opengis.net/def/crs/EPSG/0/28992`** (de OGC-URI-vorm; `EPSG:28992` geeft
400 — anders dan de toepasbare-regels-API!). Pre-prod-catalogus: 3012 regelingen.

Relevante endpoints (uit de OpenAPI-spec, `/publish/pages/166112/omgevingsdocumenten-presenteren-v8.json`):
- `POST /regelingen/_zoek` — body `{"geometrie": {"type": "Point", "coordinates": [x, y]}}` (RD;
  voorbeeld `[139784, 442870]`) → `_embedded.regelingen[]`. **Live geverifieerd:** één punt geeft
  ~20 regelingen over álle bestuurslagen. Velden per regeling: `identificatie` (`/akn/nl/act/...`),
  `officieleTitel`, `opschrift`, `citeerTitel`, `type` (`{code, waarde}`, bv. `"AMvB"`,
  `"Omgevingsplan"`, `"Omgevingsverordening"`, `"Waterschapsverordening"`, `"Programma"`,
  `"Omgevingsvisie"`), `aangeleverdDoorEen` (`{naam, bestuurslaag, code}` = bevoegd gezag).
- `POST /regelingen/{uriIdentificatie}/regeltekstannotaties/_zoek` — zelfde geo-body. `{uriIdentificatie}`
  = de `identificatie` met `/` → `_` (bv. `_akn_nl_act_mnre1034_2020_regOW01`). **Live bevinding:**
  vaak leeg (de eerste regeling gaf 0); daarom alleen best-effort voor de top-1 regeling, niet per regeling.

## Architectuur & data-flow

```
POST /api/chat {vraag, locatie?}
   └─ chatbot.beantwoord(... regels_fn, omgevingsplan_fn ...)
        ├─ RAG (IPLO)                                   [bestaand]
        ├─ toepasbare regels (Zoek→Qwen→typeringen)     [bestaand]
        └─ NIEUW: omgevingsplan_fn(locatie)
              wgs84_naar_rd(lat,lon)  →  OzonConnector.regelingen_op_punt(rd)   (cap N)
                                      →  per regeling: regelteksten_op_punt(uri, rd)  (cap M)
              → blok: regeling(en) + bevoegd gezag + geldende regeltekst-opschriften
        →  Qwen krijgt alle drie als context → één antwoord
        →  structureel "omgevingsplan"-blok ongewijzigd terug
```

### Componenten (spiegelt de toepasbare-regels-aanpak)

- `src/leefomgevinglab/connectors/ozon.py` — **`OzonConnector(BaseConnector)`**
  - `regelingen_op_punt(geo_rd: tuple[float,float]) -> list[dict]`
    — `POST {base}/regelingen/_zoek` body `{"geometrie": Point}`, headers `Content-Crs` (OGC-URI),
    `Accept: application/hal+json`, `x-api-key`. Parseert `_embedded.regelingen[]` → lijst
    `{titel, type, bevoegd_gezag, uri}` (titel = `opschrift`/`officieleTitel`; type = `type.waarde`;
    bevoegd_gezag = `aangeleverdDoorEen.naam`; uri = `identificatie` met `/`→`_`). Geen filtering/cap
    in de connector — dat doet de service.
  - `regelteksten_op_punt(regeling_uri: str, geo_rd, max_m: int = 5) -> list[str]`
    — `POST {base}/regelingen/{uri}/regeltekstannotaties/_zoek` zelfde geo-body → top-M
    regeltekst-opschriften (titels), niet de volledige body. Lege respons → `[]`.
  - Raise `ConnectorError` zonder key.
- `src/leefomgevinglab/usecases/vergunningen/omgevingsplan.py` — **`omgevingsplan_op_locatie(locatie: dict, ozon_connector, max_regelingen=3, max_regelteksten=5) -> dict | None`**
  - `resolver.wgs84_naar_rd(lat, lon)` → RD; `regelingen_op_punt`; **filter** op relevante types
    (`Omgevingsplan`, `Omgevingsverordening`, `Waterschapsverordening`) en cap op `max_regelingen`.
    Geen relevante regelingen → `None`. Voor de **top-1** relevante regeling (prioriteit Omgevingsplan
    > Omgevingsverordening > Waterschapsverordening) best-effort `regelteksten_op_punt` (cap
    `max_regelteksten`); leeg/fout → gewoon zonder regelteksten. `ConnectorError` uit de connector
    propageert (de chatbot vangt 'm — onafhankelijke degradatie).
- `src/geluidsmeter/api.py` — `/api/chat` bouwt een `omgevingsplan_fn`-closure over `_ozon_connector()`
  + `omgevingsplan.omgevingsplan_op_locatie`, en geeft die door aan `beantwoord`.
- `src/leefomgevinglab/usecases/vergunningen/chatbot.py` — `beantwoord` krijgt `omgevingsplan_fn=None`;
  `build_prompt` krijgt een `omgevingsplan`-sectie.
- `core/config.yaml` — `leefomgevinglab.ozon`: `base_url`, `api_key_header`, `max_regelingen`,
  `max_regelteksten`.
- `src/leefomgevinglab/static/chat.html` — "Wat geldt hier"-kaartje onder het antwoord.

## Antwoordcontract (`POST /api/chat`)

Additief; bestaande velden (incl. `regels`) ongewijzigd:

```jsonc
{
  "vraag": "...", "antwoord": "...", "bronnen": [...],
  "regels": { ... },                          // toepasbare regels (bestaand)
  "omgevingsplan": {                          // NIEUW — null als geen locatie / geen relevante regeling / bron down
    "regelingen": [
      {"titel": "Omgevingsverordening Utrecht", "type": "Omgevingsverordening",
       "bevoegd_gezag": "provincie Utrecht"},
      {"titel": "Waterschapsverordening De Stichtse Rijnlanden", "type": "Waterschapsverordening",
       "bevoegd_gezag": "Hoogheemraadschap De Stichtse Rijnlanden"}
    ],
    "top_regeling": "Omgevingsverordening Utrecht",      // de hoogst-geprioriteerde
    "regelteksten": ["Bouwregels woongebied"],           // best-effort voor top_regeling; [] indien geen
    "locatie_rd": [139784.0, 442870.0],
    "aantal_beperkt_tot": 3,
    "bron": "DSO Presenteren (Ozon)"
  },
  "onzekerheid": true, "disclaimer": "...", "vangnet": "...", "beschikbaar": true
}
```

`omgevingsplan` is `null` wanneer: geen `locatie`; `regelingen_op_punt` leeg; of de Ozon-laag wierp
`ConnectorError`. `beschikbaar` (top-level) blijft de RAG-beschikbaarheid.

### Prompt

`build_prompt` voegt, alleen bij een gevulde `omgevingsplan`, een compacte sectie toe:
> "Op de gekozen locatie gelden volgens het DSO (Ozon) o.a.: Omgevingsplan gemeente Den Haag
> (regels over: Bouwregels woongebied, Aan-huis-verbonden beroep). Gebruik dit om concreet te zijn
> over wat er op deze plek geldt; trek geen stellig juridisch besluit."

De bestaande niet-juridische/no-hallucination-instructie en de toepasbare-regels-sectie blijven staan.

## Degradatie

Onafhankelijk, zelfde principe als de andere lagen:

| Situatie | `omgevingsplan` | RAG-antwoord | `regels` |
|---|---|---|---|
| Alles ok | gevuld | proza | gevuld |
| Geen locatie | null | proza | null |
| Geen regelingen op punt | null | proza | (eigen status) |
| Ozon-bron down | null | proza | (eigen status) |
| RAG down | null/gevuld | null, beschikbaar:false | (eigen status) |

`omgevingsplan_fn` draait in `beantwoord` achter `try/except ConnectorError`; een fout daar mag het
RAG-antwoord of de toepasbare-regels nooit laten vallen.

## Begrenzing & performance

- **Harde caps** (config): `max_regelingen` (default 3), `max_regelteksten` per regeling (default 5).
  Voorkomt grote payloads en houdt latency in toom. `aantal_beperkt_tot` maakt de cap zichtbaar.
- **Connector-cache** (bestaand, op url+body) versnelt herhaalvragen op dezelfde plek.
- Elke Ozon-call via `BaseConnector.post_json` met de bestaande timeout; traag/fout → laag degradeert.
- **Buiten scope:** ketenversnelling (parallelliseren/voorladen) — de chat is al ~48s; dit voegt
  begrensd toe, een echte perf-slag is een aparte iteratie.

## Error-handling & testen (TDD, mocks)

- `OzonConnector` — mock `post_json`: `regelingen_op_punt` (HAL-parsing, top-N, juiste url/headers
  incl. `Content-Crs`/`Accept`), `regelteksten_op_punt` (geo-body + uri in pad, top-M opschriften),
  geen-key → `ConnectorError`.
- `omgevingsplan_op_locatie` — mock connector: happy (regelingen+teksten, caps), geen regelingen →
  `None`, bron down → `ConnectorError`; RD via `resolver.wgs84_naar_rd`.
- `beantwoord` — `omgevingsplan_fn`: met locatie+data → prompt bevat omgevingsplan-context + veld
  gevuld; geen locatie → niet aangeroepen, `null`; Ozon down → `null`, RAG+regels blijven.
- Route `/api/chat` — `omgevingsplan_fn`-closure bedraad; bestaande tests blijven groen (veld optioneel).
- Eén live smoke-test achter `@pytest.mark.skipif(not DSO_API_KEY)`: bekend RD-punt → ≥1 regeling.
- Frontend: handmatige verificatie ("Wat geldt hier"-kaartje) op de draaiende service.

## Buiten scope (vervolg)

- Volledige regeltekst-body / juridische tekst tonen (nu alleen opschriften/titels).
- Ontwerpregelingen / besluitversies / omgevingsvergunningen (alleen geldende `regelingen`).
- Ketenversnelling (parallelle calls), adres→geocoding, multi-turn.

## Self-review-checklist (na schrijven plan)

- Spec-dekking: Ozon-connector (regelingen + regelteksten op punt) → connector-taak; "wat geldt hier"-
  traversal + caps → omgevingsplan-service-taak; derde bron in het antwoord → beantwoord/build_prompt +
  route; onafhankelijke degradatie → degradatie-tabel + tests; frontend-blok → chat.html-taak.
- Geen placeholders/TBD.
- Type-consistentie connector → service → beantwoord → route → frontend-veld `omgevingsplan`.
