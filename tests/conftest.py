import pytest
from src.services.queue_manager import queue_manager
from src.middleware.rate_limiter import rate_limiter

@pytest.fixture(autouse=True)
def reset_queue_manager_state():
    queue_manager.job_store.clear()
    queue_manager.cache_store.clear()
    queue_manager.idempotency_store.clear()
    queue_manager._job_queue = None
    rate_limiter.requests.clear()
    if queue_manager.worker_tasks:
        for t in queue_manager.worker_tasks:
            try:
                if not t.done():
                    t.cancel()
            except Exception:
                pass
    queue_manager.worker_tasks = []
