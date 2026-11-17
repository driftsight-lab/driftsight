"""Ingest API 통합 테스트 — 수집 응답 형식·중복·부분 거부·헬스체크 (PostgreSQL 필요)."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from alembic import command
from src.ingest.main import create_app
from src.shared.config import get_settings
from src.shared.db import create_engine
from tests.ingest.otlp_factory import payload, rag_trace, span

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BACKEND = Path(__file__).resolve().parents[2]
HEADERS = {"X-Ingest-Source": "collector"}


@pytest_asyncio.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    engine: AsyncEngine = create_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE versions, traces RESTART IDENTITY CASCADE"))
    app = create_app(async_sessionmaker(engine, expire_on_commit=False))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as client:
        yield client
    await engine.dispose()


async def test_ingest_response_and_duplicate(http: httpx.AsyncClient) -> None:
    spans = rag_trace(uuid.uuid4().hex)  # 재전송은 같은 span id
    orphan = [span(uuid.uuid4().hex, "gen_ai.chat", parent="b" * 16)]

    first = await http.post("/internal/v1/traces", json=payload(spans, orphan), headers=HEADERS)
    second = await http.post("/internal/v1/traces", json=payload(spans), headers=HEADERS)

    assert first.status_code == 200
    body = first.json()
    assert (body["accepted"], body["duplicated"]) == (1, 0)
    assert [r["reason"] for r in body["rejected"]] == ["ROOT_SPAN_MISSING"]
    assert second.json() == {"accepted": 0, "duplicated": 1, "rejected": []}


async def test_health_reports_queue_depth(http: httpx.AsyncClient) -> None:
    await http.post("/internal/v1/traces", json=payload(rag_trace(), rag_trace()), headers=HEADERS)

    resp = await http.get("/health")

    assert resp.json() == {
        "status": "UP",
        "db": "UP",
        "evalQueueDepth": 2,
        "budgetExceeded": False,
    }


async def test_traces_count_metric_by_result() -> None:
    # telemetry.md > 5 — app.ingest.traces.count{result}
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    get_settings.cache_clear()
    reader = InMemoryMetricReader()
    engine = create_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE versions, traces RESTART IDENTITY CASCADE"))
    app = create_app(
        async_sessionmaker(engine, expire_on_commit=False),
        meter_provider=MeterProvider(metric_readers=[reader]),
    )
    spans = rag_trace(uuid.uuid4().hex)
    orphan = [span(uuid.uuid4().hex, "gen_ai.chat", parent="d" * 16)]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as http:
            await http.post("/internal/v1/traces", json=payload(spans, orphan), headers=HEADERS)
            await http.post("/internal/v1/traces", json=payload(spans), headers=HEADERS)
    await engine.dispose()

    data = reader.get_metrics_data()
    points = {
        p.attributes["result"]: p.value
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "app.ingest.traces.count"
        for p in m.data.data_points
    }
    assert points == {"accepted": 1, "rejected": 1, "duplicated": 1}
