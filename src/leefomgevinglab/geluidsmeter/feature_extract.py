"""Feature extractie uit audio frames — geen ruwe audio bewaard."""
import numpy as np
from datetime import datetime, timezone


def rms_to_dbfs(samples: np.ndarray) -> float:
    rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
    if rms < 1e-10:
        return -120.0
    return float(20 * np.log10(rms / 32768.0))


def lmax_dbfs(samples: np.ndarray) -> float:
    peak = np.max(np.abs(samples.astype(np.float64)))
    if peak < 1:
        return -120.0
    return float(20 * np.log10(peak / 32768.0))


def frequency_bands(samples: np.ndarray, sample_rate: int, bands_hz: dict) -> dict:
    n = len(samples)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    fft_mag = np.abs(np.fft.rfft(samples.astype(np.float64))) / n  # amplitude-spectrum, zelfde schaal als tijddomein
    result = {}
    for name, (low, high) in bands_hz.items():
        mask = (freqs >= low) & (freqs < high)
        band_energy = np.sqrt(np.mean(fft_mag[mask] ** 2)) if mask.any() else 0.0
        result[f"band_{name}_dbfs"] = float(20 * np.log10(band_energy / 32768.0)) if band_energy > 1e-10 else -120.0
    return result


def detect_event(rms_db: float, lmax_db: float, bands: dict, config: dict) -> str:
    peak_thresh = config["features"]["peak_threshold_db_relative"]
    lf_thresh = config["features"]["low_freq_threshold_relative"]
    delta = lmax_db - rms_db
    lf = bands.get("band_low_dbfs", -120.0)
    mid = bands.get("band_mid_dbfs", -120.0)
    if delta >= peak_thresh:
        return "peak"
    if (lf - mid) >= lf_thresh:
        return "continuous_low_freq"
    if rms_db < -60:
        return "quiet"
    return "unknown"


def extract(samples: np.ndarray, sample_rate: int, config: dict) -> dict:
    bands_hz = {k: v for k, v in config["features"]["bands_hz"].items()}
    rms_db = rms_to_dbfs(samples)
    lmax_db = lmax_dbfs(samples)
    bands = frequency_bands(samples, sample_rate, bands_hz)
    event = detect_event(rms_db, lmax_db, {"band_low_dbfs": bands.get("band_low_dbfs", -120.0),
                                            "band_mid_dbfs": bands.get("band_mid_dbfs", -120.0)}, config)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rms_dbfs": round(rms_db, 2),
        "lmax_dbfs": round(lmax_db, 2),
        **{k: round(v, 2) for k, v in bands.items()},
        "event_type": event,
        "quality_label": config["project"]["quality_label"],
        "raw_audio_stored": False,
    }
