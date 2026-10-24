from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Source(str, Enum):
    SCADA = "SCADA"
    CBTC = "CBTC"
    TCMS = "TCMS"
    AFC = "AFC"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    WARN = "WARN"


class EvidenceType(str, Enum):
    EVENT = "EVENT"
    TELEMETRY_ANOMALY = "TELEMETRY_ANOMALY"
    TICKET = "TICKET"
    HISTORY = "HISTORY"
    ABSENCE = "ABSENCE"
    DATA_GAP = "DATA_GAP"
    TOPOLOGY = "TOPOLOGY"


class AnalysisStatus(str, Enum):
    RANKED = "RANKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    ts: datetime
    source: Source
    equipment_id: str
    station_code: str | None = None
    train_id: str | None = None
    code: str
    severity: Severity
    message: str
    extra: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    created_at: datetime
    closed_at: datetime | None = None
    equipment_id: str
    station_code: str | None = None
    text: str
    priority: str
    team: str
    resolution: str | None = None


class TelemetryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_id: str
    metric: str
    ts: datetime
    value: float
    unit: str


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    start: datetime
    end: datetime
    member_event_ids: list[str]
    equipment_ids: list[str]
    station_codes: list[str]
    systems: list[str]
    priority_score: float
    priority_factors: dict[str, float]
    recurrence: dict[str, Any] = Field(default_factory=dict)
    duplicate_ticket_groups: list[list[str]] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    incident_id: str
    type: EvidenceType
    source_refs: list[str]
    ts: datetime | None = None
    equipment_id: str | None = None
    summary: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    cause_equipment_id: str
    cause_description: str
    score: float
    confidence: Confidence
    confidence_value: float
    score_breakdown: dict[str, float]
    supports: list[str]
    contradicts: list[str]
    unexplained: list[str]
    would_confirm: list[str]
    would_rule_out: list[str]
    next_checks: list[str]


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    as_of: datetime
    status: AnalysisStatus
    hypotheses: list[Hypothesis]
    abstain_reasons: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)

