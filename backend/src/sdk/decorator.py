"""`@trace_llm` — LLM 호출을 `gen_ai.{operation}` CLIENT 스팬으로 감싼다 (telemetry.md > 3.5).

- 요청 속성(`model`·`max_tokens`·`temperature`)은 감싼 함수의 같은 이름 인자에서 읽는다.
- 응답 속성(토큰·응답 모델·종료 사유·비용)은 함수가 돌려준 `LlmResult`에서 읽는다.
- 계측 오류는 삼킨다. 예외는 `exception.type`만 남기고 원문 메시지는 기록하지 않는다 (4.4).
"""

import functools
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.util.types import AttributeValue

from src.sdk import semconv
from src.sdk.attributes import COST_USD, LLM_RETRY_COUNT, sanitize
from src.sdk.tracer import TRACER_NAME

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmResult:
    """계측 대상 LLM 호출의 반환값. 생성 함수는 이 형태로 결과를 돌려준다."""

    text: str
    input_tokens: int
    output_tokens: int
    response_model: str | None = None
    finish_reasons: tuple[str, ...] = ()
    cost_usd: float = 0.0  # 단가표 기반 계산은 후속 작업(S-4-3) — 그 전까지 0
    retry_count: int = 0


def _request_attributes(
    provider: str, operation: str, arguments: Mapping[str, Any]
) -> dict[str, AttributeValue | None]:
    return {
        semconv.GEN_AI_PROVIDER_NAME: provider,
        semconv.GEN_AI_OPERATION_NAME: operation,
        semconv.GEN_AI_REQUEST_MODEL: arguments.get("model"),
        semconv.GEN_AI_REQUEST_MAX_TOKENS: arguments.get("max_tokens"),
        semconv.GEN_AI_REQUEST_TEMPERATURE: arguments.get("temperature"),
    }


def _response_attributes(result: LlmResult) -> dict[str, AttributeValue | None]:
    return {
        semconv.GEN_AI_RESPONSE_MODEL: result.response_model,
        semconv.GEN_AI_RESPONSE_FINISH_REASONS: list(result.finish_reasons) or None,
        semconv.GEN_AI_USAGE_INPUT_TOKENS: result.input_tokens,
        semconv.GEN_AI_USAGE_OUTPUT_TOKENS: result.output_tokens,
        COST_USD: result.cost_usd,
        LLM_RETRY_COUNT: result.retry_count,
    }


def _safe_set(span: Span, attrs: Mapping[str, AttributeValue | None]) -> None:
    try:
        span.set_attributes(sanitize(attrs))
    except Exception as exc:  # noqa: BLE001 — 계측이 서비스 응답을 막지 않게 한다
        logger.warning("span attribute failed: %s", type(exc).__name__)


def _record_error(span: Span, exc: BaseException) -> None:
    _safe_set(span, {semconv.EXCEPTION_TYPE: type(exc).__name__})
    span.set_status(Status(StatusCode.ERROR))


def trace_llm[**P](
    *,
    provider: str,
    operation: str = "chat",
    tracer_provider: trace.TracerProvider | None = None,
) -> Callable[[Callable[P, Awaitable[LlmResult]]], Callable[P, Awaitable[LlmResult]]]:
    """async LLM 호출 함수에 `gen_ai.{operation}` 스팬을 붙인다."""
    span_name = f"gen_ai.{operation}"

    def decorate(
        fn: Callable[P, Awaitable[LlmResult]],
    ) -> Callable[P, Awaitable[LlmResult]]:
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> LlmResult:
            tracer = trace.get_tracer(TRACER_NAME, tracer_provider=tracer_provider)
            with tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
                record_exception=False,  # 예외 원문(메시지·스택)을 남기지 않는다
                set_status_on_exception=False,
            ) as span:
                try:
                    bound = signature.bind_partial(*args, **kwargs).arguments
                except TypeError:
                    bound = {}
                _safe_set(span, _request_attributes(provider, operation, bound))
                try:
                    result = await fn(*args, **kwargs)
                except BaseException as exc:
                    _record_error(span, exc)
                    raise
                _safe_set(span, _response_attributes(result))  # 토큰은 응답 후에만 안다
                return result

        return wrapper

    return decorate
