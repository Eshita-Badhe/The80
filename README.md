# MetroPulse by The80

MetroPulse is a FastAPI application that serves its existing HTML, CSS, and browser JavaScript dashboard. Telemetry and incidents are simulated or user-provided sample data; the prototype does not connect to live metro systems.

## Run locally

From this directory, install the Python dependencies and start the backend:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000`. The FastAPI server also serves the frontend files.

To enable OpenAI AI investigation, open `The80/.env` and replace the placeholder `OPENAI_API_KEY` with your OpenAI API key. `OPENAI_MODEL` defaults to `gpt-4o-mini`; set it to a model available to your OpenAI API project if needed. Never put the key in frontend files, HTML, JavaScript, or browser environment variables. The backend sends only the selected incident's bounded evidence context to OpenAI when you request a review, explanation, or chat response.

## Voice Agent

The chat widget has a microphone button that switches its existing panel into Voice Agent mode. Voice uses OpenAI Realtime over browser WebRTC. The browser posts its SDP offer to the same-origin FastAPI backend; the backend creates the Realtime call with the permanent `OPENAI_API_KEY` and returns only the SDP answer. No permanent key or ephemeral API key is returned to the browser. `OPENAI_REALTIME_MODEL` defaults to `gpt-realtime-2.1`, and `OPENAI_REALTIME_VOICE` defaults to `marin` (both can be overridden in `.env`).

The agent is instructed to speak Hindi by default, switch to English when spoken to in English or asked, and handle Hinglish. Current incident questions invoke the existing `/api/ai/chat` backend with the selected incident and bounded conversation context. The transcript is kept in browser memory and is also added to the text chat history for the current page session. Mute disables the microphone track; ending, backing out, closing the widget, or pressing Escape stops tracks and closes the WebRTC session. Microphone access requires user permission and a secure browser context; `localhost` and `127.0.0.1` are supported by modern browsers.

To try it, open the chat widget, choose the incident in its context selector, press the microphone button, grant microphone access, and ask a question. The default Realtime voice is selected from OpenAI's supported voices; pronunciation and language quality can vary, so test Hindi/Hinglish speech in the target browser and microphone before a presentation. No live Hindi pronunciation test is run as part of the automated test suite.

## AI endpoints

- `GET /api/ai/status` checks the configured model against OpenAI and reports online only when the credentials and model are accepted.
- `POST /api/ai/chat` answers using bounded context from current incidents, anomalies, and telemetry.
- `POST /api/ai/explain` generates an advisory incident explanation.
- `POST /api/ai/verify` returns structured advisory evidence review JSON.
- `POST /api/ai/voice/connect?incident_id=...` creates a backend-authorized Realtime WebRTC session from an SDP offer and returns the SDP answer.

AI output does not change deterministic incident priority, confirm root causes, or operate infrastructure. OpenAI API usage may incur charges under your OpenAI account. The floating assistant keeps conversation messages in browser memory for the current page session; conversations are not saved to the backend.
