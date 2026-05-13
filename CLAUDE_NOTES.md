# Geluidsmeter — Claude Notes

## Environment check (2026-05-13)

| Check | Uitkomst |
|---|---|
| Host | orin3, Jetson AGX Orin 64GB |
| OS | Ubuntu 22.04.5 LTS (aarch64) |
| Python | 3.10.12 |
| pipx | niet geïnstalleerd |
| uv | niet geïnstalleerd |
| portolan | niet geïnstalleerd |
| Mic | C922 Pro Stream Webcam (PortAudio device 0, `hw:0,0` — gebruik `"C922 Pro Stream Webcam"` als device_name) |
| NVMe | /mnt/nvme/ — 429GB vrij (eigenaar root/marc — sudo nodig voor dirs) |
| eMMC / | 12GB vrij — krap |
| RAM | 61GB totaal, ~31GB vrij |
| Poort 8791 | **BEZET** door `felix-nazaten/upload_server.py` (pid 1388) |
| Poort 8792 | vrij → Geluidsmeter API |

## Keuzes gemaakt bij project-init

- **Mic:** C922 gedeeld met Derwisch (`plughw:CARD=Webcam,DEV=0`) — kan conflicteren als `ritueel.py` opneemt
- **Data:** `/mnt/nvme/geluidsmeter/data/` — NVMe (sudo nodig voor aanmaken)
- **API poort:** 8792 (8791 al bezet)
- **Portolan:** lokale catalogus in MVP, geen MinIO

## NVMe dirs aanmaken (handmatig — sudo vereist)

```bash
sudo mkdir -p /mnt/nvme/geluidsmeter/data/{raw_features,processed,external/{atlas,cvgg,pdok_3d_geluid},catalog}
sudo chown -R bob:bob /mnt/nvme/geluidsmeter
```

## Venv aanmaken en packages installeren

```bash
cd ~/Geluidsmeter
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

## Eerste test (na venv + NVMe dirs)

```bash
cd ~/Geluidsmeter
source .venv/bin/activate
python3 scripts/01_record_features.py --duration 5 --dry-run
```

## Portolan installeren (na uv of pipx)

```bash
# Als uv beschikbaar:
uv tool install portolan-cli

# Anders:
pipx install portolan-cli
```
