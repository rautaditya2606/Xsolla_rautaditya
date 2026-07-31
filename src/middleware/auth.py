from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.config import config
from src.models.schemas import ErrorEnvelope, ErrorDetail

security_bearer = HTTPBearer(auto_error=False)

class UnauthorizedException(HTTPException):
    def __init__(self, message: str = "Missing or invalid authorization token"):
        super().__init__(
            status_code=401,
            detail={"error": {"code": "unauthorized", "message": message}}
        )

async def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer)
):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise UnauthorizedException("Missing or invalid authorization header")
    if credentials.credentials != config.BEARER_TOKEN:
        raise UnauthorizedException("Invalid bearer token")
    return credentials.credentials
