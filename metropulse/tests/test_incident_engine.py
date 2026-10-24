import json
from datetime import datetime, timezone
from pathlib import Path

from metropulse.engines import IncidentEngine
from metropulse.ingest import load_dataset
from metropulse.schemas import Incident, Ticket


DATA = Path(__file__).parents[2] / "data"


def test_seed_42_incidents_match_planted_scenarios_and_membership_targets():
    dataset = load_dataset(DATA)
    incidents = IncidentEngine(dataset["topology"]).detect(dataset["events"], dataset["tickets"])
    truth = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))
    labels = {
        event_id: (scenario["incident_id"], role)
        for scenario in truth["incidents"]
        for role, event_ids in scenario.get("events_by_role", {}).items()
        for event_id in event_ids
    }

    assert len(incidents) == 20
    scenario_to_detected = {}
    expected_members = {
        event_id
        for event_id, (_scenario_id, role) in labels.items()
        if role in {"root", "supporting", "symptom"}
    }
    predicted_members = {event_id for incident in incidents for event_id in incident.member_event_ids}

    for incident in incidents:
        scenario_ids = {labels[event_id][0] for event_id in incident.member_event_ids if event_id in labels}
        assert len(scenario_ids) == 1
        scenario_id = scenario_ids.pop()
        assert scenario_id not in scenario_to_detected
        scenario_to_detected[scenario_id] = incident

    assert len(scenario_to_detected) == len(truth["incidents"]) == 20
    true_positive = len(predicted_members & expected_members)
    assert true_positive / len(predicted_members) >= 0.85
    assert true_positive / len(expected_members) >= 0.95
    assert not any(labels.get(event_id, (None, None))[1] in {"red_herring", "noise"} for event_id in predicted_members)


def test_recurring_door_faults_stay_separate_and_link_by_dominant_equipment():
    dataset = load_dataset(DATA)
    incidents = IncidentEngine(dataset["topology"]).detect(dataset["events"], dataset["tickets"])
    door_incidents = [
        incident for incident in incidents
        if "TR03-D4" in incident.equipment_ids and incident.start.date().isoformat() in {"2026-09-04", "2026-09-09", "2026-09-10"}
    ]

    assert len(door_incidents) == 3
    chronological = sorted(door_incidents, key=lambda incident: incident.start)
    assert chronological[0].recurrence["prior_incident_ids"] == []
    assert chronological[1].recurrence["prior_incident_ids"] == [chronological[0].incident_id]
    assert chronological[2].recurrence["prior_incident_ids"] == [chronological[0].incident_id, chronological[1].incident_id]


def test_incident_output_is_deterministic():
    dataset = load_dataset(DATA)
    engine = IncidentEngine(dataset["topology"])
    first = [item.model_dump(mode="json") for item in engine.detect(dataset["events"], dataset["tickets"])]
    second = [item.model_dump(mode="json") for item in engine.detect(dataset["events"], dataset["tickets"])]

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_ticket_dedup_requires_text_similarity_and_station_or_equipment_match():
    dataset = load_dataset(DATA)
    engine = IncidentEngine(dataset["topology"])
    when = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
    incident = Incident(
        incident_id="INC-TEST", start=when, end=when,
        member_event_ids=[], equipment_ids=["PSD-SWG-P01"], station_codes=["SWG", "BPT"],
        systems=["CBTC"], priority_score=0, priority_factors={},
    )
    tickets = [
        Ticket(ticket_id="TKT-1", created_at=when, equipment_id="PSD-SWG-P01", station_code="SWG", text="PSD faulty at SWG", priority="P2", team="PSD"),
        Ticket(ticket_id="TKT-2", created_at=when, equipment_id="PSD-SWG-P01", station_code="SWG", text="OCC: PSD faults reported at SWG", priority="P2", team="PSD"),
        Ticket(ticket_id="TKT-3", created_at=when, equipment_id="PSD-BPT-P01", station_code="BPT", text="PSD faulty at SWG", priority="P2", team="PSD"),
    ]

    assert engine._ticket_groups(incident, tickets) == [["TKT-1", "TKT-2"]]
