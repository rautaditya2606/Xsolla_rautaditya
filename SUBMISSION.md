# Candidate Submission: AI Diff Review Service

## Service Configuration
- **Base URL**: `https://ai-diff-review-rautaditya2606.onrender.com`
- **Bearer Token**: `xsolla-secret-bearer-token-rautaditya2606`
- **Repository URL**: `https://github.com/rautaditya2606/Xsolla_rautaditya`

---

## 1. Architecture & Design Decisions
The AI Diff Review Service is implemented in Python 3.11+ using FastAPI. The architecture focuses on contract compliance, deterministic execution, and low-latency response processing:

```text
[ HTTP Client ] ---> [ FastAPI / Bearer Auth / Custom Sliding Window Rate Limiter ]
                                         |
                               POST /v1/reviews (Thin Route)
                                         |
                       [ QueueManager & Result Cache Store ]
                                         |
                        (Bounded Background Worker Pool)
                                         |
                              [ JobProcessor Pipeline ]
                   ┌─────────────────────┴─────────────────────┐
           [ Unidiff Parser ]                          [ Provider Factory ]
     (line-number & hunk tracking)                     ├─ MockProvider (9 rules)
    [ Sequential Chunker (<=64KiB) ]                   └─ LLMProvider (graceful fallback)
                                         |
                               [ SSE Manager Broadcast ]
                                 └─ Structured event replay
```

### Key Architectural Decisions:
1. **Custom Sliding Window Rate Limiter**: Implemented custom sliding window rate limiting (30 requests/minute) to guarantee precise calculation of `Retry-After` header delays and standard 429 error messages.
2. **Robust Diff Parsing**: Integrated standard unified diff parsing (`unidiff`) to track file hunks, line numbers, and added lines reliably across edge cases.
3. **Result-Based Cache Store**: Decoupled caching from job object lifetimes by indexing execution results directly by payload hash (`sha256(diff + options)`). Cache hits instantly yield completed results with `cacheHit: True`.
4. **Bounded Worker Queue**: Employed a fixed concurrency worker pool (4 concurrent workers) to decouple job acceptance (HTTP 202) from job execution without thread or process bloat.
5. **Structured SSE Event Log**: Event progress and results are stored as structured objects rather than formatted strings, allowing clean replay on client reconnects and clean separation from transport protocols.
6. **Provider Abstraction**: Enforced a clean provider interface (`BaseProvider`) allowing seamless switching between static rule scanning and LLM processing.
7. **Thin Routes & Raw Body Parsing**: Enforced payload size checks (1 MiB limit) on raw request bytes prior to schema parsing to prevent memory exhaustion on oversized payloads.

---

## 2. Provider Design

- **`MockProvider`**:
  - Deterministic rule evaluation engine executing 9 scoring rules (`MOCK-001` through `MOCK-008` & `MOCK-INJ`).
  - `MOCK-004` (swallowed exception detection) uses a stateful brace-depth analyzer (`{ ... }`) anchored to the `{` character following the `catch` statement.
  - Findings are deduplicated by finding key (`ruleId:path:line`) and sorted deterministically by `path` (lexicographical) -> `line` (ascending) -> `ruleId`.
  - `MOCK-INJ` prompt injection markers are treated as inert text findings without interrupting job flow or altering review behavior.

- **`LLMProvider`**:
  - Connects to an external OpenAI-compatible LLM endpoint using asynchronous HTTP requests.
  - Configuration settings (`LLM_API_KEY`, `LLM_MODEL`) are maintained server-side.
  - Gracefully handles missing API keys or external service failures by setting job status to `failed` with a descriptive error messages instead of crashing with HTTP 500.

---

## 3. Verification of Cross-Cutting Behaviors

Verified using automated pytest tests and manual end-to-end testing against the deployed service.

1. **Chunking (<= 64 KiB)**:
   - Diffs exceeding 64 KiB are split strictly on file boundaries into sequential chunks.
   - Verified that chunked and unchunked execution produce identical findings and ordering, and `usage.chunks` accurately reflects chunk count.

2. **Caching & Idempotency**:
   - **Idempotency**: Requests containing an `Idempotency-Key` header check stored key mappings before processing. Submitting identical payloads returns the existing `jobId` (202); submitting modified payloads yields a 409 `idempotency_conflict` error.
   - **Caching**: Submitting identical diff and option payloads returns completed cached results (`cacheHit: true`) with zero redundant processing.

3. **SSE Replay & Streaming**:
   - Historical job events (`status`, `finding`, `done`) are preserved in job log storage.
   - Connecting or reconnecting to `GET /v1/reviews/{jobId}/stream` replays past events sequentially before streaming live updates.

---

## 4. AI Tools Used
- **Antigravity (Google DeepMind)**: Used for architecture refactoring, diff parser integration, worker queue design, test suite execution, and edge-case verification.

---

## 5. Rejected AI Suggestion & Rationale
- **Rejected Suggestion**: Storing pre-formatted SSE string literals directly in memory for event replay.
- **Why Rejected**: Storing formatted string literals tightly coupled internal event models with the transport protocol. Storing structured event objects decouples data representation from serialization and simplifies test assertions.

---

## 6. Future Improvements
1. **Persistent State Store**: Replace in-memory stores with Redis / SQLite to support server restarts and horizontal scaling.
2. **Prometheus Metrics**: Expose `/metrics` endpoint to monitor queue depth, execution latency, and cache hit rates.
3. **AST Code Analysis**: Introduce AST parser integrations (e.g. tree-sitter) for deeper semantic code analysis beyond regex/string matching.
