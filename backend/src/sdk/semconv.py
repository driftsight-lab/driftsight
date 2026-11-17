"""OTel 시맨틱 컨벤션 매핑 계층 (ADR-002, telemetry.md > 9. 표준 변경 대응).

표준 속성 키(`gen_ai.*`, `http.*`)는 이 파일에서만 정의한다. 표준이 바뀌면 이 파일만 고친다.
자체 속성(`app.*`)은 표준과 독립이므로 `attributes.py`에 둔다.
"""

# 적용 리비전 — telemetry.md > 9는 configs/otel/semconv.lock 고정을 정하지만, configs/는
# 양 파트 공동 소유(CODEOWNERS)라 lock 파일 생성은 후속 작업으로 두고 여기 상수로 고정한다.
SEMCONV_VERSION = "1.44.0"
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
