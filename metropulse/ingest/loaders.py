from __future__ import annotations

from pathlib import Path
from typing import Any

from ..schemas import Event, Ticket, TelemetryPoint
from ..topology import Topology
from .parsers import parse_afc, parse_cbtc, parse_scada, parse_tcms, parse_telemetry, parse_tickets


def load_dataset(data_dir: str | Path) -> dict[str, Any]:
    root = Path(data_dir)
    topology = Topology.from_json(root / "topology.json")
    events: list[Event] = []
    rejects: list[dict[str, Any]] = []
    for parser, filename in ((parse_scada, "scada_events.csv"), (parse_cbtc, "cbtc_psd_events.json"), (parse_tcms, "tcms_events.txt"), (parse_afc, "afc_events.csv")):
        parsed, rejected = parser(root / filename, topology)
        events.extend(parsed)
        rejects.extend([{"source": filename, **item} for item in rejected])
    tickets, ticket_rejects = parse_tickets(root / "tickets.csv")
    telemetry, telemetry_rejects = parse_telemetry(root / "telemetry.csv")
    rejects.extend([{"source": "tickets.csv", **item} for item in ticket_rejects])
    rejects.extend([{"source": "telemetry.csv", **item} for item in telemetry_rejects])
    unknown = [event for event in events if not topology.has_node(event.equipment_id)]
    rejects.extend({"source": "topology.json", "event_id": event.event_id, "reason": f"unknown equipment: {event.equipment_id}"} for event in unknown)
    return {"topology": topology, "events": events, "tickets": tickets, "telemetry": telemetry, "rejects": rejects}

