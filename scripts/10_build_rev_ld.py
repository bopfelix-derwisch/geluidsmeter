#!/usr/bin/env python3
"""Bouw de lokale REV-LD-graph: REV-productiefaciliteiten in Zuid-Holland -> RDF op NVMe.

NB: de open REV-laag heeft geen Seveso-vlag; dit is de productiefaciliteiten-laag
(klasse ll:REVProductiefaciliteit), niet specifiek Seveso. Zie design-doc.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from leefomgevinglab.connectors.rev import RevConnector
from leefomgevinglab.ld import kkg
from leefomgevinglab.ld.rev_to_rdf import build_rev_graph
from leefomgevinglab.ld.store import save_graph

# Provincie in de KKG: type imx-geo:Provincie, naam via imx-geo:naam, geometrie via
# geo:hasGeometry/geo:asWKT (geverifieerd 2026-06-21 tegen het KKG-endpoint).
PROV_WKT_Q = """PREFIX imx: <http://modellen.geostandaarden.nl/def/imx-geo#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
SELECT ?wkt WHERE {{
  ?p a imx:Provincie ; imx:naam "{prov}" ; geo:hasGeometry/geo:asWKT ?wkt .
}} LIMIT 1"""


def main():
    root = Path(__file__).parent.parent
    with open(root / "core" / "config.yaml") as _f:
        cfg = yaml.safe_load(_f)["leefomgevinglab"]
    ld = cfg["ld"]
    # Provincie-polygon uit KKG (verify de exacte URI/structuur indien leeg)
    rows = kkg.sparql(PROV_WKT_Q.format(prov=ld["provincie"]), ld["kkg_endpoint"])
    gebied_wkt = rows[0]["wkt"] if rows else None
    # REV-features (ruime bbox rond Zuid-Holland), daarna geo-filter in build_rev_graph
    rev = cfg["rev"]
    conn = RevConnector(base_url=rev["ogc_base_url"], collections=rev["collections"],
                        max_features=rev["max_features"], cache_dir=cfg["cache_dir"])
    fc = {"type": "FeatureCollection", "features": []}
    for bbox in ["3.9,51.6,4.9,52.2"]:   # Zuid-Holland (lon,lat)
        fc["features"].extend(conn.features(bbox).get("features", []))
    fprop, fvals = ld.get("filter_property"), ld.get("filter_values") or []
    filt = (lambda p: str(p.get(fprop)) in [str(v) for v in fvals]) if fprop else None
    g = build_rev_graph(fc, gebied_wkt=gebied_wkt, feature_filter=filt)
    save_graph(g, ld["store_dir"])
    print(f"REV-LD: {len(list(g.subjects(None, None)))} triples-subj, opgeslagen in {ld['store_dir']}; gebied={'ja' if gebied_wkt else 'geen'}")


if __name__ == "__main__":
    main()
