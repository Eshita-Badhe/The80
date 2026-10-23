from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_dashboard_and_scenario_workflow():
    before = client.get('/api/dashboard').json()
    assert before['simulated'] is True
    assert before['statistics']['processed_records'] >= 500
    result = client.post('/api/simulation/generate', json={'scenario':'hvac'})
    assert result.status_code == 200
    assert result.json()['records_added'] == 1
    assert client.get('/api/incidents').status_code == 200

def test_upload_rejects_unsupported_extension():
    response = client.post('/api/ingestion/upload', files={'file':('bad.exe',b'hello','application/octet-stream')})
    assert response.status_code == 415

def test_upload_accepts_csv():
    csv = b'timestamp,station_id,equipment_id,equipment_category,event_type,severity,metric,value\n2026-10-23T12:00:00+00:00,MP-01,MP-01-ESC-01,Escalator,MOTOR_TEMP_HIGH,high,temperature_c,92\n'
    response = client.post('/api/ingestion/upload', files={'file':('sample.csv',csv,'text/csv')})
    assert response.status_code == 200
    assert response.json()['accepted'] == 1
    assert len(response.json()['preview']) == 1
