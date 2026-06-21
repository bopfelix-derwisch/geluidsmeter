"""Scholen ophalen uit de KKG + nabijheid (in meters) met shapely/pyproj."""
from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.ops import transform as shp_transform

from leefomgevinglab.ld import kkg

# Scholen-punten in een provincie (BAG-onderwijs). LET OP: tegen het live KKG-endpoint
# fijnslijpen (gebruiksdoel onderwijsfunctie + provincie-filter + geometrie). Verify-stap.
SCHOLEN_Q = """PREFIX imx: <http://modellen.geostandaarden.nl/def/imx-geo#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
SELECT ?label ?lon ?lat WHERE {{
  ?s imx:naam ?label ; imx:gebruiksdoel "onderwijsfunctie" ; geo:hasGeometry/geo:asWKT ?wkt .
}} LIMIT 2000"""

_TO_RD = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def scholen_in_provincie(provincie: str, kkg_endpoint: str, sparql_fn=kkg.sparql) -> list[tuple[str, float, float]]:
    rows = sparql_fn(SCHOLEN_Q.format(prov=provincie), kkg_endpoint)
    out = []
    for r in rows:
        try:
            out.append((r.get("label") or "school", float(r["lon"]), float(r["lat"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _to_rd(geom):
    return shp_transform(lambda x, y, z=None: _TO_RD.transform(x, y), geom)


def nabij(object_wkts: list[str], scholen: list[tuple[str, float, float]], straal_m: float) -> list[str]:
    from shapely.geometry import Point
    school_rd = [_to_rd(Point(lon, lat)) for _, lon, lat in scholen]
    treffers = []
    for w in object_wkts:
        try:
            g_rd = _to_rd(shapely_wkt.loads(w))
        except Exception:
            continue
        if any(g_rd.distance(s) <= straal_m for s in school_rd):
            treffers.append(w)
    return treffers
