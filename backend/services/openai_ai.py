"""OpenAI-backed advisory explanations grounded in processed MetroPulse records."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1"
DEFAULT_REALTIME_VOICE = "marin"


class AIProviderError(Exception):
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def configuration() -> tuple[str | None, str]:
    return os.getenv("OPENAI_API_KEY", "").strip() or None, os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def realtime_configuration() -> tuple[str, str]:
    model = os.getenv("OPENAI_REALTIME_MODEL", DEFAULT_REALTIME_MODEL).strip() or DEFAULT_REALTIME_MODEL
    voice = os.getenv("OPENAI_REALTIME_VOICE", DEFAULT_REALTIME_VOICE).strip() or DEFAULT_REALTIME_VOICE
    return model, voice


def create_realtime_call(sdp_offer: str, context: dict[str, Any]) -> str:
    """Create a Realtime WebRTC call through the backend-only unified interface."""
    key, _ = configuration()
    if not key:
        raise AIProviderError("OpenAI is not configured. Add OPENAI_API_KEY to the backend .env file.")
    model, voice = realtime_configuration()
    context_json = _context_text(context)
    instructions = (
        "You are MetroPulse AI Voice Agent, a calm and concise metro engineering investigation assistant. "
        "Speak Hindi by default. If the user speaks English or requests English, answer in English; handle Hindi and Hinglish naturally. "
        "Keep spoken answers short, use clear pauses around station/equipment/incident IDs, and pronounce technical identifiers carefully. "
        "Only use the supplied, selected-incident evidence. Observed data is not proof of a cause. Never invent measurements, incidents, "
        "maintenance records, or confirmed root causes. Clearly say when evidence is missing. For every question about current records, "
        "anomalies, severity, priority, timelines, evidence, or diagnostic checks, call ask_metropulse_evidence and base your spoken response "
        "on its result. If that tool fails, say the evidence service is unavailable and do not guess. All prototype data may be simulated.\n\n"
        "Selected incident context (scoped evidence): " + context_json
    )
    session = {
        "type": "realtime",
        "model": model,
        "instructions": instructions,
        "audio": {
            "input": {"transcription": {"model": "gpt-4o-mini-transcribe"}, "turn_detection": {"type": "server_vad"}},
            "output": {"voice": voice},
        },
        "tools": [{
            "type": "function",
            "name": "ask_metropulse_evidence",
            "description": "Answer an engineering question from the current MetroPulse incident dataset using the existing backend investigation service. Call for current incident facts, analysis, evidence, priority, timeline, or diagnostic checks.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "The user's question, preserving the language spoken."}},
                "required": ["question"],
                "additionalProperties": False,
            },
        }],
        "tool_choice": "auto",
    }
    boundary = "----MetroPulse" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"sdp\"\r\nContent-Type: application/sdp\r\n\r\n".encode()
        + sdp_offer.encode("utf-8")
        + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"session\"\r\nContent-Type: application/json\r\n\r\n".encode()
        + json.dumps(session, ensure_ascii=False).encode("utf-8")
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = Request(
        f"{OPENAI_BASE_URL}/realtime/calls",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            answer = response.read().decode("utf-8").strip()
        if not answer.startswith("v=0"):
            raise ValueError("OpenAI did not return an SDP answer")
        return answer
    except HTTPError as error:
        if error.code == 401:
            raise AIProviderError("OpenAI rejected the server API key. Check OPENAI_API_KEY.", 503) from None
        if error.code == 403:
            raise AIProviderError("OpenAI denied Realtime access. Check project access and billing.", 503) from None
        if error.code == 404:
            raise AIProviderError("The configured Realtime model is unavailable. Check OPENAI_REALTIME_MODEL.", 503) from None
        if error.code == 429:
            raise AIProviderError("OpenAI rate limited the voice session. Please wait and retry.", 503) from None
        raise AIProviderError("OpenAI could not create the voice session. Check Realtime model access and retry.", 502) from None
    except (URLError, TimeoutError, OSError):
        raise AIProviderError("OpenAI did not respond while connecting the voice session.", 504) from None
    except (ValueError, UnicodeDecodeError):
        raise AIProviderError("OpenAI returned an invalid WebRTC session response.", 502) from None


def provider_status() -> dict[str, Any]:
    key, model = configuration()
    realtime_model, realtime_voice = realtime_configuration()
    if not key:
        return {"configured": False, "available": False, "provider": "OpenAI", "model": model, "realtime_model": realtime_model, "realtime_voice": realtime_voice, "status": "not_configured", "message": "Add OPENAI_API_KEY to the backend environment to enable AI investigation."}
    request = Request(f"{OPENAI_BASE_URL}/models/{model}", headers={"Authorization": f"Bearer {key}"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        available = payload.get("id") == model
        return {"configured": True, "available": available, "provider": "OpenAI", "model": model, "realtime_model": realtime_model, "realtime_voice": realtime_voice, "status": "online" if available else "model_unavailable", "message": "OpenAI credentials and selected model are available." if available else "The configured OpenAI model is not available for this key."}
    except HTTPError as error:
        if error.code == 401:
            status, message = "invalid_credentials", "OpenAI rejected this API key. Check the key in the backend environment."
        elif error.code == 403:
            status, message = "access_denied", "OpenAI denied access to this model or project. Check project access and model availability."
        elif error.code == 429:
            status, message = "rate_limited", "OpenAI rate limited the status check. Try again shortly."
        elif error.code == 404:
            status, message = "model_unavailable", "The configured OpenAI model was not found or is unavailable to this key."
        else:
            status, message = "unavailable", "OpenAI could not complete the model availability check."
        return {"configured": True, "available": False, "provider": "OpenAI", "model": model, "realtime_model": realtime_model, "realtime_voice": realtime_voice, "status": status, "message": message}
    except (URLError, TimeoutError, ValueError, OSError):
        return {"configured": True, "available": False, "provider": "OpenAI", "model": model, "realtime_model": realtime_model, "realtime_voice": realtime_voice, "status": "unavailable", "message": "OpenAI could not be reached or the backend credentials could not be checked."}


def _completion(messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
    key, model = configuration()
    if not key:
        raise AIProviderError("OpenAI is not configured. Add OPENAI_API_KEY to the backend environment.")
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1400}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty completion")
        return content.strip()
    except HTTPError as error:
        if error.code == 429:
            raise AIProviderError("OpenAI rate limited this request. Check your project limits or try again shortly.", 503) from None
        if error.code == 401:
            raise AIProviderError("OpenAI rejected OPENAI_API_KEY. Check the key in the backend .env file.", 503) from None
        if error.code == 403:
            raise AIProviderError("OpenAI denied access. Check the API project, billing, and model access.", 503) from None
        if error.code == 404:
            raise AIProviderError("The configured OpenAI model is unavailable. Check OPENAI_MODEL.", 503) from None
        raise AIProviderError("OpenAI could not complete this request. Please retry shortly.", 502) from None
    except (URLError, TimeoutError, OSError):
        raise AIProviderError("OpenAI did not respond before the request timed out. Please retry.", 504) from None
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        raise AIProviderError("OpenAI returned a response that MetroPulse could not read.", 502) from None


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
        raise AIProviderError("OpenAI returned malformed evidence review data. Please retry.", 502) from None
