from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import service


class _FakeConnector:
    def __init__(self, payload=None, error=False):
        self._payload = payload
        self._error = error

    def bepaal_regels(self, activiteit, locatie=None):
        if self._error:
            raise ConnectorError("down")
        return self._payload


def test_regels_opzoeken_bevat_contract():
    conn = _FakeConnector(payload={"regels": ["X"]})
    out = service.regels_opzoeken("kappen van een boom", {"lat": 52.0, "lon": 4.0}, conn)
    assert out["vraag"] == "kappen van een boom"
    assert out["regels_ruw"] == {"regels": ["X"]}
    assert out["beschikbaar"] is True
    assert out["onzekerheid"] is True            # altijd indicatief
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"] == service.DISCLAIMER
    assert "toepasbare regels" in out["bron"].lower()


def test_regels_opzoeken_bron_down_degradeert():
    conn = _FakeConnector(error=True)
    out = service.regels_opzoeken("activiteit X", None, conn)
    assert out["beschikbaar"] is False
    assert out["regels_ruw"] is None
    # contract blijft staan, ook als de bron faalt
    assert out["disclaimer"] == service.DISCLAIMER
    assert "bevoegd gezag" in out["vangnet"]
