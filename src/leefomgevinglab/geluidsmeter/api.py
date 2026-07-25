"""FastAPI service op poort 8792."""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv

# Laad .env (o.a. DSO_API_KEY) bij import — werkt voor systemd
# (WorkingDirectory=repo-root) en handmatige uvicorn-runs vanaf de repo-root.
load_dotenv()

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
import os
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.dso_zoek import ZoekConnector
from leefomgevinglab.usecases.vergunningen import service as vergunningen_service
from leefomgevinglab.usecases.vergunningen import resolver as vergunningen_resolver
from leefomgevinglab.usecases.vergunningen import omgevingsplan as omgevingsplan_mod
from leefomgevinglab.usecases.vergunningen import externe_veiligheid as externe_veiligheid_mod
from leefomgevinglab.connectors.externe_veiligheid import ExterneVeiligheidConnector
from leefomgevinglab.usecases import wfs_kwaliteit as wfs_kwaliteit_mod
from leefomgevinglab.connectors.ozon import OzonConnector
from functools import partial
from leefomgevinglab.rag.embed import embed_texts
from leefomgevinglab.rag.store import VectorStore
from leefomgevinglab.usecases.vergunningen import chatbot
from leefomgevinglab.semantiek import graph as semantiek_graph
from leefomgevinglab.ld import store as ld_store
from leefomgevinglab.usecases.datavraag import grounding as dv_grounding
from leefomgevinglab.usecases.datavraag import service as dv_service
from leefomgevinglab.usecases.afval import service as afval_service
from leefomgevinglab.usecases.afval import duiding as afval_duiding
from leefomgevinglab.usecases.afval import chat as afval_chat
from leefomgevinglab.afvaldb import store as afvaldb_store


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


@app.get("/", response_class=HTMLResponse)
def root():
    landing = Path(__file__).parent.parent / "static" / "index.html"
    return landing.read_text()


@app.get("/roadmap", response_class=HTMLResponse)
def roadmap_page():
    return (Path(__file__).parent.parent / "static" / "roadmap.html").read_text()


@app.get("/kwaliteit", response_class=HTMLResponse)
def kwaliteit_page():
    return (Path(__file__).parent.parent / "static" / "kwaliteit.html").read_text()


@app.get("/wfs-kwaliteit", response_class=HTMLResponse)
def wfs_kwaliteit_page():
    return (Path(__file__).parent.parent / "static" / "wfs-kwaliteit.html").read_text()


@app.get("/api/wfs-kwaliteit")
def api_wfs_kwaliteit(refresh: int = 0, bronhouder: str = "", activiteit: str = ""):
    import hashlib
    ll = _config.get("leefomgevinglab", {})
    cfg = ll.get("wfs_kwaliteit", {})
    wfs_url = cfg.get("wfs_url", "")
    cache_dir = Path(ll.get("cache_dir", "/tmp/llab_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cql = wfs_kwaliteit_mod.bouw_cql(bronhouder or None, activiteit or None)
    sleutel = hashlib.sha256((cql or "basis").encode()).hexdigest()[:16]
    cache = cache_dir / f"wfs_kwaliteit_{sleutel}.json"
    ttl = cfg.get("cache_ttl_s", 86400)
    if not refresh and cache.exists() and (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime) < ttl:
        data = json.loads(cache.read_text())
        data["uit_cache"] = True
        return data
    lagen = cfg.get("lagen") or wfs_kwaliteit_mod.lagen_uit_capabilities(
        wfs_url, namespace=cfg.get("namespace", "rev_public:"))
    imev = cfg.get("imev_verplichte_velden") or wfs_kwaliteit_mod.IMEV_VERPLICHTE_VELDEN
    data = wfs_kwaliteit_mod.scan_lagen(wfs_url, lagen, sample_n=cfg.get("sample_n", 300),
                                        cql=cql, imev_velden=imev)
    data["filter"] = {"bronhouder": bronhouder, "activiteit": activiteit}
    cache.write_text(json.dumps(data))
    data["uit_cache"] = False
    return data


@app.get("/demo", response_class=HTMLResponse)
def demo_page():
    return (Path(__file__).parent.parent / "static" / "demo.html").read_text()


@app.get("/poc", response_class=HTMLResponse)
def poc_page():
    return (Path(__file__).parent.parent / "static" / "poc.html").read_text()


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
        collections=rev.get("collections", []),
        max_features=rev.get("max_features", 500),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


@app.get("/api/rev/features")
def api_rev_features(bbox: str):
    try:
        return _rev_connector().features(bbox)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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


def _dso_env_key(env: str) -> str | None:
    """Productie- of pre-key uit .env op basis van de gekozen omgeving."""
    return os.environ.get("DSO_API_KEY_PROD") if env == "prod" else os.environ.get("DSO_API_KEY")


def _dso_base_url(dso: dict, endpoint: str, env: str) -> str:
    """Base-URL voor een endpoint (zoek|rtr|uitvoeren) in de gekozen omgeving (pre|prod)."""
    return dso.get(env, {}).get(f"{endpoint}_base_url", "")


def _zoek_connector() -> ZoekConnector:
    ll = _config.get("leefomgevinglab", {})
    dso = ll.get("dso", {})
    env = dso.get("zoek_env", "pre")
    return ZoekConnector(
        base_url=_dso_base_url(dso, "zoek", env),
        api_key=_dso_env_key(env),
        api_key_header=dso.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


def _dso_connector() -> DsoConnector:
    ll = _config.get("leefomgevinglab", {})
    dso = ll.get("dso", {})
    rtr_env = dso.get("rtr_env", "pre")
    uitv_env = dso.get("uitvoeren_env", "pre")
    return DsoConnector(
        rtr_base_url=_dso_base_url(dso, "rtr", rtr_env),
        uitvoeren_base_url=_dso_base_url(dso, "uitvoeren", uitv_env),
        rtr_api_key=_dso_env_key(rtr_env),
        uitvoeren_api_key=_dso_env_key(uitv_env),
        api_key_header=dso.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


def _ozon_connector() -> OzonConnector:
    ll = _config.get("leefomgevinglab", {})
    ozon = ll.get("ozon", {})
    env = ozon.get("environment", "pre")
    return OzonConnector(
        base_url=ozon.get(env, {}).get("base_url", ""),
        api_key=_dso_env_key(env),
        api_key_header=ozon.get("api_key_header", "x-api-key"),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


def _ev_connector() -> ExterneVeiligheidConnector:
    ll = _config.get("leefomgevinglab", {})
    ev = ll.get("externe_veiligheid", {})
    return ExterneVeiligheidConnector(
        wfs_url=ev.get("wfs_url", ""),
        cache_dir=ll.get("cache_dir", "/tmp/llab_cache"),
    )


def _llm_cfg() -> dict:
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    return {
        "llm_base_url": llm.get("base_url", "http://localhost:8080/v1"),
        "model": llm.get("model", "qwen2.5-32b"),
        "timeout_s": llm.get("timeout_s", 60),
    }


class RegelsRequest(BaseModel):
    activiteit: str
    locatie: dict | None = None


@app.post("/api/regels")
def api_regels(req: RegelsRequest):
    if not req.locatie or "lat" not in req.locatie or "lon" not in req.locatie:
        raise HTTPException(status_code=422, detail="locatie met lat en lon is verplicht")
    return vergunningen_service.regels_opzoeken(
        req.activiteit, req.locatie, _zoek_connector(), _dso_connector(), _llm_cfg()
    )


def _rag_embed_fn():
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    emb = rag.get("embed", {})
    return partial(embed_texts, base_url=emb.get("base_url", ""), model=emb.get("model", ""))


def _rag_store():
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    try:
        return VectorStore.load(rag.get("store_dir", ""))
    except FileNotFoundError:
        return None


class ChatRequest(BaseModel):
    vraag: str
    locatie: dict | None = None


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    store = _rag_store()
    if store is None:
        return {
            "vraag": req.vraag, "antwoord": None, "bronnen": [], "regels": None, "omgevingsplan": None,
            "externe_veiligheid": None,
            "onzekerheid": True, "disclaimer": chatbot.DISCLAIMER, "vangnet": chatbot.VANGNET,
            "beschikbaar": False,
        }
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    ozon_cfg = _config.get("leefomgevinglab", {}).get("ozon", {})

    def regels_fn(vraag: str, locatie: dict) -> dict:
        activiteit = vergunningen_resolver.extract_activiteit(
            vraag, llm.get("base_url", "http://localhost:8080/v1"),
            llm.get("model", "qwen2.5-32b"), llm.get("timeout_s", 60),
        )
        return vergunningen_service.regels_opzoeken(
            activiteit, locatie, _zoek_connector(), _dso_connector(), _llm_cfg()
        )

    def omgevingsplan_fn(locatie: dict):
        return omgevingsplan_mod.omgevingsplan_op_locatie(
            locatie, _ozon_connector(),
            max_regelingen=ozon_cfg.get("max_regelingen", 3),
            max_regelteksten=ozon_cfg.get("max_regelteksten", 5),
        )

    ev_cfg = _config.get("leefomgevinglab", {}).get("externe_veiligheid", {})

    def ev_fn(locatie: dict):
        return externe_veiligheid_mod.check_aandachtsgebieden(
            locatie, _ev_connector(), ev_cfg.get("lagen", {}), max_n=ev_cfg.get("max_features", 5))

    return chatbot.beantwoord(
        req.vraag, store, _rag_embed_fn(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"),
        top_k=rag.get("top_k", 4), timeout_s=llm.get("timeout_s", 60),
        locatie=req.locatie, regels_fn=regels_fn, omgevingsplan_fn=omgevingsplan_fn,
        ev_fn=ev_fn,
    )


@app.get("/chatbot", response_class=HTMLResponse)
def chatbot_page():
    return (Path(__file__).parent.parent / "static" / "chat.html").read_text()


def _semantiek_graph():
    sem = _config.get("leefomgevinglab", {}).get("semantiek", {})
    return semantiek_graph.load_graph(sem.get("store_dir", ""))


@app.get("/api/semantiek/graph")
def api_semantiek_graph(zoekTerm: str | None = None, bron: str | None = None):
    graph = _semantiek_graph()
    if graph is None:
        return {"elements": {"nodes": [], "edges": []}, "bronnen": [], "beschikbaar": False}
    nodes, edges = graph["nodes"], graph["edges"]
    if bron:
        keep = {n["data"]["id"] for n in nodes if n["data"]["bron"] in (bron, "IMX-Geo")}
        nodes = [n for n in nodes if n["data"]["id"] in keep]
        edges = [e for e in edges if e["data"]["source"] in keep and e["data"]["target"] in keep]
    if zoekTerm:
        z = zoekTerm.lower()
        match = {n["data"]["id"] for n in nodes
                 if z in n["data"]["label"].lower() or z in (n["data"].get("definitie") or "").lower()}
        keep = set(match)
        for e in edges:
            if e["data"]["source"] in match:
                keep.add(e["data"]["target"])
            if e["data"]["target"] in match:
                keep.add(e["data"]["source"])
        nodes = [n for n in nodes if n["data"]["id"] in keep]
        edges = [e for e in edges if e["data"]["source"] in keep and e["data"]["target"] in keep]
    return {"elements": {"nodes": nodes, "edges": edges}, "bronnen": graph["bronnen"], "beschikbaar": True}


@app.get("/api/semantiek/node")
def api_semantiek_node(uri: str):
    graph = _semantiek_graph()
    if graph is None:
        raise HTTPException(status_code=404, detail="Geen graaf beschikbaar")
    by_id = {n["data"]["id"]: n for n in graph["nodes"]}
    node = by_id.get(uri)
    if node is None:
        raise HTTPException(status_code=404, detail="Node niet gevonden")
    buren = []
    for e in graph["edges"]:
        if e["data"]["source"] == uri and e["data"]["target"] in by_id:
            buren.append({"node": by_id[e["data"]["target"]], "relatie": e["data"]["relatie"]})
        elif e["data"]["target"] == uri and e["data"]["source"] in by_id:
            buren.append({"node": by_id[e["data"]["source"]], "relatie": e["data"]["relatie"]})
    return {"node": node, "buren": buren}


@app.get("/semantiek", response_class=HTMLResponse)
def semantiek_page():
    return (Path(__file__).parent.parent / "static" / "semantiek.html").read_text()


def _ld_graph():
    ld = _config.get("leefomgevinglab", {}).get("ld", {})
    return ld_store.load_graph(ld.get("store_dir", ""))


class LdSparqlRequest(BaseModel):
    query: str


@app.post("/api/ld/sparql")
def api_ld_sparql(req: LdSparqlRequest):
    g = _ld_graph()
    if g is None:
        return {"rows": [], "beschikbaar": False}
    try:
        return {"rows": ld_store.run_sparql(g, req.query), "beschikbaar": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ongeldige SPARQL: {exc}")


def _dv_graph():
    ld = _config.get("leefomgevinglab", {}).get("ld", {})
    return ld_store.load_graph(ld.get("store_dir", ""))


def _dv_grounding():
    shapes = Path(__file__).parent.parent / "leefomgevinglab" / "ld" / "shapes.ttl"
    txt = shapes.read_text() if shapes.exists() else ""
    return dv_grounding.build_grounding(txt)


class DatavraagRequest(BaseModel):
    vraag: str


@app.post("/api/datavraag")
def api_datavraag(req: DatavraagRequest):
    g = _dv_graph()
    ll = _config.get("leefomgevinglab", {})
    llm = ll.get("llm", {})
    ld = ll.get("ld", {})
    return dv_service.beantwoord(
        req.vraag, g, _dv_grounding(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"), timeout_s=llm.get("timeout_s", 60),
        kkg_endpoint=ld.get("kkg_endpoint", ""), provincie=ld.get("provincie", "Zuid-Holland"),
        straal_m=ld.get("nabijheid_straal_m", 500))


@app.get("/datavraag", response_class=HTMLResponse)
def datavraag_page():
    return (Path(__file__).parent.parent / "static" / "datavraag.html").read_text()


def _afval_data_dir() -> str:
    return _config.get("leefomgevinglab", {}).get("afval", {}).get(
        "data_dir", "/mnt/nvme/geluidsmeter/data/external/afval")


def _afvaldb_path() -> str:
    return _config.get("leefomgevinglab", {}).get("afvaldb", {}).get(
        "db_path", "/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb")


@app.get("/api/afval/forecast")
def api_afval_forecast(regio: str, afvalstroom: str):
    if not Path(_afvaldb_path()).exists():
        raise HTTPException(status_code=503, detail="Afval-database nog niet gevuld")
    return afval_service.forecast(_afvaldb_path(), regio, afvalstroom)


@app.get("/afval", response_class=HTMLResponse)
def afval_page():
    return (Path(__file__).parent.parent / "static" / "afval.html").read_text()


@app.get("/api/afval/meta")
def api_afval_meta():
    try:
        return afval_service.meta(_afval_data_dir())
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")


@app.get("/api/afval/choropleth")
def api_afval_choropleth(afvalstroom: str, jaar: int, indicator: str = "volume"):
    try:
        return afval_service.choropleth(_afval_data_dir(), afvalstroom, jaar, indicator)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")


@app.get("/api/afval/trend")
def api_afval_trend(regio: str, afvalstroom: str):
    try:
        return afval_service.trend(_afval_data_dir(), regio, afvalstroom)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")


class AfvalDuidingRequest(BaseModel):
    regio: str
    afvalstroom: str
    jaar: int


@app.post("/api/afval/duiding")
def api_afval_duiding(req: AfvalDuidingRequest):
    ll = _config.get("leefomgevinglab", {})
    llm = ll.get("llm", {})
    try:
        ctx = afval_service.stroom_context(_afval_data_dir(), req.regio, req.afvalstroom, req.jaar)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Afval-aggregaat nog niet ingeladen")
    if Path(_afvaldb_path()).exists():
        try:
            fc = afval_service.forecast(_afvaldb_path(), req.regio, req.afvalstroom)
            ctx["forecast"] = fc["forecast"][-1] if fc["forecast"] else None
            ctx["extra"] = afval_service.extra_context(_afvaldb_path(), req.afvalstroom)
        except Exception:
            ctx["forecast"] = None
            ctx["extra"] = None
    else:
        ctx["forecast"] = None
        ctx["extra"] = None
    try:
        out = afval_duiding.duiding(
            ctx["naam"], req.afvalstroom, req.jaar, ctx,
            llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
            model=llm.get("model", "qwen2.5-32b"),
            timeout_s=llm.get("timeout_s", 60),
        )
    except ConnectorError:
        # LLM offline: de kerncijfers blijven waardevol, dus context wél teruggeven.
        out = {"duiding": None, "bron": afval_duiding.BRON, "disclaimer": afval_duiding.DISCLAIMER}
    out["context"] = ctx
    return out


_AFVAL_BRON_OMSCHRIJVING = {
    "cbs-": "Gemeentelijke afvalstoffen per provincie en jaar (CBS StatLine 83558NED).",
    "clo-": "Huishoudelijk afval per inwoner, lange tijdreeks (Compendium voor de Leefomgeving).",
    "afvalfonds-": "Recyclingpercentages per verpakkingsmateriaal (Afvalfonds Verpakkingen/Verpact).",
    "lma-rws-": "Nationale afvalcijfers per Euralcode en verwerking (LMA/RWS, openbaar).",
}


def _afval_bron_omschrijving(bron_id: str) -> str:
    for prefix, tekst in _AFVAL_BRON_OMSCHRIJVING.items():
        if bron_id.startswith(prefix):
            return tekst
    return ""


@app.get("/api/afval/bronnen")
def api_afval_bronnen():
    if not Path(_afvaldb_path()).exists():
        raise HTTPException(status_code=503, detail="Afval-database nog niet gevuld")
    con = afvaldb_store.open_readonly(_afvaldb_path())
    try:
        rows = afvaldb_store.bronnen(con)
    finally:
        if hasattr(con, "close"):
            con.close()
    for r in rows:
        r["omschrijving"] = _afval_bron_omschrijving(r["bron_id"])
    return rows


class AfvalChatRequest(BaseModel):
    vraag: str


@app.post("/api/afval/chat")
def api_afval_chat(req: AfvalChatRequest):
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    return afval_chat.beantwoord(
        req.vraag, _afvaldb_path(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"),
        timeout_s=llm.get("timeout_s", 60),
    )
