"""FastAPI service op poort 8792."""
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import load_config

app = FastAPI(title="Geluidsmeter API", version="0.1.0")
_config: dict = {}


@app.on_event("startup")
def startup():
    global _config
    _config = load_config()


def _latest_feature() -> dict | None:
    raw_dir = Path(_config["outputs"]["raw_features_dir"])
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    fp = raw_dir / f"sound_features_{today}.jsonl"
    if not fp.exists():
        return None
    last_line = None
    with open(fp) as f:
        for line in f:
            last_line = line.strip()
    return json.loads(last_line) if last_line else None


@app.get("/health")
def health():
    return {"status": "ok", "project": "geluidsmeter", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/latest")
def latest():
    feature = _latest_feature()
    if not feature:
        return JSONResponse({"error": "geen data vandaag"}, status_code=404)
    return feature


@app.get("/metadata")
def metadata():
    return {
        "project": _config.get("project", {}),
        "measurement": {k: v for k, v in _config.get("measurement", {}).items() if k != "device_name"},
        "api_port": _config.get("api", {}).get("port", 8792),
    }
