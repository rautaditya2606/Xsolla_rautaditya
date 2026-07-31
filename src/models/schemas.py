from typing import Literal, Optional
from pydantic import BaseModel, Field

class Finding(BaseModel):
    id: str
    ruleId: str
    path: str
    line: int
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal["security", "correctness", "performance", "style"]
    title: str
    evidence: str

class JobUsage(BaseModel):
    inputBytes: int
    chunks: int
    cacheHit: bool

class ReviewOptions(BaseModel):
    provider: Literal["mock", "llm"] = "mock"
    maxFindings: int = 100

class ReviewRequest(BaseModel):
    diff: str
    options: ReviewOptions = Field(default_factory=ReviewOptions)

class ReviewAcceptedResponse(BaseModel):
    jobId: str
    status: Literal["queued", "running", "done", "failed"] = "queued"

class JobResponse(BaseModel):
    jobId: str
    status: Literal["queued", "running", "done", "failed"]
    findings: Optional[list[Finding]] = None
    usage: Optional[JobUsage] = None

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    uptimeSeconds: float

class LimitsSpec(BaseModel):
    maxPayloadBytes: int = 1048576
    chunkBytes: int = 65536
    maxConcurrentJobs: int = 4
    rateLimitPerMinute: int = 30

class SpecResponse(BaseModel):
    specVersion: str = "1.0"
    providers: list[str] = ["mock", "llm"]
    limits: LimitsSpec = Field(default_factory=LimitsSpec)

class ErrorDetail(BaseModel):
    code: str
    message: str

class ErrorEnvelope(BaseModel):
    error: ErrorDetail
