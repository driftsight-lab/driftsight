"""버전 레지스트리 통합 테스트 — PostgreSQL 필요 (`uv run pytest -q -m integration`).

1바이트 변경 1건, 재배포 0건, 되돌림 1건, 같은 내용 다른 경로 중복 없음 (T1-05·T1-06).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from alembic import command
from src.shared.config import get_settings
from src.shared.db import create_engine
from src.shared.models import Version, VersionChange
from src.shared.version_registry import sync_versions
from src.shared.versioning import scan_configs

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    get_settings.cache_clear()
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    command.upgrade(config, "head")
    engine = create_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE versions RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


async def _sync(engine: AsyncEngine, root: Path) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await sync_versions(session, scan_configs([root / "configs"], root=root), actor="test")


async def _counts(engine: AsyncEngine) -> tuple[int, int]:
    async with engine.connect() as conn:
        versions = (await conn.execute(select(func.count()).select_from(Version))).scalar_one()
        changes = (await conn.execute(select(func.count()).select_from(VersionChange))).scalar_one()
    return versions, changes


def _write(root: Path, rel: str, data: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


async def test_register_redeploy_change_and_revert(engine: AsyncEngine, tmp_path: Path) -> None:
    _write(tmp_path, "configs/prompts/qa.md", "Answer briefly")
    _write(tmp_path, "configs/models/m.yaml", "model: claude-haiku\n")

    await _sync(engine, tmp_path)
    assert await _counts(engine) == (2, 2)  # 최초 등록: from_version_id NULL 2건

    await _sync(engine, tmp_path)
    assert await _counts(engine) == (2, 2)  # 동일 내용 재배포: 0건

    _write(tmp_path, "configs/prompts/qa.md", "Answer briefly.")  # 1바이트 변경
    await _sync(engine, tmp_path)
    assert await _counts(engine) == (3, 3)

    _write(tmp_path, "configs/prompts/qa.md", "Answer briefly")  # 되돌림 → 새 버전 없이 이력 1건
    await _sync(engine, tmp_path)
    assert await _counts(engine) == (3, 4)

    async with engine.connect() as conn:
        last = (
            await conn.execute(
                select(
                    VersionChange.from_version_id, VersionChange.to_version_id, VersionChange.source
                )
                .order_by(VersionChange.id.desc())
                .limit(1)
            )
        ).one()
    assert last.from_version_id is not None and last.from_version_id != last.to_version_id
    assert last.source == "deploy"


async def test_same_content_in_two_paths_does_not_repeat(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    _write(tmp_path, "configs/prompts/a.md", "same")
    _write(tmp_path, "configs/prompts/b.md", "same")

    await _sync(engine, tmp_path)
    first = await _counts(engine)
    await _sync(engine, tmp_path)

    assert first == (1, 1)
    assert await _counts(engine) == first
