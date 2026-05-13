"""Exporteer meetlocatie naar GeoJSON en observaties naar GeoParquet."""
import json
import math
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone


def round_to_grid(lat: float, lon: float, precision_m: float) -> tuple[float, float]:
    """Rond coördinaten af op een grid van precision_m meter (privacy)."""
    deg_lat = precision_m / 111_320
    deg_lon = precision_m / (111_320 * math.cos(math.radians(lat)))
    return (round(lat / deg_lat) * deg_lat, round(lon / deg_lon) * deg_lon)


def export_location_geojson(config: dict, private_location: dict, out_dir: Path) -> Path:
    lat_pub, lon_pub = round_to_grid(
        private_location["lat"],
        private_location["lon"],
        config["location"]["public_location_precision_m"],
    )
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon_pub, lat_pub]},
        "properties": {
            "location_id": "home_public_rounded",
            "name_public": "Meetlocatie Bob (afgerond)",
            "crs": config["location"]["crs"],
            "location_precision_m": config["location"]["public_location_precision_m"],
            "sensor_id_public": "geluidsmeter_orin3_001",
            "quality_label": config["project"]["quality_label"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    geojson = {"type": "FeatureCollection", "features": [feature]}
    out_path = out_dir / "measurement_location.geojson"
    out_path.write_text(json.dumps(geojson, indent=2))
    print(f"[geo_export] Locatie geschreven: {out_path}")
    return out_path


def export_observations_parquet(df: pd.DataFrame, out_dir: Path, location_id: str = "home_public_rounded") -> Path:
    df = df.copy()
    df["location_id"] = location_id
    df["observation_id"] = [f"{location_id}_{ts}" for ts in df["ts"].astype(str)]
    out_path = out_dir / "sound_observations.parquet"
    df.to_parquet(out_path, index=False)
    print(f"[geo_export] {len(df)} observaties geschreven: {out_path}")
    return out_path
