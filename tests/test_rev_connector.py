from leefomgevinglab.connectors.rev import RevConnector


def test_features_builds_request_and_returns_fc(tmp_path):
    captured = {}

    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return {"type": "FeatureCollection", "features": [{"id": 1}]}

    c = _Rev(base_url="https://api.pdok.nl/rws/rev/ogc/v1/",
             collection="inrichtingen", max_features=250, cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")

    assert captured["url"] == "https://api.pdok.nl/rws/rev/ogc/v1/collections/inrichtingen/items"
    assert captured["params"] == {"bbox": "4.0,52.0,4.5,52.5", "f": "json", "limit": 250}
    assert fc["type"] == "FeatureCollection"
    assert fc["features"] == [{"id": 1}]


def test_features_non_fc_returns_empty(tmp_path):
    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            return {"type": "Something", "code": "x"}

    c = _Rev(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")
    assert fc == {"type": "FeatureCollection", "features": []}
