"""계층 B 메트릭 — 플랫폼 자체 지표를 OTLP로 Collector에 보내 Prometheus로 노출한다.

- telemetry.md > 1.1: 계층 B(Ingest·Worker·Drift·Agent·Console)는 Metrics만 남긴다
- 전송 실패는 서비스에 영향을 주지 않는다(OTel SDK가 삼킨다)
- 레이블은 가짓수가 작은 값만 쓴다(telemetry.md > 5 레이블 설계 원칙)
"""

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from src.sdk.semconv import SEMCONV_SCHEMA_URL

METER_NAME = "aisv.platform"
EXPORT_INTERVAL_MS = 15_000  # Prometheus scrape_interval과 같은 주기


def setup_metrics(service_name: str, otlp_endpoint: str) -> MeterProvider:
    """OTLP/HTTP로 Collector에 보내는 전역 MeterProvider를 설정한다."""
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{otlp_endpoint.rstrip('/')}/v1/metrics"),
        export_interval_millis=EXPORT_INTERVAL_MS,
    )
    provider = MeterProvider(
        resource=Resource.create({SERVICE_NAME: service_name}, schema_url=SEMCONV_SCHEMA_URL),
        metric_readers=[reader],
    )
    metrics.set_meter_provider(provider)
    return provider
