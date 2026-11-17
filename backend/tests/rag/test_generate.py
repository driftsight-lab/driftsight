"""프롬프트 조립·생성 — `rag.build_prompt`·`gen_ai.chat` 스팬, 재시도 정책 (policies.md > 6.1)."""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.rag.generate import (
    Completion,
    Generator,
    LlmCallError,
    LlmUnavailableError,
    ModelConfig,
    PromptTemplate,
    RetryableLlmError,
    build_prompt,
)
from src.rag.retrieve import RetrievedChunk

MODEL = ModelConfig(provider="anthropic", model="claude-haiku-4-5-20251001", max_tokens=64)
COMPLETION = Completion("Paris.", 10, 2, "claude-haiku-4-5-20251001", ("end_turn",))


class FakeClient:
    def __init__(self, errors: list[Exception] | None = None) -> None:
        self.errors = errors or []
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, prompt: str, model: str, max_tokens: int) -> Completion:
        self.calls.append({"prompt": prompt, "model": model, "max_tokens": max_tokens})
        if self.errors:
            raise self.errors.pop(0)
        return COMPLETION


@pytest.fixture
def otel() -> tuple[TracerProvider, InMemorySpanExporter]:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    return provider, memory


def test_build_prompt_fills_placeholders_and_records_span(
    otel: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = otel
    template = PromptTemplate("rag-qa-v1", "C:\n{contexts}\nQ: {question}")

    prompt = build_prompt(
        template, "where?", [RetrievedChunk("d1", "in paris", 0.9)], provider.get_tracer("t")
    )

    assert prompt == "C:\n[1] in paris\nQ: where?"
    attrs = dict(memory.get_finished_spans()[0].attributes or {})
    assert attrs["app.version.prompt"] == "rag-qa-v1"
    assert attrs["app.prompt.template_hash"] == template.template_hash
    assert attrs["app.prompt.char_count"] == len(prompt)


@pytest.mark.asyncio
async def test_generate_records_gen_ai_span(
    otel: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = otel
    client = FakeClient()

    result = await Generator(client, MODEL, tracer_provider=provider).generate("prompt")

    assert result.text == "Paris." and result.retry_count == 0
    assert client.calls == [{"prompt": "prompt", "model": MODEL.model, "max_tokens": 64}]
    (span,) = memory.get_finished_spans()
    attrs = dict(span.attributes or {})
    assert span.name == "gen_ai.chat"
    assert attrs["gen_ai.request.model"] == MODEL.model
    assert attrs["gen_ai.usage.output_tokens"] == 2


@pytest.mark.asyncio
async def test_retries_twice_then_succeeds(
    otel: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = otel
    delays: list[float] = []

    async def sleep(d: float) -> None:
        delays.append(d)

    client = FakeClient([RetryableLlmError("429"), RetryableLlmError("timeout")])
    result = await Generator(client, MODEL, tracer_provider=provider, sleep=sleep).generate("p")

    assert result.retry_count == 2
    assert delays == [1.0, 3.0]
    assert dict(memory.get_finished_spans()[0].attributes or {})["app.llm.retry_count"] == 2


@pytest.mark.asyncio
async def test_gives_up_after_two_retries() -> None:
    async def sleep(d: float) -> None:
        return None

    client = FakeClient([RetryableLlmError("5xx") for _ in range(3)])

    with pytest.raises(LlmUnavailableError):
        await Generator(client, MODEL, tracer_provider=TracerProvider(), sleep=sleep).generate("p")
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_client_error_is_not_retried() -> None:
    client = FakeClient([LlmCallError("HTTP 400")])

    with pytest.raises(LlmCallError):
        await Generator(client, MODEL, tracer_provider=TracerProvider()).generate("p")
    assert len(client.calls) == 1
