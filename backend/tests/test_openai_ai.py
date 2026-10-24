import json
from backend.services import openai_ai


def test_openai_configuration_uses_server_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-only")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    assert openai_ai.configuration() == ("sk-test-only", "gpt-test")


def test_status_reports_missing_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = openai_ai.provider_status()
    assert result["provider"] == "OpenAI"
    assert result["status"] == "not_configured"
    assert "OPENAI_API_KEY" in result["message"]


def test_completion_sends_to_openai_chat_api(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-only")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    captured = {}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "Evidence-based advisory."}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr(openai_ai, "urlopen", fake_urlopen)
    answer = openai_ai._completion([{"role": "user", "content": "Review evidence"}])
    assert answer == "Evidence-based advisory."
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer sk-test-only"
    assert captured["body"]["model"] == "gpt-test"
