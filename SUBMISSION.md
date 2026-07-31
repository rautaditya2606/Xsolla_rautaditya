# Candidate Submission: AI Diff Review Service

## Service Configuration
- **Base URL**: `http://localhost:8000` (Local testing) / Render / Tunnel URL
- **Bearer Token**: `xsolla-secret-bearer-token-2026`
- **Repository URL**: `https://github.com/adityaraut/Xsolla_OA`

---

## 1. Architecture & Key Refactoring Improvements
The AI Diff Review Service is implemented in Python 3.11+ using FastAPI, Uvicorn, Asyncio, and `unidiff`. The core design focuses on robustness, contract precision, and zero external database overhead:

```
[ HTTP Client ] ---> [ FastAPI / Bearer Auth / Custom Sliding Window Rate Limiter ]
                                         |
                               POST /v1/reviews (Thin Route)
                                         |
                       [ QueueManager & Result Cache Store ]
                                         |
                         (asyncio.Queue() -> 4 Workers)
                                         |
                               [ JobProcessor Pipeline ]
                   ┌─────────────────────┴─────────────────────┐
           [ unidiff Parser ]                          [ Provider Factory ]
     (line-number & hunk tracking)                     ├─ MockProvider (9 rules)
    [ Sequential Chunker (≤64KiB) ]                    └─ LLMProvider (graceful fallback)
                                         |
                               [ SSE Manager Broadcast ]
                                 └─ Structured event replay
```

Key Refactoring Improvements:
1. **Custom Sliding Window Rate Limiter**: Replaced external libraries with a custom sliding window rate limiter (30 req/min). Dynamically computes exact `Retry-After` headers and exact `$429$` error envelopes.
2. **Standardized Diff Parsing (`unidiff`)**: Uses `unidiff.PatchSet` to parse files, hunks, and line numbers accurately across edge cases.
3. **Result-Based Cache Store**: Caching maps `sha256(diff+options)` directly to `CachedResult`. Cache hits immediately return completed jobs with `cacheHit: True` regardless of job retention.
4. **Explicit Worker Queue (`asyncio.Queue` + 4 Workers)**: Replaced semaphores with a true `asyncio.Queue()` and 4 background worker tasks initialized on server startup.
5. **Structured SSE Events**: Replaced raw string formatting in log storage with `SSEEvent(type: str, data: Any)` objects, serializing dynamically during streaming.
6. **Clean Provider Factory Abstraction**: Abstract `BaseProvider` interface implemented by `MockProvider` and `LLMProvider`, selected via `ProviderFactory`.
7. **Thin Routes & Dedicated `JobProcessor`**: Routes delegate pipeline execution to `services/job_processor.py`. Raw payload size is checked prior to JSON or Pydantic parsing.
8. **Removed Unnecessary Middleware**: Stripped `CORSMiddleware` since client calls originate strictly from HTTP API probes.

---

## 2. Provider Design
The system uses an abstract provider interface (`BaseProvider`):

- **`MockProvider`**:
  - Fully deterministic rule engine executing all 9 scoring rules (MOCK-001 through MOCK-008 and MOCK-INJ).
  - Processes added lines extracted via `unidiff`.
  - MOCK-004 (swallowed exception) uses a stateful brace-depth scanner (`{ ... }`) anchored to the `{` following the `catch` keyword.
  - Results are deduplicated by `id` (`{ruleId}:{path}:{line}`) and sorted deterministically by `path` (lexicographical) $\to$ `line` (ascending) $\to$ `ruleId`.
  - `MOCK-INJ` prompt injection markers are reported as inert findings without altering execution logic.

- **`LLMProvider`**:
  - Connects to an external OpenAI-compatible LLM endpoint using `httpx.AsyncClient`.
  - Credentials and model settings live entirely server-side (`LLM_API_KEY`, `LLM_MODEL`).
  - If `LLM_API_KEY` is missing or the external API fails, the job transitions gracefully to `"failed"` state with a clean error message, ensuring the server never crashes.

---

## 3. Verification of Cross-Cutting Behaviors

1. **Chunking (≤64 KiB)**:
   - Diffs larger than 64 KiB are grouped into chunks strictly on file boundaries using `chunker.py`.
   - Verified that findings match unchunked scans identically (zero duplicates, zero losses, ordering preserved), and `usage.chunks` accurately reflects chunk count.

2. **Caching & Idempotency**:
   - **Idempotency**: Checked before cache lookup using SHA-256 body hashes tied to `Idempotency-Key` headers. Reusing a key with an identical body returns the existing `jobId` ($202$); reusing a key with a modified body yields $409$ `idempotency_conflict`.
   - **Caching**: Payload hashes (`sha256(diff + options)`) index completed results. Repeated submissions return `"cacheHit": true` with zero redundant scanning.

3. **SSE Replay & Streaming**:
   - Every status transition, finding, and completion metric is saved as a structured `SSEEvent` to `job.event_log`.
   - Verified that connecting to `GET /v1/reviews/{jobId}/stream` replays historical events from memory before subscribing to live updates.

---

## 4. AI Tools Used
- **Antigravity (Google DeepMind)**: Used for architecture refactoring, `unidiff` integration, worker queue design, test suite updates, and edge-case verification.

---

## 5. Rejected AI Suggestion & Rationale
- **Rejected Suggestion**: An AI assistant originally suggested storing formatted SSE event strings directly in memory for replay.
- **Why Rejected**: Storing pre-formatted SSE string literals tightly coupled internal event representation with transport formatting. Storing structured `SSEEvent(type, data)` objects separates event data from serialization, allowing flexible serialization formats (e.g. `orjson`) and simpler inspection during testing.

---

## 6. What I Would Do Next with More Time
1. **Persistent State Store**: Replace in-memory dictionaries with SQLite / Redis (using Redis Pub/Sub for SSE streaming) so state survives server restarts and scales horizontally across multiple instances.
2. **Prometheus Metrics**: Expose `/metrics` for tracking job throughput, active queue length, cache hit ratios, and worker execution latencies.
3. **AST-Based Semantic Code Analysis**: Move beyond regex/string matching in the mock provider to tree-sitter AST parsing for more accurate language-aware rule checking.
