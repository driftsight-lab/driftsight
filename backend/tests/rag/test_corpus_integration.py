"""코퍼스 적재·pgvector 검색 통합 테스트 — PostgreSQL(pgvector) 필요 (integration).

적재 멱등, 검색 설정 버전별 분리, 코사인 순위, 검색 스팬 속성.
"""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from src.rag.index_corpus import index_corpus
from src.rag.retrieve import PgVectorIndex, RetrievalConfig
from src.shared.config import get_settings
from src.shared.db import create_engine
from src.shared.models import CorpusChunk
from tests.rag.fakes import HashEmbedder

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BACKEND = Path(__file__).resolve().parents[2]
CFG = RetrievalConfig(top_k=2, chunk_size=6, chunk_overlap=0)
DOCS = [
    {"doc_id": "d1", "text": "the eiffel tower is in paris france"},
    {"doc_id": "d2", "text": "python is a popular programming language"},
    {"doc_id": "d3", "text": "paris is the capital city of france"},
]


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], int, int]]:
    get_settings.cache_clear()
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    engine: AsyncEngine = create_engine(get_settings())
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE versions RESTART IDENTITY CASCADE"))
        for name in ("r-v1", "r-v2"):  # 검색 설정 버전 2개 (id 1·2)
            await conn.execute(
                text(
                    "INSERT INTO versions (kind, name, content_hash, config, created_at) "
                    "VALUES ('retrieval', :n, :h, '{}', now())"
                ),
                {"n": name, "h": hashlib.sha256(name.encode()).hexdigest()},
            )
    yield async_sessionmaker(engine, expire_on_commit=False), 1, 2
    await engine.dispose()


async def _count(factory: async_sessionmaker[AsyncSession], version_id: int) -> int:
    async with factory() as s:
        stmt = select(func.count()).where(CorpusChunk.retrieval_version_id == version_id)
        return (await s.execute(stmt)).scalar_one()


async def test_index_is_idempotent_per_version(
    factory: tuple[async_sessionmaker[AsyncSession], int, int],
) -> None:
    sessions, v1, v2 = factory
    embedder = HashEmbedder(dim=384)

    first = await index_corpus(sessions, embedder, CFG, v1, DOCS)
    again = await index_corpus(sessions, embedder, CFG, v1, DOCS)
    other = await index_corpus(sessions, embedder, CFG, v2, DOCS[:1])

    assert first == 5  # d1(7단어 → 2) + d2(6단어 → 1) + d3(7단어 → 2), chunk_size 6
    assert again == 0  # 같은 버전 재적재는 중복 없음
    assert other == 2
    assert await _count(sessions, v1) == 5
    assert await _count(sessions, v2) == 2


async def test_search_uses_only_current_version_ordered_by_cosine(
    factory: tuple[async_sessionmaker[AsyncSession], int, int],
) -> None:
    sessions, v1, v2 = factory
    embedder = HashEmbedder(dim=384)
    await index_corpus(sessions, embedder, CFG, v1, DOCS)
    await index_corpus(sessions, embedder, CFG, v2, [{"doc_id": "x", "text": "paris france"}])

    hits = await PgVectorIndex(sessions, embedder, CFG, v1).search("capital of france paris", 2)

    assert len(hits) == 2
    assert "x" not in {h.doc_id for h in hits}  # 다른 검색 설정 버전의 청크는 섞이지 않는다
    assert hits[0].doc_id == "d3"
    assert hits[0].score >= hits[1].score
