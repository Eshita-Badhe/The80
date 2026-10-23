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

To enable Groq AI, set `GROQ_API_KEY` in `The80/.env` or the backend process environment. `GROQ_MODEL` defaults to `openai/gpt-oss-120b` and can be changed to another model enabled for your Groq account. Never put the key in frontend files or browser environment variables.

## AI endpoints

- `GET /api/ai/status` checks the configured model against Groq and reports online only when the credentials and model are accepted.
- `POST /api/ai/chat` answers using bounded context from current incidents, anomalies, and telemetry.
- `POST /api/ai/explain` generates an advisory incident explanation.
- `POST /api/ai/verify` returns structured advisory evidence review JSON.

AI output does not change deterministic incident priority, confirm root causes, or operate infrastructure. The floating assistant keeps conversation messages in browser memory for the current page session; conversations are not saved to the backend.
