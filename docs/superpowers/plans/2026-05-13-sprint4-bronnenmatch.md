# Sprint 4 — Bronnenmatch + Visualisatie — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Externe geluidsbrondata (NWB, BGT, geluidkaarten) downloaden via PDOK WFS, matchen met gemeten waarden, en tonen in notebook + FastAPI dashboard.

**Architecture:** Script `03_fetch_external.py` haalt WFS-data op voor een bbox rond de meetlocatie en slaat op als GeoJSON. Module `source_match.py` bevat matchlogica (dBFS→dB(A), bronidentificatie, normcheck). Notebook + dashboard lezen beide uit dezelfde cached bestanden.

**Tech Stack:** geopandas (WFS read), requests (HTTP), shapely (geometrie), pandas, matplotlib (notebook plots), Chart.js + Leaflet (dashboard, via CDN), FastAPI (bestaande service)

---

## File Map

| Actie | Pad | Verantwoordelijkheid |
|-------|-----|----------------------|
| Create | `scripts/03_fetch_external.py` | WFS download, bbox query, GeoJSON opslaan |
| Create | `src/geluidsmeter/source_match.py` | dBFS→dB(A), bronmatch, normcheck |
| Create | `tests/test_source_match.py` | pytest tests voor source_match |
| Create | `notebooks/bronnenmatch.ipynb` | Analyse notebook (3 secties) |
| Modify | `src/geluidsmeter/api.py` | Nieuw `/summary` endpoint |
| Create | `src/geluidsmeter/static/dashboard.html` | Dashboard frontend |
| Modify | `core/config.yaml` | calibration_offset_db + sources sectie |

---

## Task 1: Config uitbreiden

**Files:**
- Modify: `core/config.yaml`

- [ ] **Stap 1: Voeg kalibratie en sources toe aan config.yaml**

```yaml
# Toevoegen aan measurement sectie:
measurement:
  # ... bestaande keys ...
  calibration_offset_db: 0    # dBFS → dB(A) schatting; 0 = ongekalibreerd

# Nieuwe sectie onderaan:
sources:
  wfs_bbox_m: 500             # bbox straal rond meetlocatie in meters
  force_refresh: false        # true = WFS opnieuw ophalen ook als data bestaat
  nwb_wfs_url: "https://service.pdok.nl/rws/nwbwegen/wfs/v1_0"
  bgt_ogcapi_url: "https://api.pdok.nl/lv/bgt/ogc/v1"
  geluidkaarten_wfs_url: "https://service.pdok.nl/ienw/geluidsbelastingkaarten-wegen-lden/wfs/v1_0"
```

- [ ] **Stap 2: Verifieer dat config laadt zonder fout**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
python3 -c "from src.geluidsmeter.config import load_config; c=load_config(); print(c['sources'])"
```

Verwacht: `{'wfs_bbox_m': 500, 'force_refresh': False, ...}`

- [ ] **Stap 3: Commit**

```bash
git add core/config.yaml
git commit -m "feat(sprint4): config uitbreiden met kalibratie en WFS sources"
```

---

## Task 2: source_match.py — TDD

**Files:**
- Create: `src/geluidsmeter/source_match.py`
- Create: `tests/test_source_match.py`

- [ ] **Stap 1: Maak tests directory aan en schrijf de falende tests**

```bash
mkdir -p ~/Geluidsmeter/tests
touch ~/Geluidsmeter/tests/__init__.py
```

Schrijf `tests/test_source_match.py`:

```python
import pytest
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from src.geluidsmeter.source_match import (
    estimate_dba,
    check_norm,
    identify_sources,
    match_cvgg,
)


def test_estimate_dba_zero_offset():
    assert estimate_dba(-60.0, 0.0) == -60.0


def test_estimate_dba_with_offset():
    assert abs(estimate_dba(-60.0, 114.0) - 54.0) < 0.01


def test_check_norm_within():
    result = check_norm(lden_db=45.0, lnight_db=38.0)
    assert result["lden_status"] == "ok"
    assert result["lnight_status"] == "ok"
    assert result["lden_delta"] == pytest.approx(-3.0)


def test_check_norm_exceeded():
    result = check_norm(lden_db=55.0, lnight_db=50.0)
    assert result["lden_status"] == "overschreden"
    assert result["lnight_status"] == "overschreden"
    assert result["lden_delta"] == pytest.approx(7.0)


def test_identify_sources_empty():
    empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    result = identify_sources(empty_gdf, Point(5.0, 52.0))
    assert result["dominant_source"] == "onbekend"
    assert result["weg_pct"] == 0


def test_identify_sources_with_road():
    road = gpd.GeoDataFrame(
        {"wegbeheerdersoort": ["Rijksweg"], "geometry": [Point(5.0, 52.0).buffer(0.001)]},
        crs="EPSG:4326",
    )
    result = identify_sources(road, Point(5.0, 52.0))
    assert result["weg_count"] >= 1
    assert result["dominant_source"] == "wegverkeer"


def test_match_cvgg_no_overlap():
    gdf = gpd.GeoDataFrame(
        {"lden": [52.0], "lnight": [43.0],
         "geometry": [Point(10.0, 53.0).buffer(0.001)]},
        crs="EPSG:4326",
    )
    result = match_cvgg(Point(5.0, 52.0), gdf)
    assert result["lden"] is None
    assert result["lnight"] is None


def test_match_cvgg_with_overlap():
    gdf = gpd.GeoDataFrame(
        {"lden": [52.0], "lnight": [43.0],
         "geometry": [Point(5.0, 52.0).buffer(0.1)]},
        crs="EPSG:4326",
    )
    result = match_cvgg(Point(5.0, 52.0), gdf)
    assert result["lden"] == pytest.approx(52.0)
    assert result["lnight"] == pytest.approx(43.0)
```

- [ ] **Stap 2: Verifieer dat tests falen**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
pip install pytest -q
pytest tests/test_source_match.py -v 2>&1 | head -20
```

Verwacht: `ImportError: cannot import name 'estimate_dba' from 'src.geluidsmeter.source_match'`

- [ ] **Stap 3: Schrijf source_match.py**

```python
"""Matchlogica: meting vs. referentiedata, bronidentificatie, normtoetsing."""
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

NORM_LDEN_DB = 48.0   # Omgevingswet art. 5.67 — wonen
NORM_LNIGHT_DB = 43.0


def estimate_dba(rms_dbfs: float, offset_db: float) -> float:
    """Schat dB(A) uit dBFS meting via kalibratiefactor."""
    return rms_dbfs + offset_db


def check_norm(lden_db: float, lnight_db: float) -> dict:
    """Vergelijk geschatte Lden/Lnight met Omgevingswet norm."""
    return {
        "lden_db": round(lden_db, 1),
        "lden_norm": NORM_LDEN_DB,
        "lden_delta": round(lden_db - NORM_LDEN_DB, 1),
        "lden_status": "ok" if lden_db <= NORM_LDEN_DB else "overschreden",
        "lnight_db": round(lnight_db, 1),
        "lnight_norm": NORM_LNIGHT_DB,
        "lnight_delta": round(lnight_db - NORM_LNIGHT_DB, 1),
        "lnight_status": "ok" if lnight_db <= NORM_LNIGHT_DB else "overschreden",
    }


def identify_sources(nwb_gdf: gpd.GeoDataFrame, location: Point) -> dict:
    """Analyseer wegtypen in de bbox als bronindicatie."""
    if nwb_gdf.empty:
        return {"dominant_source": "onbekend", "weg_count": 0, "weg_pct": 0}

    weg_count = len(nwb_gdf)
    rijks = nwb_gdf[nwb_gdf.get("wegbeheerdersoort", pd.Series()).str.contains(
        "Rijks|snelweg|autosnelweg", case=False, na=False
    )] if "wegbeheerdersoort" in nwb_gdf.columns else nwb_gdf.iloc[0:0]

    dominant = "wegverkeer" if weg_count > 0 else "onbekend"
    return {
        "dominant_source": dominant,
        "weg_count": weg_count,
        "rijksweg_count": len(rijks),
        "weg_pct": 100,
    }


def match_cvgg(location: Point, cvgg_gdf: gpd.GeoDataFrame) -> dict:
    """Point-in-polygon: haal Lden/Lnight op voor de meetlocatie."""
    if cvgg_gdf.empty:
        return {"lden": None, "lnight": None, "source": "geen data"}

    hits = cvgg_gdf[cvgg_gdf.geometry.contains(location)]
    if hits.empty:
        return {"lden": None, "lnight": None, "source": "geen overlap"}

    row = hits.iloc[0]
    return {
        "lden": float(row["lden"]) if "lden" in row else None,
        "lnight": float(row["lnight"]) if "lnight" in row else None,
        "source": "cvgg",
    }
```

- [ ] **Stap 4: Fix import in test (pandas nodig voor identify_sources)**

Voeg toe bovenaan `tests/test_source_match.py`:
```python
import pandas as pd
```

- [ ] **Stap 5: Run tests — verwacht PASS**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
pytest tests/test_source_match.py -v
```

Verwacht: `8 passed`

- [ ] **Stap 6: Commit**

```bash
git add src/geluidsmeter/source_match.py tests/test_source_match.py tests/__init__.py
git commit -m "feat(sprint4): source_match.py met tests — dBFS→dB(A), normcheck, bronmatch"
```

---

## Task 3: WFS downloader — 03_fetch_external.py

**Files:**
- Create: `scripts/03_fetch_external.py`

- [ ] **Stap 1: Schrijf het script**

```python
#!/usr/bin/env python3
"""Download WFS-data van PDOK voor de meetlocatie-bbox. Eenmalig uitvoeren."""
import sys
import json
import math
import argparse
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from geluidsmeter.config import load_config, load_private_location


def bbox_from_location(lat: float, lon: float, radius_m: int) -> tuple:
    """Berekent (minx, miny, maxx, maxy) bbox in WGS84."""
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fetch_wfs(url: str, typename: str, bbox: tuple, out_path: Path) -> bool:
    """Download WFS GetFeature als GeoJSON. Retourneert True bij succes."""
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": typename,
        "outputFormat": "application/json",
        "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326",
        "count": "500",
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("features"):
            print(f"  [leeg] {typename} — geen features in bbox")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False))
        print(f"  [ok] {len(data.get('features', []))} features → {out_path}")
        return True
    except Exception as e:
        print(f"  [fout] {typename}: {e}")
        return False


def fetch_bgt_ogcapi(base_url: str, collection: str, bbox: tuple, out_path: Path) -> bool:
    """Download BGT-collectie via OGC API Features (GeoJSON)."""
    minx, miny, maxx, maxy = bbox
    url = f"{base_url}/collections/{collection}/items"
    params = {"bbox": f"{minx},{miny},{maxx},{maxy}", "limit": 500, "f": "json"}
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False))
        print(f"  [ok] {len(data.get('features', []))} features → {out_path}")
        return True
    except Exception as e:
        print(f"  [fout] BGT {collection}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download externe geluidsbrondata via PDOK WFS")
    parser.add_argument("--force", action="store_true", help="Overschrijf bestaande bestanden")
    args = parser.parse_args()

    config = load_config()
    loc = load_private_location(config)
    src = config["sources"]
    bbox = bbox_from_location(loc["lat"], loc["lon"], src["wfs_bbox_m"])
    ext_base = Path("/mnt/nvme/geluidsmeter/data/external")

    print(f"[03_fetch_external] bbox={tuple(round(x, 6) for x in bbox)}, radius={src['wfs_bbox_m']}m")

    # NWB Wegen — wegtype context
    nwb_out = ext_base / "atlas" / "nwb_wegvakken.geojson"
    if args.force or not nwb_out.exists():
        print("→ NWB Wegen (wegvakken)...")
        fetch_wfs(src["nwb_wfs_url"], "nwbwegen:wegvakken", bbox, nwb_out)
    else:
        print(f"→ NWB Wegen: al aanwezig ({nwb_out})")

    # BGT Wegdeel — infrastructuurtype
    bgt_out = ext_base / "bgt" / "bgt_wegdeel.geojson"
    if args.force or not bgt_out.exists():
        print("→ BGT Wegdeel...")
        fetch_bgt_ogcapi(src["bgt_ogcapi_url"], "wegdeel", bbox, bgt_out)
    else:
        print(f"→ BGT: al aanwezig ({bgt_out})")

    # Geluidkaarten IenW — Lden (optioneel, service kan ontbreken)
    cvgg_out = ext_base / "cvgg" / "geluidkaart_lden.geojson"
    if args.force or not cvgg_out.exists():
        print("→ Geluidkaarten IenW (Lden)...")
        ok = fetch_wfs(src["geluidkaarten_wfs_url"], "geluidsbelastingkaarten:geluidzone",
                       bbox, cvgg_out)
        if not ok:
            print("  ℹ Geluidkaarten niet beschikbaar — normcheck gebruikt alleen kalibratiemeting.")
    else:
        print(f"→ Geluidkaarten: al aanwezig ({cvgg_out})")

    print("[03_fetch_external] Klaar.")


if __name__ == "__main__":
    main()
```

- [ ] **Stap 2: Test de downloader (--force zodat alles gedownload wordt)**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
python3 scripts/03_fetch_external.py --force
```

Verwacht per bron: `[ok] N features → /mnt/nvme/...` of `[fout] ... — normcheck gebruikt alleen kalibratiemeting.`

- [ ] **Stap 3: Verifieer output**

```bash
ls -lh /mnt/nvme/geluidsmeter/data/external/atlas/
ls -lh /mnt/nvme/geluidsmeter/data/external/bgt/
ls -lh /mnt/nvme/geluidsmeter/data/external/cvgg/
```

- [ ] **Stap 4: Commit**

```bash
git add scripts/03_fetch_external.py
git commit -m "feat(sprint4): WFS downloader — NWB, BGT, geluidkaarten naar external/"
```

---

## Task 4: bronnenmatch.ipynb

**Files:**
- Create: `notebooks/bronnenmatch.ipynb`

- [ ] **Stap 1: Maak notebook aan**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
pip install jupyter ipykernel matplotlib -q
jupyter nbconvert --to notebook --execute /dev/null 2>/dev/null || true
```

- [ ] **Stap 2: Schrijf het notebook als Python-script en converteer**

Maak `notebooks/bronnenmatch_build.py`:

```python
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []

cells.append(nbf.v4.new_markdown_cell("# Bronnenmatch — Geluidsmeter\n\n"
    "Vergelijking gemeten geluid vs. referentiedata (NWB, BGT, CVGG).  \n"
    "**Let op:** dB(A)-waarden zijn *indicatief* — ongekalibreerd prototype."))

cells.append(nbf.v4.new_code_cell("""\
import sys, json
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from shapely.geometry import Point

sys.path.insert(0, str(Path("..") / "src"))
from geluidsmeter.config import load_config, load_private_location
from geluidsmeter.aggregate import load_features
from geluidsmeter.source_match import estimate_dba, check_norm, identify_sources, match_cvgg

def _round_location(lat, lon, precision_m):
    import math
    deg = precision_m / 111_000
    decimals = max(0, -int(math.floor(math.log10(deg))))
    return round(lat, decimals), round(lon, decimals)

config = load_config("../core/config.yaml")
loc = load_private_location(config)
offset = config["measurement"].get("calibration_offset_db", 0)
precision_m = config["location"]["public_location_precision_m"]
lat_pub, lon_pub = _round_location(loc["lat"], loc["lon"], precision_m)
location = Point(lon_pub, lat_pub)

print(f"Locatie (afgerond): {lat_pub:.4f}, {lon_pub:.4f}")
print(f"Kalibratie offset: {offset} dB (0 = ongekalibreerd)")
"""))

cells.append(nbf.v4.new_markdown_cell("## 1. Meting vs. model"))

cells.append(nbf.v4.new_code_cell("""\
raw_dir = Path(config["outputs"]["raw_features_dir"])
df = load_features(raw_dir)

if df.empty:
    print("Geen meetdata gevonden.")
else:
    df["dba_est"] = df["rms_dbfs"].apply(lambda x: estimate_dba(x, offset))
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df["ts"], df["dba_est"], label="Gemeten (geschatte dB(A))", color="#4ade80", lw=1.5)
    ax.axhline(48, color="#f87171", ls="--", label="Norm Lden dag 48 dB(A)")
    ax.axhline(43, color="#fb923c", ls="--", label="Norm Lnight nacht 43 dB(A)")
    ax.set_ylabel("Geschatte dB(A)")
    ax.set_xlabel("Tijd (UTC)")
    ax.set_title("Gemeten geluidsniveau vs. Omgevingswet normen")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("meting_vs_norm.png", dpi=120)
    plt.show()
    print(f"Totaal {len(df)} metingen")
"""))

cells.append(nbf.v4.new_markdown_cell("## 2. Bronidentificatie"))

cells.append(nbf.v4.new_code_cell("""\
nwb_path = Path("/mnt/nvme/geluidsmeter/data/external/atlas/nwb_wegvakken.geojson")
if nwb_path.exists():
    nwb_gdf = gpd.read_file(nwb_path)
    sources = identify_sources(nwb_gdf, location)
    print(f"Dominante bron: {sources['dominant_source']}")
    print(f"Wegvakken in bbox: {sources['weg_count']} (waarvan rijkswegen: {sources.get('rijksweg_count', 0)})")

    cats = {}
    if "wegbeheerdersoort" in nwb_gdf.columns:
        cats = nwb_gdf["wegbeheerdersoort"].value_counts().to_dict()

    if cats:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.barh(list(cats.keys()), list(cats.values()), color="#3b82f6")
        ax.set_xlabel("Aantal wegvakken")
        ax.set_title("Wegbeheer in bbox (bronidentificatie)")
        plt.tight_layout()
        plt.savefig("bronidentificatie.png", dpi=120)
        plt.show()
else:
    print("NWB data niet gevonden — voer eerst 03_fetch_external.py uit.")
"""))

cells.append(nbf.v4.new_markdown_cell("## 3. Normtoetsing"))

cells.append(nbf.v4.new_code_cell("""\
if not df.empty:
    df["dba_est"] = df["rms_dbfs"].apply(lambda x: estimate_dba(x, offset))
    dag_df = df[df["hour"].isin(range(7, 19))]
    nacht_df = df[~df["hour"].isin(range(7, 23))]

    lden_est = float(df["dba_est"].mean()) if not df.empty else None
    lnight_est = float(nacht_df["dba_est"].mean()) if not nacht_df.empty else None

    if lden_est is not None and lnight_est is not None:
        norm = check_norm(lden_est, lnight_est)
        print("=== Normtoetsing (prototype — ongekalibreerd) ===")
        for k, v in norm.items():
            print(f"  {k}: {v}")

        tabel = pd.DataFrame([
            {"Periode": "Etmaal (Lden)", "Gemeten dB(A)": norm["lden_db"],
             "Norm dB(A)": norm["lden_norm"], "Delta": norm["lden_delta"],
             "Status": norm["lden_status"]},
            {"Periode": "Nacht (Lnight)", "Gemeten dB(A)": norm["lnight_db"],
             "Norm dB(A)": norm["lnight_norm"], "Delta": norm["lnight_delta"],
             "Status": norm["lnight_status"]},
        ])
        display(tabel)
    else:
        print("Onvoldoende data voor normtoetsing (dag + nacht nodig).")
"""))

nb.cells = cells
nbf.write(nb, "bronnenmatch.ipynb")
print("Notebook geschreven: bronnenmatch.ipynb")
```

```bash
cd ~/Geluidsmeter/notebooks && source ../.venv/bin/activate
pip install nbformat -q
python3 bronnenmatch_build.py
rm bronnenmatch_build.py
```

- [ ] **Stap 3: Test notebook**

```bash
cd ~/Geluidsmeter/notebooks && source ../.venv/bin/activate
jupyter nbconvert --to notebook --execute bronnenmatch.ipynb --output bronnenmatch.ipynb 2>&1 | tail -5
```

Verwacht: `[NbConvertApp] Writing N bytes to bronnenmatch.ipynb`

- [ ] **Stap 4: Commit**

```bash
cd ~/Geluidsmeter
git add notebooks/bronnenmatch.ipynb
git commit -m "feat(sprint4): bronnenmatch notebook — meting vs. norm, bronidentificatie, normtoetsing"
```

---

## Task 5: Dashboard — /summary endpoint + HTML

**Files:**
- Modify: `src/geluidsmeter/api.py`
- Create: `src/geluidsmeter/static/dashboard.html`

- [ ] **Stap 1: Maak static dir aan**

```bash
mkdir -p ~/Geluidsmeter/src/geluidsmeter/static
```

- [ ] **Stap 2: Voeg /summary endpoint toe aan api.py**

Voeg toe aan `src/geluidsmeter/api.py` (na bestaande imports):

```python
import glob
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
```

Voeg toe na `app = FastAPI(...)`:

```python
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
```

Voeg toe na het `/metadata` endpoint:

```python
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

    return {
        "today": today,
        "rms_dba_latest": rms_dba,
        "calibration_offset_db": offset,
        "calibrated": offset != 0,
        "profile": profile,
        "history": history[-168:],  # max 7 dagen × 24 × 6 = 1008 punten, cap op 168
        "norm_lden": 48,
        "norm_lnight": 43,
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (_static_dir / "dashboard.html").read_text()
```

- [ ] **Stap 3: Schrijf dashboard.html**

Schrijf `src/geluidsmeter/static/dashboard.html`:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Geluidsmeter — Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
    header { padding: 16px 24px; background: #1e293b; border-bottom: 1px solid #334155; }
    header h1 { font-size: 1.1rem; color: #94a3b8; font-weight: 500; }
    .kpi-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; padding: 16px 24px; }
    .kpi { background: #1e293b; border-radius: 8px; padding: 16px; border-left: 3px solid #334155; }
    .kpi .label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
    .kpi .value { font-size: 1.8rem; font-weight: 700; margin: 4px 0; }
    .kpi .sub { font-size: 0.75rem; color: #64748b; }
    .ok { color: #4ade80; } .warn { color: #fb923c; } .err { color: #f87171; }
    .panels { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 0 24px 24px; }
    .panel { background: #1e293b; border-radius: 8px; overflow: hidden; }
    .panel-header { padding: 10px 16px; font-size: 0.8rem; color: #94a3b8; border-bottom: 1px solid #334155; }
    #map { height: 280px; }
    canvas { padding: 12px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem;
             background: #7c3aed; color: #ddd8fe; margin-left: 8px; }
  </style>
</head>
<body>
<header>
  <h1>Geluidsmeter <span class="badge" id="cal-badge">ongekalibreerd</span></h1>
</header>

<div class="kpi-row">
  <div class="kpi" style="border-left-color:#4ade80">
    <div class="label">Gemeten (laatste)</div>
    <div class="value ok" id="kpi-meting">—</div>
    <div class="sub">geschatte dB(A)</div>
  </div>
  <div class="kpi" style="border-left-color:#3b82f6">
    <div class="label">Norm Lden dag</div>
    <div class="value" style="color:#3b82f6">48 dB(A)</div>
    <div class="sub">Omgevingswet art. 5.67</div>
  </div>
  <div class="kpi" id="kpi-status-block" style="border-left-color:#64748b">
    <div class="label">Status norm</div>
    <div class="value" id="kpi-status">—</div>
    <div class="sub" id="kpi-delta">—</div>
  </div>
</div>

<div class="panels">
  <div class="panel">
    <div class="panel-header">Kaart — meetlocatie</div>
    <div id="map"></div>
  </div>
  <div class="panel">
    <div class="panel-header">Tijdreeks — geschatte dB(A), laatste metingen</div>
    <canvas id="chart" height="280"></canvas>
  </div>
</div>

<script>
async function init() {
  const data = await fetch("/summary").then(r => r.json());

  // KPI
  const meting = data.rms_dba_latest;
  document.getElementById("kpi-meting").textContent = meting !== null ? meting + " dB(A)" : "—";
  if (!data.calibrated) document.getElementById("cal-badge").textContent = "ongekalibreerd";
  else { document.getElementById("cal-badge").textContent = "gekalibreerd"; document.getElementById("cal-badge").style.background = "#166534"; }

  if (meting !== null) {
    const delta = Math.round((meting - data.norm_lden) * 10) / 10;
    const ok = meting <= data.norm_lden;
    document.getElementById("kpi-status").textContent = ok ? "✓ OK" : "⚠ Overschreden";
    document.getElementById("kpi-status").className = "value " + (ok ? "ok" : "err");
    document.getElementById("kpi-delta").textContent = (delta >= 0 ? "+" : "") + delta + " dB t.o.v. norm";
    document.getElementById("kpi-status-block").style.borderLeftColor = ok ? "#4ade80" : "#f87171";
  }

  // Kaart
  const map = L.map("map").setView([52.1, 5.1], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "© OpenStreetMap" }).addTo(map);

  // Tijdreeks
  const history = data.history || [];
  const labels = history.map(h => h.ts.substring(11, 16));
  const values = history.map(h => h.dba_est);
  const ctx = document.getElementById("chart").getContext("2d");
  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Geschatte dB(A)", data: values, borderColor: "#4ade80",
          backgroundColor: "rgba(74,222,128,0.1)", borderWidth: 1.5, pointRadius: 0, tension: 0.2 },
        { label: "Norm Lden 48 dB(A)", data: Array(labels.length).fill(48),
          borderColor: "#f87171", borderDash: [4, 4], borderWidth: 1, pointRadius: 0 },
      ]
    },
    options: { plugins: { legend: { labels: { color: "#94a3b8", boxWidth: 12 } } },
               scales: { x: { ticks: { color: "#64748b", maxTicksLimit: 12 }, grid: { color: "#1e293b" } },
                         y: { ticks: { color: "#64748b" }, grid: { color: "#334155" } } },
               animation: false }
  });
}
init();
</script>
</body>
</html>
```

- [ ] **Stap 4: Test de API**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
pip install python-multipart -q  # vereist door StaticFiles
uvicorn geluidsmeter.api:app --host 0.0.0.0 --port 8792 &
sleep 2
curl -s http://localhost:8792/summary | python3 -m json.tool | head -20
curl -s -o /dev/null -w "%{http_code}" http://localhost:8792/dashboard
```

Verwacht: JSON met `today`, `rms_dba_latest`, `history` — en HTTP 200 voor dashboard.

```bash
pkill -f "uvicorn geluidsmeter.api"
```

- [ ] **Stap 5: Commit**

```bash
git add src/geluidsmeter/api.py src/geluidsmeter/static/dashboard.html
git commit -m "feat(sprint4): dashboard — /summary endpoint + HTML met KPI, kaart, tijdreeks"
```

---

## Task 6: Eindcheck + geluidkaarten layer discovery

**Files:**
- Modify: `scripts/03_fetch_external.py` (indien geluidkaarten WFS endpoint afwijkt)

- [ ] **Stap 1: Check welke WFS layers beschikbaar zijn bij IenW**

```bash
cd ~/Geluidsmeter && source .venv/bin/activate
python3 -c "
import requests
url = 'https://service.pdok.nl/ienw/geluidsbelastingkaarten-wegen-lden/wfs/v1_0'
r = requests.get(url, params={'service':'WFS','request':'GetCapabilities'}, timeout=10)
print(r.status_code, r.text[:500])
"
```

- Als 200 + XML terug: noteer de correcte `typeName` uit de XML en pas `geluidkaarten_wfs_url` + typename in `03_fetch_external.py` aan.
- Als 404/fout: service bestaat (nog) niet onder dit pad. Zoek op [pdok.nl/datasets](https://www.pdok.nl/datasets) naar "geluidbelastingkaarten" en update de URL in `config.yaml`.

- [ ] **Stap 2: Voer 03_fetch_external.py opnieuw uit na eventuele URL-correctie**

```bash
python3 scripts/03_fetch_external.py --force
```

- [ ] **Stap 3: Final commit**

```bash
git add -A
git commit -m "feat(sprint4): sprint 4 volledig — bronnenmatch, notebook, dashboard"
```

---

## Zelf-review notities

- `_round_location` is geïmporteerd vanuit `aggregate.py` in het notebook — dat is een private functie (underscore). Als dit problemen geeft, verplaats naar `config.py` of exporteer expliciet vanuit `aggregate.py`.
- `StaticFiles` vereist `pip install python-multipart` als die nog niet aanwezig is — stap 4 doet dit.
- `identify_sources` importeert impliciet `pd` via de functie body — zorg dat `import pandas as pd` bovenaan `source_match.py` staat.
