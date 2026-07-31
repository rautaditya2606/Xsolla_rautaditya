# AI Diff Review Service

An asynchronous REST API built with FastAPI and Python 3.11 for automated unified diff reviews. It accepts a unified git diff, processes it through static mock review rules or an LLM provider, and streams progress or returns structured review findings.

## Highlights

- **Async Worker Pool**: Uses `asyncio.Queue` with 4 concurrent background workers to handle job processing cleanly without blocking request handlers.
- **Diff Parsing & Chunking**: Utilizes `unidiff` for line-by-line diff analysis and splits large diffs (>64 KiB) strictly along file boundaries.
- **Result Caching & Idempotency**: SHA-256 payload hashing ensures identical submissions instantly return cached findings (`cacheHit=true`). Supports `Idempotency-Key` headers to detect duplicate requests.
- **Dual Providers**:
  - `mock`: Deterministic static scanner evaluating 9 rules (`MOCK-001` through `MOCK-008` & `MOCK-INJ`).
  - `llm`: Optional provider using OpenAI or Anthropic (handles missing keys gracefully by marking job status as `failed` instead of throwing HTTP 500).
- **Server-Sent Events (SSE)**: Real-time progress updates on `/v1/reviews/{id}/stream` with replay support for reconnected clients.
- **Rate Limiting**: Custom sliding window rate limiter (30 requests/minute per client) returning standard 429 status and `Retry-After` headers.
- **Automated CI/CD**: GitHub Actions pipeline checking code quality (`ruff`) and running test suites (`pytest`) on every push.

---

## Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml            # GitHub Actions CI pipeline
├── src/
│   ├── main.py               # Application entrypoint & error handlers
│   ├── config.py             # Environment variables & constants
│   ├── middleware/
│   │   ├── auth.py           # Bearer token validation
│   │   └── rate_limiter.py   # Sliding window rate limiter
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response schemas
│   ├── providers/
│   │   ├── base.py           # Provider interface
│   │   ├── mock_provider.py  # Mock rule evaluation engine
│   │   └── llm_provider.py   # OpenAI / Anthropic integration
│   ├── routes/
│   │   ├── health.py         # /health and /spec public endpoints
│   │   └── reviews.py        # /v1/reviews endpoints
│   └── services/
│       ├── diff_parser.py    # Unidiff parser wrapper
│       ├── chunker.py        # 64 KiB file-boundary chunking
│       ├── queue_manager.py  # Async worker queue & in-memory cache
│       ├── job_processor.py  # Execution pipeline orchestrator
│       ├── provider_factory.py
│       └── sse_manager.py    # Structured SSE log & broadcaster
├── tests/                    # Integration & manual edge-case tests
├── Dockerfile
├── pyproject.toml            # Linter & tool configuration
├── render.yaml
└── requirements.txt
```

---

## Environment Variables

Copy `.env.example` to `.env` before running locally:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `BEARER_TOKEN` | Bearer token for authenticating `/v1/*` routes | `xsolla-secret-bearer-token-rautaditya2606` |
| `PORT` | HTTP server port | `8000` |
| `LLM_API_KEY` | Optional API key for OpenAI / Anthropic | *(empty)* |
| `LLM_PROVIDER` | LLM provider type (`openai` or `anthropic`) | `openai` |
| `LLM_MODEL` | LLM model identifier | `gpt-4o-mini` |

---

## Local Setup & Development

### 1. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Server

```bash
uvicorn src.main:app --reload --port 8000
```

The service will be available at `http://localhost:8000`.

---

## Continuous Integration (CI)

This repository includes an automated CI workflow configured with GitHub Actions ([.github/workflows/ci.yml](file:///.github/workflows/ci.yml)).

On every `push` or `pull_request` to the `main` branch, the pipeline automatically:
1. Sets up Python 3.11 environment with `pip` package caching.
2. Installs dependencies from `requirements.txt`.
3. Runs code linting via `ruff` (`python -m ruff check .`).
4. Runs automated tests via `pytest` with execution timeouts (`python -m pytest -v --timeout=30`).

---

## Docker & Deployment

### Run via Docker

```bash
# Build image
docker build -t ai-diff-review .

# Run container
docker run -d -p 8000:8000 --env-file .env --name ai-diff-review-app ai-diff-review
```

### Docker Hub

The prebuilt Docker image is available on Docker Hub:

```bash
docker pull adityaraut2606/ai-diff-review:latest
docker run -d -p 8000:8000 adityaraut2606/ai-diff-review:latest
```

### Deploy to Render

Deploy directly using `render.yaml` or set up a Docker Web Service pointing to `adityaraut2606/ai-diff-review:latest`.

---

## API Endpoints Overview

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/` | No | Root greeting endpoint (`hi :)`) |
| `GET` | `/health` | No | System health and service uptime |
| `GET` | `/spec` | No | Declarative limits, providers, and version |
| `POST` | `/v1/reviews` | Yes | Submit a unified diff for analysis |
| `GET` | `/v1/reviews/{id}` | Yes | Fetch job status, findings, and usage metrics |
| `GET` | `/v1/reviews/{id}/stream` | Yes | Stream SSE events (`status`, `finding`, `done`) |

### Example Usage

#### Submit a Diff Review

```bash
curl -X POST http://localhost:8000/v1/reviews \
  -H "Authorization: Bearer xsolla-secret-bearer-token-rautaditya2606" \
  -H "Content-Type: application/json" \
  -d '{
    "diff": "--- a/src/db.ts\n+++ b/src/db.ts\n@@ -1,1 +1,2 @@\n function db() {\n+  eval(\"test\");\n }\n",
    "options": {
      "provider": "mock",
      "maxFindings": 10
    }
  }'
```

Response:
```json
{
  "jobId": "c4b12345-6789-abcd-ef01-234567890abc",
  "status": "queued"
}
```

#### Fetch Job Results

```bash
curl -H "Authorization: Bearer xsolla-secret-bearer-token-rautaditya2606" \
  http://localhost:8000/v1/reviews/c4b12345-6789-abcd-ef01-234567890abc
```

---

## Running Tests

Run the full automated test suite (includes auth, rate limits, caching, chunking, SSE replay, and edge-case verifications):

```bash
python -m pytest -v
```
