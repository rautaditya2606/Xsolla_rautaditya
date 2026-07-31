import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.text == "hi :)"

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptimeSeconds" in data
        assert data["uptimeSeconds"] >= 0

@pytest.mark.asyncio
async def test_spec_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/spec")
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
