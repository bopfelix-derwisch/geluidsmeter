# LeefomgevingLab — fundering & eerste twee use-cases (design)

**Datum:** 2026-06-20
**Status:** goedgekeurd ontwerp, klaar voor implementatieplan
**Bron-architectuur:** `LeefomgevingLab architectuuropzet v0_3.md` (in repo-root)

## Doel

Geluidsmeter uitbouwen tot **LeefomgevingLab**: een edge-proeftuin op het BALO-denkraam
waarin geluid één van meerdere use-cases is. Dit ontwerp dekt de **fundering** (repo-migratie
+ connector-laag + REST-laag) en de **eerste twee use-cases**: UC-04 (REV-viewer) en
UC-03 (vergunningen-chatbot). Latere thema's (lucht, afval, Seveso, OGC-uitserveren,
IAM/eHerkenning) vallen buiten dit ontwerp.

## Bevestigde keuzes (de drie knopen)

1. **Repo-strategie** — de huidige `Geluidsmeter`-repo groeit uit tot `LeefomgevingLab`.
   Git-historie blijft behouden. Draaiende geluid-services, het Cloudflare-domein en de
   NVMe-datastructuur blijven ongemoeid tijdens de verbouwing.
2. **Eerste twee use-cases** — UC-04 REV-viewer eerst (volledig op open OGC/WFS-API's),
   daarna UC-03 vergunningen-chatbot (conservatief ingeperkt; zie sectie D).
3. **L4 façades** — afgeslankt tot **één interne REST-laag** (FastAPI op poort 8792).
   OGC API Features van PDOK/REV gaan direct naar de kaart. GraphQL en webhooks worden
   niet gebouwd tot er bewijs is dat ze nodig zijn (YAGNI).

## Architectuur (afgeslankt t.o.v. v0.3)

```
Viewer (MapLibre) + Chatbot
        |
   REST /api/*  (FastAPI 8792)        <- L4, één datapad
        |
   connectors/  (BaseConnector)       <- L1
   ├── pdok.py   (BRT-achtergrond, BAG)
   ├── rev.py    (REV via PDOK OGC API Features)
   └── dso.py    (Toepasbare Regels + Stelselcatalogus)
        |
   externe open API's: PDOK / REV / DSO
   (PDOK/REV OGC Features kunnen ook direct naar de kaart)

Edge-runtime: Jetson AGX Orin · Qwen2.5 lokaal (8080) · RAG-vectorstore op NVMe
```

## A. Repo-migratie & structuur

Doelstructuur (huidige repo, hernoemd naar LeefomgevingLab):

```
src/leefomgevinglab/
  connectors/        # base.py + pdok.py, rev.py, dso.py
  usecases/
    geluid/          # = huidige src/geluidsmeter/* (verplaatst via git mv)
    rev_viewer/      # UC-04
    vergunningen/    # UC-03
  api.py             # bestaande geluid-routes + /api/rev, /api/regels, /api/duiding
  viewer/static/     # MapLibre-viewer (HTML/JS), naast bestaande dashboard.html
core/  scripts/  systemd/  tests/
```

**Migratie-veiligheid (kritisch):**
- Verplaatsing met `git mv` zodat historie behouden blijft.
- De draaiende `geluidsmeter-capture.service` en `geluidsmeter-api.service` mogen niet
  breken tijdens de verbouwing. De `geluidsmeter`-package-import blijft daarom werken
  (dunne compat-shim, of services pas in een latere, expliciete stap omzetten).
- NVMe-datapaden (`/mnt/nvme/geluidsmeter/...`) blijven ongewijzigd in dit ontwerp.
- `core/location_private.yaml` blijft in `.gitignore`; DSO-API-key komt in `.env`
  (`.env.example` bijwerken, `.env` niet committen).

## B. Connector-laag (fundering, fase 0)

`BaseConnector` met:
- HTTP-timeout (configureerbaar, default kort genoeg om de UI niet te laten hangen)
- on-disk response-cache op NVMe (`/mnt/nvme/geluidsmeter/data/cache/`) met TTL
- nette degradatie: bij bronfout een gestructureerde "bron tijdelijk niet beschikbaar"
  i.p.v. een exception die de request laat crashen

Concrete connectors (startset):
- `pdok.py` — BRT-achtergrondkaart + BAG (basislagen)
- `rev.py` — REV via PDOK OGC API Features (risico-objecten/contouren)
- `dso.py` — DSO Toepasbare Regels (activiteit + locatie) + Stelselcatalogus;
  API-key uit `.env`

Elke connector levert genormaliseerde GeoJSON/JSON aan de REST-laag.
Patroon = "nieuw thema = nieuwe connector + DQ-profiel + STAC-collection".

## C. UC-04 REV-viewer (fase 1, eerst af)

MapLibre GL JS viewer (open source, conform v0.3 §3):
- PDOK BRT-achtergrond als basislaag
- REV-laag (OGC API Features), klikbare objecten → popup met objectvelden
- Knop "AI-duiding" → Qwen lokaal (8080) duidt het geselecteerde object in gewone taal,
  altijd met bronverwijzing

REST-routes:
- `GET /api/rev/features?bbox=...` → REV-features binnen bounding box
- `POST /api/duiding` → LLM-duiding op gestructureerde objectvelden

Geen RAG nodig — puur kaartdata + LLM-duiding op gestructureerde velden.

## D. UC-03 vergunningen-chatbot (fase 2, conservatief)

Het risicovolle deel; daarom expliciet ingeperkt.

- **Bronnen:** DSO Toepasbare Regels (activiteit + locatie) + Stelselcatalogus
  + RAG op IPLO-teksten.
- **Antwoordcontract** — elk antwoord bevat:
  1. wat de regels zeggen,
  2. **letterlijke bronverwijzing/URL**,
  3. expliciete onzekerheid,
  4. vangnet: "raadpleeg het bevoegd gezag — dit is een indicatie, geen juridisch besluit".
- **Geen** stellige ja/nee-vergunninguitspraken zonder bron. Bij onduidelijke regels zegt
  het model dat, i.p.v. te gokken.
- **RAG-pijplijn:** ingest IPLO → chunk → embed → lokale vectorstore op NVMe.
- **Kwaliteitsbewaking:** kleine eval-set van bekende vragen + verwachte bron/antwoord-vorm,
  om regressie in correctheid te signaleren.

REST-routes:
- `POST /api/regels` → vraag (activiteit + locatie) → geduid antwoord volgens contract.

## E. Expliciet buiten scope (niet nu)

- GraphQL-domeingraaf en webhooks (L4)
- IAM/eHerkenning (v0.3 fase 6) en alle afgeschermde bronnen (AMICE-BTO, DSO indienen)
- UC's voor lucht (UC-07), afval (UC-08), Seveso/BRZO+ (UC-12)
- Eigen data uitserveren als OGC API Features / SensorThings (UC-06)
- Zware modellering (wflow/Ribasim) — al uit scope in v0.3

## Testen

- **Connectors:** unit-tests met gemockte HTTP-responses; cache-hit/miss en
  degradatie-pad expliciet getest.
- **REST-laag:** route-tests (FastAPI TestClient) voor de nieuwe endpoints, inclusief
  foutpaden (bron niet beschikbaar).
- **UC-03:** eval-set draait als test; controleert dat antwoorden het antwoordcontract
  naleven (bronverwijzing aanwezig, geen stellige uitspraak zonder bron).
- Bestaande geluid-tests blijven groen na de `git mv`-migratie.

## Open punten voor het implementatieplan

- Exacte volgorde van de `git mv`-migratie t.o.v. de draaiende services (shim nu of later).
- DSO-API-key aanvragen (vrij, via developer.omgevingswet.overheid.nl) vóór UC-03.
- Keuze embedding-model voor de RAG-vectorstore (lokaal op Orin).
