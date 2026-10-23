"""Deterministic fictional metro data for demonstrations."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

STATIONS = [
    {"station_id": "MP-01", "name": "Riverfront", "line": "Aqua", "line_color": "#36d6c0"},
    {"station_id": "MP-02", "name": "Civic Square", "line": "Aqua", "line_color": "#36d6c0"},
    {"station_id": "MP-03", "name": "Old Town", "line": "Aqua", "line_color": "#36d6c0"},
    {"station_id": "MP-04", "name": "Central Exchange", "line": "Aqua / Coral", "line_color": "#f08772"},
    {"station_id": "MP-05", "name": "University Park", "line": "Aqua", "line_color": "#36d6c0"},
    {"station_id": "MP-06", "name": "East Market", "line": "Aqua", "line_color": "#36d6c0"},
    {"station_id": "MP-07", "name": "Tech District", "line": "Coral", "line_color": "#f08772"},
    {"station_id": "MP-08", "name": "Hillview", "line": "Coral", "line_color": "#f08772"},
    {"station_id": "MP-09", "name": "Garden Gate", "line": "Coral", "line_color": "#f08772"},
]
CATEGORIES = ["Escalator", "Lift", "Signaling", "Power", "Platform Screen Door", "Communications", "HVAC"]
SCENARIOS = {
    "communications": {"category": "Communications", "event_type": "COMM_TIMEOUT", "severity": "critical", "value": 920, "metric": "latency_ms", "station": "MP-04", "description": "Backbone communication timeout"},
    "power": {"category": "Power", "event_type": "VOLTAGE_SAG", "severity": "high", "value": 356, "metric": "voltage_v", "station": "MP-02", "description": "Traction supply voltage fluctuation"},
    "escalator": {"category": "Escalator", "event_type": "MOTOR_TEMP_HIGH", "severity": "high", "value": 94, "metric": "temperature_c", "station": "MP-06", "description": "Escalator drive motor overheating"},
    "sensor": {"category": "Lift", "event_type": "SENSOR_DRIFT", "severity": "medium", "value": 18, "metric": "vibration_mm_s", "station": "MP-03", "description": "Lift vibration sensor reading outside baseline"},
    "signaling": {"category": "Signaling", "event_type": "SIGNAL_ASPECT_MISMATCH", "severity": "critical", "value": 1, "metric": "error_count", "station": "MP-04", "description": "Signal aspect feedback mismatch"},
    "hvac": {"category": "HVAC", "event_type": "TEMP_HIGH", "severity": "medium", "value": 36, "metric": "temperature_c", "station": "MP-08", "description": "Concourse temperature above comfort threshold"},
    "cascade": {"category": "Power", "event_type": "VOLTAGE_SAG", "severity": "critical", "value": 350, "metric": "voltage_v", "station": "MP-04", "description": "Power instability with correlated signaling and communications warnings"},
}

def generate_records(count: int = 720, seed: int = 80, start: datetime | None = None) -> list[dict]:
    rng = random.Random(seed)
    start = start or datetime.now(timezone.utc) - timedelta(hours=12)
    rows = []
    for i in range(count):
        station = rng.choice(STATIONS)
        category = rng.choice(CATEGORIES)
        metric, value = {
            "Escalator": ("temperature_c", round(rng.gauss(48, 5), 1)),
            "Lift": ("vibration_mm_s", round(abs(rng.gauss(2.2, 0.8)), 2)),
            "Signaling": ("error_count", max(0, int(rng.gauss(0.1, 0.4)))),
            "Power": ("voltage_v", round(rng.gauss(400, 5), 1)),
            "Platform Screen Door": ("current_a", round(rng.gauss(1.8, 0.3), 2)),
            "Communications": ("latency_ms", max(2, round(rng.gauss(32, 10), 1))),
            "HVAC": ("temperature_c", round(rng.gauss(23, 2), 1)),
        }[category]
        ts = start + timedelta(seconds=i * 60 + rng.randint(0, 35))
        rows.append({"record_id": f"EV-{i+1:05d}", "timestamp": ts.isoformat(), "station_id": station["station_id"], "equipment_id": f"{station['station_id']}-{category[:3].upper()}-{rng.randint(1, 3):02d}", "equipment_category": category, "event_type": "HEARTBEAT", "severity": "normal", "status": "healthy", "metric": metric, "value": value, "unit": {"temperature_c": "°C", "vibration_mm_s": "mm/s", "voltage_v": "V", "current_a": "A", "latency_ms": "ms", "error_count": "count"}[metric], "incident_id": None, "description": f"Routine {category.lower()} telemetry received", "source": "simulated", "raw_log": f"[{ts.isoformat()}] {station['station_id']} {category} {metric}={value} routine heartbeat"})
    return rows

def generate_scenario(scenario: str, seed: int | None = None) -> list[dict]:
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    spec = SCENARIOS[scenario]
    rng = random.Random(seed if seed is not None else random.randrange(1, 10**9))
    now = datetime.now(timezone.utc)
    incident_id = f"INC-{now:%y%m%d-%H%M%S}-{rng.randint(10,99)}"
    stations = [spec["station"]]
    if scenario == "cascade":
        stations = ["MP-04", "MP-04", "MP-05"]
    result = []
    for index, station_id in enumerate(stations):
        t = now + timedelta(minutes=index)
        active_spec = dict(spec)
        if scenario == "cascade" and index:
            active_spec.update({"category": "Signaling" if index == 1 else "Communications", "event_type": "INTERLOCK_WARNING" if index == 1 else "COMM_TIMEOUT", "metric": "error_count" if index == 1 else "latency_ms", "value": 2 if index == 1 else 680, "description": "Correlated downstream warning during power instability"})
        station = next(s for s in STATIONS if s["station_id"] == station_id)
        result.append({"record_id": f"EV-SIM-{incident_id[-8:]}-{index+1}", "timestamp": t.isoformat(), "station_id": station_id, "equipment_id": f"{station_id}-{active_spec['category'][:3].upper()}-{index+1:02d}", "equipment_category": active_spec["category"], "event_type": active_spec["event_type"], "severity": active_spec["severity"], "status": "degraded" if active_spec["severity"] != "critical" else "critical", "metric": active_spec["metric"], "value": active_spec["value"], "unit": "ms" if active_spec["metric"] == "latency_ms" else "V" if active_spec["metric"] == "voltage_v" else "°C" if active_spec["metric"] == "temperature_c" else "count", "incident_id": incident_id, "description": active_spec["description"], "source": "simulated", "raw_log": f"[{t.isoformat()}] {station_id} {active_spec['event_type']} {active_spec['metric']}={active_spec['value']}"})
    return result

def baseline_dataset() -> list[dict]:
    rows = generate_records(720, seed=80)
    # Stable seeded incidents make the first load useful and reproducible.
    for key in ("communications", "power", "escalator", "sensor", "signaling", "hvac", "cascade"):
        rows.extend(generate_scenario(key, seed=80 + len(rows)))
    return rows
