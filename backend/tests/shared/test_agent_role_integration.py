"""에이전트 읽기 전용 계정 — 테스트 계획 8.2-10 (PostgreSQL 필요, integration).

DB 계정 권한이 쓰기를 막는지(애플리케이션 코드가 아니라 DB가 거부) 확인한다.
"""

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from alembic.config import Config

from alembic import command
from src.shared.config import get_settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BACKEND = Path(__file__).resolve().parents[2]
AGENT_PASSWORD = "agent-it-dummy"  # 임시 컨테이너용 더미


def _alembic(direction: str, target: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    getattr(command, direction)(config, target)


def _agent_dsn() -> str:
    base = urlsplit(get_settings().database_url.get_secret_value().replace("+asyncpg", ""))
    netloc = f"aisv_ro:{AGENT_PASSWORD}@{base.hostname}:{base.port}"
    return urlunsplit((base.scheme, netloc, base.path, "", ""))


@pytest.fixture(autouse=True)
def migrated(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    _alembic("upgrade", "head")
    _alembic("downgrade", "2cb72c655250")  # 역할 리비전을 비밀번호와 함께 다시 적용
    monkeypatch.setenv(
        "AGENT_DB_DSN", _agent_dsn().replace("postgresql://", "postgresql+asyncpg://")
    )
    _alembic("upgrade", "head")


async def test_agent_role_can_read_but_not_write() -> None:
    conn = await asyncpg.connect(_agent_dsn())
    try:
        assert await conn.fetchval("SELECT count(*) FROM traces") >= 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="permission denied"):
            await conn.execute("UPDATE traces SET answer = answer")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO versions (kind, name, content_hash, config, created_at) "
                "VALUES ('prompt', 'x', repeat('b', 64), '{}', now())"
            )
    finally:
        await conn.close()


async def test_offline_sql_never_contains_password(capsys: pytest.CaptureFixture[str]) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "2cb72c655250:0e3ff8a88e42", sql=True)

    out = capsys.readouterr().out
    assert "CREATE ROLE aisv_ro NOLOGIN" in out
    assert AGENT_PASSWORD not in out
