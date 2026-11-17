"""코퍼스 적재 명령 — 현재 검색 설정 버전으로 청크·임베딩을 `corpus_chunks`에 저장한다.

    uv run python -m src.rag.index_corpus          # RAG_CORPUS_PATH·DATABASE_URL 필요

- 검색 설정 버전 단위로 멱등이다(`uq_corpus_chunks_doc_chunk` ON CONFLICT DO NOTHING)
- 적재 전에 설정 파일을 버전으로 등록해 `retrieval_version_id`를 얻는다 (ADR-005)
"""

import asyncio
import logging
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.rag.retrieve import Chunk, Embedder, RetrievalConfig, chunk_text, load_corpus_jsonl
from src.shared.db import utc_now
from src.shared.models import CorpusChunk

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


def _batches(items: Sequence[Chunk], size: int) -> Iterable[Sequence[Chunk]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def index_corpus(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    cfg: RetrievalConfig,
    retrieval_version_id: int,
    docs: Iterable[dict[str, Any]],
    *,
    batch_size: int = EMBED_BATCH_SIZE,
) -> int:
    """청크를 임베딩해 저장하고 새로 들어간 행 수를 돌려준다."""
    inserted = 0
    for doc in docs:
        chunks = chunk_text(str(doc["doc_id"])[:100], str(doc["text"]), cfg)
        for start, batch in enumerate(_batches(chunks, batch_size)):
            vectors = embedder.embed([c.text for c in batch])
            now = utc_now()
            rows = [
                {
                    "retrieval_version_id": retrieval_version_id,
                    "doc_id": c.doc_id,
                    "chunk_index": start * batch_size + i,
                    "text": c.text,
                    "embedding": vectors[i].tolist(),
                    "embedding_model": embedder.name,
                    "created_at": now,
                }
                for i, c in enumerate(batch)
            ]
            stmt = (
                insert(CorpusChunk)
                .values(rows)
                .on_conflict_do_nothing(constraint="uq_corpus_chunks_doc_chunk")
                .returning(CorpusChunk.id)
            )
            async with session_factory() as session, session.begin():
                inserted += len((await session.execute(stmt)).all())
    return inserted


async def _main() -> None:
    from src.rag.main import (
        RETRIEVAL_SOURCE,
        RagSettings,
        _register_versions,
        _snapshots,
    )
    from src.rag.retrieve import SentenceTransformerEmbedder
    from src.shared.db import get_sessionmaker

    settings = RagSettings()  # type: ignore[call-arg]
    if settings.rag_corpus_path is None or not settings.rag_corpus_path.is_file():
        raise SystemExit("RAG_CORPUS_PATH must point to corpus.jsonl")
    snaps, by_source = _snapshots(settings)
    versions = await _register_versions(snaps, by_source, actor="index_corpus")
    if versions is None:
        raise SystemExit("version registration failed — check DATABASE_URL")
    cfg = RetrievalConfig.from_config(by_source[RETRIEVAL_SOURCE].config)
    embedder = SentenceTransformerEmbedder(settings.embedding_repo, settings.embedding_revision)
    count = await index_corpus(
        get_sessionmaker(),
        embedder,
        cfg,
        versions.retrieval.id,
        load_corpus_jsonl(settings.rag_corpus_path),
    )
    logger.info("indexed %d new chunks for retrieval version %s", count, versions.retrieval.name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
