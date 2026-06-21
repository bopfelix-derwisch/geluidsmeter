"""Scholen ophalen uit de KKG (BAG-onderwijs) + nabijheid (in meters) met shapely/pyproj."""
from pyproj import Transformer
from shapely import wkt as shapely_wkt
from shapely.geometry import box, Point
from shapely.ops import transform as shp_transform

from leefomgevinglab.ld import kkg

# Provincie-polygon uit de KKG (imx-geo:Provincie, geverifieerd 2026-06-21).
PROVINCIE_Q = """PREFIX imx: <http://modellen.geostandaarden.nl/def/imx-geo#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
SELECT ?wkt WHERE {{ ?p a imx:Provincie ; imx:naam "{prov}" ; geo:hasGeometry/geo:asWKT ?wkt }} LIMIT 1"""

# Scholen = onderwijs-gebouwen (BAG gebruiksdoel "onderwijsfunctie"), ruimtelijk gefilterd op een
# bbox-polygon via GeoSPARQL (geof:sfIntersects werkt op de KKG; geof:centroid NIET -> centroïde
# lokaal met shapely). Geverifieerd 2026-06-21. NB: filter is de bbox van het gebied.
SCHOLEN_Q = """PREFIX imx: <http://modellen.geostandaarden.nl/def/imx-geo#>
PREFIX ext: <https://modellen.kkg.kadaster.nl/def/imxgeo-ext#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?naam ?g WHERE {{
  ?s imx:gebruiksdoel "onderwijsfunctie" ; ext:maaiveldgeometrie/geo:asWKT ?g .
  FILTER(geof:sfIntersects(?g, "{bbox}"^^geo:wktLiteral))
  OPTIONAL {{ ?s rdfs:label ?naam }}
}} LIMIT 5000"""

_TO_RD = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def provincie_polygon(provincie: str, kkg_endpoint: str, sparql_fn=kkg.sparql) -> str | None:
    rows = sparql_fn(PROVINCIE_Q.format(prov=provincie), kkg_endpoint)
    return rows[0]["wkt"] if rows else None


def _bbox_wkt(gebied_wkt: str) -> str:
    minx, miny, maxx, maxy = shapely_wkt.loads(gebied_wkt).bounds
    return box(minx, miny, maxx, maxy).wkt


def scholen_in_gebied(gebied_wkt: str, kkg_endpoint: str, sparql_fn=kkg.sparql,
                      timeout_s: float = 120.0) -> list[tuple[str, float, float]]:
    """Scholen (label, lon, lat) in de bbox van het gebied; centroïde lokaal uit de geometrie."""
    rows = sparql_fn(SCHOLEN_Q.format(bbox=_bbox_wkt(gebied_wkt)), kkg_endpoint, timeout_s=timeout_s)
    out = []
    for r in rows:
        try:
            c = shapely_wkt.loads(r["g"]).centroid
            out.append((r.get("naam") or "school", float(c.x), float(c.y)))
        except Exception:
            continue
    return out


def _to_rd(geom):
    return shp_transform(lambda x, y, z=None: _TO_RD.transform(x, y), geom)


def nabij(object_wkts: list[str], scholen: list[tuple[str, float, float]], straal_m: float) -> list[str]:
    """De WKT's die binnen straal_m meter van minstens één school liggen (projectie naar RD)."""
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
