from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_v1_auth_missing():
    response = client.post("/v1/reviews", json={"diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new"})
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "unauthorized"

def test_v1_auth_invalid_token():
    headers = {"Authorization": "Bearer wrong-token"}
    response = client.post("/v1/reviews", json={"diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new"}, headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "unauthorized"

def test_v1_auth_valid_token():
    headers = {"Authorization": "Bearer xsolla-secret-bearer-token-2026"}
    response = client.post("/v1/reviews", json={"diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new"}, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert "jobId" in data
    assert data["status"] == "queued"
