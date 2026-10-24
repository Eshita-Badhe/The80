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

## AI endpoints

- `GET /api/ai/status` checks the configured model against OpenAI and reports online only when the credentials and model are accepted.
- `POST /api/ai/chat` answers using bounded context from current incidents, anomalies, and telemetry.
- `POST /api/ai/explain` generates an advisory incident explanation.
- `POST /api/ai/verify` returns structured advisory evidence review JSON.

AI output does not change deterministic incident priority, confirm root causes, or operate infrastructure. OpenAI API usage may incur charges under your OpenAI account. The floating assistant keeps conversation messages in browser memory for the current page session; conversations are not saved to the backend.
