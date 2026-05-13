"""Matchlogica: meting vs. referentiedata, bronidentificatie, normtoetsing."""
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

NORM_LDEN_DB = 48.0   # Omgevingswet art. 5.67 — wonen
NORM_LNIGHT_DB = 43.0


def estimate_dba(rms_dbfs: float, offset_db: float) -> float:
    """Schat dB(A) uit dBFS meting via kalibratiefactor."""
    return rms_dbfs + offset_db


def check_norm(lden_db: float, lnight_db: float) -> dict:
    """Vergelijk geschatte Lden/Lnight met Omgevingswet norm."""
    return {
        "lden_db": round(lden_db, 1),
        "lden_norm": NORM_LDEN_DB,
        "lden_delta": round(lden_db - NORM_LDEN_DB, 1),
        "lden_status": "ok" if lden_db <= NORM_LDEN_DB else "overschreden",
        "lnight_db": round(lnight_db, 1),
        "lnight_norm": NORM_LNIGHT_DB,
        "lnight_delta": round(lnight_db - NORM_LNIGHT_DB, 1),
        "lnight_status": "ok" if lnight_db <= NORM_LNIGHT_DB else "overschreden",
    }


def identify_sources(nwb_gdf: gpd.GeoDataFrame) -> dict:
    """Analyseer wegtypen in de bbox als bronindicatie."""
    if nwb_gdf.empty:
        return {"dominant_source": "onbekend", "weg_count": 0, "weg_detected": False}

    weg_count = len(nwb_gdf)
    rijks = nwb_gdf[nwb_gdf.get("wegbeheerdersoort", pd.Series()).str.contains(
        "Rijks|snelweg|autosnelweg", case=False, na=False
    )] if "wegbeheerdersoort" in nwb_gdf.columns else nwb_gdf.iloc[0:0]

    dominant = "wegverkeer" if weg_count > 0 else "onbekend"
    return {
        "dominant_source": dominant,
        "weg_count": weg_count,
        "rijksweg_count": len(rijks),
        "weg_detected": True,
    }


def match_cvgg(location: Point, cvgg_gdf: gpd.GeoDataFrame) -> dict:
    """Point-in-polygon: haal Lden/Lnight op voor de meetlocatie."""
    if cvgg_gdf.empty:
        return {"lden": None, "lnight": None, "source": "geen data"}

    hits = cvgg_gdf[cvgg_gdf.geometry.contains(location)]
    if hits.empty:
        return {"lden": None, "lnight": None, "source": "geen overlap"}

    row = hits.iloc[0]

    def _safe_float(val):
        try:
            f = float(val)
            return None if pd.isna(f) else f
        except (TypeError, ValueError):
            return None

    return {
        "lden": _safe_float(row.get("lden")) if "lden" in row.index else None,
        "lnight": _safe_float(row.get("lnight")) if "lnight" in row.index else None,
        "source": "cvgg",
    }
