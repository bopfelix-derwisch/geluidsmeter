"""FastAPI service op poort 8792."""
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config, load_private_location
from .aggregate import _round_location

app = FastAPI(title="Geluidsmeter API", version="0.1.0")
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
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


@app.get("/summary")
def summary():
    """Dagprofiel + laatste meting voor dashboard."""
    processed_dir = Path(_config["outputs"]["processed_dir"])
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    profile_path = processed_dir / f"daily_profile_{today}.json"
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}

    offset = _config.get("measurement", {}).get("calibration_offset_db", 0)
    feature = _latest_feature()
    rms_dba = None
    if feature:
        rms_dba = round(feature["rms_dbfs"] + offset, 1)

    raw_dir = Path(_config["outputs"]["raw_features_dir"])
    history = []
    for fp in sorted(raw_dir.glob("sound_features_*.jsonl"))[-7:]:
        with open(fp) as f:
            for line in f:
                row = json.loads(line)
                history.append({"ts": row["ts"], "rms_dbfs": row["rms_dbfs"],
                                 "dba_est": round(row["rms_dbfs"] + offset, 1)})

    loc = load_private_location(_config)
    precision_m = _config.get("location", {}).get("public_location_precision_m", 100)
    pub_lat, pub_lon = _round_location(loc["lat"], loc["lon"], precision_m)

    return {
        "today": today,
        "rms_dba_latest": rms_dba,
        "calibration_offset_db": offset,
        "calibrated": offset != 0,
        "profile": profile,
        "history": history[-10080:],  # max 7 dagen × 24h × 60 metingen/uur
        "norm_lden": 48,
        "norm_lnight": 43,
        "location": {"lat": pub_lat, "lon": pub_lon, "precision_m": precision_m},
    }


@app.get("/geodata/nwb")
def geodata_nwb():
    p = Path(_config["outputs"]["external_dir"]) / "atlas" / "nwb_wegvakken.geojson"
    if not p.exists():
        return JSONResponse({"type": "FeatureCollection", "features": []})
    return JSONResponse(json.loads(p.read_text()))


@app.get("/geodata/bgt")
def geodata_bgt():
    p = Path(_config["outputs"]["external_dir"]) / "bgt" / "bgt_wegdeel.geojson"
    if not p.exists():
        return JSONResponse({"type": "FeatureCollection", "features": []})
    return JSONResponse(json.loads(p.read_text()))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (_static_dir / "dashboard.html").read_text()
