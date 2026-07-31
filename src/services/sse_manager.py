import json
import asyncio
from typing import Any, AsyncGenerator, NamedTuple
from src.models.schemas import Finding, JobUsage

class SSEEvent(NamedTuple):
    type: str
    data: Any

    def to_sse_formatted_str(self) -> str:
        data_str = json.dumps(self.data) if not isinstance(self.data, str) else self.data
        return f"event: {self.type}\ndata: {data_str}\n\n"

class SSEManager:
    def __init__(self):
        # Maps jobId -> list of structured SSEEvent objects
        self.event_logs: dict[str, list[SSEEvent]] = {}
        # Maps jobId -> set of active asyncio.Queue objects for live subscribers
        self.subscribers: dict[str, set[asyncio.Queue]] = {}

    def init_job(self, job_id: str):
        if job_id not in self.event_logs:
            self.event_logs[job_id] = []
            self.subscribers[job_id] = set()

    def emit_event(self, job_id: str, event_type: str, data: Any):
        event = SSEEvent(type=event_type, data=data)
        
        # 1. Store structured event in log for replay
        if job_id not in self.event_logs:
            self.event_logs[job_id] = []
        self.event_logs[job_id].append(event)
        
        # 2. Push to active subscribers
        if job_id in self.subscribers:
            for q in list(self.subscribers[job_id]):
                q.put_nowait(event)

    def emit_status(self, job_id: str, status: str):
        self.emit_event(job_id, "status", {"status": status})

    def emit_finding(self, job_id: str, finding: Finding):
        self.emit_event(job_id, "finding", finding.model_dump())

    def emit_done(self, job_id: str, total_findings: int, usage: JobUsage):
        self.emit_event(job_id, "done", {
            "total": total_findings,
            "usage": usage.model_dump()
        })

    def emit_error(self, job_id: str, message: str, code: str = "internal"):
        self.emit_event(job_id, "error", {
            "error": {"code": code, "message": message}
        })

    async def stream_events(self, job_id: str, is_job_finished_func) -> AsyncGenerator[str, None]:
        self.init_job(job_id)
        
        # 1. Replay historical events
        past_events = list(self.event_logs.get(job_id, []))
        for evt in past_events:
            yield evt.to_sse_formatted_str()
            
        if is_job_finished_func(job_id):
            return

        # 2. Live streaming via queue
        q = asyncio.Queue()
        self.subscribers[job_id].add(q)
        
        try:
            while True:
                evt: SSEEvent = await q.get()
                yield evt.to_sse_formatted_str()
                if evt.type in ("done", "error"):
                    break
        finally:
            if job_id in self.subscribers and q in self.subscribers[job_id]:
                self.subscribers[job_id].remove(q)

sse_manager = SSEManager()
