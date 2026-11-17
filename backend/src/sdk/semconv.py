"""OTel 시맨틱 컨벤션 매핑 계층 (ADR-002, telemetry.md > 9. 표준 변경 대응).

표준 속성 키(`gen_ai.*`, `http.*`)는 이 파일에서만 정의한다. 표준이 바뀌면 이 파일만 고친다.
자체 속성(`app.*`)은 표준과 독립이므로 `attributes.py`에 둔다.
"""

from pathlib import Path

# 적용 리비전 — 원본은 configs/otel/semconv.lock (telemetry.md > 9, ADR-002).
# 매핑 계층(이 파일)과 lock이 다르면 기동 시 검증에서 멈춘다.
SEMCONV_VERSION = "1.44.0"
SEMCONV_LOCK = Path("otel") / "semconv.lock"
SEMCONV_SCHEMA_URL = f"https://opentelemetry.io/schemas/{SEMCONV_VERSION}"

# gen_ai.* (telemetry.md > 3.5 · 4. 속성 표)
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# 공통
SERVICE_NAME = "service.name"
EXCEPTION_TYPE = "exception.type"
HTTP_REQUEST_METHOD = "http.request.method"
HTTP_ROUTE = "http.route"
HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"


def check_semconv_lock(configs_dir: Path) -> None:
    """`configs/otel/semconv.lock`의 리비전이 매핑 계층과 같은지 확인한다.

    리비전이 바뀌었는데 매핑을 고치지 않으면 속성 이름이 어긋난 데이터가 쌓인다(telemetry.md > 9).
    """
    lock = configs_dir / SEMCONV_LOCK
    pinned = lock.read_text(encoding="utf-8").strip()
    if pinned != SEMCONV_VERSION:
        raise RuntimeError(f"semconv lock {pinned!r} != SDK mapping {SEMCONV_VERSION!r}")
