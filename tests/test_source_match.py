import pytest
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from src.leefomgevinglab.geluidsmeter.source_match import (
    estimate_dba,
    check_norm,
    identify_sources,
    match_cvgg,
)


def test_estimate_dba_zero_offset():
    assert estimate_dba(-60.0, 0.0) == -60.0


def test_estimate_dba_with_offset():
    assert abs(estimate_dba(-60.0, 114.0) - 54.0) < 0.01


def test_check_norm_within():
    result = check_norm(lden_db=45.0, lnight_db=38.0)
    assert result["lden_status"] == "ok"
    assert result["lnight_status"] == "ok"
    assert result["lden_delta"] == pytest.approx(-3.0)


def test_check_norm_exceeded():
    result = check_norm(lden_db=55.0, lnight_db=50.0)
    assert result["lden_status"] == "overschreden"
    assert result["lnight_status"] == "overschreden"
    assert result["lden_delta"] == pytest.approx(7.0)


def test_identify_sources_empty():
    empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    result = identify_sources(empty_gdf)
    assert result["dominant_source"] == "onbekend"
    assert result["weg_detected"] is False


def test_identify_sources_with_road():
    road = gpd.GeoDataFrame(
        {"wegbeheerdersoort": ["Rijksweg"], "geometry": [Point(5.0, 52.0).buffer(0.001)]},
        crs="EPSG:4326",
    )
    result = identify_sources(road)
    assert result["weg_count"] >= 1
    assert result["dominant_source"] == "wegverkeer"
    assert result["weg_detected"] is True


def test_match_cvgg_no_overlap():
    gdf = gpd.GeoDataFrame(
        {"lden": [52.0], "lnight": [43.0],
         "geometry": [Point(10.0, 53.0).buffer(0.001)]},
        crs="EPSG:4326",
    )
    result = match_cvgg(Point(5.0, 52.0), gdf)
    assert result["lden"] is None
    assert result["lnight"] is None


def test_match_cvgg_with_overlap():
    gdf = gpd.GeoDataFrame(
        {"lden": [52.0], "lnight": [43.0],
         "geometry": [Point(5.0, 52.0).buffer(0.1)]},
        crs="EPSG:4326",
    )
    result = match_cvgg(Point(5.0, 52.0), gdf)
    assert result["lden"] == pytest.approx(52.0)
    assert result["lnight"] == pytest.approx(43.0)
