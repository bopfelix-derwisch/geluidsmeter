#!/usr/bin/env python3
"""Meet 60 seconden geluid en sla features op als JSONL. Geen ruwe audio."""
import sys
import json
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from geluidsmeter.config import load_config
from geluidsmeter.feature_extract import extract


def main():
    parser = argparse.ArgumentParser(description="Geluidsmeter — eenmalige feature meting")
    parser.add_argument("--config", default=None)
    parser.add_argument("--duration", type=int, default=None, help="Opnameduur in seconden (overschrijft config)")
    parser.add_argument("--dry-run", action="store_true", help="Toon features maar sla niet op")
    args = parser.parse_args()

    config = load_config(args.config)
    meas = config["measurement"]
    duration = args.duration or meas["aggregate_seconds"]
    sample_rate = meas["sample_rate"]
    device = meas.get("device_name") or None
    out_dir = Path(config["outputs"]["raw_features_dir"])

    print(f"[01_record_features] device={device or 'default'}  {duration}s @ {sample_rate}Hz")
    print(f"[01_record_features] store_raw_audio={meas['store_raw_audio']}  output={out_dir}")

    try:
        import sounddevice as sd
    except ImportError:
        print("FOUT: sounddevice niet geïnstalleerd. Voer uit: pip install sounddevice")
        sys.exit(1)

    print("[01_record_features] Opname start...")
    samples = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=meas["channels"],
        dtype="int16",
        device=device,
    )
    sd.wait()
    print("[01_record_features] Opname klaar. Features extraheren...")

    flat = samples[:, 0] if meas["channels"] > 1 else samples.flatten()
    features = extract(flat, sample_rate, config)

    print(json.dumps(features, indent=2))

    if args.dry_run:
        print("[01_record_features] Dry-run — niet opgeslagen.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_file = out_dir / f"sound_features_{today}.jsonl"
    with open(out_file, "a") as f:
        f.write(json.dumps(features) + "\n")
    print(f"[01_record_features] Opgeslagen in {out_file}")


if __name__ == "__main__":
    main()
