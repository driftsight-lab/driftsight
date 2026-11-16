"""트레이서 초기화와 배치 전송 (telemetry.md > 2.3 전송·버퍼 설정).

- `BatchSpanProcessor`: 5초 주기 또는 큐 512건 (policies.md > 2.1 OTLP 배치 전송 주기)
- 전송 실패: 2회 재시도(1s → 3s) 후 드롭. 서비스 응답을 막지 않는다 (policies.md > 6.1)
"""

import logging
import time
from collections.abc import Callable, Sequence

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from src.sdk.semconv import SEMCONV_SCHEMA_URL

logger = logging.getLogger(__name__)

TRACER_NAME = "aisv.sdk"
BATCH_SCHEDULE_DELAY_MS = 5_000
BATCH_MAX_QUEUE_SIZE = 512
EXPORT_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 3.0)


class DroppingRetryExporter(SpanExporter):
    """감싼 익스포터의 실패를 2회 재시도한 뒤 드롭한다. 예외를 밖으로 던지지 않는다."""

    def __init__(
        self,
        inner: SpanExporter,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner = inner
        self._sleep = sleep
        self.dropped_spans = 0

    def _try_export(self, spans: Sequence[ReadableSpan]) -> bool:
        try:
            return self._inner.export(spans) == SpanExportResult.SUCCESS
        except Exception as exc:  # noqa: BLE001 — 수집 실패가 서비스를 막지 않게 삼킨다
            logger.warning("span export failed: %s", type(exc).__name__)
            return False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._try_export(spans):
            return SpanExportResult.SUCCESS
        for delay in EXPORT_RETRY_DELAYS_SECONDS:
            self._sleep(delay)
            if self._try_export(spans):
                return SpanExportResult.SUCCESS
        self.dropped_spans += len(spans)
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


def build_tracer_provider(service_name: str, exporter: SpanExporter) -> TracerProvider:
    """서비스 이름과 익스포터로 배치 전송 TracerProvider를 만든다."""
    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: service_name}, schema_url=SEMCONV_SCHEMA_URL)
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            DroppingRetryExporter(exporter),
            schedule_delay_millis=BATCH_SCHEDULE_DELAY_MS,
            max_queue_size=BATCH_MAX_QUEUE_SIZE,
        )
    )
    return provider


def setup_tracing(service_name: str, otlp_endpoint: str) -> TracerProvider:
    """OTLP/HTTP로 Collector에 보내는 전역 TracerProvider를 설정한다.

    `otlp_endpoint`는 `OTEL_EXPORTER_OTLP_ENDPOINT`(예: http://otel-collector:4318).
    """
    exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint.rstrip('/')}/v1/traces")
    provider = build_tracer_provider(service_name, exporter)
    trace.set_tracer_provider(provider)
    return provider


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME, schema_url=SEMCONV_SCHEMA_URL)
