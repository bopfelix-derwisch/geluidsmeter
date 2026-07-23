"""UC-08 service: leest het gebundelde afval-aggregaat en levert meta,
choropleth-GeoJSON en tijdreeksen. Geen netwerk — puur bestand-gebaseerd.
"""
import json
from pathlib import Path

import pandas as pd

from .transform import AFVALSTROMEN

BRON = "CBS StatLine 83558NED (Gemeentelijke afvalstoffen; hoeveelheden)"
LICENTIE = "CC-BY 4.0"
LABEL = "Open proxy voor het gesloten LMA/AMICE-aggregaat — illustratief"
INDICATOREN = [
    {"key": "volume", "label": "Hoeveelheid (kton)"},
    {"key": "circulariteit", "label": "Circulariteit (%)"},
]


def _paths(data_dir: str):
    d = Path(data_dir)
    return d / "aggregaat.parquet", d / "circulariteit.parquet", d / "provincies.geojson"


def _load_geo(data_dir: str) -> dict:
    _, _, geo = _paths(data_dir)
    return json.loads(geo.read_text())


def meta(data_dir: str) -> dict:
    vol_p, _, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    geo = _load_geo(data_dir)
    regios = [{"code": f["properties"]["identificatie"], "naam": f["properties"]["naam"]}
              for f in geo["features"]]
    jaren = sorted(int(j) for j in vol["jaar"].unique())
    return {
        "regios": regios,
        "afvalstromen": list(AFVALSTROMEN.keys()),
        "jaren": jaren,
        "indicatoren": INDICATOREN,
        "bron": BRON,
        "licentie": LICENTIE,
        "label": LABEL,
    }


def choropleth(data_dir: str, afvalstroom: str, jaar: int, indicator: str) -> dict:
    vol_p, circ_p, _ = _paths(data_dir)
    geo = _load_geo(data_dir)
    if indicator == "circulariteit":
        df = pd.read_parquet(circ_p)
        df = df[df["jaar"] == int(jaar)]
        lookup = dict(zip(df["regio_code"], df["circulariteit_pct"]))
        eenheid = "%"
    else:
        df = pd.read_parquet(vol_p)
        df = df[(df["jaar"] == int(jaar)) & (df["afvalstroom"] == afvalstroom)]
        lookup = dict(zip(df["regio_code"], df["hoeveelheid_kton"]))
        eenheid = "kton"
    for f in geo["features"]:
        code = f["properties"]["identificatie"]
        val = lookup.get(code)
        f["properties"].update({
            "value": None if val is None else float(val),
            "indicator": indicator,
            "afvalstroom": afvalstroom,
            "jaar": int(jaar),
            "eenheid": eenheid,
        })
    return geo


def trend(data_dir: str, regio: str, afvalstroom: str) -> dict:
    vol_p, circ_p, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    circ = pd.read_parquet(circ_p)
    geo = _load_geo(data_dir)
    naam = next((f["properties"]["naam"] for f in geo["features"]
                 if f["properties"]["identificatie"] == regio), regio)
    v = vol[(vol["regio_code"] == regio) & (vol["afvalstroom"] == afvalstroom)]
    circ_map = dict(zip(circ[circ["regio_code"] == regio]["jaar"],
                        circ[circ["regio_code"] == regio]["circulariteit_pct"]))
    reeks = []
    for _, r in v.sort_values("jaar").iterrows():
        jaar = int(r["jaar"])
        pct = circ_map.get(jaar)
        reeks.append({
            "jaar": jaar,
            "hoeveelheid_kton": float(r["hoeveelheid_kton"]),
            "circulariteit_pct": None if pct is None else float(pct),
        })
    return {"regio": regio, "naam": naam, "afvalstroom": afvalstroom, "reeks": reeks}
