"""RAG 기동 시 버전 등록 — 실제 configs/ + RAG 기본 설정 (PostgreSQL 필요, integration)."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import func, select

from alembic import command
from src.rag.main import RagSettings, _register_versions, _snapshots
from src.shared.config import get_settings
from src.shared.db import get_engine, get_sessionmaker
from src.shared.models import VersionChange

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def migrated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIGS_DIR", str(BACKEND.parent / "configs"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")


async def _change_count() -> int:
    async with get_sessionmaker()() as session:
        return (await session.execute(select(func.count()).select_from(VersionChange))).scalar_one()


async def test_registers_three_versions_and_is_idempotent() -> None:
    snaps, by_source = _snapshots(RagSettings())  # type: ignore[call-arg]

    first = await _register_versions(snaps, by_source, actor="rag")
    count = await _change_count()
    second = await _register_versions(snaps, by_source, actor="rag")

    assert first is not None and second == first
    assert first.prompt.name == "rag-qa-v1"
    assert first.model.name == "rag-gen-v1"
    assert first.retrieval.name == "rag-retrieval-v1"
    assert await _change_count() == count  # 재기동은 이력을 늘리지 않는다
    await get_engine().dispose()
