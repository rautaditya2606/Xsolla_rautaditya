import time
from fastapi import APIRouter
from src.config import config
from src.models.schemas import HealthResponse, SpecResponse, LimitsSpec

from fastapi.responses import PlainTextResponse

router = APIRouter()
SERVER_START_TIME = time.time()

@router.get("/", response_class=PlainTextResponse)
async def root():
    return "hi :)"

@router.get("/health", response_model=HealthResponse)
async def get_health():
    uptime = time.time() - SERVER_START_TIME
    return HealthResponse(
        status="ok",
        version="1.0.0",
        uptimeSeconds=round(uptime, 2)
    )

@router.get("/spec", response_model=SpecResponse)
async def get_spec():
    return SpecResponse(
        specVersion=config.SPEC_VERSION,
        providers=["mock", "llm"],
        limits=LimitsSpec(
            maxPayloadBytes=config.MAX_PAYLOAD_BYTES,
            chunkBytes=config.CHUNK_BYTES,
            maxConcurrentJobs=config.MAX_CONCURRENT_JOBS,
            rateLimitPerMinute=config.RATE_LIMIT_PER_MINUTE
        )
    )
