"""Ingest API (:8001, Docker 내부 네트워크 전용) — api.md > 10. 수집.

- `POST /internal/v1/traces`: Collector OTLP/HTTP JSON, `X-Ingest-Source: collector` 필수
  응답 `{accepted, duplicated, rejected[{traceId, reason}]}`
- `GET /health`: `{status, db, evalQueueDepth, budgetExceeded}` — 버전·경로·에러 상세 미노출
- 오류 코드: api.md > 0.5 (400 INVALID_REQUEST · 403 FORBIDDEN · 500 INTERNAL_ERROR)
- 계층 B 지표: `app.ingest.traces.count{result}` 메트릭만 내보낸다(telemetry.md > 5).
  `ingest.receive` 스팬은 내보내지 않는다 — OTLP로 보내면 Collector 트레이스 파이프라인을 거쳐
  자기 자신에게 되돌아온다(계층 B는 메트릭만, telemetry.md > 1.1)
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ingest.otlp import group_spans, parse_batch
from src.ingest.repository import pending_job_count
from src.ingest.service import IngestResult, ingest
from src.sdk.attributes import sanitize
from src.sdk.metrics import METER_NAME, setup_metrics
from src.shared.config import BaseAppSettings
from src.shared.db import get_sessionmaker

logger = logging.getLogger(__name__)

INGEST_SOURCE_HEADER = "X-Ingest-Source"
INGEST_SOURCE_COLLECTOR = "collector"
MAX_TRACES_PER_BATCH = 500  # api.md > 10.2 traces[] 1~500건
MAX_BODY_BYTES = 32 * 1024 * 1024


INGEST_BATCH_SIZE = "app.ingest.batch_size"
INGEST_ACCEPTED = "app.ingest.accepted"


class IngestSettings(BaseAppSettings):
    """Ingest 설정 — 변수명은 docs/ops/env-setup.md."""

    otel_exporter_otlp_endpoint: str | None = None  # 없으면 메트릭을 내보내지 않는다
    otel_service_name: str = "ingest"


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code})


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    meter_provider: metrics.MeterProvider | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        provider = meter_provider
        if provider is None:
            settings = IngestSettings()  # type: ignore[call-arg]
            if settings.otel_exporter_otlp_endpoint:
                provider = setup_metrics(
                    settings.otel_service_name, settings.otel_exporter_otlp_endpoint
                )
        meter = (provider or metrics.get_meter_provider()).get_meter(METER_NAME)
        app.state.traces_count = meter.create_counter(
            "app.ingest.traces.count", description="수집 트레이스 수"
        )
        yield

    app = FastAPI(
        title="aisv-ingest", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    tracer = trace.get_tracer("aisv.ingest")  # 트레이스 내보내기 미설정 — 기록되지 않는다

    def record(request: Request, result: IngestResult) -> None:
        counter = getattr(request.app.state, "traces_count", None)
        if counter is None:  # lifespan 없이 띄운 경우 — 전역(기본 no-op) meter로 기록
            counter = metrics.get_meter(METER_NAME).create_counter("app.ingest.traces.count")
            request.app.state.traces_count = counter
        for label, value in (
            ("accepted", result.accepted),
            ("duplicated", result.duplicated),
            ("rejected", len(result.rejected)),
        ):
            if value:
                counter.add(value, {"result": label})

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
        with tracer.start_as_current_span("ingest.receive", kind=SpanKind.SERVER) as span:
            try:
                result = await ingest(factory(), batch)
            except Exception as exc:  # noqa: BLE001 — 상세 미노출, 서버 로그에만 분류 기록
                logger.error("ingest failed: %s", type(exc).__name__)
                return _error(500, "INTERNAL_ERROR")
            span.set_attributes(
                sanitize(
                    {
                        INGEST_BATCH_SIZE: len(batch.records) + len(batch.orphans),
                        INGEST_ACCEPTED: result.accepted,
                    }
                )
            )
        record(request, result)
        for r in result.rejected:  # 원인 추적용 — trace id와 사유만 남긴다(본문 미기록)
            logger.warning("trace rejected: %s %s", r["traceId"], r["reason"])
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
