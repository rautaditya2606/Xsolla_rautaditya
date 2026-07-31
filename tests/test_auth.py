import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.mark.asyncio
async def test_v1_auth_missing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/reviews", json={"diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new"})
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "unauthorized"

@pytest.mark.asyncio
async def test_v1_auth_invalid_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer wrong-token"}
        response = await client.post("/v1/reviews", json={"diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new"}, headers=headers)
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "unauthorized"

@pytest.mark.asyncio
async def test_v1_auth_valid_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer xsolla-secret-bearer-token-2026"}
        response = await client.post("/v1/reviews", json={"diff": "--- a/a.txt\n+++ b/a.txt\n@@ -1,1 +1,1 @@\n-old\n+new"}, headers=headers)
        assert response.status_code == 202
        data = response.json()
        assert "jobId" in data
        assert data["status"] == "queued"
