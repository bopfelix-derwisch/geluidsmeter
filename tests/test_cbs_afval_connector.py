import httpx
from leefomgevinglab.connectors.cbs_afval import CbsAfvalConnector


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_typed_dataset_volgt_nextlink(tmp_path, monkeypatch):
    pages = {
        "https://cbs/OData/83558NED/TypedDataSet": {
            "value": [{"Regiokenmerken": "PV24    ", "Perioden": "2020JJ00"}],
            "odata.nextLink": "https://cbs/OData/83558NED/TypedDataSet?$skip=1",
        },
        "https://cbs/OData/83558NED/TypedDataSet?$skip=1": {
            "value": [{"Regiokenmerken": "PV25    ", "Perioden": "2020JJ00"}],
        },
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse(pages[url])

    monkeypatch.setattr(httpx, "get", fake_get)
    c = CbsAfvalConnector(base_url="https://cbs/OData", table_id="83558NED",
                          cache_dir=str(tmp_path))
    rows = c.typed_dataset()
    assert [r["Regiokenmerken"].strip() for r in rows] == ["PV24", "PV25"]
