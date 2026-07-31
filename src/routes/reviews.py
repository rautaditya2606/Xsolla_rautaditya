import json
from fastapi import APIRouter, Request, Header, Depends, status
from fastapi.responses import JSONResponse, StreamingResponse

from src.config import config
from src.middleware.auth import verify_bearer_token
from src.middleware.rate_limiter import check_rate_limit
from src.models.schemas import ReviewRequest, ReviewAcceptedResponse, JobResponse
from src.services.diff_parser import is_valid_diff
from src.services.queue_manager import queue_manager
from src.services.sse_manager import sse_manager

router = APIRouter(prefix="/v1/reviews", dependencies=[Depends(verify_bearer_token)])

@router.post("", response_model=ReviewAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_review(
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    # 1. Custom rate limit check
    rate_limit_res = check_rate_limit(request)
    if rate_limit_res:
        return rate_limit_res

    # 2. Check raw body size prior to JSON/Pydantic parsing
    raw_body = await request.body()
    if len(raw_body) > config.MAX_PAYLOAD_BYTES:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"error": {"code": "payload_too_large", "message": "Payload size exceeds 1 MiB limit"}}
        )

    # 3. Parse JSON
    try:
        json_data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": {"code": "invalid_json", "message": "Invalid JSON format in body"}}
        )

    # 4. Validate diff presence and unidiff parseability
    diff_text = json_data.get("diff")
    if not diff_text or not isinstance(diff_text, str) or not is_valid_diff(diff_text):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "invalid_diff", "message": "Field 'diff' is missing, empty, or not parseable as unified diff"}}
        )

    options_data = json_data.get("options", {})
    if not isinstance(options_data, dict):
        options_data = {}

    try:
        req_obj = ReviewRequest(diff=diff_text, options=options_data)
    except Exception:
        req_obj = ReviewRequest(diff=diff_text)

    # 5. Create job via queue_manager
    try:
        job, _ = queue_manager.create_job(
            diff_text=req_obj.diff,
            options=req_obj.options,
            idempotency_key=idempotency_key,
            raw_body_bytes=raw_body
        )
    except ValueError as err:
        if str(err) == "IDEMPOTENCY_CONFLICT":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"error": {"code": "idempotency_conflict", "message": "Idempotency key reused with different payload"}}
            )
        raise err

    return ReviewAcceptedResponse(jobId=job.job_id, status=job.status)

@router.get("/{job_id}", response_model=JobResponse)
async def get_review_job(job_id: str):
    job = queue_manager.get_job(job_id)
    if not job:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "not_found", "message": f"Job '{job_id}' not found"}}
        )

    if job.status == "done":
        return JobResponse(
            jobId=job.job_id,
            status="done",
            findings=job.findings or [],
            usage=job.usage
        )
    elif job.status == "failed":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "jobId": job.job_id,
                "status": "failed",
                "findings": [],
                "usage": None,
                "error": {"code": "internal", "message": job.error_message or "Job processing failed"}
            }
        )
    else:
        return JobResponse(
            jobId=job.job_id,
            status=job.status
        )

@router.get("/{job_id}/stream")
async def stream_review_job(job_id: str):
    job = queue_manager.get_job(job_id)
    if not job:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "not_found", "message": f"Job '{job_id}' not found"}}
        )

    return StreamingResponse(
        sse_manager.stream_events(job_id, queue_manager.is_job_finished),
        media_type="text/event-stream"
    )
