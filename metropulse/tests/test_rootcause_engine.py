import json
from datetime import timedelta
from pathlib import Path

from metropulse.engines import EvidenceEngine, IncidentEngine, RootCauseEngine
from metropulse.ingest import load_dataset
from metropulse.schemas import AnalysisStatus, Confidence, EvidenceType


DATA = Path(__file__).parents[2] / "data"


def test_seed_42_root_causes_and_abstentions_match_scenarios():
    dataset = load_dataset(DATA)
    incidents = IncidentEngine(dataset["topology"]).detect(dataset["events"], dataset["tickets"])
    evidence_engine = EvidenceEngine(dataset["topology"])
    root_engine = RootCauseEngine(dataset["topology"])
    truth = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))
    truth_by_id = {
        f"INC-{int(item['incident_id'].split('-')[-1]):03d}": item
        for item in truth["incidents"]
    }
    analyses = {}

    for incident in incidents:
        as_of = incident.end + timedelta(minutes=30)
        evidence = evidence_engine.build(
            incident,
            dataset["events"],
            dataset["tickets"],
            dataset["telemetry"],
            as_of=as_of,
            prior_incidents=[prior for prior in incidents if prior.end < incident.start],
        )
        analyses[incident.incident_id] = root_engine.analyze(incident, evidence, dataset["events"], as_of=as_of)

    root_cases = [item for item in truth_by_id.values() if item["expected_label"] == "ROOT_CAUSE"]
    for item in root_cases:
        key = f"INC-{int(item['incident_id'].split('-')[-1]):03d}"
        analysis = analyses[key]
        assert analysis.hypotheses[0].cause_equipment_id == item["root_cause_equipment"]
        assert item["root_cause_equipment"] in {hypothesis.cause_equipment_id for hypothesis in analysis.hypotheses[:3]}
        assert analysis.hypotheses[0].would_confirm

    ambiguous_cases = [item for item in truth_by_id.values() if item["expected_label"] == "INSUFFICIENT_EVIDENCE"]
    for item in ambiguous_cases:
        key = f"INC-{int(item['incident_id'].split('-')[-1]):03d}"
        assert analyses[key].status is AnalysisStatus.INSUFFICIENT_EVIDENCE
        assert analyses[key].abstain_reasons

    missing_log_cases = [item for item in truth_by_id.values() if item["expected_label"] == "LOW_CONFIDENCE_ROOT_CAUSE"]
    for item in missing_log_cases:
        key = f"INC-{int(item['incident_id'].split('-')[-1]):03d}"
        analysis = analyses[key]
        top = analysis.hypotheses[0]
        assert analysis.status is AnalysisStatus.INSUFFICIENT_EVIDENCE or (
            top.cause_equipment_id == item["root_cause_equipment"] and top.confidence is Confidence.LOW
        )
        assert analysis.data_gaps


def test_hypothesis_evidence_links_resolve_and_have_next_checks():
    dataset = load_dataset(DATA)
    incidents = IncidentEngine(dataset["topology"]).detect(dataset["events"], dataset["tickets"])
    evidence_engine = EvidenceEngine(dataset["topology"])
    root_engine = RootCauseEngine(dataset["topology"])
    incident = incidents[0]
    as_of = incident.end + timedelta(minutes=30)
    evidence = evidence_engine.build(
        incident, dataset["events"], dataset["tickets"], dataset["telemetry"], as_of=as_of
    )
    analysis = root_engine.analyze(incident, evidence, dataset["events"], as_of=as_of)
    evidence_ids = {item.evidence_id for item in evidence}

    assert all(set(hypothesis.supports + hypothesis.contradicts + hypothesis.unexplained) <= evidence_ids for hypothesis in analysis.hypotheses)
    assert all(hypothesis.would_confirm and hypothesis.would_rule_out and hypothesis.next_checks for hypothesis in analysis.hypotheses)
    assert all(item.type is not EvidenceType.EVENT or item.source_refs for item in evidence)
