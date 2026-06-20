"""FastAPI service op poort 8792."""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import geopandas as gpd
from shapely.geometry import Point as ShapelyPoint
from .config import load_config, load_private_location
from .aggregate import _round_location
from .source_match import get_rivm_lden
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.connectors.rev import RevConnector
from leefomgevinglab.usecases.rev_viewer import service as rev_service


class MobileSubmission(BaseModel):
    dba: float | None = None
    lat: float
    lon: float
    naam: str = "Mobiele meting"


def _location_entry(
    config: dict,
    pub_lat: float,
    pub_lon: float,
    rms_dba: float | None,
    rivm_lden: float | None,
) -> dict:
    norm_lden = 48
    norm_status = None
    if rms_dba is not None:
        norm_status = "binnen_norm" if rms_dba <= norm_lden else "boven_norm"
    loc_cfg = config.get("location", {})
    return {
        "id": loc_cfg.get("public_id", "meetlocatie"),
        "naam": loc_cfg.get("public_name", "Meetlocatie"),
        "lat": pub_lat,
        "lon": pub_lon,
        "precision_m": loc_cfg.get("public_location_precision_m", 100),
        "lden_gemeten": rms_dba,
        "rivm_lden": rivm_lden,
        "norm_lden": norm_lden,
        "norm_status": norm_status,
        "laatste_meting": datetime.now(timezone.utc).isoformat() if rms_dba is not None else None,
        "kwaliteit": config.get("project", {}).get("quality_label", "prototype_indicatief_niet_juridisch"),
        "source": "jetson",
    }


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


def _mobile_location_entries(rivm_gdf=None) -> list[dict]:
    fp_str = _config.get("mobile", {}).get("measurements_file", "")
    if not fp_str:
        return []
    fp = Path(fp_str)
    if not fp.exists():
        return []
    norm_lden = 48
    entries = []
    with open(fp) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                dba = rec.get("dba")
                norm_status = None
                if dba is not None:
                    norm_status = "binnen_norm" if dba <= norm_lden else "boven_norm"
                rivm_lden = None
                if rivm_gdf is not None:
                    rivm_lden = get_rivm_lden(ShapelyPoint(rec["lon"], rec["lat"]), rivm_gdf)
                entries.append({
                    "id": rec["id"],
                    "naam": rec.get("naam", "Mobiele meting"),
                    "lat": rec["lat"],
                    "lon": rec["lon"],
                    "precision_m": 20,
                    "lden_gemeten": dba,
                    "rivm_lden": rivm_lden,
                    "norm_lden": norm_lden,
                    "norm_status": norm_status,
                    "laatste_meting": rec["ts"],
                    "kwaliteit": rec.get("kwaliteit", "prototype_indicatief_niet_juridisch"),
                    "source": "mobile",
                })
            except KeyError:
                continue
    return entries


@app.get("/")
def root():
    return RedirectResponse(url="/public")


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

    rivm_lden = None
    rivm_path = Path(_config["outputs"]["external_dir"]) / "rivm" / "geluid_buurt.geojson"
    if rivm_path.exists():
        rivm_gdf = gpd.read_file(rivm_path)
        rivm_lden = get_rivm_lden(ShapelyPoint(loc["lon"], loc["lat"]), rivm_gdf)

    return {
        "today": today,
        "rms_dba_latest": rms_dba,
        "calibration_offset_db": offset,
        "calibrated": offset != 0,
        "profile": profile,
        "history": history[-10080:],
        "norm_lden": 48,
        "norm_lnight": 43,
        "rivm_lden": rivm_lden,
        "location": {"lat": pub_lat, "lon": pub_lon, "precision_m": precision_m},
    }


@app.get("/api/locations")
def api_locations():
    offset = _config.get("measurement", {}).get("calibration_offset_db", 0)
    feature = _latest_feature()
    # Zonder kalibratie (offset=0) is rms_dbfs negatief — niet vergelijkbaar met norm in dB(A)
    calibrated = offset != 0
    rms_dba = round(feature["rms_dbfs"] + offset, 1) if (feature and calibrated) else None

    loc = load_private_location(_config)
    precision_m = _config.get("location", {}).get("public_location_precision_m", 100)
    pub_lat, pub_lon = _round_location(loc["lat"], loc["lon"], precision_m)

    rivm_lden = None
    rivm_path = Path(_config["outputs"]["external_dir"]) / "rivm" / "geluid_buurt.geojson"
    if rivm_path.exists():
        rivm_gdf = gpd.read_file(rivm_path)
        rivm_lden = get_rivm_lden(ShapelyPoint(loc["lon"], loc["lat"]), rivm_gdf)

    return [_location_entry(_config, pub_lat, pub_lon, rms_dba, rivm_lden)] + _mobile_location_entries(rivm_gdf if rivm_path.exists() else None)


@app.post("/api/submit", status_code=201)
def api_submit(
    submission: MobileSubmission,
    authorization: str | None = Header(default=None),
):
    submit_token = _config.get("mobile", {}).get("submit_token", "")
    if not submit_token or authorization != f"Bearer {submit_token}":
        raise HTTPException(status_code=401, detail="Ongeldige token")

    record = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "lat": submission.lat,
        "lon": submission.lon,
        "naam": submission.naam,
        "dba": submission.dba,
        "source": "mobile",
        "kwaliteit": _config.get("project", {}).get(
            "quality_label", "prototype_indicatief_niet_juridisch"
        ),
    }

    fp = Path(_config["mobile"]["measurements_file"])
    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "a") as f:
        f.write(json.dumps(record) + "\n")

    return {"id": record["id"], "accepted": True}


@app.get("/geodata/rivm")
def geodata_rivm():
    p = Path(_config["outputs"]["external_dir"]) / "rivm" / "geluid_buurt.geojson"
    if not p.exists():
        return JSONResponse({"type": "FeatureCollection", "features": []})
    return JSONResponse(json.loads(p.read_text()))


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


@app.get("/public", response_class=HTMLResponse)
def public_page():
    return (_static_dir / "public.html").read_text()


@app.get("/meten", response_class=HTMLResponse)
def meten_page():
    return (_static_dir / "meten.html").read_text()


def _rev_connector() -> RevConnector:
    ll = _config.get("leefomgevinglab", {})
    rev = ll.get("rev", {})
    return RevConnector(
        base_url=rev.get("ogc_base_url", ""),
        collection=rev.get("collection", ""),
        max_features=rev.get("max_features", 500),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


@app.get("/api/rev/features")
def api_rev_features(bbox: str):
    try:
        return _rev_connector().features(bbox)
    except ConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class DuidingRequest(BaseModel):
    properties: dict


@app.post("/api/duiding")
def api_duiding(req: DuidingRequest):
    ll = _config.get("leefomgevinglab", {})
    llm = ll.get("llm", {})
    try:
        return rev_service.duiding(
            req.properties,
            llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
            model=llm.get("model", "qwen2.5-32b"),
            timeout_s=llm.get("timeout_s", 60),
        )
    except ConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/viewer", response_class=HTMLResponse)
def viewer_page():
    viewer_html = Path(__file__).parent.parent / "leefomgevinglab" / "viewer" / "static" / "viewer.html"
    return viewer_html.read_text()
