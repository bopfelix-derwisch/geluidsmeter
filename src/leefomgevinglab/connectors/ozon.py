"""DSO Ozon (Omgevingsdocument Presenteren v8): wat geldt hier op een punt.

Pre-productie, x-api-key, HAL. Geometrie in RD via Content-Crs (OGC-URI-vorm).
Live geverifieerd 2026-06-23; zie spec 2026-06-23-omgevingsplan-ozon-chatbot-design.md.
"""
from .base import BaseConnector, ConnectorError

_CRS_RD = "http://www.opengis.net/def/crs/EPSG/0/28992"


def _geo_body(geo_rd: tuple[float, float]) -> dict:
    return {"geometrie": {"type": "Point", "coordinates": [geo_rd[0], geo_rd[1]]}}


class OzonConnector(BaseConnector):
    def __init__(self, base_url: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def _headers(self) -> dict:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        return {self.api_key_header: self.api_key,
                "Accept": "application/hal+json",
                "Content-Crs": _CRS_RD}

    def regelingen_op_punt(self, geo_rd: tuple[float, float]) -> list[dict]:
        headers = self._headers()
        url = f"{self.base_url}/regelingen/_zoek"
        data = self.post_json(url, json_body=_geo_body(geo_rd), headers=headers)
        out = []
        for r in (data.get("_embedded") or {}).get("regelingen") or []:
            bg = r.get("aangeleverdDoorEen") or {}
            out.append({
                "titel": r.get("opschrift") or r.get("officieleTitel"),
                "type": (r.get("type") or {}).get("waarde"),
                "bevoegd_gezag": bg.get("naam"),
                "uri": (r.get("identificatie") or "").replace("/", "_"),
            })
        return out

    def regelteksten_op_punt(self, regeling_uri: str, geo_rd: tuple[float, float],
                             max_m: int = 5) -> list[str]:
        headers = self._headers()
        url = f"{self.base_url}/regelingen/{regeling_uri}/regeltekstannotaties/_zoek"
        data = self.post_json(url, json_body=_geo_body(geo_rd), headers=headers)
        emb = data.get("_embedded") or {}
        items = next(iter(emb.values()), []) if emb else []
        out = []
        for it in items[:max_m]:
            titel = it.get("opschrift") or it.get("titel") or (it.get("regeltekst") or {}).get("opschrift")
            if titel:
                out.append(titel)
        return out
