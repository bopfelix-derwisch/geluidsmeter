# scripts/11_fetch_afval_aggregaat.py
"""Ingest UC-08: haalt CBS 83558NED + PDOK-provinciegeometrie op en schrijft het
gebundelde afval-aggregaat (Parquet + GeoJSON) naar de data-dir.

Eenmalig online; daarna draait het dashboard offline op deze bestanden.
Bron: CBS 83558NED (CC-BY 4.0) — open proxy voor het gesloten LMA/AMICE-aggregaat.
"""
import sys
from pathlib import Path

import httpx
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leefomgevinglab.connectors.cbs_afval import CbsAfvalConnector
from leefomgevinglab.usecases.afval import transform


def bouw_aggregaat(rows: list[dict], provincie_features: list[dict]):
    vol = pd.DataFrame(transform.tidy_volumes(rows),
                       columns=["regio_code", "jaar", "afvalstroom", "hoeveelheid_kton"])
    circ = pd.DataFrame(transform.circulariteit_rows(rows),
                        columns=["regio_code", "jaar", "nuttige_toepassing_kton",
                                 "verwijderen_kton", "circulariteit_pct"])
    aanwezige = set(vol["regio_code"]) | set(circ["regio_code"])
    features = []
    for f in provincie_features:
        ident = f["properties"].get("identificatie")
        if ident not in aanwezige:
            continue
        features.append({
            "type": "Feature",
            "geometry": f["geometry"],
            "properties": {"identificatie": ident, "naam": f["properties"].get("naam")},
        })
    geo = {"type": "FeatureCollection", "features": features}
    return vol, circ, geo


def _fetch_provincies(pdok_base: str) -> list[dict]:
    url = f"{pdok_base.rstrip('/')}/collections/provinciegebied/items"
    resp = httpx.get(url, params={"f": "json", "limit": 20}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def main():
    cfg = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "core" / "config.yaml"))
    af = cfg["leefomgevinglab"]["afval"]
    cache_dir = cfg["leefomgevinglab"].get("cache_dir", "/tmp/llab_cache")
    data_dir = Path(af["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)

    conn = CbsAfvalConnector(base_url=af["odata_base_url"], table_id=af["table_id"],
                             cache_dir=cache_dir, timeout=30.0)
    print("CBS 83558NED ophalen...")
    rows = conn.typed_dataset()
    print(f"  {len(rows)} rijen")
    print("PDOK-provinciegeometrie ophalen...")
    provincies = _fetch_provincies(af["pdok_provincie_url"])

    vol, circ, geo = bouw_aggregaat(rows, provincies)
    vol.to_parquet(data_dir / "aggregaat.parquet", index=False)
    circ.to_parquet(data_dir / "circulariteit.parquet", index=False)
    (data_dir / "provincies.geojson").write_text(
        __import__("json").dumps(geo), encoding="utf-8")
    print(f"Geschreven: {len(vol)} volume-rijen, {len(circ)} circulariteit-rijen, "
          f"{len(geo['features'])} provincies -> {data_dir}")


if __name__ == "__main__":
    main()
