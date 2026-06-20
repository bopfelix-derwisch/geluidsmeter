# Geluidsmeter

Lokaal geluidsprofiel meten op een vaste locatie (Jetson AGX Orin / orin3). Privacyvriendelijke features, geo-informatie als uitvoer, publicatie via Portolan/STAC.

**⚠️ Prototype — indicatief, niet juridisch bruikbaar.**

## Architectuur

```
[C922 USB-mic op orin3]
  → audio_capture.py (sounddevice, 60s frames)
  → feature_extract.py (RMS/Lmax/banden/events — géén ruwe audio)
  → JSONL in /mnt/nvme/geluidsmeter/data/raw_features/
  → aggregate.py (dag/avond/nacht profiel)
  → GeoParquet + GeoJSON in /mnt/nvme/geluidsmeter/data/processed/
  → Portolan CLI (STAC catalogus)
```

## Setup

```bash
# 1. NVMe dirs aanmaken (eenmalig, sudo vereist)
sudo mkdir -p /mnt/nvme/geluidsmeter/data/{raw_features,processed,external/{atlas,cvgg,pdok_3d_geluid},catalog}
sudo chown -R bob:bob /mnt/nvme/geluidsmeter

# 2. Venv
cd ~/Geluidsmeter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Locatie invullen (NOOIT committen)
nano core/location_private.yaml

# 4. Test meting (5 seconden, geen opslaan)
python3 scripts/01_record_features.py --duration 5 --dry-run

# 5. Capture loop starten
python3 -c "from geluidsmeter.audio_capture import run_capture_loop; run_capture_loop()"
```

## API

```bash
bash scripts/05_run_api.sh
# → http://localhost:8792/latest
# → http://localhost:8792/health
```

## Poorten

| Dienst | Poort |
|---|---|
| Geluidsmeter API | **8792** |
| Derwisch backend | 8789 |
| Derwisch LLM | 8080/8081 |
| felix-nazaten upload | 8791 |

## LeefomgevingLab — toekomstige architectuur

Dit project groeit uit tot **LeefomgevingLab**, een edge geo-lab op Jetson Orin. Geluid is één van meerdere use-cases. De REV-viewer (UC-04) is beschikbaar op `/viewer` met features uit PDOK OGC API (productiefaciliteiten). Raadpleeg `LeefomgevingLab architectuuropzet v0_3.md` en `docs/superpowers/specs/2026-06-20-leefomgevinglab-fundering-design.md` voor architectuur; zie `docs/superpowers/plans/2026-06-20-leefomgevinglab-fundering-uc04.md` voor implementatieplan.

## Privacy

- `store_raw_audio: false` — geen ruwe audio op disk
- Locatie afgerond op 100m grid in publieke output
- `core/location_private.yaml` staat in `.gitignore`
