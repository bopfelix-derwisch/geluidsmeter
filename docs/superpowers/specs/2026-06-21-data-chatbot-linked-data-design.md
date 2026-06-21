# Data-chatbot op een linked-data-laag (SPARQL) — design

**Datum:** 2026-06-21
**Status:** goedgekeurd ontwerp; opgesplitst in Plan A (LD-fundament) + Plan B (chatbot)
**POC:** eigen POC, los van de IPLO-RAG-chatbot (die regelteksten uitlegt). Deze beantwoordt
**data-vragen** over de leefomgeving via linked data + SPARQL.

## Drijvende vraag

"Hoeveel Seveso-installaties zijn er in de provincie Zuid-Holland, en liggen die in de buurt
van een school?" — een telling + ruimtelijke nabijheid over echte open data. De cijfers moeten
**kloppen en herleidbaar** zijn (de LLM verzint geen aantallen).

## Bevestigde keuzes (brainstorm)

1. **Linked data + SPARQL** als kern (i.p.v. losse OGC-API-calls): generieke chatbot met RAG op
   een LD-laag + de data.
2. **Hergebruik bestaande LD-endpoints** waar mogelijk; voor **REV een eigen LD-laag** maken.
3. **LLM-gegenereerde SPARQL met fallback** — generiek, maar met een vaste fallback-sjabloon voor
   de demo-vraag zodat die gegarandeerd werkt.
4. **Opsplitsen:** Plan A = REV→LD-fundament; Plan B = de chatbot.

## Geverifieerde feiten (bron-onderzoek 2026-06-21)

- **Kadaster Knowledge Graph (KKG)** is publiek bevraagbaar via SPARQL en is **gepubliceerd op het
  IMX-Geo-model** (sluit aan op onze semantische browser). Endpoint (Virtuoso, JSON-results):
  `https://api.labs.kadaster.nl/datasets/kadaster/kkg/services/kkg/sparql` — geverifieerd HTTP 200.
  Bevat BAG, BGT, BRT, bestuurlijke gebieden (BRK), publiekrechtelijke beperkingen.
  → **provinciegrens** en **scholen** (BAG-verblijfsobjecten met onderwijsfunctie) hieruit te halen.
- **REV** (Seveso) is **niet** in de KKG. Wel open als OGC API Features
  (`api.pdok.nl/rws/productie-en-industrie-productiefaciliteiten/ogc/v1`). Seveso is een **subset**
  van de productiefaciliteiten ("Conversietabel E6 Seveso Inrichtingen") → exacte filter-property te
  bevestigen in de bouw.
- rdflib (al aanwezig) ondersteunt lokale SPARQL over een in-memory graph — geschikt voor een
  **beperkt aantal objecten**.

## Rolzuiverheid

We blijven **afnemer/verrijker**: we maken een **eigen lokale LD-representatie** van open REV-data
voor eigen bevraging (niet als register/bronhouder gepubliceerd). KKG bevragen we als afnemer.

## Architectuur

```
NL-vraag
  -> Chatbot (Plan B): RAG op ontologie/SHACL + voorbeeldqueries
       -> LLM schrijft SPARQL (met fallback-sjabloon voor de demo-vraag)
  -> Uitvoeren:
       - lokale REV-LD-graph (rdflib)         [Plan A]
       - KKG-SPARQL-endpoint (provincie/scholen)
  -> Nabijheid ("binnen R m van school") met shapely op geselecteerde coordinaten
  -> Antwoord: cijfers + bron + onzekerheid (conservatief contract)

LD-laag:
  - KKG (hergebruik, IMX-Geo-model)                         [extern]
  - Eigen REV-LD: Seveso (Zuid-Holland) als RDF/GeoSPARQL   [Plan A, lokaal op NVMe]
```

## Plan A — REV→LD-fundament (de spec waarmee we doorgaan)

Levert een lokale, bevraagbare LD-laag van REV-Seveso + de KKG-verbinding.

**Componenten:**
- `kkg.py` — KKG-SPARQL-connector: `sparql(query) -> rows` tegen het KKG-endpoint (httpx,
  `application/sparql-results+json`), met `ConnectorError` en cache.
- `rev_to_rdf.py` — converteer REV-features (uit de bestaande `RevConnector`, gefilterd op Zuid-
  Holland-polygon via shapely + Seveso-filter) naar **RDF**: per object een resource met type,
  label, en geometrie als **GeoSPARQL WKT** (`geo:asWKT`), IMX-Geo-uitgelijnd waar mogelijk.
- `store.py` — lokale triple store: bouw rdflib `Graph`, serialiseer als Turtle op NVMe
  (`/mnt/nvme/geluidsmeter/data/ld/rev.ttl`), laad terug, en `sparql(query) -> rows` lokaal.
- `shapes.ttl` — **SHACL-shape** die het Seveso-objecttype definieert (verplichte properties:
  id, naam, geometrie).
- `scripts/10_build_rev_ld.py` — bouw de REV-LD-graph (one-off/cron), met de ZH-polygon uit KKG.
- Optioneel klein endpoint `POST /api/ld/sparql` (lokale graph) voor inspectie.

**Verify-stappen (in de bouw):** exacte Seveso-filter-property in REV; KKG-class/property-URIs voor
provinciegebied + BAG-onderwijsfunctie; GeoSPARQL-prefix.

## Plan B — de chatbot (schets, later)

- **RAG-grounding**: ontologie (klassen/properties van de REV-LD + relevante KKG-termen) + de
  SHACL-shape + een handvol voorbeeld-SPARQL-queries als context.
- **NL→SPARQL**: LLM (Qwen) genereert SPARQL; **fallback-sjabloon** voor de demo-vraag
  (tel Seveso in provincie + nabijheid school) als de gegenereerde query faalt/valideert niet.
- **Uitvoeren + nabijheid**: lokale REV-graph (tellen/selecteren) + KKG (provincie/scholen);
  nabijheid met shapely op de geselecteerde coordinaten.
- **Antwoordcontract**: cijfers + bronnen + onzekerheid + vangnet; toon de gebruikte SPARQL
  (transparantie/leerwaarde).
- **Frontend**: `/datavraag` chat-pagina.

## Foutafhandeling

- KKG/REV onbereikbaar → `ConnectorError` → nette degradatie ("bron tijdelijk niet beschikbaar").
- Lege/onbekende filter → 0-resultaat met uitleg, geen crash.
- (Plan B) ongeldige gegenereerde SPARQL → fallback-sjabloon; lukt ook dat niet → eerlijk "kon de
  vraag niet vertalen".

## Testen

- **kkg.py**: gemockte SPARQL-results → rows-parsing; ConnectorError-pad.
- **rev_to_rdf.py**: REV-feature-fixture → verwachte triples (type, label, WKT); ZH-filter
  (punt binnen/buiten polygon).
- **store.py**: bouw + save/load + een lokale SPARQL-telquery → verwacht aantal.
- Bestaande suite blijft groen.

## Out of scope (Plan B en later)

- De chatbot zelf (Plan B). Live KKG-class-mapping fijnslijpen. Federatieve SPARQL (SERVICE).
  GeoSPARQL-afstandsfuncties in de store (we doen nabijheid met shapely). Publiceren van onze
  REV-LD als extern endpoint (rolzuiverheid).

## Open punten

- Exacte Seveso-filter in REV (property/waarde) — verify in Plan A Task voor de converter.
- KKG-URIs voor provinciegebied + BAG-onderwijsfunctie — verify in Plan A bij de KKG-connector.
