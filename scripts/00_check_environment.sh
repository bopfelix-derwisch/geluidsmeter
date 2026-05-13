#!/usr/bin/env bash
# Environment check — uitvoer bewaren in CLAUDE_NOTES.md
set -euo pipefail

echo "=== Geluidsmeter Environment Check ==="
echo "Datum: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

echo "--- Machine ---"
uname -a
hostnamectl 2>/dev/null | grep -E "hostname|OS|Kernel" || true

echo ""
echo "--- Python ---"
python3 --version
which python3

echo ""
echo "--- Tools ---"
which pipx 2>/dev/null && echo "pipx: $(pipx --version)" || echo "pipx: niet geïnstalleerd"
which uv 2>/dev/null && echo "uv: $(uv --version)" || echo "uv: niet geïnstalleerd"
which portolan 2>/dev/null && echo "portolan: $(portolan --version 2>/dev/null || echo 'versie onbekend')" || echo "portolan: niet geïnstalleerd"

echo ""
echo "--- Audio ---"
arecord -l 2>/dev/null || echo "arecord niet beschikbaar"
lsusb | grep -i -E "audio|webcam|logitech" || true

echo ""
echo "--- Storage ---"
df -h /home/bob /mnt/nvme 2>/dev/null || df -h /home/bob
ls /mnt/nvme/geluidsmeter/data/ 2>/dev/null && echo "NVMe data dirs: OK" || echo "NVMe data dirs: aanmaken vereist"

echo ""
echo "--- Memory ---"
free -h

echo ""
echo "--- Actieve services (derwisch/geluidsmeter) ---"
systemctl --type=service --state=running 2>/dev/null | grep -E "derwisch|geluidsmeter" || echo "geen relevante services actief"

echo ""
echo "--- Poorten in gebruik ---"
ss -tlnp 2>/dev/null | grep -E "8789|8080|8081|8790|8791|8792" || echo "geen van deze poorten in gebruik"

echo ""
echo "--- Python packages (venv) ---"
if [ -d "$(dirname "$0")/../.venv" ]; then
  source "$(dirname "$0")/../.venv/bin/activate" && pip list 2>/dev/null | grep -E "numpy|scipy|sounddevice|pandas|geopandas|fastapi|pyarrow|pyyaml" || true
else
  echo ".venv nog niet aangemaakt — voer eerst: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
fi

echo ""
echo "=== Check klaar ==="
