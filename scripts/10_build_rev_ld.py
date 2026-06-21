#!/usr/bin/env python3
"""Bouw de lokale REV-LD-graph: REV-Seveso in Zuid-Holland -> RDF op NVMe."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from leefomgevinglab.connectors.rev import RevConnector
from leefomgevinglab.ld import kkg
from leefomgevinglab.ld.rev_to_rdf import build_rev_graph
from leefomgevinglab.ld.store import save_graph

PROV_WKT_Q = """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
SELECT ?wkt WHERE {{
  ?p rdfs:label "{prov}" ; geo:hasGeometry/geo:asWKT ?wkt .
}} LIMIT 1"""


def main():
    root = Path(__file__).parent.parent
    cfg = yaml.safe_load(open(root / "core" / "config.yaml"))["leefomgevinglab"]
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
    sev_prop, sev_vals = ld.get("seveso_property"), ld.get("seveso_values") or []
    filt = (lambda p: str(p.get(sev_prop)) in [str(v) for v in sev_vals]) if sev_prop else None
    g = build_rev_graph(fc, gebied_wkt=gebied_wkt, seveso_filter=filt)
    save_graph(g, ld["store_dir"])
    print(f"REV-LD: {len(list(g.subjects(None, None)))} triples-subj, opgeslagen in {ld['store_dir']}; gebied={'ja' if gebied_wkt else 'geen'}")


if __name__ == "__main__":
    main()
