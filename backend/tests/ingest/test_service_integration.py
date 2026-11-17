"""수집 service 통합 테스트 — test-plan 8.2-1·8.2-4 (PostgreSQL 필요, integration)."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from src.ingest.otlp import parse_batch
from src.ingest.service import ingest
from src.shared.config import get_settings
from src.shared.db import create_engine
from src.shared.models import EvalJob, Span, Trace, Version
from tests.ingest.otlp_factory import payload, rag_trace

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BACKEND = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    engine: AsyncEngine = create_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE versions, traces RESTART IDENTITY CASCADE"))
        for kind in ("prompt", "model", "retrieval"):  # id 1·2·3
            await conn.execute(
                text(
                    "INSERT INTO versions (kind, name, content_hash, config, created_at) "
                    "VALUES (:k, :k, repeat('a', 64), '{}', now())"
                ),
                {"k": kind},
            )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _count(factory: async_sessionmaker[AsyncSession], model: type) -> int:
    async with factory() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _ingest(factory: async_sessionmaker[AsyncSession], *traces: list[dict], **kw: object):
    records, rejected = parse_batch(payload(*traces))
    return await ingest(factory, records, rejected, **kw)  # type: ignore[arg-type]


async def test_stores_trace_spans_and_job(factory: async_sessionmaker[AsyncSession]) -> None:
    result = await _ingest(factory, rag_trace())

    assert (result.accepted, result.duplicated, result.rejected) == (1, 0, [])
    assert await _count(factory, Trace) == 1
    assert await _count(factory, Span) == 4
    assert await _count(factory, EvalJob) == 1
    async with factory() as s:
        trace = (await s.execute(select(Trace))).scalar_one()
        job = (await s.execute(select(EvalJob))).scalar_one()
    assert (trace.prompt_version_id, trace.model_version_id, trace.retrieval_version_id) == (
        1,
        2,
        3,
    )
    assert job.status == "PENDING" and job.attempts == 0 and job.trace_pk == trace.id
    assert trace.started_at <= trace.ended_at <= trace.created_at  # policies.md > 2.2


async def test_duplicate_trace_is_idempotent(factory: async_sessionmaker[AsyncSession]) -> None:
    tid = uuid.uuid4().hex  # 8.2-4
    await _ingest(factory, rag_trace(tid))

    result = await _ingest(factory, rag_trace(tid))

    assert (result.accepted, result.duplicated) == (0, 1)
    assert await _count(factory, EvalJob) == 1
    assert await _count(factory, Span) == 4


async def test_error_trace_stored_without_job(factory: async_sessionmaker[AsyncSession]) -> None:
    result = await _ingest(factory, rag_trace(answer=None, status_code=503))

    assert result.accepted == 1
    assert await _count(factory, Trace) == 1
    assert await _count(factory, EvalJob) == 0


async def test_unknown_version_ids_become_null(factory: async_sessionmaker[AsyncSession]) -> None:
    await _ingest(factory, rag_trace(versions=(999, 2, 3)))

    async with factory() as s:
        trace = (await s.execute(select(Trace))).scalar_one()
    assert trace.prompt_version_id is None and trace.model_version_id == 2


async def test_eval_job_failure_rolls_back_trace(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    # 8.2-1 시나리오 3 — eval_jobs INSERT 실패 시 traces도 남지 않는다. 다른 트레이스는 저장된다
    failing_tid = uuid.uuid4().hex

    async def failing_job(session: AsyncSession, trace_pk: int, now: datetime) -> None:
        trace_id = (
            await session.execute(select(Trace.trace_id).where(Trace.id == trace_pk))
        ).scalar_one()
        if trace_id == failing_tid:
            await session.execute(  # attempts CHECK 위반을 유도
                text(
                    "INSERT INTO eval_jobs (trace_pk, status, attempts, available_at, created_at) "
                    "VALUES (:pk, 'PENDING', -1, now(), now())"
                ),
                {"pk": trace_pk},
            )
        else:
            from src.ingest.repository import insert_eval_job

            await insert_eval_job(session, trace_pk, now)

    result = await _ingest(
        factory, rag_trace(failing_tid), rag_trace(), insert_eval_job=failing_job
    )

    assert result.accepted == 1
    assert result.rejected == [{"traceId": failing_tid, "reason": "CONSTRAINT_VIOLATION"}]
    async with factory() as s:
        orphans = (
            await s.execute(
                select(func.count())
                .select_from(Trace)
                .outerjoin(EvalJob, EvalJob.trace_pk == Trace.id)
                .where(EvalJob.id.is_(None), Trace.status == "OK")
            )
        ).scalar_one()
        failed = (
            await s.execute(select(func.count()).where(Trace.trace_id == failing_tid))
        ).scalar_one()
    assert orphans == 0  # "traces는 있는데 eval_jobs가 없는" OK 트레이스 0건
    assert failed == 0
    assert await _count(factory, Version) == 3
