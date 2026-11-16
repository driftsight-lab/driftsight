"""DB 세션 통합 테스트 — PostgreSQL 필요 (`uv run pytest -q -m integration`).

`DATABASE_URL`이 실제 PostgreSQL을 가리켜야 한다.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.shared.config import get_settings
from src.shared.db import create_engine, with_db_retry

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    get_settings.cache_clear()
    engine = create_engine(get_settings())
    yield engine
    await engine.dispose()


async def test_session_connects(engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(engine)

    async def select_one() -> int:
        async with session_factory() as session:
            return (await session.execute(text("SELECT 1"))).scalar_one()

    assert await with_db_retry(select_one) == 1


async def test_connection_timezone_is_utc(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        timezone = (await conn.execute(text("SHOW timezone"))).scalar_one()

    assert timezone == "UTC"
