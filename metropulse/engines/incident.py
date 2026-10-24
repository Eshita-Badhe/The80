from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Iterable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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
        ticket_list = list(tickets)
        seeds = self._seeds(ordered)
        clusters = self._cluster(seeds)
        clusters = [self._attach_symptoms(cluster, ordered) for cluster in clusters]
        clusters = [cluster for cluster in clusters if self._is_incident_cluster(cluster)]
        incidents = [self._make_incident(index, cluster, ticket_list) for index, cluster in enumerate(clusters, 1)]
        self._set_recurrence(incidents, ordered)
        return sorted(incidents, key=lambda item: (-item.priority_score, item.incident_id))

    def _seeds(self, events: list[Event]) -> list[Event]:
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
            or (
                event.event_id in burst_ids
                and (event.code not in NOISE_CODES or (event.code == "TCM802" and event.equipment_id.startswith("TR")))
            )
        ]

    @staticmethod
    def _is_incident_cluster(cluster: list[Event]) -> bool:
        """Discard isolated major alarms and retain clusters with a clear incident signature."""
        code_counts = Counter(event.code for event in cluster)
        equipment_code_counts = Counter((event.equipment_id, event.code) for event in cluster)
        root_signature = any(ALARM_CODES.get(event.code, {}).get("role") == "root" for event in cluster)
        if root_signature and len(cluster) >= 3:
            return True

        # Door sensor failures are a repeated single-equipment pattern. TCM802 is
        # normally noise, so only a sustained burst plus headway symptoms qualifies.
        door_burst = any(
            equipment.startswith("TR") and code == "TCM802" and count >= 4
            for (equipment, code), count in equipment_code_counts.items()
        )
        if door_burst and code_counts["HDW301"] >= 2:
            return True

        # RTU loss can hide the UPS's own alarm. A station-wide PSD power burst
        # plus a nearby RTU alarm is a distinct, useful data-gap signature.
        psd_power_equipment = {
            event.equipment_id for event in cluster
            if event.code == "PSD405" and event.equipment_id.startswith("PSD-")
        }
        if code_counts["PSD405"] >= 4 and len(psd_power_equipment) >= 3 and code_counts["RTU001"]:
            return True
        return False

    def _can_link(self, left: Event, right: Event) -> bool:
        delta = abs((left.ts - right.ts).total_seconds())
        if delta > (1800 if left.equipment_id == right.equipment_id else 600):
            return False
        share_station = bool(left.station_code and left.station_code == right.station_code)
        train_equipment = left.equipment_id.startswith("TR") and right.equipment_id.startswith("TR")
        if share_station and not train_equipment:
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
        incident_equipment = {event.equipment_id for event in cluster}
        upstream = {
            ancestor
            for equipment in incident_equipment
            for ancestor in self.topology.ancestors_within(equipment, max_depth=3)
        }
        door_equipment = {
            event.equipment_id for event in cluster
            if event.code == "TCM802" and event.equipment_id.startswith("TR")
        }
        for event in events:
            if event.event_id in members:
                continue
            # Routine background codes never hitchhike on a nearby incident.
            if event.code in NOISE_CODES and not (
                event.code == "TCM802" and event.equipment_id in door_equipment
            ):
                continue
            nearby = (
                start - timedelta(minutes=30) <= event.ts <= end + timedelta(minutes=30)
                and any(self._can_link(event, root) for root in cluster)
            )
            is_upstream_precursor = (
                event.equipment_id in upstream
                and ALARM_CODES.get(event.code, {}).get("role") == "precursor"
                and start - timedelta(minutes=90) <= event.ts < start
            )
            is_door_drift = (
                event.code == "TCM804" and event.equipment_id in door_equipment
                and start - timedelta(minutes=200) <= event.ts < start
            )
            if nearby or is_upstream_precursor or is_door_drift:
                members.add(event.event_id)
        return [event for event in events if event.event_id in members]

    def _ticket_groups(self, incident: Incident, tickets: list[Ticket]) -> list[list[str]]:
        relevant = [
            ticket for ticket in tickets
            if ticket.created_at <= incident.end + timedelta(minutes=60)
            and ticket.created_at >= incident.start - timedelta(minutes=60)
            and (ticket.equipment_id in incident.equipment_ids or ticket.station_code in incident.station_codes)
        ]
        ordered = sorted(relevant, key=lambda item: item.ticket_id)
        if len(ordered) < 2:
            return []
        try:
            matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5)).fit_transform(
                [ticket.text.casefold() for ticket in ordered]
            )
            similarities = cosine_similarity(matrix)
        except ValueError:
            return []
        parent = list(range(len(ordered)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for left in range(len(ordered)):
            for right in range(left + 1, len(ordered)):
                first, second = ordered[left], ordered[right]
                same_asset = first.equipment_id == second.equipment_id
                same_station = bool(first.station_code and first.station_code == second.station_code)
                close_in_time = abs((first.created_at - second.created_at).total_seconds()) <= 3600
                if (same_asset or same_station) and close_in_time and similarities[left, right] >= 0.30:
                    root_left, root_right = find(left), find(right)
                    if root_left != root_right:
                        parent[root_right] = root_left
        groups: dict[int, list[str]] = defaultdict(list)
        for index, ticket in enumerate(ordered):
            groups[find(index)].append(ticket.ticket_id)
        return sorted((group for group in groups.values() if len(group) > 1), key=lambda group: group[0])

    def _make_incident(self, number: int, cluster: list[Event], tickets: list[Ticket]) -> Incident:
        start, end = min(event.ts for event in cluster), max(event.ts for event in cluster)
        equipment = sorted({event.equipment_id for event in cluster})
        stations = sorted({event.station_code for event in cluster if event.station_code})
        systems = sorted({event.source.value for event in cluster})
        max_severity = max(SEVERITY_WEIGHT[event.severity] for event in cluster)
        underground = sum(1 for station in stations if self.topology.stations.get(station, {}).get("underground", False))
        peak = sum(1 for event in cluster if event.ts.hour in {7, 8, 9, 17, 18, 19})
        p1 = sum(1 for ticket in tickets if ticket.priority == "P1" and (ticket.equipment_id in equipment or ticket.station_code in stations))
        factors = {
            "max_severity": max_severity * 12.0,
            "systems": min(15.0, len(systems) * 5.0),
            "stations": min(10.0, len(stations) * 3.0),
            "underground": 8.0 if underground else 0.0,
            "peak_hour": 4.0 if peak else 0.0,
            "p1_ticket": 10.0 if p1 else 0.0,
            "recurrence": 0.0,
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

    def _set_recurrence(self, incidents: list[Incident], events: list[Event]) -> None:
        seen: dict[str, list[Incident]] = defaultdict(list)
        event_lookup = {event.event_id: event for event in events}
        for incident in sorted(incidents, key=lambda item: (item.start, item.incident_id)):
            counts = Counter(
                event_lookup[event_id].equipment_id
                for event_id in incident.member_event_ids
                if event_id in event_lookup
            )
            dominant = min(counts, key=lambda equipment: (-counts[equipment], equipment)) if counts else ""
            prior = [item.incident_id for item in seen[dominant]]
            incident.recurrence = {"prior_incident_ids": prior, "count": len(prior)}
            incident.priority_factors["recurrence"] = min(8.0, len(prior) * 4.0)
            incident.priority_score = round(min(100.0, sum(incident.priority_factors.values())), 3)
            if dominant:
                seen[dominant].append(incident)

