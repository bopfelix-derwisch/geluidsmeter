#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

if ! command -v portolan &>/dev/null; then
  echo "FOUT: portolan niet geïnstalleerd. Voer uit: uv tool install portolan-cli"
  exit 1
fi

if [ ! -f "catalog.json" ] && [ ! -d ".portolan" ]; then
  portolan init
fi

portolan add /mnt/nvme/geluidsmeter/data/processed/

if [ ! -f "metadata.yaml" ]; then
  portolan metadata init || true
fi

portolan metadata validate || true
portolan check --fix
portolan readme || true

echo "Portolan catalogus bijgewerkt."
echo "Optioneel pushen:"
echo "  portolan push s3://<bucket>/geluidsmeter --collection geluidsmeter"
