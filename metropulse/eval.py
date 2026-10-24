from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _normalized_incident_id(value: str) -> str:
    return f"INC-{int(value.split('-')[-1]):03d}"


def evaluate(data_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    data_root, output_root = Path(data_dir), Path(output_dir)
    ground_truth = json.loads((data_root / "ground_truth.json").read_text(encoding="utf-8"))
    incidents = json.loads((output_root / "incidents.json").read_text(encoding="utf-8"))
    truth_by_id = {_normalized_incident_id(item["incident_id"]): item for item in ground_truth["incidents"]}
    labels = {
        event_id: (_normalized_incident_id(item["incident_id"]), role)
        for item in ground_truth["incidents"]
        for role, event_ids in item.get("events_by_role", {}).items()
        for event_id in event_ids
    }
    predicted_events = {event_id for item in incidents for event_id in item["member_event_ids"]}
    expected_events = {
        event_id for event_id, (_incident_id, role) in labels.items()
        if role in {"root", "supporting", "symptom"}
    }
    true_positive = len(predicted_events & expected_events)
    event_metrics = {
        "precision": true_positive / len(predicted_events) if predicted_events else 0.0,
        "recall": true_positive / len(expected_events) if expected_events else 0.0,
        "f1": 2 * true_positive / (len(predicted_events) + len(expected_events)) if predicted_events or expected_events else 0.0,
        "true_positive": true_positive,
        "predicted": len(predicted_events),
        "expected": len(expected_events),
    }

    detected_by_truth = {}
    membership_errors = []
    for incident in incidents:
        mapped = {labels[event_id][0] for event_id in incident["member_event_ids"] if event_id in labels}
        if len(mapped) != 1:
            membership_errors.append({"incident_id": incident["incident_id"], "ground_truth_ids": sorted(mapped)})
            continue
        truth_id = next(iter(mapped))
        if truth_id in detected_by_truth:
            membership_errors.append({"incident_id": incident["incident_id"], "ground_truth_ids": [truth_id], "error": "split"})
        detected_by_truth[truth_id] = incident["incident_id"]
    root_rows, abstention_rows, ambiguous_pass, high_wrong = [], [], 0, 0
    for truth_id, truth in sorted(truth_by_id.items()):
        detected_id = detected_by_truth.get(truth_id)
        analysis_path = output_root / "analysis" / f"{detected_id}.json" if detected_id else None
        analysis = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path and analysis_path.exists() else None
        hypotheses = analysis.get("hypotheses", []) if analysis else []
        top = hypotheses[0] if hypotheses else None
        expected = truth.get("root_cause_equipment")
        if truth["expected_label"] == "ROOT_CAUSE":
            top3 = [item["cause_equipment_id"] for item in hypotheses[:3]]
            root_rows.append({
                "incident_id": truth_id,
                "scenario": truth["scenario"],
                "expected": expected,
                "top1": top["cause_equipment_id"] if top else None,
                "confidence": top["confidence"] if top else None,
                "top1_pass": bool(top and top["cause_equipment_id"] == expected),
                "top3_pass": expected in top3,
            })
            if top and top["confidence"] == "HIGH" and top["cause_equipment_id"] != expected:
                high_wrong += 1
        elif truth["expected_label"] == "INSUFFICIENT_EVIDENCE":
            passed = bool(analysis and analysis["status"] == "INSUFFICIENT_EVIDENCE")
            ambiguous_pass += int(passed)
            abstention_rows.append({"incident_id": truth_id, "scenario": truth["scenario"], "status": analysis.get("status") if analysis else None, "top": top.get("cause_equipment_id") if top else None, "pass": passed, "reasons": analysis.get("abstain_reasons", []) if analysis else []})
        else:
            accepted_low_root = bool(
                analysis and top and top["cause_equipment_id"] == expected
                and top["confidence"] == "LOW"
                and any("DATA_GAP" in str(reason) or "data gap" in str(reason).lower() for reason in analysis.get("abstain_reasons", []))
            )
            passed = bool(analysis and analysis["status"] == "INSUFFICIENT_EVIDENCE") or accepted_low_root
            ambiguous_pass += int(passed)
            abstention_rows.append({"incident_id": truth_id, "scenario": truth["scenario"], "status": analysis.get("status") if analysis else None, "top": top.get("cause_equipment_id") if top else None, "confidence": top.get("confidence") if top else None, "pass": passed, "reasons": analysis.get("abstain_reasons", []) if analysis else []})

    root_count = len(root_rows)
    scorecard = {
        "data_notice": "Synthetic planted scenarios; these results are not performance claims on real metro data.",
        "incident_detection": {
            "planted": len(ground_truth["incidents"]),
            "detected": len(incidents),
            "one_to_one_matches": len(detected_by_truth),
            "merge_or_split_errors": membership_errors,
        },
        "event_membership": event_metrics,
        "root_cause": {
            "root_cause_incidents": root_count,
            "top1": sum(row["top1_pass"] for row in root_rows),
            "top3": sum(row["top3_pass"] for row in root_rows),
            "correct_ambiguous_abstentions": ambiguous_pass,
            "abstention_scenarios": abstention_rows,
            "wrong_high_confidence": high_wrong,
            "per_incident": root_rows,
        },
    }
    return scorecard


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MetroPulse output against synthetic ground truth.")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    scorecard = evaluate(args.data, args.out.parent)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    print(json.dumps(scorecard, indent=2))


if __name__ == "__main__":
    main()
