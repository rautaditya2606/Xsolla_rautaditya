import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.config import config
from src.services.queue_manager import queue_manager

AUTH_HEADERS = {"Authorization": f"Bearer {config.BEARER_TOKEN}"}
VALID_DIFF = """--- a/src/db.ts
+++ b/src/db.ts
@@ -1,2 +1,5 @@
 function db() {
+  eval("test");
+  const query = "SELECT * FROM users WHERE id = " + id;
+  try { run(); } catch(e) {}
 }
"""

@pytest.fixture(autouse=True)
def reset_queue_manager_state():
    queue_manager.job_store.clear()
    queue_manager.cache_store.clear()
    queue_manager.idempotency_store.clear()
    queue_manager._job_queue = None
    if queue_manager.worker_tasks:
        for t in queue_manager.worker_tasks:
            try:
                if not t.done():
                    t.cancel()
            except Exception:
                pass
    queue_manager.worker_tasks = []

@pytest.mark.asyncio
async def test_1_auth_failure_all_v1_routes():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res1 = await client.post("/v1/reviews", json={"diff": VALID_DIFF})
        assert res1.status_code == 401
        assert res1.json()["error"]["code"] == "unauthorized"

        res2 = await client.get("/v1/reviews/job-123")
        assert res2.status_code == 401
        assert res2.json()["error"]["code"] == "unauthorized"

        res3 = await client.get("/v1/reviews/job-123/stream")
        assert res3.status_code == 401
        assert res3.json()["error"]["code"] == "unauthorized"

@pytest.mark.asyncio
async def test_2_idempotency_conflict():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {**AUTH_HEADERS, "Idempotency-Key": "manual-key-001"}
        body_a = {"diff": VALID_DIFF}
        body_b = {"diff": "--- a/b.ts\n+++ b/b.ts\n@@ -1,1 +1,1 @@\n-a\n+eval('b');\n"}

        res1 = await client.post("/v1/reviews", json=body_a, headers=headers)
        assert res1.status_code == 202

        res2 = await client.post("/v1/reviews", json=body_b, headers=headers)
        assert res2.status_code == 409
        assert res2.json()["error"]["code"] == "idempotency_conflict"

@pytest.mark.asyncio
async def test_3_cache_hit_new_job_id():
    queue_manager.start_workers(4)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {"diff": VALID_DIFF}
        res1 = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        assert res1.status_code == 202
        job_id1 = res1.json()["jobId"]

        # Wait for worker loop to process job 1
        for _ in range(10):
            await asyncio.sleep(0.05)
            j = queue_manager.get_job(job_id1)
            print(f"DEBUG: job1 status={j.status if j else None}, err={j.error_message if j else None}", flush=True)
            if j and j.status == "done":
                break

        res2 = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        assert res2.status_code == 202
        job_id2 = res2.json()["jobId"]

        get_res2 = await client.get(f"/v1/reviews/{job_id2}", headers=AUTH_HEADERS)
        assert get_res2.status_code == 200
        data2 = get_res2.json()
        assert data2["status"] == "done"
        assert data2["usage"]["cacheHit"] is True

@pytest.mark.asyncio
async def test_4_sse_identical_replay():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/v1/reviews", json={"diff": VALID_DIFF}, headers=AUTH_HEADERS)
        job_id = res.json()["jobId"]

        for _ in range(10):
            await asyncio.sleep(0.05)
            j = queue_manager.get_job(job_id)
            if j and j.status == "done":
                break

        s1 = await client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH_HEADERS)
        stream1_text = s1.text

        s2 = await client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH_HEADERS)
        stream2_text = s2.text

        assert stream1_text == stream2_text
        assert "event: status" in stream1_text
        assert "event: done" in stream1_text

@pytest.mark.asyncio
async def test_5_max_findings_truncation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {
            "diff": VALID_DIFF,
            "options": {"maxFindings": 1}
        }
        res = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        job_id = res.json()["jobId"]

        for _ in range(10):
            await asyncio.sleep(0.05)
            j = queue_manager.get_job(job_id)
            if j and j.status == "done":
                break

        get_res = await client.get(f"/v1/reviews/{job_id}", headers=AUTH_HEADERS)
        data = get_res.json()
        assert data["status"] == "done"
        assert len(data["findings"]) == 1

        s_res = await client.get(f"/v1/reviews/{job_id}/stream", headers=AUTH_HEADERS)
        assert '"total": 3' in s_res.text or '"total": 2' in s_res.text

@pytest.mark.asyncio
async def test_6_chunking_large_diff():
    lines_f1 = "".join([f"  // line {i}\n" for i in range(2500)]) + "+eval('f1');\n"
    lines_f2 = "".join([f"  // line {i}\n" for i in range(2500)]) + "+eval('f2');\n"
    lines_f3 = "".join([f"  // line {i}\n" for i in range(500)]) + "+eval('f3');\n"

    file1 = f"--- a/file1.ts\n+++ b/file1.ts\n@@ -1,2500 +1,2501 @@\n{lines_f1}"
    file2 = f"--- a/file2.ts\n+++ b/file2.ts\n@@ -1,2500 +1,2501 @@\n{lines_f2}"
    file3 = f"--- a/file3.ts\n+++ b/file3.ts\n@@ -1,500 +1,501 @@\n{lines_f3}"

    large_diff = file1 + file2 + file3
    assert len(large_diff.encode("utf-8")) > 65536

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/v1/reviews", json={"diff": large_diff}, headers=AUTH_HEADERS)
        assert res.status_code == 202
        job_id = res.json()["jobId"]

        for _ in range(20):
            await asyncio.sleep(0.05)
            j = queue_manager.get_job(job_id)
            if j and j.status == "done":
                break

        get_res = await client.get(f"/v1/reviews/{job_id}", headers=AUTH_HEADERS)
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["status"] == "done"
        assert data["usage"]["chunks"] > 1
        findings = data["findings"]
        rule_ids = [f["ruleId"] for f in findings]
        assert rule_ids == ["MOCK-001", "MOCK-001", "MOCK-001"]

@pytest.mark.asyncio
async def test_7_concurrency_queueing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        job_ids = []
        for i in range(5):
            res = await client.post("/v1/reviews", json={"diff": VALID_DIFF}, headers=AUTH_HEADERS)
            assert res.status_code == 202
            job_ids.append(res.json()["jobId"])

        await asyncio.sleep(0.3)
        for jid in job_ids:
            get_res = await client.get(f"/v1/reviews/{jid}", headers=AUTH_HEADERS)
            assert get_res.status_code == 200
            assert get_res.json()["status"] in ("done", "running", "queued")

@pytest.mark.asyncio
async def test_8_llm_provider_missing_key_graceful_failure():
    config.LLM_API_KEY = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {
            "diff": VALID_DIFF,
            "options": {"provider": "llm"}
        }
        res = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        assert res.status_code == 202
        job_id = res.json()["jobId"]

        for _ in range(10):
            await asyncio.sleep(0.05)
            j = queue_manager.get_job(job_id)
            if j and j.status == "failed":
                break

        get_res = await client.get(f"/v1/reviews/{job_id}", headers=AUTH_HEADERS)
        assert get_res.status_code == 200  # NOT HTTP 500!
        data = get_res.json()
        assert data["status"] == "failed"
        assert "error" in data
        assert "LLM_API_KEY" in data["error"]["message"]

@pytest.mark.asyncio
async def test_9_ordering_exact():
    unordered_diff = """--- a/z_file.ts
+++ b/z_file.ts
@@ -1,1 +1,2 @@
 function z() {
+  eval("test");
 }
--- a/a_file.ts
+++ b/a_file.ts
@@ -1,1 +1,3 @@
 function a() {
+  const query = "SELECT * FROM users WHERE id = " + id;
+  eval("test");
 }
"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/v1/reviews", json={"diff": unordered_diff}, headers=AUTH_HEADERS)
        job_id = res.json()["jobId"]

        for _ in range(10):
            await asyncio.sleep(0.05)
            j = queue_manager.get_job(job_id)
            if j and j.status == "done":
                break

        get_res = await client.get(f"/v1/reviews/{job_id}", headers=AUTH_HEADERS)
        data = get_res.json()
        findings = data["findings"]
        for i in range(len(findings) - 1):
            f1, f2 = findings[i], findings[i + 1]
            t1 = (f1["path"], f1["line"], f1["ruleId"])
            t2 = (f2["path"], f2["line"], f2["ruleId"])
            assert t1 <= t2

@pytest.mark.asyncio
async def test_10_unknown_json_fields_ignored():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {
            "diff": VALID_DIFF,
            "unknownField": 12345,
            "extraMeta": {"a": 1}
        }
        res = await client.post("/v1/reviews", json=body, headers=AUTH_HEADERS)
        assert res.status_code == 202

@pytest.mark.asyncio
async def test_11_invalid_json():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/v1/reviews",
            content="{ invalid json ...",
            headers={**AUTH_HEADERS, "Content-Type": "application/json"}
        )
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "invalid_json"

@pytest.mark.asyncio
async def test_12_invalid_diff():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/v1/reviews", json={"diff": "not a diff format"}, headers=AUTH_HEADERS)
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "invalid_diff"

@pytest.mark.asyncio
async def test_13_payload_too_large():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        large_diff = "x" * (1048576 + 10)
        res = await client.post("/v1/reviews", json={"diff": large_diff}, headers=AUTH_HEADERS)
        assert res.status_code == 413
        assert res.json()["error"]["code"] == "payload_too_large"
