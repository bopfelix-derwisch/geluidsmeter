"""REV (externe veiligheid) via PDOK OGC API Features.

De PDOK REV-service (INSPIRE, EPSG:4258) levert lat,lon en negeert bbox-crs.
Deze connector normaliseert naar schone CRS84 GeoJSON (lon,lat) voor de viewer.

De productiefaciliteiten zijn bij PDOK over meerdere collections per economische
sector verdeeld. De connector haalt alle geconfigureerde collections op en voegt
ze samen tot één FeatureCollection, met de sector als property `rev_sector`.
"""
from .base import BaseConnector, ConnectorError

SECTOR_TITLES = {
    "production_facility_b": "Winning van delfstoffen",
    "production_facility_c": "Productie",
    "production_facility_d": "Stroom, gas, stoom, airco",
    "production_facility_e": "Watervoorziening, riolering, afvalbeheer, sanering",
    "production_facility_f": "Bouw",
    "production_facility_h": "Transport en opslagdiensten",
}


def _swap_positions(coords):
    """Draai elke positie [lat, lon, ...] om naar [lon, lat, ...] (recursief)."""
    if coords and isinstance(coords[0], (int, float)):
        return [coords[1], coords[0]] + list(coords[2:])
    return [_swap_positions(c) for c in coords]


class RevConnector(BaseConnector):
    def __init__(self, base_url: str, collections, max_features: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.collections = list(collections)
        self.max_features = max_features

    def features(self, bbox: str) -> dict:
        parts = [p.strip() for p in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox moet 4 komma-gescheiden waarden zijn: minLon,minLat,maxLon,maxLat")
        # invoer minLon,minLat,maxLon,maxLat -> bron wil minLat,minLon,maxLat,maxLon
        api_bbox = ",".join([parts[1], parts[0], parts[3], parts[2]])
        merged = {"type": "FeatureCollection", "features": []}
        for coll in self.collections:
            url = f"{self.base_url}/collections/{coll}/items"
            params = {"bbox": api_bbox, "f": "json", "limit": self.max_features}
            try:
                data = self.get_json(url, params)
            except ConnectorError:
                # Eén collection onbereikbaar? Sla over en toon de rest.
                continue
            if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
                continue
            for feat in data.get("features", []):
                geom = feat.get("geometry")
                if geom and geom.get("coordinates") is not None:
                    geom["coordinates"] = _swap_positions(geom["coordinates"])
                fb = feat.get("bbox")
                if isinstance(fb, list) and len(fb) == 4:
                    feat["bbox"] = [fb[1], fb[0], fb[3], fb[2]]
                feat.setdefault("properties", {})["rev_sector"] = SECTOR_TITLES.get(coll, coll)
                merged["features"].append(feat)
        return merged
