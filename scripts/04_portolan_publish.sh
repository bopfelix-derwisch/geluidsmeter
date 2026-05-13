#!/usr/bin/env bash
set -euo pipefail

CATALOG_DIR="/mnt/nvme/geluidsmeter/data/catalog"
PROCESSED_DIR="/mnt/nvme/geluidsmeter/data/processed"
COLLECTION_DIR="$CATALOG_DIR/geluidsmeter"
TODAY="$(date -u +%Y-%m-%d)"

if ! command -v portolan &>/dev/null; then
  echo "FOUT: portolan niet geïnstalleerd. Voer uit: pipx install portolan-cli"
  exit 1
fi

# Catalogus initialiseren als die nog niet bestaat
if [ ! -f "$CATALOG_DIR/catalog.json" ]; then
  portolan init "$CATALOG_DIR" --auto --title "Geluidsmeter" --description "Lokaal geluidsprofiel — prototype indicatief"
fi

# Collection-subdir aanmaken
mkdir -p "$COLLECTION_DIR"

# GeoParquet kopiëren naar collection (portolan beheert bestanden binnen de catalog)
for f in "$PROCESSED_DIR"/measurements_*.parquet; do
  [ -f "$f" ] && cp -u "$f" "$COLLECTION_DIR/"
done

# Toevoegen aan catalogus
cd "$CATALOG_DIR"
portolan add geluidsmeter/ --datetime "$TODAY"

portolan check --fix "$CATALOG_DIR" || true

echo "Portolan catalogus bijgewerkt: $CATALOG_DIR"
