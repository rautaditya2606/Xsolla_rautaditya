from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.config import config
from src.middleware.auth import UnauthorizedException
from src.services.queue_manager import queue_manager
from src.routes.health import router as health_router
from src.routes.reviews import router as reviews_router

import asyncio
import httpx

async def self_pinger():
    await asyncio.sleep(10)
    url = f"http://127.0.0.1:{config.PORT}/health"
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(url)
            except Exception:
                pass
            await asyncio.sleep(240)

@asynccontextmanager
async def lifespan(app: FastAPI):
    queue_manager.start_workers(config.MAX_CONCURRENT_JOBS)
    ping_task = asyncio.create_task(self_pinger())
    yield
    ping_task.cancel()

app = FastAPI(
    title="AI Diff Review Service",
    version="1.0.0",
    lifespan=lifespan
)

# Custom Error Envelope Exception Handlers
@app.exception_handler(UnauthorizedException)
async def unauthorized_exception_handler(request: Request, exc: UnauthorizedException):
    return JSONResponse(status_code=exc.status_code, content=exc.detail)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_json", "message": "Invalid request parameters or JSON format"}}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal", "message": f"Internal server error: {str(exc)}"}}
    )

# Include Routers
app.include_router(health_router)
app.include_router(reviews_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=config.PORT, reload=True)
