# Geluidsmeter — Claude Code instructies

Lees altijd eerst: `CLAUDE_NOTES.md`
Dan: `core/config.yaml`

---

## ⚠️ Kritieke waarschuwingen

| # | Valkuil | Correct |
|---|---------|---------|
| 1 | `find ~` **bevriest** op orin3 | Gebruik `ls` of specifieke paden |
| 2 | Poort **8791** is bezet | Door `felix-nazaten/upload_server.py` — Geluidsmeter gebruikt **8792** |
| 3 | NVMe data-dirs vereisen **sudo** | `sudo mkdir /mnt/nvme/geluidsmeter/... && sudo chown bob:bob` |
| 4 | C922 mic is **gedeeld** met Derwisch ritueel.py | Conflict als ritueel.py opneemt — check eerst |
| 5 | `core/location_private.yaml` **nooit committen** | Staat in .gitignore — bevat echte coördinaten |
| 6 | Data staat op **NVMe**, niet in de repo | `/mnt/nvme/geluidsmeter/data/` — staat ook in .gitignore |

---

## Repo-locatie

| Repo | Pad | Remote |
|------|-----|--------|
| Geluidsmeter | `/home/bob/Geluidsmeter` | https://github.com/bopfelix-derwisch/geluidsmeter |

Push met: `git push origin master`

---

## Services (nog niet actief — Sprint 0)

- `geluidsmeter-capture.service` — audio capture loop (unit in `systemd/`)
- `geluidsmeter-api.service` — FastAPI op poort 8792 (unit in `systemd/`)

Installeren (als je zover bent):
```bash
sudo cp systemd/geluidsmeter-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geluidsmeter-capture
```

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
- ⏭️ **Sprint 5:** demo

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
| **Geluidsmeter API** | **8792** |
| felix-nazaten upload | 8791 (bezet) |
| Derwisch transcriptie | 8790 |
| Derwisch backend | 8789 |
| Derwisch LLM Qwen | 8080 |
| Derwisch LLM Nemo | 8081 |
