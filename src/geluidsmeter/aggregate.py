"""Aggregatie van JSONL features naar dag/avond/nacht profiel."""
import json
import math
import pandas as pd
from pathlib import Path
from datetime import datetime


DAY_HOURS   = range(7, 19)
EVENING_HOURS = range(19, 23)
# nacht: 23-7


def load_features(raw_dir: Path, date: str | None = None) -> pd.DataFrame:
    pattern = f"sound_features_{date}.jsonl" if date else "sound_features_*.jsonl"
    files = sorted(raw_dir.glob(pattern))
    rows = []
    for fp in files:
        with open(fp) as f:
            for line in f:
                rows.append(json.loads(line))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["hour"] = df["ts"].dt.hour
    return df


def daily_profile(df: pd.DataFrame, date: str, location_id: str, quality_label: str) -> dict:
    def mean_db(subset):
        if subset.empty:
            return None
        return round(float(subset["rms_dbfs"].mean()), 2)

    day_df = df[df["hour"].isin(DAY_HOURS)]
    eve_df = df[df["hour"].isin(EVENING_HOURS)]
    ngt_df = df[~df["hour"].isin(list(DAY_HOURS) + list(EVENING_HOURS))]

    return {
        "profile_id": f"{location_id}_{date}",
        "location_id": location_id,
        "date": date,
        "day_laeq_indicative": mean_db(day_df),
        "evening_laeq_indicative": mean_db(eve_df),
        "night_laeq_indicative": mean_db(ngt_df),
        "lmax_day": round(float(day_df["lmax_dbfs"].max()), 2) if not day_df.empty else None,
        "lmax_evening": round(float(eve_df["lmax_dbfs"].max()), 2) if not eve_df.empty else None,
        "lmax_night": round(float(ngt_df["lmax_dbfs"].max()), 2) if not ngt_df.empty else None,
        "number_of_peaks": int((df["event_type"] == "peak").sum()),
        "number_of_low_freq_events": int((df["event_type"] == "continuous_low_freq").sum()),
        "quality_label": quality_label,
    }


def _round_location(lat: float, lon: float, precision_m: int) -> tuple[float, float]:
    """Rond coördinaten af op ~precision_m nauwkeurigheid."""
    deg = precision_m / 111_000
    decimals = max(0, -int(math.floor(math.log10(deg))))
    return round(lat, decimals), round(lon, decimals)


def write_geoparquet(df: pd.DataFrame, out_path: Path, config: dict) -> None:
    import geopandas as gpd
    from shapely.geometry import Point
    from .config import load_private_location

    loc = load_private_location(config)
    precision_m = config["location"]["public_location_precision_m"]
    lat, lon = _round_location(loc["lat"], loc["lon"], precision_m)

    gdf = gpd.GeoDataFrame(df.copy(), geometry=[Point(lon, lat)] * len(df), crs="EPSG:4326")
    gdf.to_parquet(out_path)
