"""Normalization, quality checks, rule anomalies, and explainable incident grouping."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
import hashlib

THRESHOLDS = {"temperature_c": 80, "vibration_mm_s": 8, "voltage_v": 380, "current_a": 4, "latency_ms": 250, "error_count": 1}
SEVERITY_RANK = {"normal": 0, "low": 1, "medium": 2, "high": 3, "critical": 4, "warning": 2, "degraded": 3}
ALIASES = {
    "timestamp": ("time", "ts", "datetime", "event_time", "created_at"),
    "station_id": ("station", "station_code", "location_id"),
    "equipment_id": ("asset_id", "device_id", "equipment", "asset"),
    "equipment_category": ("category", "equipment_type", "asset_type"),
    "event_type": ("event", "code", "error_code", "event_code"),
    "severity": ("level", "priority", "alarm_level"),
    "metric": ("sensor", "measurement", "metric_name", "sensor_type"),
    "value": ("reading", "observed_value", "measurement_value"),
}

def process_records(records: list[dict]) -> dict:
    normalized, anomalies, issues = [], [], []
    seen = set()
    for index, original in enumerate(records):
        row = dict(original)
        # Map common vendor/export column names into the internal schema, case-insensitively.
        lower_keys = {str(k).strip().lower(): k for k in row}
        for canonical, aliases in ALIASES.items():
            if row.get(canonical) in (None, ""):
                source_key = next((lower_keys[name] for name in aliases if name in lower_keys and row.get(lower_keys[name]) not in (None, "")), None)
                if source_key is not None:
                    row[canonical] = row[source_key]
        row["raw_log"] = str(original.get("raw_log") or original)
        try:
            ts = datetime.fromisoformat(str(row.get("timestamp", "")).replace("Z", "+00:00"))
            row["timestamp"] = ts.isoformat()
        except (ValueError, TypeError):
            issues.append({"row": index + 1, "issue": "Missing or invalid timestamp"})
            continue
        for field in ("station_id", "equipment_id", "event_type", "severity", "equipment_category"):
            if row.get(field) is not None:
                row[field] = str(row[field]).strip().upper() if field in ("station_id", "equipment_id", "severity", "event_type") else str(row[field]).strip().title()
        if not row.get("equipment_id") or not row.get("station_id"):
            issues.append({"row": index + 1, "issue": "Missing station or equipment ID"})
            continue
        signature = (row["timestamp"], row["equipment_id"], row.get("event_type"), str(row.get("value")))
        if signature in seen:
            issues.append({"row": index + 1, "issue": "Duplicate record"})
            continue
        seen.add(signature)
        row["record_id"] = str(row.get("record_id") or f"EV-IMP-{index+1:05d}")
        row["source"] = row.get("source") or "uploaded"
        normalized.append(row)
        metric = row.get("metric")
        try:
            value = float(row["value"])
        except (ValueError, TypeError, KeyError):
            value = None
        threshold = THRESHOLDS.get(metric)
        flagged = value is not None and threshold is not None and ((metric == "voltage_v" and (value < threshold or value > 420)) or (metric != "voltage_v" and value > threshold))
        # Explicit event codes and severity are valid evidence even if the sensor field is absent.
        explicit = str(row.get("event_type", "")).upper() not in ("HEARTBEAT", "NORMAL", "") and str(row.get("severity", "normal")).lower() != "normal"
        if flagged or explicit:
            severity = str(row.get("severity", "medium")).lower()
            anomaly_id = "AN-" + hashlib.sha1(row["record_id"].encode()).hexdigest()[:8].upper()
            expected = [threshold, 420] if metric == "voltage_v" and flagged else threshold
            anomalies.append({"anomaly_id": anomaly_id, "record_id": row["record_id"], "timestamp": row["timestamp"], "station_id": row["station_id"], "equipment_id": row["equipment_id"], "type": row.get("event_type", "THRESHOLD_EXCEEDED"), "metric": metric, "observed_value": value if value is not None else row.get("value"), "threshold": expected, "severity": severity, "explanation": f"{metric}={value} is outside configured range 380–420" if flagged and metric == "voltage_v" else f"{metric}={value} crosses configured {threshold} threshold" if flagged else f"Explicit {row.get('event_type')} event marked {severity}"})
    groups = defaultdict(list)
    # Prefer supplied incident linkage. Otherwise group tightly by the same equipment and category.
    for row in normalized:
        key = row.get("incident_id") or (row["station_id"], row["equipment_id"], row.get("equipment_category", "Unknown"), row.get("event_type", "UNKNOWN"), row["timestamp"][:13])
        groups[str(key)].append(row)
    incidents = []
    anomaly_by_record = defaultdict(list)
    for a in anomalies:
        anomaly_by_record[a["record_id"]].append(a)
    for key, rows in groups.items():
        evidence = [a for row in rows for a in anomaly_by_record.get(row["record_id"], [])]
        rank = max([SEVERITY_RANK.get(str(r.get("severity", "normal")).lower(), 0) for r in rows] + [SEVERITY_RANK.get(a["severity"], 0) for a in evidence] + [0])
        score = min(100, 18 + rank * 15 + min(20, len(rows) * 5) + min(12, len(evidence) * 4))
        priority = "critical" if score >= 80 else "high" if score >= 62 else "medium" if score >= 40 else "low"
        incident_id = str(rows[0].get("incident_id") or "INC-" + hashlib.sha1(str(key).encode()).hexdigest()[:8].upper())
        incidents.append({"incident_id": incident_id, "timestamp": min(r["timestamp"] for r in rows), "station_id": rows[0]["station_id"], "equipment_id": rows[0]["equipment_id"], "equipment_category": rows[0].get("equipment_category", "Unknown"), "type": rows[0].get("event_type", "Infrastructure event"), "severity": max((str(r.get("severity", "normal")).lower() for r in rows), key=lambda s: SEVERITY_RANK.get(s, 0)), "status": "open" if evidence or rank >= 2 else "monitoring", "priority_score": score, "priority": priority, "record_ids": [r["record_id"] for r in rows], "anomaly_ids": [a["anomaly_id"] for a in evidence], "event_count": len(rows), "explanation": f"Score {score}/100 from severity, {len(rows)} linked event(s), and {len(evidence)} rule-based anomaly finding(s). Events are grouped only by explicit incident link or matching equipment, category, and hour."})
    incidents.sort(key=lambda x: (-x["priority_score"], x["timestamp"]))
    return {"events": normalized, "anomalies": anomalies, "incidents": incidents, "statistics": {"input_records": len(records), "processed_records": len(normalized), "rejected_or_duplicate": len(records)-len(normalized), "anomalies": len(anomalies), "incidents": len(incidents), "open_incidents": sum(i["status"] == "open" for i in incidents), "critical_incidents": sum(i["priority"] == "critical" for i in incidents), "stations_affected": len({i["station_id"] for i in incidents if i["status"] == "open"}), "issues": issues}}
