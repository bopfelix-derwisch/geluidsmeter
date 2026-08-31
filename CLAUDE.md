# LeefomgevingLab — Claude Code instructies

> **Machine-breed:** `~/.claude/CLAUDE.md` (gedeelde faciliteiten + valkuilen) en `ORIN3_SYSTEEM.md` — niet hier herhalen.
> **Domein:** Edge & Geo (deelt geo-basisdata met `waterlab`). **Start via** `orin3` → window `leefomgevinglab` (pad `/mnt/nvme/workspaces/LeefomgevingLab`) voor consistente memory.
> Voorheen het losse project *Geluidsmeter*; geluid is nu één use-case hierin. Paden/mappen die nog `geluidsmeter` heten (o.a. de NVMe-datadir) zijn **niet** fout — die naam is bewust niet meeverhuisd.

Lees altijd eerst: `CLAUDE_NOTES.md`
Dan: `core/config.yaml`

---

## ⚠️ Kritieke waarschuwingen

| # | Valkuil | Correct |
|---|---------|---------|
| 1 | `find ~` **bevriest** op orin3 | Gebruik `ls` of specifieke paden |
| 2 | Poort **8791** is bezet | Door `felix-nazaten/upload_server.py` — LeefomgevingLab gebruikt **8792** |
| 3 | NVMe data-dirs vereisen **sudo** | `sudo mkdir /mnt/nvme/geluidsmeter/... && sudo chown bob:bob` |
| 4 | C922 mic is **gedeeld** met Derwisch ritueel.py | Conflict als ritueel.py opneemt — check eerst |
| 5 | `core/location_private.yaml` **nooit committen** | Staat in .gitignore — bevat echte coördinaten |
| 6 | Data staat op **NVMe**, niet in de repo | `/mnt/nvme/geluidsmeter/data/` — staat ook in .gitignore |

---

## Repo-locatie

| Repo | Pad | Remote |
|------|-----|--------|
| LeefomgevingLab | `/home/bob/LeefomgevingLab` (symlink → `/mnt/nvme/workspaces/LeefomgevingLab`) | https://github.com/bopfelix-derwisch/leefomgevinglab |

Push met: `git push origin master`
> Repo hernoemd `geluidsmeter` → `leefomgevinglab` (2026-07-29); `origin` bijgewerkt, oude URL redirect (301).

---

## Services (draaien — status 2026-08-31)

| Unit | Staat | Wat |
|---|---|---|
| `leefomgevinglab-api.service` | enabled + active | FastAPI op **8792** (`uvicorn leefomgevinglab.geluidsmeter.api:app --app-dir src`) |
| `leefomgevinglab-embed.service` | enabled + active | llama-server **bge-m3 embeddings op 8082** (voor de RAG) |
| `leefomgevinglab-capture.service` | geïnstalleerd, **disabled + inactive** | audio capture loop; bewust uit (C922 wordt gedeeld met Derwisch `ritueel.py`) |
| `leefomgevinglab-tunnel.service` | alleen in `systemd/`, **niet geïnstalleerd** | overbodig: de tunnel is dashboard-managed via de centrale `cloudflared` |

Unit-bronbestanden staan in `systemd/`; geïnstalleerd staan ze in `/etc/systemd/system/`.
Na wijziging: `sudo cp systemd/leefomgevinglab-*.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart leefomgevinglab-api`.
Ze worden bewaakt door **sysmonitor** (`~/sysmonitor/sysmonitor.py`, SERVICES + ENDPOINTS).

---

## Architectuur (kort)

```
C922 USB-mic (plughw:CARD=Webcam,DEV=0)
  → audio_capture.py (sounddevice, 60s frames)
  → feature_extract.py (RMS/Lmax/banden — géén ruwe audio)
  → JSONL → /mnt/nvme/geluidsmeter/data/raw_features/
  → aggregate.py → GeoParquet → /mnt/nvme/geluidsmeter/data/processed/
  → Portolan CLI → STAC catalogus
```

---

## Sprint status

- ✅ **Sprint 0:** structuur, config, code, systemd units, git init
- ✅ **Sprint 1:** NVMe dirs, venv, packages, C922 mic werkend (32kHz, gain 3/15)
- ✅ **Sprint 2:** aggregatie + GeoParquet
- ✅ **Sprint 3:** Portolan installeren + catalogus
- ✅ **Sprint 4:** bronnenmatch Atlas/CVGG/PDOK + dashboard
- ✅ **Sprint 5:** publieke demo via Cloudflare Tunnel — destijds `geluid.felixisfelix.com`, **nu `leefomgevinglab.felixisfelix.com`** (de oude hostname bestaat niet meer)
- ✅ **LeefomgevingLab fundering:** connector-laag (BaseConnector) + UC-04 REV-viewer met routes `/viewer`, `/api/rev/features` (PDOK OGC API), `/api/duiding` (lokale Qwen duiding). Code onder `src/leefomgevinglab/` (connectors/ + usecases/).
- ✅ **Geluid is nu één use-case** — niet meer gepland maar **live**: `/public` en `/dashboard` geven 200 (geverifieerd 2026-08-31). Let op de omgekeerde mapstructuur: de FastAPI-app van *alle* use-cases zit in `src/leefomgevinglab/geluidsmeter/api.py` — die modulenaam is historisch, het is niet alleen de geluidsmeter.
- 🚧 **UC-03b — RAG:** vergunningen-chatbot op `/chatbot` (`POST /api/chat`). RAG-pijplijn: IPLO/DSO-docs ingest → chunking → embeddings via llama.cpp `/v1/embeddings` (default poort 8082) → VectorStore (NVMe) → conversationele antwoorden met bronverwijzing, vangnet, no-hallucination-prompt. Index gebouwd via `scripts/07_build_rag_index.py`; embedding-server moet voor live gebruik actief zijn.
- 🚧 **UC-08 — Afval/circulair-dashboard:** provincie-choropleth + trend + Qwen-duiding op open CBS-afvalcijfers (83558NED, CC-BY 4.0) als open proxy voor het gesloten LMA/AMICE-aggregaat. Routes `/afval`, `/api/afval/{meta,choropleth,trend,duiding}`. Ingest via `scripts/11_fetch_afval_aggregaat.py` → `/mnt/nvme/geluidsmeter/data/external/afval/`. Code onder `src/leefomgevinglab/usecases/afval/` + `connectors/cbs_afval.py`.
- 🚧 **UC-08b — Afvaldatabase & doorkijk:** DuckDB-database (`afvaldb/`) met canoniek datamodel (CBS↔AMICE: `afval_feit` + `afvalstroom_crosswalk`), gevuld uit CBS (live) + CLO/Afvalfonds/LMA (snapshot: pdfplumber of curated CSV) via `scripts/12_fetch_afval_bronnen.py`. Holt-forecast (`afvaldb/forecast.py`) → `/api/afval/forecast` + doorkijk-grafiek en extra cijfers in de modal. DB op `/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb`.
- 🚧 **UC-08c — Brondata & data-chatbot:** linkerpaneel op `/afval` met brondata-uitleg (`GET /api/afval/bronnen`) en een NL→SQL-chatbot (`POST /api/afval/chat`, `usecases/afval/chat.py`) die read-only DuckDB-SELECT's genereert (Qwen), valideert (SELECT-only, verboden trefwoorden, LIMIT) en samenvat. Toont de uitgevoerde SQL + bron/disclaimer.

---

## Eerste run (Sprint 1)

```bash
# NVMe dirs (eenmalig, jij doet dit met sudo)
sudo mkdir -p /mnt/nvme/geluidsmeter/data/{raw_features,processed,external/{atlas,cvgg,pdok_3d_geluid},catalog}
sudo chown -R bob:bob /mnt/nvme/geluidsmeter

# Venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Eerste test (5s, geen opslaan)
python3 scripts/01_record_features.py --duration 5 --dry-run
```

---

## Poorten (context orin3)

| Dienst | Poort |
|---|---|
| **LeefomgevingLab API** | **8792** |
| **LeefomgevingLab embeddings (bge-m3)** | **8082** |
| felix-nazaten upload | 8791 (bezet) |
| Derwisch transcriptie | 8790 |
| Derwisch backend | 8789 (**https**, self-signed) |
| morele-helper admin | 8788 |
| waterlab dashboard | 8000 |
| sysmonitor status | 8795 |
| Derwisch LLM Qwen | 8080 |
| ~~Derwisch LLM Nemo~~ | ~~8081~~ — unit is disabled, er draait niets |
