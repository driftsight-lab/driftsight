"""초기 스키마 통합 테스트 — PostgreSQL(pgvector) 필요 (`uv run pytest -q -m integration`).

upgrade·downgrade 왕복과 주요 제약(UNIQUE·CHECK·FK RESTRICT)을 실제 DB로 확인한다.
"""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from src.shared.config import get_settings
from src.shared.db import create_engine, utc_now
from src.shared.models import EvalJob, Trace

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

TRACES_EXISTS_SQL = (
    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename='traces'"
)
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _alembic(direction: str, target: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    getattr(command, direction)(config, target)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    get_settings.cache_clear()
    _alembic("upgrade", "head")
    engine = create_engine(get_settings())
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE eval_jobs, spans, evaluations, embeddings, traces"))
    await engine.dispose()


def _trace(trace_id: str, status: str = "OK") -> Trace:
    now = utc_now()
    return Trace(
        trace_id=trace_id,
        service_name="rag",
        question="q",
        answer="a",
        provider="anthropic",
        model_name="claude",
        input_tokens=1,
        output_tokens=1,
        cost_usd=Decimal("0"),
        latency_ms=1,
        status=status,
        started_at=now,
        ended_at=now,
        created_at=now,
    )


def _trace_id() -> str:
    return uuid.uuid4().hex


async def test_upgrade_downgrade_round_trip(engine: AsyncEngine) -> None:
    _alembic("downgrade", "base")
    async with engine.connect() as conn:
        remaining = (await conn.execute(text(TRACES_EXISTS_SQL))).scalar_one()
    assert remaining == 0

    _alembic("upgrade", "head")
    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename IN "
                    "('traces','spans','versions','version_changes',"
                    "'eval_jobs','evaluations','embeddings')"
                )
            )
        ).scalar_one()
    assert tables == 7


async def test_trace_and_eval_job_in_one_transaction(engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        trace = _trace(_trace_id())
        session.add(trace)
        await session.flush()
        now = utc_now()
        session.add(
            EvalJob(
                trace_pk=trace.id, status="PENDING", attempts=0, available_at=now, created_at=now
            )
        )

    async with session_factory() as session:
        count = (await session.execute(text("SELECT count(*) FROM eval_jobs"))).scalar_one()
    assert count == 1


async def test_duplicate_trace_id_rejected(engine: AsyncEngine) -> None:
    trace_id = _trace_id()
    session_factory = async_sessionmaker(engine)
    async with session_factory() as session, session.begin():
        session.add(_trace(trace_id))

    with pytest.raises(IntegrityError, match="uq_traces_trace_id"):
        async with session_factory() as session, session.begin():
            session.add(_trace(trace_id))


async def test_status_check_rejects_unknown_code(engine: AsyncEngine) -> None:
    session: AsyncSession
    async with async_sessionmaker(engine)() as session:
        with pytest.raises(IntegrityError, match="ck_traces_status"):
            async with session.begin():
                session.add(_trace(_trace_id(), status="UNKNOWN"))
