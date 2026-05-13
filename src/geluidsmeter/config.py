import os
import yaml
from pathlib import Path

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "core" / "config.yaml"

def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path or os.environ.get("GELUIDSMETER_CONFIG_PATH", _DEFAULT_CONFIG))
    with open(cfg_path) as f:
        return yaml.safe_load(f)

def load_private_location(config: dict) -> dict:
    loc_path = Path(config["location"]["private_location_file"])
    if not loc_path.exists():
        raise FileNotFoundError(f"Privélocatie niet gevonden: {loc_path}")
    with open(loc_path) as f:
        return yaml.safe_load(f)["location"]
