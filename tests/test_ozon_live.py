"""Live smoke tegen Ozon pre-prod. Skipt zonder DSO_API_KEY."""
import os
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DSO_API_KEY"),
                                reason="DSO_API_KEY niet gezet; live-test overgeslagen")

OZON = "https://service.pre.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/presenteren/v8"


def test_live_regelingen_op_punt(tmp_path):
    from leefomgevinglab.connectors.ozon import OzonConnector
    c = OzonConnector(base_url=OZON, api_key=os.environ["DSO_API_KEY"], cache_dir=str(tmp_path))
    regelingen = c.regelingen_op_punt((139784.0, 442870.0))
    assert len(regelingen) >= 1
    assert all("type" in r and "titel" in r for r in regelingen)
