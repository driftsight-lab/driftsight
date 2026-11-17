"""질의 API — 스팬 4종(부모 관계)·버전 3종 부착·오류 코드 (telemetry.md > 3.1·3.2, api.md > 0.5)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.rag.generate import Generator, LlmUnavailableError, ModelConfig, PromptTemplate
from src.rag.main import RagRuntime, create_app
from src.rag.retrieve import RetrievalConfig, Retriever, VectorIndex
from src.shared.models.enums import VersionKind
from src.shared.versioning import VersionContext, VersionRef
from tests.rag.fakes import HashEmbedder
from tests.rag.test_generate import FakeClient

VERSIONS = VersionContext(
    prompt=VersionRef(11, VersionKind.PROMPT, "rag-qa-v1", "h1"),
    model=VersionRef(12, VersionKind.MODEL, "rag-gen-v1", "h2"),
    retrieval=VersionRef(13, VersionKind.RETRIEVAL, "rag-retrieval-v1", "h3"),
)


def _runtime(provider: TracerProvider, client: FakeClient) -> RagRuntime:
    index = VectorIndex(HashEmbedder(), RetrievalConfig(top_k=2, chunk_size=20))
    index.build([{"doc_id": "d1", "text": "paris is the capital of france"}])
    tracer = provider.get_tracer("t")
    return RagRuntime(
        retriever=Retriever(index, tracer),
        generator=Generator(
            client,
            ModelConfig("anthropic", "claude-haiku-4-5-20251001", 64),
            tracer_provider=provider,
        ),
        template=PromptTemplate("rag-qa-v1", "{contexts}\n{question}"),
        versions=VERSIONS,
        service_name="rag",
        tracer=tracer,
    )


@pytest_asyncio.fixture
async def setup() -> AsyncIterator[tuple[FastAPI, InMemorySpanExporter, FakeClient]]:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    client = FakeClient()
    app = create_app(_runtime(provider, client))
    async with app.router.lifespan_context(app):
        yield app, memory, client


async def _post(app: FastAPI, json: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://rag") as http:
        return await http.post("/chat", json=json)


@pytest.mark.asyncio
async def test_chat_emits_four_spans_with_versions(
    setup: tuple[FastAPI, InMemorySpanExporter, FakeClient],
) -> None:
    app, memory, _ = setup

    resp = await _post(app, {"question": "capital of france?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Paris."
    spans = {s.name: s for s in memory.get_finished_spans()}
    assert set(spans) == {"rag.request", "rag.retrieve", "rag.build_prompt", "gen_ai.chat"}
    root = spans["rag.request"]
    assert format(root.context.trace_id, "032x") == body["traceId"]
    for child in ("rag.retrieve", "rag.build_prompt", "gen_ai.chat"):
        assert spans[child].parent is not None
        assert spans[child].parent.span_id == root.context.span_id
    attrs = dict(root.attributes or {})
    assert attrs["app.version.prompt_id"] == 11
    assert attrs["app.version.model_id"] == 12
    assert attrs["app.version.retrieval_id"] == 13
    assert attrs["app.content.question"] == "capital of france?"
    assert attrs["app.content.answer"] == "Paris."
    assert attrs["http.response.status_code"] == 200
    assert attrs["http.route"] == "/chat"


@pytest.mark.asyncio
async def test_empty_question_is_400(
    setup: tuple[FastAPI, InMemorySpanExporter, FakeClient],
) -> None:
    app, _, _ = setup

    resp = await _post(app, {"question": ""})

    assert resp.status_code == 400
    assert resp.json() == {"error": "INVALID_REQUEST", "fields": ["question"]}


@pytest.mark.asyncio
async def test_llm_unavailable_is_503_without_answer(
    setup: tuple[FastAPI, InMemorySpanExporter, FakeClient],
) -> None:
    app, memory, client = setup
    client.errors = [LlmUnavailableError("down")]  # Generator 재시도 밖에서 바로 실패

    resp = await _post(app, {"question": "q"})

    assert resp.status_code == 503
    assert resp.json() == {"error": "EXTERNAL_API_UNAVAILABLE"}
    root = next(s for s in memory.get_finished_spans() if s.name == "rag.request")
    attrs = dict(root.attributes or {})
    assert attrs["http.response.status_code"] == 503
    assert attrs["exception.type"] == "LlmUnavailableError"
    assert "app.content.answer" not in attrs
