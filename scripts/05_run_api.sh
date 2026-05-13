#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

PORT=$(python3 -c "import yaml; c=yaml.safe_load(open('core/config.yaml')); print(c['api']['port'])" 2>/dev/null || echo "8792")

echo "Geluidsmeter API starten op poort $PORT..."
uvicorn geluidsmeter.api:app --host 0.0.0.0 --port "$PORT" --app-dir src
