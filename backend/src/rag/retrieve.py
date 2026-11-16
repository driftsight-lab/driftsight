"""코퍼스 인덱싱과 검색 — `rag.retrieve` 스팬 (telemetry.md > 3.3).

벡터 저장은 프로세스 메모리의 정규화 행렬(정확 코사인 검색)이다. 코퍼스 전용 pgvector 테이블은
ERD에 아직 없어 후속 작업으로 둔다.
"""

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Tracer

from src.sdk import attributes as A
from src.sdk.attributes import contexts_attributes, sanitize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalConfig:
    """버전 관리 대상 검색 설정 (kind=retrieval)."""

    top_k: int
    chunk_size: int
    chunk_overlap: int = 0

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "RetrievalConfig":
        cfg = cls(
            top_k=int(config["top_k"]),
            chunk_size=int(config["chunk_size"]),
            chunk_overlap=int(config.get("chunk_overlap", 0)),
        )
        if cfg.top_k < 1 or cfg.chunk_size < 1 or not 0 <= cfg.chunk_overlap < cfg.chunk_size:
            raise ValueError(f"invalid retrieval config: {cfg}")
        return cfg


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    doc_id: str
    text: str
    score: float


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """L2 정규화된 (len(texts), dim) 행렬."""
        ...


class SentenceTransformerEmbedder:
    """`EMBEDDING_REPO`@`EMBEDDING_REVISION` 로컬 CPU 임베딩 (리비전 고정, model-registry.md)."""

    def __init__(self, repo: str, revision: str | None) -> None:
        from sentence_transformers import SentenceTransformer  # 무거운 import는 사용할 때만

        self.name = repo
        self._model = SentenceTransformer(repo, revision=revision, device="cpu")

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)


def chunk_text(doc_id: str, text: str, cfg: RetrievalConfig) -> list[Chunk]:
    """단어 단위로 `chunk_size`씩, `chunk_overlap`만큼 겹쳐 자른다."""
    words = text.split()
    if not words:
        return []
    step = cfg.chunk_size - cfg.chunk_overlap
    return [
        Chunk(doc_id, " ".join(words[i : i + cfg.chunk_size]))
        for i in range(0, max(len(words) - cfg.chunk_overlap, 1), step)
    ]


def load_corpus_jsonl(path: Path) -> list[dict[str, Any]]:
    """`model` 파트 `prepare_msmarco` 출력(corpus.jsonl: doc_id·text …)을 읽는다."""
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class VectorIndex:
    """정규화 임베딩 행렬에 대한 정확 코사인 검색."""

    def __init__(self, embedder: Embedder, cfg: RetrievalConfig) -> None:
        self.embedder = embedder
        self.cfg = cfg
        self._chunks: list[Chunk] = []
        self._matrix = np.zeros((0, 0), dtype=np.float32)

    def __len__(self) -> int:
        return len(self._chunks)

    def build(self, docs: Iterable[dict[str, Any]]) -> None:
        chunks = [c for d in docs for c in chunk_text(str(d["doc_id"]), str(d["text"]), self.cfg)]
        self._chunks = chunks
        self._matrix = self.embedder.embed([c.text for c in chunks]) if chunks else self._matrix
        logger.info("rag index built: %d chunks", len(chunks))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self._chunks:
            return []
        q = self.embedder.embed([query])[0]
        scores = self._matrix @ q
        order = np.argsort(-scores)[:top_k]
        return [
            RetrievedChunk(self._chunks[i].doc_id, self._chunks[i].text, float(scores[i]))
            for i in order
        ]


class Retriever:
    """`rag.retrieve` 스팬을 남기며 검색한다."""

    def __init__(self, index: VectorIndex, tracer: Tracer | None = None) -> None:
        self.index = index
        self._tracer = tracer or trace.get_tracer("aisv.rag")

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        cfg = self.index.cfg
        with self._tracer.start_as_current_span("rag.retrieve") as span:
            hits = self.index.search(question, cfg.top_k)
            span.set_attributes(
                sanitize(
                    {
                        A.RETRIEVAL_TOP_K: cfg.top_k,
                        A.RETRIEVAL_CHUNK_SIZE: cfg.chunk_size,
                        A.RETRIEVAL_DOC_COUNT: len(hits),  # top_k와 다르면 인덱스 이상 신호
                        A.RETRIEVAL_DOC_IDS: [h.doc_id for h in hits],
                        A.RETRIEVAL_TOP_SCORE: hits[0].score if hits else None,
                        **contexts_attributes([{"doc_id": h.doc_id, "text": h.text} for h in hits]),
                    }
                )
            )
            return hits
