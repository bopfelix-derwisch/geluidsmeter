from geluidsmeter.api import _location_entry


def _make_config(public_name="Testbuurt", public_id="test-id"):
    return {
        "location": {
            "public_location_precision_m": 100,
            "public_name": public_name,
            "public_id": public_id,
        },
        "project": {"quality_label": "prototype_indicatief_niet_juridisch"},
    }


def test_location_entry_boven_norm():
    entry = _location_entry(
        config=_make_config(),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=55.0,
        rivm_lden=55.5,
    )
    assert entry["norm_status"] == "boven_norm"
    assert entry["lden_gemeten"] == 55.0
    assert entry["rivm_lden"] == 55.5
    assert entry["norm_lden"] == 48
    assert entry["laatste_meting"] is not None


def test_location_entry_binnen_norm():
    entry = _location_entry(
        config=_make_config(),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=44.0,
        rivm_lden=55.5,
    )
    assert entry["norm_status"] == "binnen_norm"


def test_location_entry_geen_meting():
    entry = _location_entry(
        config=_make_config(),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=None,
        rivm_lden=None,
    )
    assert entry["norm_status"] is None
    assert entry["lden_gemeten"] is None
    assert entry["laatste_meting"] is None


def test_location_entry_velden():
    entry = _location_entry(
        config=_make_config(public_name="Archipelbuurt, Den Haag", public_id="archipelbuurt-denhaag"),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=50.0,
        rivm_lden=55.5,
    )
    assert entry["id"] == "archipelbuurt-denhaag"
    assert entry["naam"] == "Archipelbuurt, Den Haag"
    assert entry["lat"] == 52.08
    assert entry["lon"] == 4.29
    assert entry["precision_m"] == 100
    assert entry["kwaliteit"] == "prototype_indicatief_niet_juridisch"
