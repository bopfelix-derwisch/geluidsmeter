import json
import geluidsmeter.api as api_module
from fastapi.testclient import TestClient


def _config_met_tmp(tmp_path):
    api_module._config = {
        "mobile": {
            "submit_token": "test-token-abc",
            "measurements_file": str(tmp_path / "mobile.jsonl"),
        },
        "project": {"quality_label": "prototype_indicatief_niet_juridisch"},
    }


def test_submit_401_verkeerde_token(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    resp = client.post(
        "/api/submit",
        json={"dba": 52.0, "lat": 52.08, "lon": 4.29, "naam": "Test"},
        headers={"Authorization": "Bearer verkeerd"},
    )
    assert resp.status_code == 401


def test_submit_201_correct(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    resp = client.post(
        "/api/submit",
        json={"dba": 63.2, "lat": 52.079, "lon": 4.315, "naam": "Binnenhof"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["accepted"] is True
    assert "id" in body


def test_submit_schrijft_jsonl(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    client.post(
        "/api/submit",
        json={"dba": 55.0, "lat": 52.079, "lon": 4.315, "naam": "Test locatie"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    fp = tmp_path / "mobile.jsonl"
    assert fp.exists()
    rec = json.loads(fp.read_text().strip())
    assert rec["dba"] == 55.0
    assert rec["naam"] == "Test locatie"
    assert rec["source"] == "mobile"
    assert rec["lat"] == 52.079


def test_submit_default_naam(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    client.post(
        "/api/submit",
        json={"dba": 40.0, "lat": 52.0, "lon": 4.3},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    rec = json.loads((tmp_path / "mobile.jsonl").read_text().strip())
    assert rec["naam"] == "Mobiele meting"


def test_mobile_entries_leeg_als_geen_file():
    api_module._config = {"mobile": {"measurements_file": "/tmp/bestaat-niet-sprint6-xyz.jsonl"}}
    assert api_module._mobile_location_entries() == []


def test_mobile_entries_leeg_als_geen_mobile_config():
    api_module._config = {}
    assert api_module._mobile_location_entries() == []


def test_mobile_entries_boven_norm(tmp_path):
    fp = tmp_path / "mobile.jsonl"
    fp.write_text(json.dumps({
        "id": "abc-123",
        "ts": "2026-05-14T10:00:00+00:00",
        "lat": 52.079,
        "lon": 4.315,
        "naam": "Binnenhof, Den Haag",
        "dba": 55.0,
        "source": "mobile",
        "kwaliteit": "prototype_indicatief_niet_juridisch",
    }) + "\n")
    api_module._config = {"mobile": {"measurements_file": str(fp)}}

    entries = api_module._mobile_location_entries()

    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == "abc-123"
    assert e["naam"] == "Binnenhof, Den Haag"
    assert e["lden_gemeten"] == 55.0
    assert e["norm_status"] == "boven_norm"
    assert e["rivm_lden"] is None
    assert e["precision_m"] == 20
    assert e["source"] == "mobile"


def test_mobile_entries_geen_dba(tmp_path):
    fp = tmp_path / "mobile.jsonl"
    fp.write_text(json.dumps({
        "id": "xyz", "ts": "2026-05-14T10:00:00+00:00",
        "lat": 52.0, "lon": 4.0, "naam": "Test",
        "dba": None, "source": "mobile",
        "kwaliteit": "prototype_indicatief_niet_juridisch",
    }) + "\n")
    api_module._config = {"mobile": {"measurements_file": str(fp)}}

    entries = api_module._mobile_location_entries()
    assert entries[0]["norm_status"] is None
    assert entries[0]["lden_gemeten"] is None


def test_mobile_entries_sla_ongeldige_regels_over(tmp_path):
    fp = tmp_path / "mobile.jsonl"
    # Eerste regel: ongeldige JSON. Tweede: mist verplichte velden. Derde: geldig.
    fp.write_text(
        "niet-json\n"
        + json.dumps({"geen_id": True}) + "\n"
        + json.dumps({
            "id": "goed", "ts": "2026-05-14T10:00:00+00:00",
            "lat": 52.0, "lon": 4.0, "naam": "Goed",
            "dba": 40.0, "source": "mobile",
            "kwaliteit": "prototype_indicatief_niet_juridisch",
        }) + "\n"
    )
    api_module._config = {"mobile": {"measurements_file": str(fp)}}
    entries = api_module._mobile_location_entries()
    assert len(entries) == 1
    assert entries[0]["id"] == "goed"
