from __future__ import annotations

from collections import Counter, deque
from datetime import datetime
from typing import Iterable

from ..knowledge_base import ALARM_CODES, FAILURE_PATTERNS
from ..schemas import Analysis, AnalysisStatus, Confidence, Evidence, EvidenceType, Event, Hypothesis, Incident, Severity
from ..topology import Topology


SEVERITY_STRENGTH = {
    Severity.WARN: 0.25,
    Severity.MINOR: 0.50,
    Severity.MAJOR: 0.75,
    Severity.CRITICAL: 1.0,
}


class RootCauseEngine:
    """Deterministic, evidence-linked cause ranking with explicit abstention."""

    def __init__(self, topology: Topology):
        self.topology = topology

    def analyze(
        self,
        incident: Incident,
        evidence: Iterable[Evidence],
        events: Iterable[Event],
        *,
        as_of: datetime | None = None,
    ) -> Analysis:
        evidence = sorted(evidence, key=lambda item: item.evidence_id)
        event_lookup = {event.event_id: event for event in events}
        incident_events = [
            event_lookup[event_id]
            for event_id in incident.member_event_ids
            if event_id in event_lookup and (as_of is None or event_lookup[event_id].ts <= as_of)
        ]
        if as_of is None:
            as_of = incident.end
        evidence_event_lookup = {
            item.source_refs[0]: item
            for item in evidence
            if item.type is EvidenceType.EVENT and item.source_refs
        }
        candidate_ids = self._candidates(incident.equipment_ids)
        if not candidate_ids:
            return Analysis(
                incident_id=incident.incident_id,
                as_of=as_of,
                status=AnalysisStatus.INSUFFICIENT_EVIDENCE,
                hypotheses=[],
                abstain_reasons=["No candidate equipment was connected to the incident by causal topology."],
            )

        observed_equipment = {event.equipment_id for event in incident_events}
        rows = []
        for candidate_id in sorted(candidate_ids):
            node = self.topology.nodes.get(candidate_id, {})
            node_type = str(node.get("type", "unknown"))
            own_events = [event for event in incident_events if event.equipment_id == candidate_id]
            own_fault_events = [
                event for event in own_events
                if event.severity in {Severity.MAJOR, Severity.CRITICAL}
                or ALARM_CODES.get(event.code, {}).get("role") == "root"
            ]
            descendants = self._downstream(candidate_id, max_depth=4)
            downstream_affected = {
                equipment for equipment in observed_equipment
                if equipment in descendants
            }
            affected = observed_equipment - {candidate_id}
            coverage = len(downstream_affected) / len(affected) if affected else 0.0
            own_strength = max((SEVERITY_STRENGTH[event.severity] for event in own_events), default=0.0)
            first_own = min((event.ts for event in own_fault_events), default=None)
            first_symptom = min((event.ts for event in incident_events if event.equipment_id != candidate_id), default=None)
            precedence = float(first_own is not None and (first_symptom is None or first_own <= first_symptom))
            affinity_hits = [
                event for event in incident_events
                if node_type in FAILURE_PATTERNS.get(event.code, {}).get("node_types", [])
                and event.equipment_id != candidate_id
            ]
            affinity = min(1.0, len(affinity_hits) / 2.0)
            own_anomaly = any(
                item.type is EvidenceType.TELEMETRY_ANOMALY and item.equipment_id == candidate_id
                for item in evidence
            )
            telemetry = float(own_anomaly)
            own_count = len(own_events)
            prior_history = sum(
                1 for item in evidence
                if item.type is EvidenceType.HISTORY
                and candidate_id in item.attributes.get("shared_equipment", [])
            ) if own_count >= 2 or any(ALARM_CODES.get(event.code, {}).get("role") == "root" for event in own_events) else 0
            repetition = min(1.0, max(0.0, (own_count - 1) / 3.0))
            history = min(1.0, prior_history / 2.0)
            repeat_history = max(repetition, history)
            healthy_children = self._healthy_descendant_nodes(candidate_id, evidence)
            child_groups = self._descendant_groups(candidate_id)
            healthy_groups = {
                str(self.topology.nodes[node].get("type", "unknown"))
                for node in healthy_children if node in self.topology.nodes
            }
            contradiction = len(healthy_groups & child_groups) / len(child_groups) if child_groups else 0.0

            score = max(0.0, min(1.0,
                0.28 * coverage
                + 0.22 * own_strength
                + 0.10 * precedence
                + 0.12 * affinity
                + 0.12 * telemetry
                + 0.12 * repeat_history
                - 0.22 * contradiction
            ))
            signature = (
                len(affinity_hits) >= 2
                or own_anomaly
                or own_count >= 4
                or (own_count >= 2 and own_strength >= 0.75 and coverage >= 0.5)
            )
            covering_gaps = [
                item for item in evidence
                if item.type is EvidenceType.DATA_GAP
                and candidate_id in item.attributes.get("affected_equipment", [])
            ]
            own_alarm_precedence = bool(first_own and (first_symptom is None or first_own <= first_symptom))
            rows.append({
                "equipment_id": candidate_id,
                "node_type": node_type,
                "score": round(score, 6),
                "coverage": round(coverage, 6),
                "own_alarm_strength": own_strength,
                "temporal_precedence": precedence,
                "pattern_affinity": round(affinity, 6),
                "telemetry_corroboration": telemetry,
                "repetition_history": round(repeat_history, 6),
                "contradiction_penalty": round(contradiction, 6),
                "own_count": own_count,
                "own_alarm_precedence": own_alarm_precedence,
                "signature": signature,
                "covering_gaps": covering_gaps,
                "own_events": own_events,
                "own_fault_events": own_fault_events,
                "affinity_hits": affinity_hits,
            })

        rows.sort(key=lambda row: (-row["score"], row["equipment_id"]))
        top = rows[0]
        runner_up = rows[1] if len(rows) > 1 else None
        credible_runner_up = bool(
            runner_up
            and runner_up["score"] >= 0.25
            and runner_up["score"] >= 0.6 * top["score"]
        )
        gap = top["score"] - runner_up["score"] if runner_up else 1.0
        abstain_reasons = []
        if not top["signature"]:
            abstain_reasons.append("The leading candidate has no downstream signature, repeated alarm pattern, or telemetry corroboration.")
        if credible_runner_up and gap < 0.15:
            abstain_reasons.append("Two credible candidates have scores too close to distinguish reliably.")
        status = AnalysisStatus.INSUFFICIENT_EVIDENCE if abstain_reasons else AnalysisStatus.RANKED

        hypotheses = []
        valid_evidence_ids = {item.evidence_id for item in evidence}
        for rank, row in enumerate(rows, 1):
            supports, contradicts = self._stance(row, evidence, evidence_event_lookup)
            unexplained = [
                item.evidence_id for item in evidence
                if item.type is EvidenceType.EVENT and item.evidence_id not in supports
            ]
            candidate_gap = bool(row["covering_gaps"])
            if candidate_gap and not row["own_fault_events"]:
                confidence = Confidence.LOW
            elif row["signature"] and rank == 1 and row["own_alarm_precedence"] and row["coverage"] >= 0.6 and not credible_runner_up and not candidate_gap:
                confidence = Confidence.HIGH
            elif row["signature"]:
                confidence = Confidence.MEDIUM
            else:
                confidence = Confidence.LOW
            if rank == 1 and candidate_gap and not row["own_fault_events"]:
                abstain_reasons.append(f"{row['equipment_id']} has a data gap and no logged alarm; confidence is capped at LOW.")

            supports = [item for item in supports if item in valid_evidence_ids]
            contradicts = [item for item in contradicts if item in valid_evidence_ids]
            hypotheses.append(Hypothesis(
                rank=rank,
                cause_equipment_id=row["equipment_id"],
                cause_description=self._description(row["equipment_id"], row["node_type"]),
                score=row["score"],
                confidence=confidence,
                confidence_value=row["score"],
                score_breakdown={key: row[key] for key in (
                    "coverage", "own_alarm_strength", "temporal_precedence", "pattern_affinity",
                    "telemetry_corroboration", "repetition_history", "contradiction_penalty",
                )},
                supports=supports,
                contradicts=contradicts,
                unexplained=unexplained,
                would_confirm=self._checks(row["equipment_id"], row["node_type"], confirm=True),
                would_rule_out=self._checks(row["equipment_id"], row["node_type"], confirm=False),
                next_checks=self._checks(row["equipment_id"], row["node_type"], confirm=True),
            ))

        data_gaps = sorted({
            item.evidence_id for item in evidence if item.type is EvidenceType.DATA_GAP
        })
        return Analysis(
            incident_id=incident.incident_id,
            as_of=as_of,
            status=status,
            hypotheses=hypotheses,
            abstain_reasons=sorted(set(abstain_reasons)),
            data_gaps=data_gaps,
        )

    def _candidates(self, equipment_ids: list[str]) -> set[str]:
        candidates = set(equipment_ids)
        queue = deque((equipment, 0) for equipment in equipment_ids)
        seen = set(equipment_ids)
        while queue:
            equipment, depth = queue.popleft()
            if depth >= 3:
                continue
            for parent in sorted(self.topology._parents.get(equipment, ())):
                if parent not in seen:
                    candidates.add(parent)
                    seen.add(parent)
                    queue.append((parent, depth + 1))
        return candidates

    def _downstream(self, equipment_id: str, *, max_depth: int) -> set[str]:
        result: set[str] = set()
        queue = deque([(equipment_id, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for child in sorted(self.topology._children.get(node, ())):
                if child not in result:
                    result.add(child)
                    queue.append((child, depth + 1))
        return result

    def _descendant_groups(self, candidate: str) -> set[str]:
        descendants = self.topology.descendants(candidate)
        return {
            str(self.topology.nodes[node].get("type", "unknown"))
            for node in descendants if node in self.topology.nodes
        }

    def _healthy_descendant_nodes(self, candidate: str, evidence: list[Evidence]) -> set[str]:
        descendants = self.topology.descendants(candidate)
        return {
            node
            for item in evidence if item.type is EvidenceType.ABSENCE
            for node in item.attributes.get("healthy_equipment", [])
            if node in descendants
        }

    def _stance(self, row: dict, evidence: list[Evidence], event_lookup: dict[str, Evidence]) -> tuple[list[str], list[str]]:
        candidate = row["equipment_id"]
        candidate_type = row["node_type"]
        supports, contradicts = [], []
        for item in evidence:
            if item.type is EvidenceType.ABSENCE:
                if any(node in self.topology.descendants(candidate) for node in item.attributes.get("healthy_equipment", [])):
                    contradicts.append(item.evidence_id)
                continue
            if item.equipment_id == candidate and item.type in {EvidenceType.EVENT, EvidenceType.TELEMETRY_ANOMALY, EvidenceType.HISTORY, EvidenceType.TICKET}:
                supports.append(item.evidence_id)
                continue
            if item.type is EvidenceType.EVENT:
                code = item.attributes.get("code")
                if candidate_type in FAILURE_PATTERNS.get(code, {}).get("node_types", []):
                    supports.append(item.evidence_id)
        if row["affinity_hits"]:
            supports.extend(
                item.evidence_id for event in row["affinity_hits"]
                if (item := event_lookup.get(event.event_id)) is not None
            )
        return sorted(set(supports)), sorted(set(contradicts))

    @staticmethod
    def _description(equipment_id: str, node_type: str) -> str:
        names = {
            "ups": "uninterruptible power supply",
            "lv_panel": "low-voltage panel",
            "traction_substation": "traction substation",
            "zone_controller": "CBTC zone controller",
            "train_door": "train door assembly",
            "train_control_mgmt": "train control management system",
        }
        return f"{names.get(node_type, node_type.replace('_', ' '))} {equipment_id}"

    @staticmethod
    def _checks(equipment_id: str, node_type: str, *, confirm: bool) -> list[str]:
        checks = {
            "ups": (
                f"Check {equipment_id} output voltage and battery_pct across the incident window.",
                f"Verify whether downstream PSD power faults clear when {equipment_id} is on a stable supply.",
            ),
            "lv_panel": (
                f"Check {equipment_id} incomer breaker state and output voltage during the incident.",
                f"Verify whether AFC, lifts, escalators, and ventilation at the affected station were healthy.",
            ),
            "traction_substation": (
                f"Check OHE voltage and transformer alarms at {equipment_id} before the first train symptom.",
                f"Compare traction voltage readings from adjacent substations during the same interval.",
            ),
            "zone_controller": (
                f"Review {equipment_id} heartbeat and configuration logs around the incident.",
                f"Check whether ATP and PSD-train synchronization alarms persist with {equipment_id} healthy.",
            ),
            "train_door": (
                f"Inspect {equipment_id} sensor alignment and close_time_ms trend before the incident.",
                f"Repeat door cycles on {equipment_id} and compare its obstruction rate with other doors on the train.",
            ),
        }
        selected = checks.get(node_type, (
            f"Check independent telemetry and maintenance records for {equipment_id}.",
            f"Compare {equipment_id} against a known-good peer during the same period.",
        ))
        return [selected[0] if confirm else selected[1]]
