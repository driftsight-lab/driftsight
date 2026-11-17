"""async DB 엔진·세션 팩토리, ORM 기반, UTC 시각, 연결 오류 재시도.

- DB 접근은 SQLAlchemy async 세션으로만 한다 (backend/CLAUDE.md > 6)
- 모든 TIMESTAMPTZ는 UTC로 저장한다 (erd.md > 6. 공통 컬럼 규칙)
- DB 커넥션 재시도: 연결 끊김·일시적 오류만 3회, 0.5s → 1s → 2s.
  제약 위반은 즉시 실패 (policies.md > 6.1 재시도 규칙)
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.shared.config import BaseAppSettings, get_settings

# policies.md > 6.1 — DB 커넥션 재시도 백오프 (재시도 3회)
DB_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.5, 1.0, 2.0)


class Base(DeclarativeBase):
    """ORM 선언 기반. 테이블 모델은 스키마 리비전 작업에서 추가한다."""


def utc_now() -> datetime:
    """애플리케이션의 현재 시각 생성 지점. 항상 tz-aware UTC."""
    return datetime.now(UTC)


def create_engine(settings: BaseAppSettings) -> AsyncEngine:
    """설정으로 async 엔진을 만든다. 커넥션 시간대는 UTC로 고정한다."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        # DB 재기동 후 끊긴 커넥션을 사용 전에 걸러낸다 (policies.md > 2.3)
        pool_pre_ping=True,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """프로세스당 하나의 엔진."""
    return create_engine(get_settings())


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """프로세스당 하나의 세션 팩토리."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


def is_transient_db_error(exc: BaseException) -> bool:
    """연결 끊김·일시적 오류면 True. 제약 위반 등 나머지는 False.

    커넥션 수립 단계의 거부·타임아웃은 SQLAlchemy가 감싸지 않고 `OSError`로 올라온다
    (DB 재기동 중, policies.md > 2.3).
    """
    if isinstance(exc, OperationalError | InterfaceError | OSError):
        return True
    return isinstance(exc, DBAPIError) and exc.connection_invalidated


async def with_db_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """연결 오류에 한해 `operation`을 재시도한다.

    `operation`은 세션 열기부터 커밋까지 한 트랜잭션 단위여야 한다.
    재시도 시 트랜잭션 전체를 다시 실행하므로, 트랜잭션 경계는 호출자가 정한다.
    """
    for delay in DB_RETRY_BACKOFF_SECONDS:
        try:
            return await operation()
        except (DBAPIError, OSError) as exc:
            if not is_transient_db_error(exc):
                raise
            await sleep(delay)
    return await operation()
