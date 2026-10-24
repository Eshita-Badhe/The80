from __future__ import annotations

import argparse
import json
import re
from datetime import timedelta
from pathlib import Path

from .ingest import load_dataset
from .engines import EvidenceEngine, IncidentEngine, RootCauseEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MetroPulse deterministic pipeline.")
    parser.add_argument("command", choices=["ingest", "run"])
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    dataset = load_dataset(args.data)
    if args.command == "run":
        incidents = IncidentEngine(dataset["topology"]).detect(dataset["events"], dataset["tickets"])
        evidence_engine = EvidenceEngine(dataset["topology"])
        root_cause_engine = RootCauseEngine(dataset["topology"])
        evidence_dir = (args.out or Path("out")) / "evidence"
        analysis_dir = (args.out or Path("out")) / "analysis"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        # Remove only prior pipeline artifacts with our exact generated naming
        # convention so reruns cannot leave stale incidents in the output.
        for directory in (evidence_dir, analysis_dir):
            for existing in directory.iterdir():
                if existing.is_file() and re.fullmatch(r"INC-\d{3}\.json", existing.name):
                    existing.unlink()
        analyses = []
        for incident in incidents:
            bundle = evidence_engine.build(
                incident, dataset["events"], dataset["tickets"], dataset["telemetry"],
                as_of=incident.end + timedelta(minutes=30),
                prior_incidents=[prior for prior in incidents if prior.end < incident.start],
            )
            (evidence_dir / f"{incident.incident_id}.json").write_text(
                json.dumps([item.model_dump(mode="json") for item in bundle], indent=2), encoding="utf-8"
            )
            analysis = root_cause_engine.analyze(
                incident, bundle, dataset["events"], as_of=incident.end + timedelta(minutes=30)
            )
            analyses.append(analysis)
            (analysis_dir / f"{incident.incident_id}.json").write_text(
                json.dumps(analysis.model_dump(mode="json"), indent=2), encoding="utf-8"
            )
        output_dir = args.out or Path("out")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "incidents.json").write_text(
            json.dumps([item.model_dump(mode="json") for item in incidents], indent=2), encoding="utf-8"
        )
        result = {
            "events": len(dataset["events"]), "tickets": len(dataset["tickets"]),
            "telemetry": len(dataset["telemetry"]), "rejects": dataset["rejects"],
            "incidents": len(incidents), "evidence_bundles": len(incidents),
            "analyses": len(analyses),
            "ranked": sum(item.status.value == "RANKED" for item in analyses),
            "insufficient_evidence": sum(item.status.value == "INSUFFICIENT_EVIDENCE" for item in analyses),
        }
        print(json.dumps(result, indent=2))
        (output_dir / "ingest_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    result = {
        "events": len(dataset["events"]),
        "tickets": len(dataset["tickets"]),
        "telemetry": len(dataset["telemetry"]),
        "rejects": dataset["rejects"],
        "topology_nodes": len(dataset["topology"].nodes),
        "topology_edges": sum(len(value) for value in dataset["topology"]._adj.values()) // 2,
    }
    print(json.dumps(result, indent=2))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "ingest_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
