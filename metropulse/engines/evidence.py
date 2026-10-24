from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable

from ..schemas import Evidence, EvidenceType, Event, Incident, TelemetryPoint, Ticket
from ..topology import Topology


class EvidenceEngine:
    def __init__(self, topology: Topology):
        self.topology = topology

    def build(
        self,
        incident: Incident,
        events: Iterable[Event],
        tickets: Iterable[Ticket],
        telemetry: Iterable[TelemetryPoint],
        *,
        as_of: datetime | None = None,
        prior_incidents: Iterable[Incident] = (),
    ) -> list[Evidence]:
        cutoff = as_of or incident.end
        members = [event for event in events if event.event_id in incident.member_event_ids and event.ts <= cutoff]
        records: list[Evidence] = []

        for event in members:
            records.append(self._evidence(incident, len(records) + 1, EvidenceType.EVENT, [event.event_id], event.ts, event.equipment_id, event.message, {"code": event.code, "severity": event.severity.value, "source": event.source.value}))
            if event.code == "RTU001":
                affected = sorted({
                    equipment
                    for member in members
                    for equipment in ({member.equipment_id} | self.topology.ancestors_within(member.equipment_id, max_depth=3))
                })
                records.append(self._evidence(
                    incident, len(records) + 1, EvidenceType.DATA_GAP, [event.event_id],
                    event.ts, event.equipment_id,
                    f"RTU communication loss may hide equipment logs for: {', '.join(affected)}.",
                    {"affected_equipment": affected, "gap_source": event.event_id},
                ))

        relevant_tickets = [
            ticket for ticket in tickets
            if ticket.created_at <= cutoff
            and ticket.created_at <= incident.end + timedelta(hours=1)
            and ticket.created_at >= incident.start - timedelta(hours=1)
            and (ticket.equipment_id in incident.equipment_ids or ticket.station_code in incident.station_codes)
        ]
        for ticket in sorted(relevant_tickets, key=lambda item: item.ticket_id):
            resolution_visible = ticket.closed_at is not None and ticket.closed_at <= cutoff
            attributes = {"priority": ticket.priority, "team": ticket.team, "text": ticket.text}
            if resolution_visible and ticket.resolution:
                attributes["resolution"] = ticket.resolution
            summary = f"Ticket {ticket.ticket_id}: {ticket.text}"
            if resolution_visible and ticket.resolution:
                summary += f" Resolution: {ticket.resolution}"
            records.append(self._evidence(incident, len(records) + 1, EvidenceType.TICKET, [ticket.ticket_id], ticket.created_at, ticket.equipment_id, summary, attributes))

        points = [point for point in telemetry if point.ts <= cutoff and point.ts >= incident.start - timedelta(hours=52) and (point.equipment_id in incident.equipment_ids or point.equipment_id in self._upstream(incident))]
        for equipment, metric_points in self._group_points(points).items():
            for metric, values in metric_points.items():
                lookback = timedelta(hours=52) if equipment in incident.equipment_ids and metric == "close_time_ms" else timedelta(minutes=90)
                anomaly = self._anomaly(values, incident.start, incident.end, lookback=lookback)
                if anomaly:
                    source_refs = [f"telemetry:{equipment}:{metric}:{anomaly['start']}:{anomaly['end']}"]
                    records.append(self._evidence(incident, len(records) + 1, EvidenceType.TELEMETRY_ANOMALY, source_refs, anomaly["start"], equipment, anomaly["summary"], anomaly))

        for prior in prior_incidents:
            shared_equipment = sorted(set(prior.equipment_ids) & set(incident.equipment_ids))
            if prior.end < incident.start and shared_equipment:
                records.append(self._evidence(incident, len(records) + 1, EvidenceType.HISTORY, [prior.incident_id], prior.end, shared_equipment[0], f"Prior incident {prior.incident_id} affected {', '.join(shared_equipment)}.", {"prior_incident_id": prior.incident_id, "shared_equipment": shared_equipment}))

        for station in incident.station_codes:
            healthy = sorted({
                event.equipment_id for event in events
                if event.station_code == station and event.ts <= cutoff and event.ts >= incident.start - timedelta(minutes=30)
                and event.equipment_id not in incident.equipment_ids
            })
            if healthy:
                records.append(self._evidence(incident, len(records) + 1, EvidenceType.ABSENCE, healthy, incident.start, None, f"Observed neighboring equipment at {station}; no matching incident alarms in the window.", {"station_code": station, "healthy_equipment": healthy}))

        for equipment in incident.equipment_ids:
            node_type = self.topology.nodes.get(equipment, {}).get("type")
            expected_metrics = {
                "ups": ("output_voltage_v", "battery_pct"),
                "traction_substation": ("ohe_voltage_kv",),
                "train_door": ("close_time_ms",),
            }.get(node_type, ())
            window_points = [
                point for point in points
                if point.equipment_id == equipment
                and incident.start - timedelta(minutes=90) <= point.ts <= min(cutoff, incident.end + timedelta(minutes=45))
            ]
            covered_metrics = {point.metric for point in window_points}
            missing = sorted(metric for metric in expected_metrics if metric not in covered_metrics)
            if missing:
                records.append(self._evidence(incident, len(records) + 1, EvidenceType.DATA_GAP, [f"telemetry-series:{equipment}:{metric}" for metric in missing], incident.start, equipment, f"Telemetry series missing for {equipment}: {', '.join(missing)}.", {"missing_metrics": missing, "affected_equipment": [equipment]}))
        return records

    def _upstream(self, incident: Incident) -> set[str]:
        return {
            ancestor for equipment in incident.equipment_ids
            for ancestor in self.topology.ancestors_within(equipment, max_depth=3)
        }

    @staticmethod
    def _group_points(points: list[TelemetryPoint]) -> dict[str, dict[str, list[TelemetryPoint]]]:
        grouped: dict[str, dict[str, list[TelemetryPoint]]] = defaultdict(lambda: defaultdict(list))
        for point in points:
            grouped[point.equipment_id][point.metric].append(point)
        return grouped

    @staticmethod
    def _anomaly(points: list[TelemetryPoint], start: datetime, end: datetime, *, lookback: timedelta = timedelta(minutes=90)) -> dict | None:
        values = [point.value for point in points]
        if len(values) < 4:
            return None
        center = median(values)
        scale = max(median([abs(value - center) for value in values]) * 1.4826, abs(center) * 0.01, 1e-9)
        abnormal = [point for point in points if abs(point.value - center) / scale >= 3]
        in_window = [point for point in abnormal if start - lookback <= point.ts <= end + timedelta(minutes=45)]
        if not in_window:
            return None
        first, last = min(in_window, key=lambda item: item.ts), max(in_window, key=lambda item: item.ts)
        return {"metric": first.metric, "start": first.ts, "end": last.ts, "baseline": center, "peak": max(in_window, key=lambda item: abs(item.value - center)).value, "summary": f"{first.metric} anomaly from {first.ts.isoformat()} to {last.ts.isoformat()}."}

    @staticmethod
    def _evidence(incident: Incident, number: int, evidence_type: EvidenceType, source_refs: list[str], ts: datetime | None, equipment_id: str | None, summary: str, attributes: dict) -> Evidence:
        return Evidence(evidence_id=f"EVD-{incident.incident_id}-{number:03d}", incident_id=incident.incident_id, type=evidence_type, source_refs=source_refs, ts=ts, equipment_id=equipment_id, summary=summary, attributes=attributes)
