import time
import math
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from src.config import config

class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = config.RATE_LIMIT_PER_MINUTE, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Maps client_identifier -> list of float timestamps
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, client_id: str) -> tuple[bool, int]:
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean up timestamps older than window_seconds
        timestamps = [t for t in self.requests[client_id] if t > window_start]
        self.requests[client_id] = timestamps
        
        if len(timestamps) >= self.max_requests:
            # Rate limited! Compute exact Retry-After in seconds
            oldest_timestamp = timestamps[0]
            retry_after = math.ceil(self.window_seconds - (now - oldest_timestamp))
            return True, max(1, retry_after)
            
        # Record request
        self.requests[client_id].append(now)
        return False, 0

rate_limiter = SlidingWindowRateLimiter()

def check_rate_limit(request: Request) -> JSONResponse | None:
    client_ip = request.client.host if request.client else "global"
    is_limited, retry_after = rate_limiter.is_rate_limited(client_ip)
    
    if is_limited:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Rate limit exceeded. Please try again later."
                }
            },
            headers={"Retry-After": str(retry_after)}
        )
    return None
