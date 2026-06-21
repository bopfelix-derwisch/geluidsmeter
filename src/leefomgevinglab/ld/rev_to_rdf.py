"""Zet REV-features (GeoJSON) om naar een lokale RDF-graph (GeoSPARQL WKT)."""
import hashlib

import rdflib
from rdflib import RDF, RDFS, Literal, URIRef
from shapely.geometry import shape
from shapely import wkt as shapely_wkt

LL = rdflib.Namespace("https://leefomgevinglab.local/rev/")
GEO = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
SEVESO_CLASS = LL.SevesoInrichting


def _feature_id(props: dict, geom_wkt: str) -> str:
    raw = str(props.get("gml_id") or props.get("identifier") or props.get("local_id") or geom_wkt)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_rev_graph(features: dict, gebied_wkt: str | None = None, seveso_filter=None) -> rdflib.Graph:
    g = rdflib.Graph()
    g.bind("ll", LL)
    g.bind("geo", GEO)
    gebied = shapely_wkt.loads(gebied_wkt) if gebied_wkt else None
    for feat in features.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if not geom:
            continue
        if seveso_filter is not None and not seveso_filter(props):
            continue
        shp = shape(geom)
        if gebied is not None and not shp.intersects(gebied):
            continue
        geom_wkt = shp.wkt
        s = URIRef(LL[_feature_id(props, geom_wkt)])
        g.add((s, RDF.type, SEVESO_CLASS))
        naam = props.get("name") or props.get("naam") or "REV-object"
        g.add((s, RDFS.label, Literal(naam)))
        g.add((s, GEO.asWKT, Literal(geom_wkt, datatype=GEO.wktLiteral)))
    return g
