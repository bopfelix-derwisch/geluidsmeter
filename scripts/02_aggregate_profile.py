#!/usr/bin/env python3
"""Aggregeer JSONL features naar dagprofiel."""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from geluidsmeter.config import load_config
from geluidsmeter.aggregate import load_features, daily_profile, write_geoparquet


def main():
    config = load_config()
    raw_dir = Path(config["outputs"]["raw_features_dir"])
    out_dir = Path(config["outputs"]["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    df = load_features(raw_dir, today)
    if df.empty:
        print(f"Geen features gevonden voor {today}")
        return

    profile = daily_profile(df, today, "home_public_rounded", config["project"]["quality_label"])
    print(json.dumps(profile, indent=2))

    out_file = out_dir / f"daily_profile_{today}.json"
    out_file.write_text(json.dumps(profile, indent=2))
    print(f"Profiel geschreven: {out_file}")

    parquet_file = out_dir / f"measurements_{today}.parquet"
    write_geoparquet(df, parquet_file, config)
    print(f"GeoParquet geschreven: {parquet_file}")


if __name__ == "__main__":
    main()
