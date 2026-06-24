"""Live smoke tegen de open REV WFS. Skipt zonder DSO_API_KEY (live-test-vlag)."""
import os
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DSO_API_KEY"),
                                reason="live-tests uit (DSO_API_KEY niet gezet)")

WFS = "https://rev-portaal.nl/geoserver/wfs"


def test_live_explosieaandachtsgebied_op_rd_punt(tmp_path):
    from leefomgevinglab.connectors.externe_veiligheid import ExterneVeiligheidConnector
    c = ExterneVeiligheidConnector(wfs_url=WFS, cache_dir=str(tmp_path))
    # RD-punt binnen een bekend explosieaandachtsgebied (Bungalowpark Hessenheem, propaan; geverifieerd 2026-06-24)
    treffers = c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", (232003.1, 473064.6))
    assert len(treffers) >= 1
    assert treffers[0]["maatgevende_stof"] == "propaan"
