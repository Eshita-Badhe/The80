from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Iterable

from ..knowledge_base import ALARM_CODES, NOISE_CODES
from ..schemas import Event, Incident, Severity, Ticket
from ..topology import Topology


SEVERITY_WEIGHT = {
    Severity.WARN: 1,
    Severity.MINOR: 2,
    Severity.MAJOR: 3,
    Severity.CRITICAL: 4,
}


class IncidentEngine:
    def __init__(self, topology: Topology):
        self.topology = topology

    def detect(self, events: Iterable[Event], tickets: Iterable[Ticket] = ()) -> list[Incident]:
        ordered = sorted(events, key=lambda event: (event.ts, event.event_id))
        if not ordered:
            return []
        baseline = Counter((event.code, event.equipment_id) for event in ordered)
        seeds = self._seeds(ordered, baseline)
        clusters = self._cluster(seeds)
        clusters = [self._attach_symptoms(cluster, ordered) for cluster in clusters]
        incidents = [self._make_incident(index, cluster, list(tickets), baseline) for index, cluster in enumerate(clusters, 1)]
        self._set_recurrence(incidents)
        return sorted(incidents, key=lambda item: (-item.priority_score, item.incident_id))

    def _seeds(self, events: list[Event], baseline: Counter) -> list[Event]:
        by_pair: dict[tuple[str, str], list[Event]] = defaultdict(list)
        for event in events:
            by_pair[(event.code, event.equipment_id)].append(event)
        burst_ids = {
            event.event_id
            for group in by_pair.values()
            for event in group
            if sum(abs((event.ts - other.ts).total_seconds()) <= 3600 for other in group) >= 3
        }
        return [
            event
            for event in events
            if event.severity in {Severity.MAJOR, Severity.CRITICAL}
            or event.event_id in burst_ids
            or (event.code not in NOISE_CODES and baseline[(event.code, event.equipment_id)] >= 2)
        ]

    def _can_link(self, left: Event, right: Event) -> bool:
        delta = abs((left.ts - right.ts).total_seconds())
        if delta > (1800 if left.equipment_id == right.equipment_id else 600):
            return False
        if left.station_code and left.station_code == right.station_code:
            return True
        return self.topology.distance(left.equipment_id, right.equipment_id, max_hops=3) is not None

    def _cluster(self, seeds: list[Event]) -> list[list[Event]]:
        parent = list(range(len(seeds)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for index, event in enumerate(seeds):
            for other_index in range(index):
                if self._can_link(event, seeds[other_index]):
                    union(index, other_index)
        groups: dict[int, list[Event]] = defaultdict(list)
        for index, event in enumerate(seeds):
            groups[find(index)].append(event)
        return sorted(groups.values(), key=lambda group: (min(item.ts for item in group), min(item.event_id for item in group)))

    def _attach_symptoms(self, cluster: list[Event], events: list[Event]) -> list[Event]:
        members = {event.event_id for event in cluster}
        start = min(event.ts for event in cluster)
        end = max(event.ts for event in cluster)
        for event in events:
            if event.event_id in members or event.severity not in {Severity.MINOR, Severity.WARN}:
                continue
            if start - timedelta(minutes=10) <= event.ts <= end + timedelta(minutes=10) and any(self._can_link(event, root) for root in cluster):
                members.add(event.event_id)
        return [event for event in events if event.event_id in members]

    def _ticket_groups(self, incident: Incident, tickets: list[Ticket]) -> list[list[str]]:
        relevant = [
            ticket for ticket in tickets
            if ticket.created_at <= incident.end + timedelta(minutes=60)
            and ticket.created_at >= incident.start - timedelta(minutes=60)
            and (ticket.equipment_id in incident.equipment_ids or ticket.station_code in incident.station_codes)
        ]
        groups: list[list[Ticket]] = []
        for ticket in sorted(relevant, key=lambda item: item.ticket_id):
            for group in groups:
                reference = group[0]
                if SequenceMatcher(None, ticket.text.casefold(), reference.text.casefold()).ratio() >= 0.55:
                    group.append(ticket)
                    break
            else:
                groups.append([ticket])
        return [[ticket.ticket_id for ticket in group] for group in groups]

    def _make_incident(self, number: int, cluster: list[Event], tickets: list[Ticket], baseline: Counter) -> Incident:
        start, end = min(event.ts for event in cluster), max(event.ts for event in cluster)
        equipment = sorted({event.equipment_id for event in cluster})
        stations = sorted({event.station_code for event in cluster if event.station_code})
        systems = sorted({event.source.value for event in cluster})
        max_severity = max(SEVERITY_WEIGHT[event.severity] for event in cluster)
        underground = sum(1 for station in stations if self.topology.stations.get(station, {}).get("underground", False))
        peak = sum(1 for event in cluster if event.ts.hour in {7, 8, 9, 17, 18, 19})
        p1 = sum(1 for ticket in tickets if ticket.priority == "P1" and ticket.equipment_id in equipment)
        repeated = sum(1 for event in cluster if baseline[(event.code, event.equipment_id)] >= 3)
        factors = {
            "max_severity": max_severity * 12.0,
            "systems": min(15.0, len(systems) * 5.0),
            "stations": min(10.0, len(stations) * 3.0),
            "underground": 8.0 if underground else 0.0,
            "peak_hour": 4.0 if peak else 0.0,
            "p1_ticket": 10.0 if p1 else 0.0,
            "recurrence": min(8.0, repeated * 2.0),
        }
        score = round(min(100.0, sum(factors.values())), 3)
        incident = Incident(
            incident_id=f"INC-{number:03d}",
            start=start,
            end=end,
            member_event_ids=sorted(event.event_id for event in cluster),
            equipment_ids=equipment,
            station_codes=stations,
            systems=systems,
            priority_score=score,
            priority_factors=factors,
            recurrence={"prior_incident_ids": [], "count": 0},
            duplicate_ticket_groups=[],
            flags=[],
        )
        incident.duplicate_ticket_groups = self._ticket_groups(incident, tickets)
        if any(event.code in NOISE_CODES for event in cluster):
            incident.flags.append("contains_background_code")
        return incident

    def _set_recurrence(self, incidents: list[Incident]) -> None:
        seen: dict[str, list[Incident]] = defaultdict(list)
        for incident in sorted(incidents, key=lambda item: (item.start, item.incident_id)):
            dominant = incident.equipment_ids[0] if incident.equipment_ids else ""
            prior = [item.incident_id for item in seen[dominant]]
            incident.recurrence = {"prior_incident_ids": prior, "count": len(prior)}
            if dominant:
                seen[dominant].append(incident)

