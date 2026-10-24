from pathlib import Path

from metropulse.ingest import load_dataset
from metropulse.schemas import Severity, Source


DATA = Path(__file__).parents[2] / "data"


def test_generated_dataset_loads_without_rejects():
    dataset = load_dataset(DATA)
    assert len(dataset["events"]) == 1495
    assert len(dataset["tickets"]) == 154
    assert len(dataset["telemetry"]) == 73238
    assert dataset["rejects"] == []


def test_source_specific_normalization():
    dataset = load_dataset(DATA)
    events = {event.event_id: event for event in dataset["events"]}
    assert events["SC-000001"].station_code == "SJN"
    assert events["SC-000003"].severity is Severity.WARN
    assert events["TC-000001"].equipment_id == "TR03-D2"
    assert events["AF-000001"].equipment_id == "AFC-SJN-G02"
    assert events["CB-000001"].source is Source.CBTC
    assert all(event.ts.tzinfo is not None for event in dataset["events"])


def test_causal_topology_ignores_monitoring_edges():
    topology = load_dataset(DATA)["topology"]
    assert topology.distance("RTU001", "UPS-BPT") is None
