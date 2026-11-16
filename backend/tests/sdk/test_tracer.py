"""트레이서·전송 — 배치 설정, 실패 2회 재시도 후 드롭, 예외 비전파 (telemetry.md > 2.3)."""

from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.sdk.semconv import SEMCONV_SCHEMA_URL
from src.sdk.tracer import (
    BATCH_MAX_QUEUE_SIZE,
    BATCH_SCHEDULE_DELAY_MS,
    DroppingRetryExporter,
    build_tracer_provider,
)


class _FlakyExporter(SpanExporter):
    def __init__(self, failures: int, raise_error: bool = False) -> None:
        self.failures = failures
        self.raise_error = raise_error
        self.calls = 0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.calls += 1
        if self.calls <= self.failures:
            if self.raise_error:
                raise ConnectionError("collector down")
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS


def test_retry_then_success() -> None:
    inner, delays = _FlakyExporter(failures=2), []
    exporter = DroppingRetryExporter(inner, sleep=delays.append)

    assert exporter.export([]) == SpanExportResult.SUCCESS
    assert inner.calls == 3
    assert delays == [1.0, 3.0]


def test_drop_after_two_retries_without_raising() -> None:
    inner, delays = _FlakyExporter(failures=10, raise_error=True), []
    exporter = DroppingRetryExporter(inner, sleep=delays.append)

    assert exporter.export([]) == SpanExportResult.FAILURE  # 예외가 밖으로 나오지 않는다
    assert inner.calls == 3
    assert delays == [1.0, 3.0]


def test_provider_uses_batch_processor_settings() -> None:
    provider = build_tracer_provider("rag", InMemorySpanExporter())
    processor = provider._active_span_processor._span_processors[0]  # noqa: SLF001

    assert isinstance(processor, BatchSpanProcessor)
    assert processor._batch_processor._schedule_delay == BATCH_SCHEDULE_DELAY_MS / 1000  # noqa: SLF001
    assert processor._batch_processor._max_queue_size == BATCH_MAX_QUEUE_SIZE  # noqa: SLF001
    assert provider.resource.attributes["service.name"] == "rag"
    assert provider.resource.schema_url == SEMCONV_SCHEMA_URL
    provider.shutdown()


def test_span_is_exported_after_flush() -> None:
    memory = InMemorySpanExporter()
    provider = build_tracer_provider("rag", memory)

    with provider.get_tracer("t").start_as_current_span("gen_ai.chat"):
        pass
    provider.force_flush()

    assert [s.name for s in memory.get_finished_spans()] == ["gen_ai.chat"]
    provider.shutdown()
