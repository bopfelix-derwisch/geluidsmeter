import leefomgevinglab.geluidsmeter.api as api

_DSO = {
    "api_key_header": "x-api-key",
    "zoek_env": "pre", "rtr_env": "prod", "uitvoeren_env": "pre",
    "pre": {
        "zoek_base_url": "https://pre/zoek/v2",
        "rtr_base_url": "https://pre/rtr/v2",
        "uitvoeren_base_url": "https://pre/uitv/v3",
    },
    "prod": {
        "zoek_base_url": "https://prod/zoek/v2",
        "rtr_base_url": "https://prod/rtr/v2",
        "uitvoeren_base_url": "https://prod/uitv/v3",
    },
}


def _setup(monkeypatch):
    api._config = {"leefomgevinglab": {"dso": _DSO, "cache_dir": "/tmp/llab_test_cache"}}
    monkeypatch.setenv("DSO_API_KEY", "PRE_KEY")
    monkeypatch.setenv("DSO_API_KEY_PROD", "PROD_KEY")


def test_rtr_op_prod_uitvoeren_op_pre(monkeypatch):
    _setup(monkeypatch)
    c = api._dso_connector()
    # RTR -> productie-url + productie-key
    assert c.rtr_base_url == "https://prod/rtr/v2"
    assert c.rtr_api_key == "PROD_KEY"
    # Uitvoeren -> pre-url + pre-key
    assert c.uitvoeren_base_url == "https://pre/uitv/v3"
    assert c.uitvoeren_api_key == "PRE_KEY"


def test_zoek_blijft_pre(monkeypatch):
    _setup(monkeypatch)
    z = api._zoek_connector()
    assert z.base_url == "https://pre/zoek/v2"
    assert z.api_key == "PRE_KEY"


def test_env_key_helper(monkeypatch):
    monkeypatch.setenv("DSO_API_KEY", "PRE_KEY")
    monkeypatch.setenv("DSO_API_KEY_PROD", "PROD_KEY")
    assert api._dso_env_key("prod") == "PROD_KEY"
    assert api._dso_env_key("pre") == "PRE_KEY"


def test_ozon_op_prod(monkeypatch):
    api._config = {"leefomgevinglab": {"cache_dir": "/tmp/llab_test_cache", "ozon": {
        "api_key_header": "x-api-key", "environment": "prod",
        "pre": {"base_url": "https://pre/presenteren/v8"},
        "prod": {"base_url": "https://prod/presenteren/v8"}}}}
    monkeypatch.setenv("DSO_API_KEY", "PRE_KEY")
    monkeypatch.setenv("DSO_API_KEY_PROD", "PROD_KEY")
    o = api._ozon_connector()
    assert o.base_url == "https://prod/presenteren/v8"
    assert o.api_key == "PROD_KEY"
