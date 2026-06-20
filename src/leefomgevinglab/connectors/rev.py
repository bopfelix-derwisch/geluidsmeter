"""REV (externe veiligheid) via PDOK OGC API Features.

De PDOK REV-service (INSPIRE, EPSG:4258) levert lat,lon en negeert bbox-crs.
Deze connector normaliseert naar schone CRS84 GeoJSON (lon,lat) voor de viewer.
"""
from .base import BaseConnector


def _swap_positions(coords):
    """Draai elke positie [lat, lon, ...] om naar [lon, lat, ...] (recursief)."""
    if coords and isinstance(coords[0], (int, float)):
        return [coords[1], coords[0]] + list(coords[2:])
    return [_swap_positions(c) for c in coords]


class RevConnector(BaseConnector):
    def __init__(self, base_url: str, collection: str, max_features: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.max_features = max_features

    def features(self, bbox: str) -> dict:
        parts = [p.strip() for p in bbox.split(",")]
        # invoer minLon,minLat,maxLon,maxLat -> bron wil minLat,minLon,maxLat,maxLon
        api_bbox = ",".join([parts[1], parts[0], parts[3], parts[2]])
        url = f"{self.base_url}/collections/{self.collection}/items"
        params = {"bbox": api_bbox, "f": "json", "limit": self.max_features}
        data = self.get_json(url, params)
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            return {"type": "FeatureCollection", "features": []}
        for feat in data.get("features", []):
            geom = feat.get("geometry")
            if geom and geom.get("coordinates") is not None:
                geom["coordinates"] = _swap_positions(geom["coordinates"])
        return data
