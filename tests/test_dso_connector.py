import pytest
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.base import ConnectorError

RTR = "https://x/rtr/v2"
UITV = "https://x/uitv/v3"
REF = "http://x/werkzaamheden/id/concept/DakkapelPlaatsen"


def _conn(tmp_path, capture, ret, rtr_key="RTRKEY", uitv_key="UITVKEY"):
    class _D(DsoConnector):
        def post_json(self, url, json_body=None, headers=None):
            capture["url"] = url
            capture["body"] = json_body
            capture["headers"] = headers
            return ret

    return _D(rtr_base_url=RTR, uitvoeren_base_url=UITV,
              rtr_api_key=rtr_key, uitvoeren_api_key=uitv_key, cache_dir=str(tmp_path))


def test_bepaal_typeringen_gebruikt_rtr_key(tmp_path):
    cap = {}
    c = _conn(tmp_path, cap, [{"functioneleStructuurRef": REF, "regelbeheerobjecten": ["Conclusie"]}])
    out = c.bepaal_typeringen([REF], (155000.0, 463000.0))
    assert cap["url"] == f"{RTR}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen"
    assert cap["body"]["functioneleStructuurRefs"] == [REF]
    assert cap["body"]["_geo"] == {"intersects": {"type": "Point", "coordinates": [155000.0, 463000.0]}}
    # RTR gebruikt de RTR-key (kan productie zijn), niet de Uitvoeren-key
    assert cap["headers"]["x-api-key"] == "RTRKEY"
    assert out[0]["regelbeheerobjecten"] == ["Conclusie"]


def test_bepaal_indieningsvereisten_gebruikt_uitvoeren_key_en_crs(tmp_path):
    cap = {}
    c = _conn(tmp_path, cap, [{"indieningsvereisten": []}])
    c.bepaal_indieningsvereisten([REF], (121000.0, 487000.0))
    assert cap["url"] == f"{UITV}/indieningsvereisten/_bepaal"
    assert cap["body"]["functioneleStructuurRefs"] == [{"functioneleStructuurRef": REF, "antwoorden": []}]
    assert cap["body"]["_geo"]["intersects"]["coordinates"] == [121000.0, 487000.0]
    assert cap["headers"]["Content-Crs"] == "EPSG:28992"
    # Uitvoeren gebruikt de Uitvoeren-key (pre), niet de RTR-key
    assert cap["headers"]["x-api-key"] == "UITVKEY"


def test_ontbrekende_key_per_service_raises(tmp_path):
    # RTR-key ontbreekt -> alleen de RTR-call faalt; Uitvoeren blijft werken
    c = _conn(tmp_path, {}, [{"ok": True}], rtr_key=None, uitv_key="UITVKEY")
    with pytest.raises(ConnectorError):
        c.bepaal_typeringen([REF], (1.0, 2.0))
    # Uitvoeren met geldige key faalt niet op de key-check
    c.bepaal_indieningsvereisten([REF], (1.0, 2.0))
