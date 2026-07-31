import hashlib
import json
import uuid
import asyncio
import time
from typing import Optional, NamedTuple

from src.config import config
from src.models.schemas import ReviewOptions, Finding, JobUsage
from src.services.sse_manager import sse_manager

class CachedResult(NamedTuple):
    findings: list[Finding]
    input_bytes: int
    chunks: int

class Job:
    def __init__(self, job_id: str, diff_text: str, options: ReviewOptions, cache_hit: bool = False):
        self.job_id = job_id
        self.status: str = "queued"  # "queued", "running", "done", "failed"
        self.diff_text = diff_text
        self.options = options
        self.cache_hit = cache_hit
        self.findings: Optional[list[Finding]] = None
        self.usage: Optional[JobUsage] = None
        self.error_message: Optional[str] = None
        self.created_at = time.time()

class QueueManager:
    def __init__(self):
        self.job_store: dict[str, Job] = {}
        self.cache_store: dict[str, CachedResult] = {}
        self.idempotency_store: dict[str, tuple[str, str]] = {}
        self._job_queue: Optional[asyncio.Queue[str]] = None
        self.worker_tasks: list[asyncio.Task] = []

    def get_queue(self) -> asyncio.Queue[str]:
        if self._job_queue is None:
            self._job_queue = asyncio.Queue()
        return self._job_queue

    def start_workers(self, count: int = config.MAX_CONCURRENT_JOBS):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        # Start workers if not running
        active_tasks = [t for t in self.worker_tasks if not t.done()]
        if not active_tasks:
            self.worker_tasks = []
            for _ in range(count):
                task = loop.create_task(self._worker_loop())
                self.worker_tasks.append(task)

    async def _worker_loop(self):
        from src.services.job_processor import process_job
        q = self.get_queue()
        while True:
            try:
                job_id = await q.get()
                try:
                    await process_job(job_id, self)
                finally:
                    q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as err:
                job = self.get_job(job_id) if 'job_id' in locals() else None
                if job:
                    job.status = "failed"
                    job.error_message = str(err)

    def get_body_hash(self, body_bytes: bytes) -> str:
        return hashlib.sha256(body_bytes).hexdigest()

    def get_cache_key(self, diff_text: str, options: ReviewOptions) -> str:
        payload_str = json.dumps({
            "diff": diff_text,
            "options": options.model_dump()
        }, sort_keys=True)
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    def save_cached_result(self, diff_text: str, options: ReviewOptions, findings: list[Finding], usage: JobUsage):
        cache_key = self.get_cache_key(diff_text, options)
        self.cache_store[cache_key] = CachedResult(
            findings=findings,
            input_bytes=usage.inputBytes,
            chunks=usage.chunks
        )

    def create_job(self, diff_text: str, options: ReviewOptions, idempotency_key: str | None, raw_body_bytes: bytes) -> tuple[Job, bool]:
        body_hash = self.get_body_hash(raw_body_bytes)

        # 1. Idempotency Key check
        if idempotency_key:
            if idempotency_key in self.idempotency_store:
                existing_job_id, stored_body_hash = self.idempotency_store[idempotency_key]
                if stored_body_hash != body_hash:
                    raise ValueError("IDEMPOTENCY_CONFLICT")
                return self.job_store[existing_job_id], True

        # 2. Result-based Cache check
        cache_key = self.get_cache_key(diff_text, options)
        if cache_key in self.cache_store:
            cached_res = self.cache_store[cache_key]

            job_id = str(uuid.uuid4())
            job = Job(job_id=job_id, diff_text=diff_text, options=options, cache_hit=True)
            job.status = "done"

            truncated_findings = cached_res.findings[:options.maxFindings]
            usage = JobUsage(
                inputBytes=cached_res.input_bytes,
                chunks=cached_res.chunks,
                cacheHit=True
            )
            job.findings = truncated_findings
            job.usage = usage

            self.job_store[job_id] = job
            if idempotency_key:
                self.idempotency_store[idempotency_key] = (job_id, body_hash)

            sse_manager.init_job(job_id)
            sse_manager.emit_status(job_id, "queued")
            sse_manager.emit_status(job_id, "running")
            for f in truncated_findings:
                sse_manager.emit_finding(job_id, f)
            sse_manager.emit_done(job_id, len(cached_res.findings), usage)

            return job, True

        # 3. Create new queued Job
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, diff_text=diff_text, options=options, cache_hit=False)

        self.job_store[job_id] = job
        if idempotency_key:
            self.idempotency_store[idempotency_key] = (job_id, body_hash)

        sse_manager.init_job(job_id)
        sse_manager.emit_status(job_id, "queued")

        # Ensure workers are active
        self.start_workers()

        # Push to queue
        self.get_queue().put_nowait(job_id)

        return job, False

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.job_store.get(job_id)

    def is_job_finished(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        return job is not None and job.status in ("done", "failed")

queue_manager = QueueManager()
