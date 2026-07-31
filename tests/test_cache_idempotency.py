import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.services.queue_manager import queue_manager

AUTH_HEADERS = {"Authorization": "Bearer xsolla-secret-bearer-token-2026"}

@pytest.mark.asyncio
async def test_idempotency_same_key_same_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {**AUTH_HEADERS, "Idempotency-Key": "key-12345"}
        body = {"diff": "--- a/file.ts\n+++ b/file.ts\n@@ -1,1 +1,1 @@\n-old\n+eval('test');"}

        res1 = await client.post("/v1/reviews", json=body, headers=headers)
        assert res1.status_code == 202
        job_id_1 = res1.json()["jobId"]

        res2 = await client.post("/v1/reviews", json=body, headers=headers)
        assert res2.status_code == 202
        job_id_2 = res2.json()["jobId"]

        assert job_id_1 == job_id_2

@pytest.mark.asyncio
async def test_idempotency_same_key_different_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {**AUTH_HEADERS, "Idempotency-Key": "key-conflict-test"}
        body1 = {"diff": "--- a/a.ts\n+++ b/a.ts\n@@ -1,1 +1,1 @@\n-a\n+eval('1');"}
        body2 = {"diff": "--- a/b.ts\n+++ b/b.ts\n@@ -1,1 +1,1 @@\n-b\n+eval('2');"}

        res1 = await client.post("/v1/reviews", json=body1, headers=headers)
        assert res1.status_code == 202

        res2 = await client.post("/v1/reviews", json=body2, headers=headers)
        assert res2.status_code == 409
        data = res2.json()
        assert data["error"]["code"] == "idempotency_conflict"

@pytest.mark.asyncio
async def test_payload_caching():
    queue_manager.start_workers(4)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {"diff": "--- a/cache_test.ts\n+++ b/cache_test.ts\n@@ -1,1 +1,1 @@\n-old\n+TODO fix this"}

        res1 = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        assert res1.status_code == 202
        _ = res1.json()["jobId"]

        # Wait for queue worker to finish processing job 1
        await asyncio.sleep(0.3)

        res2 = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        assert res2.status_code == 202
        job_id2 = res2.json()["jobId"]

        # Check GET response for the second job: status must be "done" and usage.cacheHit must be True
        get_res2 = await client.get(f"/v1/reviews/{job_id2}", headers=AUTH_HEADERS)
        assert get_res2.status_code == 200
        job_data2 = get_res2.json()
        assert job_data2["status"] == "done"
        assert job_data2["usage"]["cacheHit"] is True
