# backend/CLAUDE.md — AISV-Team17

Also follow the root `CLAUDE.md`. If a rule below conflicts with the root file, follow this file.

## 1. Tech stack

| Area | Library / Tool |
| --- | --- |
| Language | Python 3.12 |
| Framework | FastAPI |
| Dependency manager | uv |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic |
| Linter / Formatter | ruff |
| Type checker | mypy |
| Testing | pytest |
| Telemetry | OpenTelemetry (GenAI semantic conventions) |
| Inference | ONNX Runtime |
| Embeddings | sentence-transformers |

## 2. Commands (run in `backend/`)

```bash
uv sync
uv run ruff check . && uv run ruff format --check .   # lint + format check
uv run mypy src                                        # type check
uv run pytest -q -m "not llm and not integration"     # unit (no infra needed)
uv run pytest -q -m integration                       # integration (PostgreSQL + OTel required)
uv run pytest -q -m llm                               # LLM call tests (Anthropic API required)
alembic upgrade head                                   # run migrations
```

- Run lint, format check, and mypy before each commit.
- Mark integration tests with `@pytest.mark.integration`. They require PostgreSQL and OTel Collector.
- Mark LLM call tests with `@pytest.mark.llm`. They call the Anthropic API.

## 3. Directory structure

| Path | Purpose |
| --- | --- |
| `src/rag/` | RAG service — retrieval and generation (:8000) |
| `src/ingest/` | Ingest API — trace receipt and storage (:8001) |
| `src/worker/` | Async eval worker — stage-1 ONNX + stage-2 LLM |
| `src/drift/` | Drift monitor — APScheduler, quality window aggregation |
| `src/agent/` | Root-cause analysis agent — read-only DB via MCP |
| `src/console/` | Console API — session auth, dashboard data (:8002) |
| `src/shared/` | Common settings, DB session, ORM base |
| `src/interfaces/` | Shared interface contracts (CODEOWNERS — both parts must approve) |
| `tests/` | pytest tests |
| `alembic/` | Alembic migration files (not `migrations/`) |

## 4. Layer architecture

Follow `router → service → repository` in that order. Do not call the database from a router directly.

## 5. OTel rules

- Use `gen_ai.*` standard attributes for LLM call spans.
- Add `app.version.*` custom attributes for prompt, model, and retrieval version tracking.
- Use `BatchSpanProcessor` for async export. Swallow export failures; never let them affect the service response.

## 6. Database rules

- Access the database only through SQLAlchemy async sessions.
- All schema changes go through Alembic. Migration files live in `backend/alembic/` (not `migrations/`). Do not run DDL directly.
- The `eval_jobs` INSERT and the trace INSERT must be in the same transaction (ADR-004).

## 7. Interface compliance

- Implement `Detector`, `DriftDetector`, `Judge`, and `Router` from `docs/specs/interfaces.md`.
- All detector methods accept a **list** of inputs (batch). Single-item input is prohibited.
- Implementations must be pure functions: no direct DB or network access. I/O is the caller's (worker's) responsibility.

## 8. Secrets

- Secrets go in environment variables only. See `docs/ops/env-setup.md` for variable names.
- The agent uses read-only DB account `aisv_ro`. Never pass a write-capable account to the agent (ADR-007).

---

end.