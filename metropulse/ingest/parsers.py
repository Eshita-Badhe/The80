from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from ..knowledge_base import ALARM_CODES
from ..schemas import Event, Severity, Source, Ticket, TelemetryPoint
from ..topology import Topology

IST = ZoneInfo("Asia/Kolkata")
REJECT = dict[str, Any]


def _timestamp(value: str, *, naive_is_ist: bool = False) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        parsed = datetime.strptime(cleaned, "%d/%m/%Y %H:%M:%S")
    if parsed.tzinfo is None:
        if not naive_is_ist:
            raise ValueError("timestamp is missing timezone")
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _severity(code: str, supplied: str | None = None) -> Severity:
    value = ALARM_CODES.get(code, {}).get("severity")
    if value is None:
        value = {"CRITICAL": "CRITICAL", "ERR": "MAJOR", "ERROR": "MAJOR", "WARN": "WARN"}.get((supplied or "").upper(), "MINOR")
    return Severity(value)


def _event(
    event_id: str,
    ts: datetime,
    source: Source,
    equipment_id: str,
    station_code: str | None,
    train_id: str | None,
    code: str,
    message: str,
    raw: dict[str, Any],
    supplied_severity: str | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        ts=ts,
        source=source,
        equipment_id=equipment_id,
        station_code=station_code,
        train_id=train_id,
        code=code,
        severity=_severity(code, supplied_severity),
        message=message,
        extra={"supplied_severity": supplied_severity} if supplied_severity else {},
        raw=raw,
    )


def _result(parser: Callable[[], list[Event]], rejects: list[REJECT]) -> tuple[list[Event], list[REJECT]]:
    try:
        return parser(), rejects
    except (KeyError, TypeError, ValueError) as exc:
        rejects.append({"reason": str(exc)})
        return [], rejects


def parse_scada(path: str | Path, topology: Topology) -> tuple[list[Event], list[REJECT]]:
    events, rejects = [], []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            try:
                station = topology.station_code(row["location"]) if row["location"].strip() else None
                if row["location"].strip() and station is None:
                    raise ValueError(f"unknown station name: {row['location']}")
                events.append(_event(row["rec_id"], _timestamp(row["ts"], naive_is_ist=True), Source.SCADA, row["point"], station, None, row["code"], row["text"], row, row.get("prio")))
            except (KeyError, ValueError) as exc:
                rejects.append({"line": line_number, "reason": str(exc), "raw": row})
    return events, rejects


def parse_cbtc(path: str | Path, topology: Topology) -> tuple[list[Event], list[REJECT]]:
    events, rejects = [], []
    for index, row in enumerate(json.loads(Path(path).read_text(encoding="utf-8")), 1):
        try:
            station = row.get("stn") or None
            if station is not None and topology.station_code(station) is None:
                raise ValueError(f"unknown station code: {station}")
            events.append(_event(row["id"], _timestamp(row["time"]), Source.CBTC, row["node"], station, None, row["alarm"], row["description"], row, row.get("level")))
        except (KeyError, ValueError) as exc:
            rejects.append({"row": index, "reason": str(exc), "raw": row})
    return events, rejects


def parse_tcms(path: str | Path, topology: Topology | None = None) -> tuple[list[Event], list[REJECT]]:
    events, rejects = [], []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            parts = [item.strip() for item in line.split("|")]
            if len(parts) != 8:
                raise ValueError("expected 8 pipe-delimited fields")
            ts, train, _car, door, level, code, message, event_id = parts
            location = re.search(r"\bloc=([A-Za-z0-9_-]+)", message)
            station = location.group(1) if location else None
            equipment = f"{train}-{door}" if door != "-" else f"{train}-TCMS"
            events.append(_event(event_id, _timestamp(ts, naive_is_ist=True), Source.TCMS, equipment, station, train, code, message, {"line": line, "fields": parts}, level))
        except (ValueError, IndexError) as exc:
            rejects.append({"line": line_number, "reason": str(exc), "raw": line})
    return events, rejects


def parse_afc(path: str | Path, topology: Topology | None = None) -> tuple[list[Event], list[REJECT]]:
    events, rejects = [], []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            try:
                station = row["station_code"].strip()
                if topology is not None and topology.station_code(station) is None:
                    raise ValueError(f"unknown station code: {station}")
                equipment = f"AFC-{station}-{row['gate_id'].strip()}"
                events.append(_event(row["event_id"], _timestamp(row["datetime"], naive_is_ist=True), Source.AFC, equipment, station, None, row["error_code"], row["message"], row, row.get("severity")))
            except (KeyError, ValueError) as exc:
                rejects.append({"line": line_number, "reason": str(exc), "raw": row})
    return events, rejects


def parse_tickets(path: str | Path) -> tuple[list[Ticket], list[REJECT]]:
    tickets, rejects = [], []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            try:
                closed = row.get("closed_at", "").strip()
                tickets.append(Ticket(ticket_id=row["ticket_id"], created_at=_timestamp(row["created_at"], naive_is_ist=True), closed_at=_timestamp(closed, naive_is_ist=True) if closed else None, equipment_id=row["equipment_id"], station_code=row["station"] or None, text=row["reported_issue"], priority=row["priority"], team=row["assigned_team"], resolution=row["resolution_notes"] or None))
            except (KeyError, ValueError) as exc:
                rejects.append({"line": line_number, "reason": str(exc), "raw": row})
    return tickets, rejects


def parse_telemetry(path: str | Path) -> tuple[list[TelemetryPoint], list[REJECT]]:
    points, rejects = [], []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            try:
                points.append(TelemetryPoint(equipment_id=row["equipment_id"], metric=row["metric"], ts=_timestamp(row["timestamp"], naive_is_ist=True), value=float(row["value"]), unit=row["unit"]))
            except (KeyError, ValueError) as exc:
                rejects.append({"line": line_number, "reason": str(exc), "raw": row})
    return points, rejects
