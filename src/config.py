import os

class Config:
    BEARER_TOKEN: str = os.getenv("BEARER_TOKEN", "xsolla-secret-bearer-token-2026")
    PORT: int = int(os.getenv("PORT", "8000"))
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY", None)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    # Contract Limits
    SPEC_VERSION: str = "1.0"
    MAX_PAYLOAD_BYTES: int = 1048576    # 1 MiB
    CHUNK_BYTES: int = 65536           # 64 KiB
    MAX_CONCURRENT_JOBS: int = 4
    RATE_LIMIT_PER_MINUTE: int = 30
    
config = Config()
