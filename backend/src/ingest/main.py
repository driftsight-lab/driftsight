"""Ingest API (:8001, Docker 내부 네트워크 전용) — api.md > 10. 수집.

- `POST /internal/v1/traces`: Collector OTLP/HTTP JSON, `X-Ingest-Source: collector` 필수
  응답 `{accepted, duplicated, rejected[{traceId, reason}]}`
- `GET /health`: `{status, db, evalQueueDepth, budgetExceeded}` — 버전·경로·에러 상세 미노출
- 오류 코드: api.md > 0.5 (400 INVALID_REQUEST · 403 FORBIDDEN · 500 INTERNAL_ERROR)
"""

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ingest.otlp import group_spans, parse_batch
from src.ingest.repository import pending_job_count
from src.ingest.service import ingest
from src.shared.db import get_sessionmaker

logger = logging.getLogger(__name__)

INGEST_SOURCE_HEADER = "X-Ingest-Source"
INGEST_SOURCE_COLLECTOR = "collector"
MAX_TRACES_PER_BATCH = 500  # api.md > 10.2 traces[] 1~500건
MAX_BODY_BYTES = 32 * 1024 * 1024


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code})


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    app = FastAPI(title="aisv-ingest", docs_url=None, redoc_url=None, openapi_url=None)

    def factory() -> async_sessionmaker[AsyncSession]:
        return session_factory or get_sessionmaker()

    @app.post("/internal/v1/traces")
    async def receive_traces(request: Request) -> JSONResponse:
        if request.headers.get(INGEST_SOURCE_HEADER) != INGEST_SOURCE_COLLECTOR:
            return _error(403, "FORBIDDEN")
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return _error(400, "INVALID_REQUEST")
        try:
            body: Any = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _error(400, "INVALID_REQUEST")
        if not isinstance(body, dict) or not isinstance(body.get("resourceSpans", []), list):
            return _error(400, "INVALID_REQUEST")
        if len(group_spans(body)) > MAX_TRACES_PER_BATCH:
            return _error(400, "INVALID_REQUEST")

        batch = parse_batch(body)
        try:
            result = await ingest(factory(), batch)
        except Exception as exc:  # noqa: BLE001 — 상세 미노출, 서버 로그에만 분류 기록
            logger.error("ingest failed: %s", type(exc).__name__)
            return _error(500, "INTERNAL_ERROR")
        return JSONResponse(
            {
                "accepted": result.accepted,
                "duplicated": result.duplicated,
                "rejected": result.rejected,
            }
        )

    @app.get("/health")
    async def health() -> JSONResponse:
        db, depth = "UP", 0
        try:
            async with factory()() as session:
                await session.execute(text("SELECT 1"))
                depth = await pending_job_count(session)
        except Exception as exc:  # noqa: BLE001 — 헬스체크는 상태만 보고한다
            logger.warning("health db check failed: %s", type(exc).__name__)
            db = "DOWN"
        return JSONResponse(
            {
                "status": "UP" if db == "UP" else "DEGRADED",
                "db": db,
                "evalQueueDepth": depth,
                "budgetExceeded": False,  # 지출 한도 판정은 후속 작업(비용 집계)
            }
        )

    return app


app = create_app()
