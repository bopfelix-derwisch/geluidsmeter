# REV-aandachtsgebieden-waarschuwing als 4e chatbot-bron — ontwerp

**Datum:** 2026-06-24
**Status:** ontwerp goedgekeurd, klaar voor implementatieplan
**Voorgangers:** chatbot met IPLO-RAG + toepasbare regels + omgevingsplan (Ozon). Deze feature voegt
externe-veiligheid (REV-aandachtsgebieden) toe als vierde bron.

## Probleem / doel

Bij het bouwen van een **kwetsbaar gebouw** (woning, school, zorginstelling…) gelden binnen een
brand-/explosie-/gifwolk-**aandachtsgebied** aanvullende eisen. De chatbot weet nu niets van die
risicocontouren. Doel: zodra er een locatie geprikt is, checkt de bot de REV-aandachtsgebieden op dat
punt en toont een **waarschuwing** als de plek in een aandachtsgebied valt — conservatief en
niet-juridisch, als vierde bron naast IPLO/regels/omgevingsplan.

## Live geverifieerde bron (2026-06-24)

**REV GeoServer WFS** — `https://rev-portaal.nl/geoserver/wfs` (de unified REV-kaartbeelden-service).
**Open** (geen key), GeoJSON-output, polygonen.

Relevante lagen (`rev_public:`-namespace; per aandachtsgebied-type, bron-categorie `ev_` = inrichtingen):
- `rev_public:ev_brandaandachtsgebieden`
- `rev_public:ev_explosieaandachtsgebieden`
- `rev_public:ev_gifwolkaandachtsgebieden`
(transport `bn_*` en buisleidingen `bl_*` bestaan ook; config-uitbreidbaar, niet in de default.)

**Query (live geverifieerd):** `GET …/wfs` met params:
`service=WFS&version=2.0.0&request=GetFeature&typeNames=<laag>&outputFormat=application/json&srsName=EPSG:4326&count=<n>&cql_filter=INTERSECTS(geometrie, POINT(<rd_x> <rd_y>))`

**Valkuilen (geverifieerd):**
- Geometrie-attribuut heet **`geometrie`** (niet `geom` → anders 400).
- De CQL-filter-POINT wordt geïnterpreteerd in de **native CRS = RD/EPSG:28992**, NIET in lon/lat.
  Een lon/lat-punt geeft stil **0 treffers** (vals-negatief — gevaarlijk voor een veiligheidswaarschuwing).
  Daarom: locatie eerst via `resolver.wgs84_naar_rd` naar RD, dan `POINT(rd_x rd_y)`. (`srsName=EPSG:4326`
  bepaalt alleen het OUTPUT-formaat.)
- Type (`brand`/`explosie`/`gifwolk`) volgt uit de **laagnaam**, niet uit een property.
- Per feature: `bedrijfsnaam` (= bron), `evactiviteit` (activiteit, bv. propaantank),
  `categorieaandachtsgebied` (registratiestatus, bv. "vastgesteld").
- Lege respons = FeatureCollection met `features: []`.

## Architectuur & data-flow

```
POST /api/chat {vraag, locatie?}
   └─ chatbot.beantwoord(... regels_fn, omgevingsplan_fn, ev_fn ...)
        ├─ RAG (IPLO) · toepasbare regels · omgevingsplan        [bestaand]
        └─ NIEUW: ev_fn(locatie)
              check_aandachtsgebieden(locatie, ev_connector):
                 rd = resolver.wgs84_naar_rd(lat,lon)
                 voor elke geconfigureerde laag: ExterneVeiligheidConnector.aandachtsgebieden_op_punt
                   → WFS GetFeature INTERSECTS(geometrie, POINT(rd)) → treffers
                 → blok met geraakte types + bronnen + waarschuwingstekst (of None)
        →  Qwen krijgt de waarschuwing als context → één antwoord
        →  structureel "externe_veiligheid"-blok + UI-waarschuwingskaartje
```

### Componenten (spiegelt omgevingsplan)

- `src/leefomgevinglab/connectors/externe_veiligheid.py` — **`ExterneVeiligheidConnector(BaseConnector)`**
  - `aandachtsgebieden_op_punt(laag: str, geo_rd: tuple[float,float], max_n: int = 5) -> list[dict]`
    — `get_json` (GET) op de WFS met de params hierboven; parseert `features[]` → per treffer
    `{bron, evactiviteit, categorie}` (uit `properties`). Lege respons → `[]`.
  - Geen api-key nodig (open WFS).
- `src/leefomgevinglab/usecases/vergunningen/externe_veiligheid.py` —
  **`check_aandachtsgebieden(locatie: dict, ev_connector, lagen: dict[str,str]) -> dict | None`**
  - `resolver.wgs84_naar_rd(lat, lon)` → RD; per (type→laag) `aandachtsgebieden_op_punt`; verzamelt de
    geraakte types + bronnen; bouwt waarschuwingstekst. Geen enkele treffer → `None`. `ConnectorError`
    uit een laag-call propageert (de chatbot vangt 'm — onafhankelijke degradatie).
  - `lagen` = mapping `{"brand": "rev_public:ev_brandaandachtsgebieden", "explosie": …, "gifwolk": …}`.
- `src/geluidsmeter/api.py` — `/api/chat` bouwt een `ev_fn`-closure over `_ev_connector()` +
  `externe_veiligheid.check_aandachtsgebieden`, doorgegeven aan `beantwoord`.
- `src/leefomgevinglab/usecases/vergunningen/chatbot.py` — `beantwoord` krijgt `ev_fn=None`;
  `build_prompt` krijgt een `externe_veiligheid`-sectie.
- `core/config.yaml` — `leefomgevinglab.externe_veiligheid`: `wfs_url`, `lagen` (de 3 type→laag-mappings).
- `src/leefomgevinglab/static/chat.html` — waarschuwingskaartje.

## Antwoordcontract (`POST /api/chat`)

Additief; bestaande velden (incl. `regels`, `omgevingsplan`) ongewijzigd:

```jsonc
{
  "vraag": "...", "antwoord": "...", "bronnen": [...],
  "regels": { ... }, "omgevingsplan": { ... },
  "externe_veiligheid": {            // NIEUW — null als locatie in géén aandachtsgebied valt / bron down
    "aandachtsgebieden": [
      {"type": "brand", "bron": "Autobedrijf Mekes", "activiteit": "OpslagtankPropaanPropeen…"}
    ],
    "waarschuwing": "Let op: deze locatie ligt in een brandaandachtsgebied (bron: Autobedrijf Mekes). Voor een kwetsbaar gebouw gelden hier aanvullende eisen; raadpleeg het bevoegd gezag.",
    "locatie_rd": [151658.2, 418729.5],
    "bron": "REV (rev-portaal.nl)"
  },
  "onzekerheid": true, "disclaimer": "...", "vangnet": "...", "beschikbaar": true
}
```

`externe_veiligheid` is `null` wanneer: geen `locatie`; het punt in **geen enkel** aandachtsgebied valt;
of de REV-WFS faalt. `type` volgt uit de geraakte laag; `bron` uit `bedrijfsnaam`.

### Prompt

`build_prompt` voegt, alleen bij een gevuld `externe_veiligheid`-blok, een waarschuwingsregel toe:
> "LET OP — externe veiligheid: deze locatie ligt in een <types>aandachtsgebied (bron: <bedrijven>).
> Voor een kwetsbaar gebouw gelden hier aanvullende eisen. Benoem dit duidelijk; trek geen stellig
> juridisch besluit; verwijs naar het bevoegd gezag."

## Degradatie

Onafhankelijk, zelfde principe als de andere lagen:

| Situatie | `externe_veiligheid` | RAG/overige bronnen |
|---|---|---|
| Punt in ≥1 aandachtsgebied | gevuld (waarschuwing) | ongewijzigd |
| Geen locatie | null | ongewijzigd |
| Punt in geen aandachtsgebied | null | ongewijzigd |
| REV-WFS down | null | ongewijzigd |

`ev_fn` draait in `beantwoord` achter `try/except ConnectorError`; een REV-fout mag nooit het
RAG-antwoord of de andere drie bronnen laten vallen.

## Begrenzing & performance

- **3 WFS-calls** (de 3 ev-hoofdtypes), elk een `INTERSECTS`-query die alleen treffers teruggeeft
  (weinig data; `count` begrensd, default 5). Config-gedreven laaglijst (uitbreidbaar met `bn_`/`bl_`).
- **Connector-cache** (bestaand, op url+params) versnelt herhaalvragen op dezelfde plek.
- Voegt enkele seconden toe aan de keten (al ~50-70s); ketenversnelling (parallelle calls) is de
  aparte, al-genoteerde follow-up.

## Error-handling & testen (TDD, mocks)

- `ExterneVeiligheidConnector` — mock `get_json`: bouwt de juiste WFS-params incl.
  `cql_filter=INTERSECTS(geometrie, POINT(<rd_x> <rd_y>))` (RD!), `typeNames`, `outputFormat`,
  `srsName`; parseert `features[]` → `{bron, activiteit, categorie}`; lege FeatureCollection → `[]`.
- `check_aandachtsgebieden` — mock connector: ≥1 treffer (in één/meer types) → blok met types +
  bronnen + waarschuwingstekst; RD via `resolver.wgs84_naar_rd`; geen treffer → `None`; bron down →
  `ConnectorError` propageert.
- `beantwoord` — `ev_fn`: met locatie+treffer → prompt bevat de waarschuwing + veld gevuld; geen
  locatie → niet aangeroepen, `null`; REV down → `null`, andere bronnen blijven.
- Route `/api/chat` — `ev_fn`-closure bedraad; bestaande tests blijven groen (veld optioneel).
- Eén live smoke-test (open WFS, geen key) op een bekend RD-punt in een brandaandachtsgebied → ≥1 treffer.
- Frontend: waarschuwingskaartje (handmatige verificatie).

## Buiten scope (vervolg)

- Transport-/buisleiding-aandachtsgebieden (`bn_*`/`bl_*`) standaard aan (nu config-uitbreidbaar).
- Onderscheid kwetsbaar / zeer kwetsbaar / beperkt kwetsbaar (de `veiligheidszones*`-lagen) en de
  juridische eisen per categorie.
- Intentie-detectie ("gaat de vraag over een kwetsbaar gebouw") — nu altijd-bij-locatie.
- Ketenversnelling (parallelle calls), multi-turn.

## Self-review-checklist (na schrijven plan)

- Spec-dekking: connector (INTERSECTS op RD-punt, geometrie-attr, type-uit-laag) → connector-taak;
  type-verzameling + waarschuwing → service-taak; 4e bron in antwoord → beantwoord/build_prompt + route;
  onafhankelijke degradatie → degradatie-tabel + tests; frontend-waarschuwing → chat.html-taak.
- Geen placeholders/TBD.
- Type-consistentie connector → service → beantwoord → route → frontend-veld `externe_veiligheid`.
