from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "hi :)"

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "uptimeSeconds" in data
    assert data["uptimeSeconds"] >= 0

def test_spec_endpoint():
    response = client.get("/spec")
    assert response.status_code == 200
    data = response.json()
    assert data["specVersion"] == "1.0"
    assert "mock" in data["providers"]
    assert "llm" in data["providers"]
    limits = data["limits"]
    assert limits["maxPayloadBytes"] == 1048576
    assert limits["chunkBytes"] == 65536
    assert limits["maxConcurrentJobs"] == 4
    assert limits["rateLimitPerMinute"] == 30
