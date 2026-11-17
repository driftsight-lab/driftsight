"""RAG 코퍼스 도메인 — corpus_chunks (erd.md > 5.7). [IMMUTABLE]."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db import Base
from src.shared.models.evaluation import EMBEDDING_DIM
from src.shared.models.version import TIMESTAMPTZ


class CorpusChunk(Base):
    __tablename__ = "corpus_chunks"
    __table_args__ = (
        UniqueConstraint(
            "retrieval_version_id", "doc_id", "chunk_index", name="uq_corpus_chunks_doc_chunk"
        ),
        CheckConstraint("chunk_index >= 0", name="ck_corpus_chunks_chunk_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    retrieval_version_id: Mapped[int] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT")
    )
    doc_id: Mapped[str] = mapped_column(String(100))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


Index(
    "idx_corpus_chunks_embedding",
    CorpusChunk.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
