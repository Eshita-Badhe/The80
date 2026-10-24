import json
from fastapi.testclient import TestClient
from backend.main import app, processed
from backend.services import openai_ai

client = TestClient(app)


def test_voice_connection_validates_origin_content_type_and_sdp(monkeypatch):
    incident_id = processed['incidents'][0]['incident_id']
    monkeypatch.setattr('backend.main.create_realtime_call', lambda sdp, context: 'v=0\r\nanswer')
    bad_type = client.post(f'/api/ai/voice/connect?incident_id={incident_id}', content='v=0\r\n', headers={'content-type':'text/plain'})
    assert bad_type.status_code == 415
    bad_sdp = client.post(f'/api/ai/voice/connect?incident_id={incident_id}', content='not-sdp', headers={'content-type':'application/sdp'})
    assert bad_sdp.status_code == 400
    bad_origin = client.post(f'/api/ai/voice/connect?incident_id={incident_id}', content='v=0\r\n', headers={'content-type':'application/sdp','origin':'https://example.invalid'})
    assert bad_origin.status_code == 403
    good = client.post(f'/api/ai/voice/connect?incident_id={incident_id}', content='v=0\r\n', headers={'content-type':'application/sdp'})
    assert good.status_code == 200
    assert good.headers['content-type'].startswith('application/sdp')
    assert good.text.startswith('v=0')


def test_realtime_request_uses_backend_key_and_selected_context(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-key')
    monkeypatch.setenv('OPENAI_REALTIME_MODEL', 'gpt-realtime-test')
    monkeypatch.setenv('OPENAI_REALTIME_VOICE', 'marin')
    captured = {}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b'v=0\r\nanswer'

    def fake_urlopen(request, timeout):
        captured['url'] = request.full_url
        captured['auth'] = request.get_header('Authorization')
        captured['body'] = request.data
        return FakeResponse()

    monkeypatch.setattr(openai_ai, 'urlopen', fake_urlopen)
    answer = openai_ai.create_realtime_call('v=0\r\noffer', {'incident':{'incident_id':'INC-TEST'}})
    body = captured['body'].decode()
    session_text = body.split('name="session"\r\nContent-Type: application/json\r\n\r\n',1)[1].split('\r\n--',1)[0]
    session = json.loads(session_text)
    assert answer.startswith('v=0')
    assert captured['url'] == 'https://api.openai.com/v1/realtime/calls'
    assert captured['auth'] == 'Bearer sk-test-key'
    assert session['model'] == 'gpt-realtime-test'
    assert session['audio']['output']['voice'] == 'marin'
    assert session['tools'][0]['name'] == 'ask_metropulse_evidence'
    assert 'INC-TEST' in session['instructions']
    assert 'Speak Hindi by default' in session['instructions']
    assert 'If the user speaks English or requests English, answer in English' in session['instructions']


def test_voice_session_rejects_wrong_origin_before_openai(monkeypatch):
    incident_id = processed['incidents'][0]['incident_id']
    monkeypatch.setattr('backend.main.create_realtime_call', lambda *args: (_ for _ in ()).throw(AssertionError('must not call provider')))
    result = client.post(
        f'/api/ai/voice/connect?incident_id={incident_id}',
        content='v=0\r\n',
        headers={'content-type':'application/sdp','origin':'https://outside.invalid'},
    )
    assert result.status_code == 403
