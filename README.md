# LeefomgevingLab

**Een BALO-proeftuin: een edge geo-lab op Jetson AGX Orin dat toepassingen bouwt bovenop echte, aanroepbare open data en API's van de leefomgeving.**

> ⚠️ **Experimenteel — persoonlijk micro-innovatielab.** Indicatief, geen operationeel overheidssysteem en geen juridisch oordeel. In dezelfde lijn als WaterLab en de geluidsmeter waar dit uit is gegroeid.

**Live demo:** https://leefomgevinglab.felixisfelix.com

De lab bouwt *toepassingen* (viewers, dashboards, chatbots) als afnemer/verrijker van de echte voorzieningen (DSO, REV/PDOK, CBS, RIVM …) — **nooit als bronhouder of schaduwregister** (rolzuiverheid conform BALO). Nieuw thema = nieuwe connector + datakwaliteit-profiel, niet een nieuw systeem.

---

## Use-cases (live)

| Use-case | Waar | Bron |
|---|---|---|
| **Afval & circulariteit-dashboard** — provincie-choropleth + trend + AI-duiding met **doorkijk naar 2035** (Holt), brondata-paneel en **NL→SQL-chatbot** (read-only) | `/afval` · `/api/afval/*` | CBS 83558NED + CLO/Afvalfonds/LMA in een canoniek **DuckDB**-datamodel (CBS↔AMICE) |
| **Vergunningen-chatbot** — "welke regels gelden voor activiteit X op locatie Y?"; kaartprik weegt DSO toepasbare regels, geldende omgevingsplan-regels én een REV-explosieaandachtsgebied-waarschuwing mee | `/chatbot` · `/api/chat` | DSO Toepasbare Regels (**productie**) + Ozon Presenteren (**productie**) + REV + IPLO-RAG (bge-m3 + Qwen) |
| **REV-viewer** — risicovolle productiefaciliteiten (externe veiligheid) op de kaart, met AI-duiding | `/viewer` · `/api/rev/features` | REV via PDOK OGC API Features |
| **Datavraag-chatbot** — NL-vraag → SPARQL op een eigen linked-data-laag | `/datavraag` · `/api/datavraag` | eigen REV-LD + Kadaster KKG (SPARQL/GeoSPARQL) |
| **Semantische browser** — informatiemodellen (IMX-Geo, IMEV) als bewegend netwerk | `/semantiek` | IMX-Geo linked data + IMEV-begrippen |
| **Geluidsmeter** — privacyvriendelijk geluidsprofiel bij een vaste meetlocatie + mobiele metingen | `/public` · `/dashboard` | eigen C922-sensor + RIVM/CVGG |
| **Roadmap & leerpunten** — wat er live is en wat we leren over de kwaliteit van het stelsel | `/roadmap` | — |

De **AI-laag** is lokaal (Qwen2.5-32B op `localhost:8080`) + Claude, altijd met bronverwijzing, conservatief contract (nette degradatie) en no-hallucination-prompts.

---

## Architectuur (kort)

```
L6 Toepassingen   dashboards · viewers · chatbots  (FastAPI, static HTML + MapLibre)
L5 Kennis & AI    RAG (IPLO/Stelselcatalogus) · Qwen lokaal · rules-as-code
L4 Façades        REST /api/* op één datapad
L3 Informatie     GeoParquet/GeoJSON · DuckDB-datamodel · STAC (Portolan)
L2 Verwerking     valideren · ruimtelijk duiden · analyseren/signaleren · forecast (Holt)
L1 Connectors     DSO · REV/PDOK · CBS · Samen Meten · Ozon · eigen sensor
L0 Edge-runtime   Jetson AGX Orin · lokale LLM
```

Patroon per thema: **connector → usecase-service → REST-route → dashboard**. Zie de connector-laag in `src/leefomgevinglab/connectors/` en de use-cases in `src/leefomgevinglab/usecases/`.

---

## Repo-structuur

```
src/leefomgevinglab/
  connectors/     BaseConnector + DSO, REV, CBS-afval, Ozon, externe-veiligheid …
  usecases/       afval/ (dashboard, service, duiding, chat), vergunningen/, rev_viewer/, datavraag/ …
  afvaldb/        DuckDB-store, crosswalk, loaders (cbs/clo/afvalfonds/lma), Holt-forecast
  rag/ semantiek/ ld/   RAG-pijplijn, linked data
  geluidsmeter/   audio capture, feature-extract, aggregatie, FastAPI-app (geluidsmeter.api:app)
  static/         dashboards en pagina's (index, afval, roadmap, viewer, chat …)
scripts/          01–12: record/aggregatie/ingest/RAG-index/tunnel …
core/config.yaml  configuratie (omgeving-schakelaars, endpoints, drempels)
docs/superpowers/ specs/ en plans/ per feature
```

Data staat op **NVMe** (`/mnt/nvme/geluidsmeter/data/…`), niet in de repo (`.gitignore`).

---

## Setup

```bash
cd /mnt/nvme/workspaces/LeefomgevingLab      # of ~/Geluidsmeter (symlink)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# NVMe data-dirs (eenmalig, sudo)
sudo mkdir -p /mnt/nvme/geluidsmeter/data/{raw_features,processed,external,catalog}
sudo chown -R bob:bob /mnt/nvme/geluidsmeter

# Geheimen in .env (NIET committen — staat in .gitignore):
#   DSO_API_KEY         DSO/Ozon pre-productie-key
#   DSO_API_KEY_PROD    DSO/Ozon productie-key (toepasbare regels + Presenteren)
```

### API draaien
```bash
bash scripts/05_run_api.sh
# uvicorn leefomgevinglab.geluidsmeter.api:app --host 0.0.0.0 --port 8792 --app-dir src
# → http://localhost:8792/            (landing)
# → http://localhost:8792/afval       (afval-dashboard)
# → http://localhost:8792/chatbot     (vergunningen-chatbot)
```
In productie draait de app als systemd-unit `leefomgevinglab-api.service` (poort 8792), publiek via een Cloudflare-tunnel.

### Data laden (voorbeelden)
```bash
python3 scripts/11_fetch_afval_aggregaat.py   # CBS-afvalaggregaat + provincie-geometrie
python3 scripts/12_fetch_afval_bronnen.py     # DuckDB-afvaldatabase + Holt-forecast
python3 scripts/07_build_rag_index.py         # RAG-index (embedding-server actief)
```

---

## Omgeving-schakelaars (DSO / Ozon)

DSO Toepasbare Regels en Ozon Presenteren zijn per endpoint op **pre** of **prod** te zetten in `core/config.yaml` (`dso.{zoek,rtr,uitvoeren}_env`, `ozon.environment`); de bijbehorende key komt uit `.env` (`DSO_API_KEY` / `DSO_API_KEY_PROD`). Standaard staat de toepasbare-regels-keten + Ozon op **productie**. Zie `/roadmap` voor de actuele status en bekende gaten (o.a. DSO-Uitvoeren prod-500, Ozon artikel-niveau).

---

## Poorten (orin3)

| Dienst | Poort |
|---|---|
| **LeefomgevingLab API** | **8792** |
| llama.cpp Qwen (lokaal) | 8080 |
| embedding-server (bge-m3) | 8082 |
| Derwisch backend | 8789 |
| felix-nazaten upload | 8791 |

---

## Privacy & eerlijkheid

- `store_raw_audio: false` — geen ruwe audio op disk; locatie afgerond op 100 m in publieke output.
- `.env` en `core/location_private.yaml` staan in `.gitignore`.
- Elke waarde is herleidbaar naar bron + licentie; modelmatige/indicatieve elementen en niet-open bronnen worden expliciet gelabeld.

---

## Meer

- Architectuur: `LeefomgevingLab architectuuropzet v0_3.md`
- Per-feature specs en plannen: `docs/superpowers/specs/` en `docs/superpowers/plans/`
- Roadmap & leerpunten: **`/roadmap`** (live)
