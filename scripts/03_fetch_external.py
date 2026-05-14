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


def bbox_wgs84_to_rd(bbox_wgs84: tuple) -> tuple:
    """Converteert WGS84 bbox naar EPSG:28992 (RD New)."""
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)
    minx, miny, maxx, maxy = bbox_wgs84
    x0, y0 = t.transform(minx, miny)
    x1, y1 = t.transform(maxx, maxy)
    return (x0, y0, x1, y1)


def fetch_wfs(url: str, typename: str, bbox: tuple, out_path: Path, srs: str = "EPSG:28992") -> bool:
    """Download WFS GetFeature als GeoJSON. Retourneert True bij succes."""
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": typename,
        "outputFormat": "application/json",
        "bbox": f"{minx},{miny},{maxx},{maxy},{srs}",
        "count": "500",
    }
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("features"):
            print(f"  [leeg] {typename} — geen features in bbox; bestand NIET opgeslagen")
            return False
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
        if not data.get("features"):
            print(f"  [leeg] BGT {collection} — geen features in bbox; bestand NIET opgeslagen")
            return False
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
    bbox_wgs84 = bbox_from_location(loc["lat"], loc["lon"], src["wfs_bbox_m"])
    bbox_rd = bbox_wgs84_to_rd(bbox_wgs84)
    ext_base = Path(config["outputs"]["external_dir"])
    force = args.force or src.get("force_refresh", False)

    print(f"[03_fetch_external] bbox WGS84={tuple(round(x, 6) for x in bbox_wgs84)}, radius={src['wfs_bbox_m']}m")
    print(f"[03_fetch_external] bbox RD={tuple(round(x, 1) for x in bbox_rd)}")

    # NWB Wegen — wegtype context
    nwb_out = ext_base / "atlas" / "nwb_wegvakken.geojson"
    if force or not nwb_out.exists():
        print("→ NWB Wegen (wegvakken)...")
        fetch_wfs(src["nwb_wfs_url"], "nwbwegen:wegvakken", bbox_rd, nwb_out)
    else:
        print(f"→ NWB Wegen: al aanwezig ({nwb_out})")

    # BGT Wegdeel — infrastructuurtype
    bgt_out = ext_base / "bgt" / "bgt_wegdeel.geojson"
    if force or not bgt_out.exists():
        print("→ BGT Wegdeel...")
        fetch_bgt_ogcapi(src["bgt_ogcapi_url"], "wegdeel", bbox_wgs84, bgt_out)
    else:
        print(f"→ BGT: al aanwezig ({bgt_out})")

    # Geluidkaarten IenW — Lden (optioneel, service kan ontbreken)
    cvgg_out = ext_base / "cvgg" / "geluidkaart_lden.geojson"
    if force or not cvgg_out.exists():
        print("→ Geluidkaarten IenW (Lden)...")
        ok = fetch_wfs(src["geluidkaarten_wfs_url"], "geluidsbelastingkaarten:geluidzone",
                       bbox_rd, cvgg_out)
        if not ok:
            print("  ℹ Geluidkaarten niet beschikbaar — normcheck gebruikt alleen kalibratiemeting.")
    else:
        print(f"→ Geluidkaarten: al aanwezig ({cvgg_out})")

    # RIVM Digibeter geluid buurt — Lden modelschatting per buurt (WGS84/CRS:84)
    rivm_out = ext_base / "rivm" / "geluid_buurt.geojson"
    if force or not rivm_out.exists():
        print("→ RIVM geluid buurt (Lden modelschatting)...")
        fetch_wfs("https://data.rivm.nl/geo/wfs", "digibeter:rivm_20220201_geluid_buurt",
                  bbox_wgs84, rivm_out, srs="CRS:84")
    else:
        print(f"→ RIVM geluid buurt: al aanwezig ({rivm_out})")

    print("[03_fetch_external] Klaar.")


if __name__ == "__main__":
    main()
