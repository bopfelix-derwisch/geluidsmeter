"""REV externe veiligheid: explosieaandachtsgebieden op een punt via de open REV WFS.

rev-portaal.nl GeoServer WFS, GeoJSON. Het CQL INTERSECTS-filter werkt op de native CRS
RD/EPSG:28992 — het punt MOET in RD (lon/lat geeft stil 0 treffers, vals-negatief).
Geometrie-attribuut: 'geometrie'. De bron-property verschilt per laag (ev=bedrijfsnaam,
bl=naamexploitant, bn=bronhouder); maatgevende_stof zit op alle drie.
Live geverifieerd 2026-06-24; zie spec 2026-06-24-externe-veiligheid-aandachtsgebieden-chatbot-design.md.
"""
from .base import BaseConnector


class ExterneVeiligheidConnector(BaseConnector):
    def __init__(self, wfs_url: str, **kwargs):
        super().__init__(**kwargs)
        self.wfs_url = wfs_url

    def aandachtsgebieden_op_punt(self, laag: str, geo_rd: tuple[float, float],
                                  max_n: int = 5) -> list[dict]:
        x, y = geo_rd
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": laag, "outputFormat": "application/json",
            "srsName": "EPSG:4326", "count": max_n,
            "cql_filter": f"INTERSECTS(geometrie, POINT({x} {y}))",
        }
        data = self.get_json(self.wfs_url, params=params)
        out = []
        for f in (data.get("features") or [])[:max_n]:
            p = f.get("properties") or {}
            stof = p.get("maatgevende_stof")
            if isinstance(stof, dict):   # live: {"categorieNaam": ..., "chemischeNaam": "propaan"}
                stof = stof.get("chemischeNaam") or stof.get("categorieNaam")
            out.append({
                "bron": p.get("bedrijfsnaam") or p.get("naamexploitant") or p.get("bronhouder"),
                "maatgevende_stof": stof,
            })
        return out
