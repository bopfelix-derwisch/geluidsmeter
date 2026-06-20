import pytest
from leefomgevinglab.connectors.rev import RevConnector


def test_features_reorders_bbox_and_swaps_coords(tmp_path):
    captured = {}

    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            # bron levert lat,lon (EPSG:4258)
            return {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Polygon",
                                 "coordinates": [[[52.0, 4.0], [52.1, 4.0], [52.1, 4.2], [52.0, 4.0]]]},
                    "properties": {"name": "X"},
                }],
            }

    c = _Rev(base_url="https://api.pdok.nl/rws/x/ogc/v1/",
             collection="production_facility_f", max_features=250, cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")

    assert captured["url"] == "https://api.pdok.nl/rws/x/ogc/v1/collections/production_facility_f/items"
    # lon,lat-bbox omgezet naar lat,lon voor de bron
    assert captured["params"] == {"bbox": "52.0,4.0,52.5,4.5", "f": "json", "limit": 250}
    # teruggegeven coordinaten omgedraaid naar lon,lat
    assert fc["features"][0]["geometry"]["coordinates"] == [[[4.0, 52.0], [4.0, 52.1], [4.2, 52.1], [4.0, 52.0]]]
    assert fc["features"][0]["properties"]["name"] == "X"


def test_features_non_fc_returns_empty(tmp_path):
    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            return {"type": "Something", "code": "x"}

    c = _Rev(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")
    assert fc == {"type": "FeatureCollection", "features": []}


def test_features_handles_missing_geometry(tmp_path):
    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            return {"type": "FeatureCollection",
                    "features": [{"type": "Feature", "geometry": None, "properties": {}}]}

    c = _Rev(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")
    assert fc["features"][0]["geometry"] is None


def test_features_invalid_bbox_raises(tmp_path):
    c = RevConnector(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    with pytest.raises(ValueError):
        c.features("4.0,52.0,4.5")  # 3 parts


def test_features_swaps_top_level_bboxes(tmp_path):
    class _Rev(RevConnector):
        def get_json(self, url, params=None):
            return {"type": "FeatureCollection",
                    "bbox": [52.0, 4.0, 52.5, 4.5],
                    "features": [{"type": "Feature", "geometry": None,
                                  "bbox": [52.0, 4.0, 52.1, 4.2], "properties": {}}]}
    c = _Rev(base_url="https://x", collection="c", cache_dir=str(tmp_path))
    fc = c.features("4.0,52.0,4.5,52.5")
    assert fc["bbox"] == [4.0, 52.0, 4.5, 52.5]
    assert fc["features"][0]["bbox"] == [4.0, 52.0, 4.2, 52.1]
