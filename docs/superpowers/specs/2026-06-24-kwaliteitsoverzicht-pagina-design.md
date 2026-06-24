# Kwaliteitsoverzicht-pagina (per POC) — ontwerp

**Datum:** 2026-06-24
**Status:** goedgekeurd; lichte bouw (één static contentpagina + route + nav, geen logica/tests).

## Doel
Een aparte tab die per POC laat zien: een functionele beschrijving, een technische beschrijving,
de kwaliteitsaspecten die we live tegenkwamen (geordend via categorie-tags), en de follow-up.
Maakt de "kwaliteit van het stelsel"-leerervaring expliciet en deelbaar.

## Plek
- Nieuwe static pagina `src/leefomgevinglab/static/kwaliteit.html`, stijl identiek aan `roadmap.html`.
- Route `GET /kwaliteit` in `src/geluidsmeter/api.py` (zelfde patroon als `/roadmap`).
- Nav-link "Kwaliteit" toevoegen op de bestaande pagina's met een nav (roadmap, viewer, chatbot, etc.).

## Ordening
Elk kwaliteitsaspect krijgt één categorie-tag; bovenaan een legenda. Categorieën:
- **Databron** — beschikbaarheid/openheid, key-eisen, pre-prod vs productie
- **Geo/CRS** — coördinaatstelsels, asvolgorde, RD↔WGS84
- **API-contract** — afwijkende endpoints/headers/veldnamen/semantiek
- **Performance** — latency, caching, ketenlengte
- **Antwoordkwaliteit & veiligheid** — conservatief contract, no-hallucination, vals-negatief-vermijding
- **Onderhoudbaarheid** — onafhankelijke degradatie, robuustheid, tests

## Structuur per POC
Eén kaart/sectie per POC met: **Functioneel** · **Technisch** · **Kwaliteitsaspecten** (getagde lijst) · **Follow-up**.

POC's: 1) Geluidsmeter, 2) REV-viewer + AI-duiding, 3) Semantische browser, 4) Datavraag-chatbot,
5) Vergunningen-chatbot RAG (IPLO), 6) DSO toepasbare regels, 7) Omgevingsplan-regels (Ozon),
8) Externe-veiligheid-waarschuwing (REV-aandachtsgebieden).

## Verificatie
Geen unit-tests (static content). Na bouw: service herstarten, `GET /kwaliteit` → HTTP 200 en de
8 POC-blokken + legenda renderen. Bestaande routes/tests onaangetast.
