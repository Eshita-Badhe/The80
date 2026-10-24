from __future__ import annotations
import csv, io, json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend.services.data_generator import STATIONS, SCENARIOS, baseline_dataset, generate_scenario
from backend.services.processor import THRESHOLDS, process_records
from backend.services.openai_ai import AIProviderError, answer_investigation_question, configuration as openai_configuration, explain_root_cause, provider_status, verify_incident_evidence

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
MAX_UPLOAD = 5 * 1024 * 1024
app = FastAPI(title="MetroPulse AI", version="0.1.0", description="Simulated metro infrastructure incident intelligence prototype.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Invalid request data. Check message and incident fields."})

records: list[dict[str, Any]] = baseline_dataset()
processed = process_records(records)
history: list[dict] = [{"id": "ING-BASELINE", "filename": "simulated_baseline.json", "format": "JSON", "records": len(records), "accepted": len(records), "rejected": 0, "status": "ready", "created_at": datetime.now(timezone.utc).isoformat(), "simulated": True}]
simulation_playing = False
ai_requests: dict[str, list[float]] = {}

class ScenarioRequest(BaseModel):
    scenario: str = Field(default="communications")

class AIIncidentRequest(BaseModel):
    incident_id: str = Field(min_length=1, max_length=100)

class AIChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=3000)

class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    incident_id: str | None = Field(default=None, max_length=100)
    conversation_context: list[AIChatMessage] = Field(default_factory=list, max_length=8)

def ai_call(function, *args):
    try:
        return function(*args)
    except AIProviderError as exc:
        raise HTTPException(exc.status_code, detail=str(exc)) from None

def check_ai_rate_limit(request: Request):
    now = time.monotonic()
    address = request.client.host if request.client else "unknown"
    recent = [stamp for stamp in ai_requests.get(address, []) if now - stamp < 60]
    if len(recent) >= 20:
        raise HTTPException(429, detail="AI request limit reached. Please wait a minute and retry.")
    recent.append(now)
    ai_requests[address] = recent

def incident_ai_context(incident_id: str) -> dict[str, Any]:
    incident = next((item for item in processed["incidents"] if item["incident_id"].lower() == incident_id.lower()), None)
    if incident is None:
        raise HTTPException(404, detail="Incident not found in the current dataset")
    record_ids = set(incident.get("record_ids", []))
    evidence = [event for event in processed["events"] if event.get("record_id") in record_ids]
    anomalies = [item for item in processed["anomalies"] if item.get("record_id") in record_ids]
    # The deterministic engine ranks incidents; it does not currently rank causal hypotheses.
    return {
        "data_notice": "Fictional simulated or user-provided prototype data; not a live metro feed.",
        "incident": {key: incident.get(key) for key in ("incident_id", "timestamp", "station_id", "equipment_id", "equipment_category", "type", "severity", "status", "priority", "priority_score", "event_count", "explanation")},
        "source_classification_candidate": {"label": incident.get("type"), "note": "Observed event classification only; not a verified cause."},
        "anomalies": [{key: item.get(key) for key in ("anomaly_id", "record_id", "timestamp", "station_id", "equipment_id", "type", "metric", "observed_value", "threshold", "severity", "explanation")} for item in anomalies[:20]],
        "telemetry_evidence": [{key: event.get(key) for key in ("record_id", "timestamp", "station_id", "equipment_id", "equipment_category", "event_type", "severity", "metric", "value", "unit", "description", "source")} for event in evidence[:20]],
        "deterministic_diagnostic_checks": ["Review equipment maintenance history and recent work orders.", "Verify the reported sensor against an independent measurement.", "Check upstream supply and neighboring equipment telemetry."],
        "deterministic_method": "Priority score uses source severity, linked event count, and rule-based anomaly count. No deterministic root-cause ranking or independent verification engine is implemented.",
    }

def relevant_chat_context(message: str, incident_id: str | None) -> dict[str, Any]:
    match = re.search(r"(?:MP-)?INC-[A-Za-z0-9-]+", message, re.IGNORECASE)
    selected = match.group(0) if match else incident_id
    if selected:
        return {"selected_incident": incident_ai_context(selected)}
    incidents = processed["incidents"][:8]
    anomalies = sorted(processed["anomalies"], key=lambda item: item["timestamp"], reverse=True)[:12]
    event_by_id = {event["record_id"]: event for event in processed["events"]}
    return {
        "data_notice": "Fictional simulated or user-provided prototype data; not a live metro feed.",
        "dataset_summary": processed["statistics"],
        "selection_rule": "Incidents listed are the deterministic highest-priority records. Anomalies are the 12 latest by timestamp.",
        "highest_priority_incidents": [{key: item.get(key) for key in ("incident_id", "timestamp", "station_id", "equipment_id", "type", "severity", "priority", "priority_score", "status", "explanation")} for item in incidents],
        "latest_anomalies": [{**{key: item.get(key) for key in ("anomaly_id", "record_id", "timestamp", "station_id", "equipment_id", "type", "metric", "observed_value", "threshold", "severity", "explanation")}, "source_event": {key: event_by_id.get(item.get("record_id"), {}).get(key) for key in ("description", "source", "raw_log")}} for item in anomalies],
        "incident_details_available_on_request": [item["incident_id"] for item in incidents],
    }

def parse_upload(name: str, content: bytes) -> list[dict]:
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "File exceeds 5 MB limit")
    suffix = Path(name).suffix.lower()
    if suffix not in (".csv", ".json", ".txt"):
        raise HTTPException(415, "Supported formats are CSV, JSON, and TXT")
    try:
        text = content.decode("utf-8-sig")
        if suffix == ".csv":
            return list(csv.DictReader(io.StringIO(text)))
        if suffix == ".json":
            value = json.loads(text)
            return value if isinstance(value, list) else value.get("records", []) if isinstance(value, dict) else []
        rows = []
        for line in text.splitlines():
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError:
                # key=value log format, preserving the complete original line.
                import re
                fields = dict(re.findall(r"([a-zA-Z_]+)=([^\s]+)", line))
                if fields: fields["raw_log"] = line; rows.append(fields)
                else: rows.append({"raw_log": line})
        return rows
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise HTTPException(400, f"Could not parse file: {exc}") from exc

@app.get("/api/health")
def health(): return {"status": "operational", "mode": "SIMULATION MODE", "simulated": True}

@app.get("/api/config")
def configuration():
    return {
        "simulated": True,
        "network": {"stations": len(STATIONS), "station_list": STATIONS},
        "thresholds": THRESHOLDS,
        "scenarios": {
            key: {
                "equipment_category": scenario["category"],
                "event_type": scenario["event_type"],
                "severity": scenario["severity"],
                "station_id": scenario["station"],
            }
            for key, scenario in SCENARIOS.items()
        },
        "supported_simulation_controls": ["start", "pause", "reset"],
        "capabilities": {
            "verification": "unavailable",
            "root_cause": "unavailable",
            "llm_explanation": "configured" if openai_configuration()[0] else "not_configured",
        },
    }

@app.get("/api/ai/status")
def ai_status():
    return provider_status()

@app.post("/api/ai/chat")
def ai_chat(payload: AIChatRequest, request: Request):
    check_ai_rate_limit(request)
    message = payload.message.strip()
    if not message:
        raise HTTPException(422, detail="Message cannot be blank")
    context = relevant_chat_context(message, payload.incident_id)
    history_items = [{"role": item.role, "content": item.content.strip()} for item in payload.conversation_context if item.content.strip()]
    answer = ai_call(answer_investigation_question, message, context, history_items)
    selected_incident = context.get("selected_incident", {}).get("incident", {}).get("incident_id")
    return {"answer": answer, "incident_id": selected_incident or payload.incident_id, "simulated": True, "provider": "OpenAI"}

@app.post("/api/ai/explain")
def ai_explain(payload: AIIncidentRequest, request: Request):
    check_ai_rate_limit(request)
    context = incident_ai_context(payload.incident_id)
    explanation = ai_call(explain_root_cause, context)
    return {"incident_id": context["incident"]["incident_id"], "explanation": explanation, "advisory": True, "simulated": True}

@app.post("/api/ai/verify")
def ai_verify(payload: AIIncidentRequest, request: Request):
    check_ai_rate_limit(request)
    context = incident_ai_context(payload.incident_id)
    result = ai_call(verify_incident_evidence, context)
    return {"incident_id": context["incident"]["incident_id"], "verification": result, "advisory": True, "simulated": True}

@app.get("/api/dashboard")
def dashboard():
    stats = {
        **processed["statistics"],
        "high_priority_incidents": sum(1 for incident in processed["incidents"] if incident["priority"] == "high"),
        "equipment_affected": len({incident["equipment_id"] for incident in processed["incidents"]}),
    }
    incidents = processed["incidents"]
    count_by_station = {s["station_id"]: 0 for s in STATIONS}
    for i in incidents:
        if i["status"] == "open": count_by_station[i["station_id"]] = count_by_station.get(i["station_id"], 0) + 1
    severity = {k: sum(1 for i in incidents if i["severity"] == k) for k in ("critical", "high", "medium", "low", "normal")}
    categories = {}
    for i in incidents: categories[i["equipment_category"]] = categories.get(i["equipment_category"], 0) + 1
    by_hour = {}
    for e in processed["events"]:
        h=e["timestamp"][:13]
        by_hour[h]=by_hour.get(h,0)+1
    recent = sorted(processed["events"], key=lambda x:x["timestamp"], reverse=True)[:10]
    return {"mode": "SIMULATION MODE", "simulated": True, "timestamp": datetime.now(timezone.utc).isoformat(), "statistics": stats, "stations": STATIONS, "station_incidents": count_by_station, "severity_distribution": severity, "category_distribution": categories, "events_by_hour": [{"hour": k, "events": v} for k,v in sorted(by_hour.items())[-12:]], "recent_events": recent, "incidents": incidents[:50], "anomalies": processed["anomalies"][:50], "playing": simulation_playing}

@app.get("/api/incidents")
def get_incidents(q: str = "", station: str = "", severity: str = "", limit: int = 200):
    result = processed["incidents"]
    if q:
        q=q.lower(); result=[i for i in result if q in str(i).lower()]
    if station: result=[i for i in result if i["station_id"] == station]
    if severity: result=[i for i in result if i["severity"] == severity.lower() or i["priority"] == severity.lower()]
    return {"incidents": result[:max(1,min(limit,500))], "total": len(result), "simulated": True}

@app.get("/api/anomalies")
def get_anomalies():
    events_by_id = {event["record_id"]: event for event in processed["events"]}
    findings = []
    for anomaly in processed["anomalies"]:
        event = events_by_id.get(anomaly["record_id"], {})
        findings.append({
            **anomaly,
            "source": event.get("source", "unknown"),
            "raw_log": event.get("raw_log"),
            "event_description": event.get("description"),
        })
    return {"anomalies": findings, "total": len(findings), "simulated": True}

@app.get("/api/processing/summary")
def summary(): return {**processed["statistics"], "processed_at": datetime.now(timezone.utc).isoformat(), "simulated": True}

@app.post("/api/processing/run")
def run_processing():
    global processed
    processed=process_records(records)
    return summary()

@app.get("/api/ingestion/history")
def ingestion_history(): return {"history": list(reversed(history)), "simulated": True}

@app.get("/api/ingestion/preview")
def preview(): return {"records": records[:20], "total": len(records), "simulated": True}

@app.post("/api/ingestion/upload")
async def upload(file: UploadFile = File(...)):
    global records, processed
    content = await file.read(MAX_UPLOAD + 1)
    parsed = parse_upload(file.filename or "upload.txt", content)
    if not parsed: raise HTTPException(400, "No records found in file")
    # Preserve safe upload rows; processor reports row-level quality issues.
    checked = process_records(parsed)
    accepted = checked["events"]
    if not accepted: raise HTTPException(422, "No valid records. Include timestamp, station_id, and equipment_id fields.")
    records.extend(accepted)
    processed=process_records(records)
    entry={"id": f"ING-{len(history)+1:04d}", "filename": file.filename, "format": Path(file.filename or "").suffix[1:].upper(), "records": len(parsed), "accepted": len(accepted), "rejected": len(parsed)-len(accepted), "status": "ready", "created_at": datetime.now(timezone.utc).isoformat(), "simulated": False}
    history.append(entry)
    return {**entry, "preview": accepted[:20], "issues": checked["statistics"]["issues"]}

@app.post("/api/simulation/generate")
def generate(request: ScenarioRequest):
    global records, processed
    try: new = generate_scenario(request.scenario)
    except ValueError as exc: raise HTTPException(400, f"Unknown scenario. Choose: {', '.join(SCENARIOS)}") from exc
    records.extend(new); processed=process_records(records)
    history.append({"id": f"ING-{len(history)+1:04d}", "filename": f"scenario_{request.scenario}.json", "format": "SIMULATION", "records": len(new), "accepted": len(new), "rejected": 0, "status": "ready", "created_at": datetime.now(timezone.utc).isoformat(), "simulated": True})
    return {"scenario": request.scenario, "records_added": len(new), "incident_id": new[0].get("incident_id"), "simulated": True, "dashboard": dashboard()}

@app.post("/api/simulation/control")
def control(action: str):
    global simulation_playing, records, processed, history
    if action == "start": simulation_playing=True
    elif action == "pause": simulation_playing=False
    elif action == "reset":
        records=baseline_dataset(); processed=process_records(records); simulation_playing=False
        history=[{"id": "ING-BASELINE", "filename": "simulated_baseline.json", "format": "JSON", "records": len(records), "accepted": len(records), "rejected": 0, "status": "ready", "created_at": datetime.now(timezone.utc).isoformat(), "simulated": True}]
    else: raise HTTPException(400,"action must be start, pause, or reset")
    return {"playing": simulation_playing,"action":action,"simulated":True}

@app.post("/api/simulation/tick")
def simulation_tick():
    global records, processed
    if not simulation_playing:
        return {"playing": False, "records_added": 0, "simulated": True}
    # Playback advances the demo with nominal telemetry; failures remain user-triggered.
    from backend.services.data_generator import generate_records
    batch = generate_records(3, seed=len(records) + 80, start=datetime.now(timezone.utc))
    records.extend(batch)
    processed = process_records(records)
    return {"playing": True, "records_added": len(batch), "simulated": True}

@app.get("/api/incidents/{incident_id}")
def incident_detail(incident_id: str):
    match=next((i for i in processed["incidents"] if i["incident_id"]==incident_id),None)
    if not match: raise HTTPException(404,"Incident not found")
    supporting=[e for e in processed["events"] if e["record_id"] in match["record_ids"]]
    findings=[a for a in processed["anomalies"] if a["anomaly_id"] in match["anomaly_ids"]]
    return {"incident":match,"evidence":supporting,"anomalies":findings,"diagnostic_checks":["Review the equipment maintenance history and recent work orders.","Verify the reported sensor against an independent measurement.","Check upstream supply and neighboring equipment telemetry."],"note":"Evidence is observed simulated telemetry; diagnostic checks are suggestions. Root cause is not inferred."}

@app.get("/api/ingestion/export/{format}")
def export_data(format: str):
    if format == "json": return {"records": records, "simulated": True}
    if format == "csv":
        out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=list(records[0].keys())); writer.writeheader(); writer.writerows(records)
        return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=metropulse-simulated.csv"})
    raise HTTPException(400,"format must be csv or json")

FRONTEND = ROOT / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
