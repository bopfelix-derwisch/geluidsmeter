"""REV (externe veiligheid) via PDOK OGC API Features."""
from .base import BaseConnector


class RevConnector(BaseConnector):
    def __init__(self, base_url: str, collection: str, max_features: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.max_features = max_features

    def features(self, bbox: str) -> dict:
        url = f"{self.base_url}/collections/{self.collection}/items"
        params = {"bbox": bbox, "f": "json", "limit": self.max_features}
        data = self.get_json(url, params)
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            return {"type": "FeatureCollection", "features": []}
        return data
