"""Audio capture via sounddevice — geen ruwe audio opgeslagen."""
import json
import time
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .feature_extract import extract


def run_capture_loop(config_path: str | None = None):
    config = load_config(config_path)
    meas = config["measurement"]
    out_dir = Path(config["outputs"]["raw_features_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    import sounddevice as sd  # type: ignore

    sample_rate = meas["sample_rate"]
    channels = meas["channels"]
    device = meas.get("device_name") or None
    aggregate_s = meas["aggregate_seconds"]

    print(f"[geluidsmeter] Capture start — device: {device or 'default'}, {sample_rate}Hz, {aggregate_s}s frames")
    print(f"[geluidsmeter] Output: {out_dir}")

    while True:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        out_file = out_dir / f"sound_features_{today}.jsonl"

        samples = sd.rec(
            int(aggregate_s * sample_rate),
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            device=device,
        )
        sd.wait()
        flat = samples[:, 0] if channels > 1 else samples.flatten()
        features = extract(flat, sample_rate, config)

        with open(out_file, "a") as f:
            f.write(json.dumps(features) + "\n")

        print(f"  {features['ts']}  rms={features['rms_dbfs']}  lmax={features['lmax_dbfs']}  event={features['event_type']}")
