"""Groq-backed advisory explanations grounded in processed MetroPulse records."""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"


class AIProviderError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def configuration() -> tuple[str | None, str]:
    return os.getenv("GROQ_API_KEY", "").strip() or None, os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def provider_status() -> dict[str, Any]:
    key, model = configuration()
    if not key:
        return {"configured": False, "available": False, "provider": "Groq", "model": model, "status": "not_configured", "message": "Add GROQ_API_KEY to the backend environment to enable AI investigation."}
    request = Request(f"{GROQ_BASE_URL}/models", headers={"Authorization": f"Bearer {key}"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        model_ids = {item.get("id") for item in payload.get("data", []) if isinstance(item, dict)}
        available = model in model_ids
        return {"configured": True, "available": available, "provider": "Groq", "model": model, "status": "online" if available else "model_unavailable", "message": "Groq is reachable and the selected model is available." if available else "The configured Groq model is not available for this key."}
    except HTTPError as error:
        if error.code == 401:
            return {"configured": True, "available": False, "provider": "Groq", "model": model, "status": "invalid_credentials", "message": "Groq rejected this API key. Create a new key and update GROQ_API_KEY."}
        if error.code == 403:
            return {"configured": True, "available": False, "provider": "Groq", "model": model, "status": "access_denied", "message": "Groq denied access for this key or model. Check the selected Groq project and model access."}
        if error.code == 429:
            return {"configured": True, "available": False, "provider": "Groq", "model": model, "status": "rate_limited", "message": "Groq rate limited the status check. Try again shortly."}
        return {"configured": True, "available": False, "provider": "Groq", "model": model, "status": "unavailable", "message": "Groq could not complete the model availability check."}
    except (URLError, TimeoutError, ValueError, OSError):
        return {"configured": True, "available": False, "provider": "Groq", "model": model, "status": "unavailable", "message": "Groq could not be reached or rejected the backend credentials."}


def _completion(messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
    key, model = configuration()
    if not key:
        raise AIProviderError("Groq AI is not configured. Add GROQ_API_KEY to the backend environment.")
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2, "max_completion_tokens": 1400}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = Request(
        f"{GROQ_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty completion")
        return content.strip()
    except HTTPError as error:
        if error.code == 429:
            raise AIProviderError("Groq is rate limited right now. Wait a moment and retry.", 503) from None
        if error.code == 401:
            raise AIProviderError("Groq rejected GROQ_API_KEY. Create a new API key and update The80/.env.", 503) from None
        if error.code == 403:
            raise AIProviderError("Groq denied access for this key or model. Check the Groq project and model permissions.", 503) from None
        raise AIProviderError("Groq could not complete this request. Please retry shortly.", 502) from None
    except (URLError, TimeoutError, OSError):
        raise AIProviderError("Groq did not respond before the request timed out. Please retry.", 504) from None
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        raise AIProviderError("Groq returned a response that MetroPulse could not read.", 502) from None


def _context_text(context: dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))[:24000]


def answer_investigation_question(question: str, context: dict[str, Any], history: list[dict[str, str]]) -> str:
    system = (
        "You are MetroPulse AI, an advisory assistant for a fictional metro monitoring prototype. "
        "Use only the supplied JSON evidence and conversation. Never invent IDs, measurements, timestamps, causes, or scores. "
        "Distinguish observed facts from hypotheses. State when evidence is missing or ambiguous. Never claim a cause is confirmed; "
        "do not operate infrastructure or execute actions. Keep answers concise, clear, and cite incident/anomaly/event IDs when present. "
        "All records may be simulated or user-provided sample data."
    )
    messages = [{"role": "system", "content": system}, {"role": "system", "content": "Current authorized investigation context JSON: " + _context_text(context)}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": question})
    return _completion(messages)


def explain_root_cause(context: dict[str, Any]) -> str:
    system = (
        "Explain the supplied deterministic incident and evidence data for an operator. Do not calculate new metrics, infer unsupported causes, "
        "or call the leading event classification a confirmed root cause. Explain when, impact only if data supports it, evidence, uncertainty, "
        "why the deterministic priority was assigned, and diagnostic checks. Cite original IDs and values. Return concise Markdown."
    )
    return _completion([{"role": "system", "content": system}, {"role": "user", "content": _context_text(context)}])


def verify_incident_evidence(context: dict[str, Any]) -> dict[str, Any]:
    system = (
        "Review this incident's evidence as an advisory only. Never confirm a root cause, change deterministic priority, invent measurements, "
        "or cite a reference absent from the supplied JSON. Treat the source event type as a candidate classification, not established causality. "
        "Return one valid JSON object with keys: incident_summary (string), hypothesis_assessments (array of objects with hypothesis, assessment "
        "('supports'|'contradicts'|'insufficient'), evidence_references (array of strings), reasoning), contradictory_signals (array of strings), "
        "missing_information (array of strings), alternative_explanations (array of strings), recommended_checks (array of strings), "
        "uncertainty_and_limitations (string). Include explicit uncertainty."
    )
    raw = _completion([{"role": "system", "content": system}, {"role": "user", "content": _context_text(context)}], json_mode=True)
    try:
        result = json.loads(raw)
        required = ("incident_summary", "hypothesis_assessments", "contradictory_signals", "missing_information", "alternative_explanations", "recommended_checks", "uncertainty_and_limitations")
        if not isinstance(result, dict) or any(key not in result for key in required):
            raise ValueError("Missing fields")
        if not isinstance(result["incident_summary"], str) or not isinstance(result["uncertainty_and_limitations"], str):
            raise ValueError("Invalid summary fields")
        if not isinstance(result["hypothesis_assessments"], list) or any(not isinstance(result[key], list) or any(not isinstance(item, str) for item in result[key]) for key in required[2:6]):
            raise ValueError("Invalid field type")
        valid_references = set()
        source_items = [context, context.get("incident", {}), *context.get("telemetry_evidence", []), *context.get("anomalies", [])]
        for item in source_items:
            if isinstance(item, dict):
                valid_references.update(item.get(key) for key in ("incident_id", "record_id", "anomaly_id") if isinstance(item.get(key), str))
        for assessment in result["hypothesis_assessments"]:
            if not isinstance(assessment, dict) or not isinstance(assessment.get("hypothesis"), str) or not isinstance(assessment.get("reasoning"), str):
                raise ValueError("Invalid hypothesis assessment")
            if assessment.get("assessment") not in {"supports", "contradicts", "insufficient"}:
                raise ValueError("Invalid assessment value")
            references = assessment.get("evidence_references")
            if not isinstance(references, list) or any(reference not in valid_references for reference in references):
                raise ValueError("Unknown evidence reference")
        return result
    except (json.JSONDecodeError, ValueError, TypeError):
        raise AIProviderError("Groq returned malformed evidence review data. Please retry.", 502) from None
