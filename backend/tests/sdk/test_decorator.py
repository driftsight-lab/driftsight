"""`@trace_llm` — 스팬 이름·kind·속성, 실패 경로, 계측이 결과를 바꾸지 않음 (telemetry.md > 3.5)."""

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from src.sdk.decorator import LlmResult, trace_llm

RESULT = LlmResult(
    text="answer",
    input_tokens=12,
    output_tokens=34,
    response_model="claude-haiku-4-5-20251001",
    finish_reasons=("end_turn",),
)


@pytest.fixture
def spans() -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    yield provider, memory
    provider.shutdown()


@pytest.mark.asyncio
async def test_records_gen_ai_attributes(
    spans: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = spans

    @trace_llm(provider="anthropic", tracer_provider=provider)
    async def generate(prompt: str, *, model: str, max_tokens: int) -> LlmResult:
        return RESULT

    result = await generate("hi", model="claude-haiku", max_tokens=256)

    assert result is RESULT  # 계측이 반환값을 바꾸지 않는다
    (span,) = memory.get_finished_spans()
    assert span.name == "gen_ai.chat"
    assert span.kind == SpanKind.CLIENT
    attrs = dict(span.attributes or {})
    assert attrs["gen_ai.provider.name"] == "anthropic"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "claude-haiku"
    assert attrs["gen_ai.request.max_tokens"] == 256
    assert "gen_ai.request.temperature" not in attrs  # 인자가 없으면 기록하지 않는다
    assert attrs["gen_ai.response.model"] == "claude-haiku-4-5-20251001"
    assert attrs["gen_ai.response.finish_reasons"] == ("end_turn",)
    assert attrs["gen_ai.usage.input_tokens"] == 12
    assert attrs["gen_ai.usage.output_tokens"] == 34
    assert attrs["app.cost.usd"] == 0.0
    assert "hi" not in attrs.values()  # 프롬프트 원문은 gen_ai.chat에 남기지 않는다


@pytest.mark.asyncio
async def test_error_records_type_only_and_reraises(
    spans: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = spans

    @trace_llm(provider="anthropic", tracer_provider=provider)
    async def generate(*, model: str) -> LlmResult:
        raise TimeoutError("user question leaked here")

    with pytest.raises(TimeoutError):
        await generate(model="claude-haiku")

    (span,) = memory.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR
    assert dict(span.attributes or {})["exception.type"] == "TimeoutError"
    assert not span.events  # 예외 메시지·스택을 이벤트로 남기지 않는다
    assert "leaked" not in str(span.attributes)


@pytest.mark.asyncio
async def test_operation_sets_span_name(
    spans: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, memory = spans

    @trace_llm(provider="anthropic", operation="text_completion", tracer_provider=provider)
    async def generate() -> LlmResult:
        return RESULT

    await generate()

    assert memory.get_finished_spans()[0].name == "gen_ai.text_completion"
