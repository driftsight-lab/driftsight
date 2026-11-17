"""검색 — 청크 분할·코사인 검색·`rag.retrieve` 스팬 속성 (telemetry.md > 3.3)."""

import json
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.rag.retrieve import (
    PgVectorIndex,
    RetrievalConfig,
    Retriever,
    VectorIndex,
    chunk_text,
    load_corpus_jsonl,
)
from tests.rag.fakes import HashEmbedder

CFG = RetrievalConfig(top_k=2, chunk_size=5, chunk_overlap=1)
DOCS = [
    {"doc_id": "d1", "text": "the eiffel tower is in paris france"},
    {"doc_id": "d2", "text": "python is a programming language"},
    {"doc_id": "d3", "text": "paris is the capital of france"},
]


def test_chunk_overlap() -> None:
    chunks = chunk_text("d", "a b c d e f g h i", CFG)

    assert [c.text for c in chunks] == ["a b c d e", "e f g h i"]


def test_config_validation() -> None:
    assert RetrievalConfig.from_config({"top_k": 4, "chunk_size": 200}).chunk_overlap == 0
    with pytest.raises(ValueError):
        RetrievalConfig.from_config({"top_k": 0, "chunk_size": 10})
    with pytest.raises(ValueError):
        RetrievalConfig.from_config({"top_k": 1, "chunk_size": 10, "chunk_overlap": 10})


@pytest.mark.asyncio
async def test_search_ranks_relevant_docs_first() -> None:
    index = VectorIndex(HashEmbedder(), CFG)
    index.build(DOCS)

    hits = await index.search("capital of france paris", top_k=2)

    assert {h.doc_id for h in hits} <= {"d1", "d3"}
    assert hits[0].score >= hits[1].score


@pytest.mark.asyncio
async def test_empty_index_returns_nothing() -> None:
    assert await VectorIndex(HashEmbedder(), CFG).search("q", 3) == []


def test_load_corpus_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join(json.dumps(d) for d in DOCS) + "\n", encoding="utf-8")

    assert [d["doc_id"] for d in load_corpus_jsonl(path)] == ["d1", "d2", "d3"]


@pytest.mark.asyncio
async def test_retrieve_span_attributes() -> None:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    index = VectorIndex(HashEmbedder(), CFG)
    index.build(DOCS)

    hits = await Retriever(index, provider.get_tracer("t")).retrieve("paris france")

    (span,) = memory.get_finished_spans()
    attrs = dict(span.attributes or {})
    assert span.name == "rag.retrieve"
    assert attrs["app.retrieval.top_k"] == 2
    assert attrs["app.retrieval.chunk_size"] == 5
    assert attrs["app.retrieval.doc_count"] == len(hits)
    assert list(attrs["app.retrieval.doc_ids"]) == [h.doc_id for h in hits]
    assert json.loads(str(attrs["app.content.contexts"]))[0]["doc_id"] == hits[0].doc_id


@pytest.mark.asyncio
async def test_pgvector_index_without_version_returns_nothing() -> None:
    # 검색 설정 버전이 등록되지 않았으면(DB 다운 등) DB에 가지 않고 빈 결과
    index = PgVectorIndex(None, HashEmbedder(), CFG, retrieval_version_id=None)  # type: ignore[arg-type]

    assert await index.search("q", 3) == []
