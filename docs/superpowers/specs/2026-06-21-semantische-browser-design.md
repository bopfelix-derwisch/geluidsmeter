# Semantische browser — informatiemodellen & koppelingen (design)

**Datum:** 2026-06-21
**Status:** goedgekeurd ontwerp, klaar voor implementatieplan
**POC:** voortgekomen uit de roadmap-optie "kennisgraaf / semantiek" (LeefomgevingLab)

## Doel & rol

Een interactieve **semantische browser** die toont hoe de informatiemodellen van de
leefomgeving aan elkaar hangen — met **IMX-Geo** (het crossdomein-model van Geonovum) als
spil, dat objecttypen/begrippen uit verschillende bronregisters (BAG, BGT, BRK, REV, …)
machine-leesbaar aan elkaar koppelt. Het lab blijft **afnemer/verrijker** (rolzuiverheid):
we laden open linked data in en visualiseren die; we zijn geen bronhouder.

Waarom innovatief: in plaats van losse modeldocumenten naast elkaar te lezen, maakt de
browser de **koppelingen tussen modellen** zichtbaar als één doorzoekbare graaf.

## Bevestigde keuzes (brainstorm)

1. **Bronnen v1:** IMX-Geo als spil + de bronmodellen waarnaar het verwijst (koppelingen via
   `skos:closeMatch`/`exactMatch`). Volledig open, geen API-key.
2. **Visualisatie:** interactieve graaf met **Cytoscape.js** (via CDN, geen buildstap); nodes
   gekleurd per bron, klik → detailpaneel, zoekbalk highlight.
3. **Stelselcatalogus:** deferred — de API is key-gated (HTTP 401 zonder DSO-key). Connector op
   mocks; live begripsverrijking pas zodra de key er is.

## Geverifieerde feiten (bron-onderzoek 2026-06-21)

- **IMX-Geo TTL is open** op GitHub (`geonovum/IMX-Geo`):
  - `conceptscheme/imxgeo-skos.ttl` — SKOS-conceptscheme (schone concepten + koppelingen)
  - `mim-ld-export/model/imx-geo-mim.ttl`, `imx-geo-ont.ttl` — MIM/OWL-export (rijker model)
- **Structuur** (geverifieerd): concepten zijn `skos:Concept` met `skos:prefLabel`,
  `skos:definition`, `skos:inScheme`. Koppelingen naar bronregisters staan als
  `skos:closeMatch`/`skos:exactMatch` naar URI's als
  `http://bag.basisregistraties.overheid.nl/id/begrip/Naam` — de **bron is af te leiden uit de
  URI-host**. Interne relaties: `skos:broader`/`narrower`/`related`.
- **Stelselcatalogus** publieke API (`/publiek/catalogus/api/opvragen/v3/concepten`) gaf
  **HTTP 401** → key vereist → deferred.
- **GIR** (BRZO+-inspectiedatabase): gesloten, geen open informatiemodel → niet in de graaf.

## Architectuur (lagen, hergebruikt het lab-patroon)

```
Frontend  /semantiek  (Cytoscape.js, CDN)
   |
REST  /api/semantiek/graph   /api/semantiek/node   (FastAPI 8792)
   |
graph-builder  (semantiek/graph.py, rdflib)  -> cytoscape JSON op NVMe
   |
ingest  (semantiek/ingest.py)  -> IMX-Geo TTL gecachet op NVMe
   |
open bron: github.com/geonovum/IMX-Geo (raw TTL)

Build: scripts/09_build_semantiek_graph.py  (one-off / cron)
Deferred: Stelselcatalogus-connector (key) voor begripsverrijking
```

## Componenten & bestanden

```
src/leefomgevinglab/
  semantiek/
    __init__.py
    ingest.py            # fetch TTL-URL's -> tekst (ConnectorError bij fout)
    graph.py             # rdflib parse -> nodes/edges -> cytoscape JSON; bron-uit-URI
scripts/
  09_build_semantiek_graph.py
core/config.yaml         # + leefomgevinglab.semantiek (ttl_urls, store_dir)
requirements.txt         # + rdflib
src/geluidsmeter/api.py  # + GET /api/semantiek/graph, /api/semantiek/node, /semantiek
src/leefomgevinglab/static/semantiek.html
tests/
  test_semantiek_graph.py
  test_semantiek_ingest.py
  test_api_semantiek.py
```

## Datamodel (graaf)

- **Node:** `{ "data": { "id": <uri>, "label": <prefLabel|fragment>, "bron": <IMX-Geo|BAG|BGT|BRK|REV|overig>, "definitie": <str|null> } }`
- **Edge:** `{ "data": { "id": <src|rel|tgt>, "source": <uri>, "target": <uri>, "relatie": <closeMatch|exactMatch|broader|narrower|related> } }`
- **bron-afleiding:** concepten in `bk:IMX-Geo`-scheme → "IMX-Geo"; externe URI's → host-map
  (`bag.basisregistraties.overheid.nl`→"BAG", `bgt.basisregistraties.overheid.nl`→"BGT",
  `brk...`→"BRK", REV/PDOK-host→"REV", anders → de host zelf als label).
- **Externe doel-URI's** (van closeMatch/exactMatch) worden ook nodes (zo ontstaat "modellen
  naast elkaar"), met hun bron uit de host en label = laatste URI-segment.

## API

- `GET /api/semantiek/graph` → `{ "elements": { "nodes": [...], "edges": [...] }, "bronnen": [...] }`.
  Optioneel `?zoekTerm=` (filtert nodes op label/definitie + hun directe buren) en `?bron=`
  (alleen die bron + IMX-Geo-spil). Ontbreekt de graaf → `{"elements":{"nodes":[],"edges":[]}, "beschikbaar": false}`.
- `GET /api/semantiek/node?uri=` → `{ "node": {...}, "buren": [ {node, relatie} ... ] }`.

## Frontend `/semantiek`

Cytoscape.js (CDN). Donkere lab-stijl. Nodes per bron gekleurd, IMX-Geo-spil geaccentueerd.
Klik node → detailpaneel (label, bron, definitie, lijst koppelingen). Zoekbalk → filtert/markeert.
Legenda met bron-kleuren. Bij lege/ontbrekende graaf: nette melding "bouw eerst de graaf".

## Foutafhandeling

- Ingest: `ConnectorError` bij onbereikbare TTL (per URL; sla over, bouw met de rest).
- Graph-builder: onleesbare/lege TTL → lege graaf, geen crash.
- API: ontbrekende graaf-cache → `beschikbaar:false` met lege elements (geen 500).

## Testen

- **graph.py:** kleine inline-TTL-fixture (concept + closeMatch naar BAG-host + broader) →
  assert nodes (incl. externe BAG-node), edges (closeMatch/broader), en bron-afleiding (BAG).
- **ingest.py:** gemockte fetch → meerdere URL's samengevoegd; per-URL-fout overgeslagen.
- **API:** served graph (gemockte cache) + ontbrekende-graaf → `beschikbaar:false`, 200.
- Frontend: handmatige verificatie in de browser na de live build.

## Out of scope (later)

- Stelselcatalogus-begripsverrijking live (DSO-key).
- Losse NEN3610-sectormodellen apart inladen (IMEV/IMWA/IMKL) — IMX-Geo dekt de koppelingen al.
- GIR (gesloten), SHACL-validatie, bewerken/annoteren, SPARQL-endpoint.

## Open punten voor het plan

- Exacte TTL-URL-set (SKOS alleen, of + MIM/OWL-export) — start met SKOS + MIM-model, beide open.
- `rdflib` toevoegen aan requirements en in de venv installeren.
