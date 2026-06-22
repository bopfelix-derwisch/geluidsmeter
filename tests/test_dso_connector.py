import pytest
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.base import ConnectorError

RTR = "https://x/rtr/v2"
UITV = "https://x/uitv/v3"
REF = "http://x/werkzaamheden/id/concept/DakkapelPlaatsen"


def _conn(tmp_path, capture, ret):
    class _D(DsoConnector):
        def post_json(self, url, json_body=None, headers=None):
            capture["url"] = url
            capture["body"] = json_body
            capture["headers"] = headers
            return ret

    return _D(rtr_base_url=RTR, uitvoeren_base_url=UITV, api_key="K", cache_dir=str(tmp_path))


def test_bepaal_typeringen(tmp_path):
    cap = {}
    c = _conn(tmp_path, cap, [{"functioneleStructuurRef": REF, "regelbeheerobjecten": ["Conclusie"]}])
    out = c.bepaal_typeringen([REF], (155000.0, 463000.0))
    assert cap["url"] == f"{RTR}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen"
    assert cap["body"]["functioneleStructuurRefs"] == [REF]
    assert cap["body"]["_geo"] == {"intersects": {"type": "Point", "coordinates": [155000.0, 463000.0]}}
    assert cap["headers"]["x-api-key"] == "K"
    assert out[0]["regelbeheerobjecten"] == ["Conclusie"]


def test_bepaal_indieningsvereisten_sets_crs_and_antwoorden(tmp_path):
    cap = {}
    c = _conn(tmp_path, cap, [{"indieningsvereisten": []}])
    c.bepaal_indieningsvereisten([REF], (121000.0, 487000.0))
    assert cap["url"] == f"{UITV}/indieningsvereisten/_bepaal"
    assert cap["body"]["functioneleStructuurRefs"] == [{"functioneleStructuurRef": REF, "antwoorden": []}]
    assert cap["body"]["_geo"]["intersects"]["coordinates"] == [121000.0, 487000.0]
    assert cap["headers"]["Content-Crs"] == "EPSG:28992"
    assert cap["headers"]["x-api-key"] == "K"


def test_without_key_raises(tmp_path):
    c = DsoConnector(rtr_base_url=RTR, uitvoeren_base_url=UITV, api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.bepaal_typeringen([REF], (1.0, 2.0))
    with pytest.raises(ConnectorError):
        c.bepaal_indieningsvereisten([REF], (1.0, 2.0))
