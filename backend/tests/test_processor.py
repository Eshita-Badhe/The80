from backend.services.data_generator import generate_records, generate_scenario
from backend.services.processor import process_records

def test_generator_is_reproducible():
    assert generate_records(12, seed=44) == generate_records(12, seed=44)

def test_threshold_anomaly_has_evidence_link():
    row = generate_scenario("escalator", seed=3)[0]
    result = process_records([row])
    assert len(result["anomalies"]) == 1
    assert result["anomalies"][0]["record_id"] == row["record_id"]
    assert result["incidents"][0]["priority_score"] > 0

def test_invalid_timestamp_is_rejected_and_reported():
    result = process_records([{"timestamp":"broken", "station_id":"MP-01", "equipment_id":"X"}])
    assert result["statistics"]["processed_records"] == 0
    assert "timestamp" in result["statistics"]["issues"][0]["issue"]

def test_duplicate_records_are_dropped():
    row = generate_records(1, seed=10)[0]
    result = process_records([row, row])
    assert result["statistics"]["processed_records"] == 1
    assert result["statistics"]["rejected_or_duplicate"] == 1

def test_cascade_scenario_keeps_shared_incident_link():
    rows = generate_scenario("cascade", seed=88)
    result = process_records(rows)
    assert len(result["incidents"]) == 1
    assert result["incidents"][0]["event_count"] == 3

def test_common_export_column_names_are_normalized():
    result = process_records([{"time":"2026-10-23T12:00:00+00:00", "station":"mp-02", "asset_id":"lift-1", "category":"Lift", "event":"VIBRATION_HIGH", "level":"high", "sensor":"vibration_mm_s", "reading":"12"}])
    assert result["events"][0]["station_id"] == "MP-02"
    assert result["events"][0]["equipment_id"] == "LIFT-1"
    assert len(result["anomalies"]) == 1
