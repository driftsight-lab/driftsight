"""DB 헬퍼 단위 테스트 — UTC 시각·재시도 분류·재시도 횟수와 백오프 (policies.md > 6.1)."""

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError

from src.shared.db import (
    DB_RETRY_BACKOFF_SECONDS,
    is_transient_db_error,
    utc_now,
    with_db_retry,
)


def _operational() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection reset"))


def _integrity() -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception("unique violation"))


class _Op:
    """지정한 예외를 차례로 던진 뒤 값을 돌려주는 가짜 작업."""

    def __init__(self, errors: list[Exception]) -> None:
        self.errors = errors
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


class _Sleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def test_utc_now_is_timezone_aware_utc() -> None:
    now = utc_now()

    assert now.tzinfo is not None
    assert now.utcoffset() is not None
    assert now.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_transient_error_classification() -> None:
    invalidated = DBAPIError("SELECT 1", {}, Exception("closed"), connection_invalidated=True)

    assert is_transient_db_error(_operational())
    assert is_transient_db_error(InterfaceError("SELECT 1", {}, Exception("closed")))
    assert is_transient_db_error(invalidated)
    assert is_transient_db_error(ConnectionRefusedError())  # 커넥션 수립 실패
    assert is_transient_db_error(TimeoutError())
    assert not is_transient_db_error(_integrity())
    assert not is_transient_db_error(DBAPIError("SELECT 1", {}, Exception("syntax")))


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_errors() -> None:
    op, sleep = _Op([_operational(), _operational()]), _Sleep()

    result = await with_db_retry(op, sleep=sleep)

    assert result == "ok"
    assert op.calls == 3
    assert sleep.delays == [0.5, 1.0]


@pytest.mark.asyncio
async def test_retry_gives_up_after_three_retries() -> None:
    op, sleep = _Op([_operational() for _ in range(4)]), _Sleep()

    with pytest.raises(OperationalError):
        await with_db_retry(op, sleep=sleep)

    assert op.calls == 4  # 최초 1회 + 재시도 3회
    assert sleep.delays == list(DB_RETRY_BACKOFF_SECONDS)


@pytest.mark.asyncio
async def test_constraint_violation_is_not_retried() -> None:
    op, sleep = _Op([_integrity()]), _Sleep()

    with pytest.raises(IntegrityError):
        await with_db_retry(op, sleep=sleep)

    assert op.calls == 1
    assert sleep.delays == []


@pytest.mark.asyncio
async def test_non_db_error_is_not_retried() -> None:
    op, sleep = _Op([ValueError("bug")]), _Sleep()

    with pytest.raises(ValueError):
        await with_db_retry(op, sleep=sleep)

    assert op.calls == 1
