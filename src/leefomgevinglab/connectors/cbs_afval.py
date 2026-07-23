"""CBS StatLine OData-connector voor tabel 83558NED (gemeentelijke afvalstoffen).

Open bron (CC-BY 4.0). Dient als open proxy voor het gesloten LMA/AMICE-aggregaat.
Dunne laag: haalt de TypedDataSet op (met OData-paginatie) en erft caching +
nette degradatie van BaseConnector. Omzetting naar tidy gebeurt in
usecases/afval/transform.py.
"""
from .base import BaseConnector


class CbsAfvalConnector(BaseConnector):
    def __init__(self, base_url: str, table_id: str, **kwargs):
        super().__init__(**kwargs)
        self.table_url = f"{base_url.rstrip('/')}/{table_id}"

    def typed_dataset(self) -> list[dict]:
        url = f"{self.table_url}/TypedDataSet"
        rows: list[dict] = []
        while url:
            data = self.get_json(url)
            rows.extend(data.get("value", []))
            url = data.get("odata.nextLink")
        return rows
