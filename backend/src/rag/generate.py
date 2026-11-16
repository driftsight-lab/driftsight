"""프롬프트 조립(`rag.build_prompt`)과 Claude 생성 호출(`gen_ai.chat`) — telemetry.md > 3.4 · 3.5.

- 생성은 소형 모델, 타임아웃 30초 (policies.md > 2.1 LLM 호출 타임아웃)
- 재시도: 429·5xx·타임아웃·연결 오류만 2회(1s → 3s), 4xx는 즉시 실패 (policies.md > 6.1)
- `temperature`는 보내지 않는다: anthropic 2.x API는 받지 않는다
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from opentelemetry import trace
from opentelemetry.trace import Tracer

from src.rag.retrieve import RetrievedChunk
from src.sdk import attributes as A
from src.sdk.attributes import sanitize
from src.sdk.decorator import LlmResult, trace_llm

GENERATION_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 3.0)


class LlmUnavailableError(RuntimeError):
    """재시도 후에도 타임아웃·429·5xx — `EXTERNAL_API_UNAVAILABLE`(503)."""


class LlmCallError(RuntimeError):
    """재시도 대상이 아닌 4xx — `EXTERNAL_API_ERROR`(502)."""


@dataclass(frozen=True)
class ModelConfig:
    """버전 관리 대상 모델 설정 (kind=model)."""

    provider: str
    model: str
    max_tokens: int

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ModelConfig":
        return cls(str(config["provider"]), str(config["model"]), int(config["max_tokens"]))


@dataclass(frozen=True)
class PromptTemplate:
    """버전 관리 대상 프롬프트 (kind=prompt). `{question}`·`{contexts}` 자리표시자."""

    name: str
    text: str

    @property
    def template_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def format_contexts(chunks: Sequence[RetrievedChunk]) -> str:
    if not chunks:
        return "(none)"
    return "\n\n".join(f"[{i}] {c.text}" for i, c in enumerate(chunks, 1))


def build_prompt(
    template: PromptTemplate, question: str, chunks: Sequence[RetrievedChunk], tracer: Tracer
) -> str:
    with tracer.start_as_current_span("rag.build_prompt") as span:
        prompt = template.text.replace("{contexts}", format_contexts(chunks)).replace(
            "{question}", question
        )
        span.set_attributes(
            sanitize(
                {
                    A.VERSION_PROMPT: template.name,
                    A.PROMPT_TEMPLATE_HASH: template.template_hash,
                    A.PROMPT_CHAR_COUNT: len(prompt),
                }
            )
        )
        return prompt


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    response_model: str | None
    finish_reasons: tuple[str, ...]


class LlmClient(Protocol):
    async def complete(self, *, prompt: str, model: str, max_tokens: int) -> Completion: ...


class RetryableLlmError(Exception):
    """클라이언트 구현이 재시도 가능 오류(429·5xx·타임아웃·연결)를 알릴 때 쓴다."""


class AnthropicClient:
    """Anthropic Messages API. 재시도는 `Generator`가 하므로 SDK 자체 재시도는 끈다."""

    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=0
        )

    async def complete(self, *, prompt: str, model: str, max_tokens: int) -> Completion:
        a = self._anthropic
        try:
            msg = await self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except (a.APITimeoutError, a.APIConnectionError, a.RateLimitError) as exc:
            raise RetryableLlmError(type(exc).__name__) from exc
        except a.APIStatusError as exc:
            if exc.status_code >= 500:
                raise RetryableLlmError(f"HTTP {exc.status_code}") from exc
            raise LlmCallError(f"HTTP {exc.status_code}") from exc
        text = "".join(getattr(block, "text", "") for block in msg.content)
        return Completion(
            text=text,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            response_model=msg.model,
            finish_reasons=(msg.stop_reason,) if msg.stop_reason else (),
        )


class Generator:
    """`gen_ai.chat` 스팬을 남기며 생성한다. 재시도 횟수는 `app.llm.retry_count`로 기록."""

    def __init__(
        self,
        client: LlmClient,
        model_config: ModelConfig,
        *,
        tracer_provider: trace.TracerProvider | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.client = client
        self.model_config = model_config
        self._sleep = sleep
        self._call = trace_llm(provider=model_config.provider, tracer_provider=tracer_provider)(
            self._complete_with_retry
        )

    async def _complete_with_retry(self, prompt: str, *, model: str, max_tokens: int) -> LlmResult:
        retries = 0
        while True:
            try:
                c = await self.client.complete(prompt=prompt, model=model, max_tokens=max_tokens)
                break
            except RetryableLlmError as exc:
                if retries >= len(GENERATION_RETRY_DELAYS_SECONDS):
                    raise LlmUnavailableError(str(exc)) from exc
                await self._sleep(GENERATION_RETRY_DELAYS_SECONDS[retries])
                retries += 1
        return LlmResult(
            text=c.text,
            input_tokens=c.input_tokens,
            output_tokens=c.output_tokens,
            response_model=c.response_model,
            finish_reasons=c.finish_reasons,
            retry_count=retries,
        )

    async def generate(self, prompt: str) -> LlmResult:
        cfg = self.model_config
        return await self._call(prompt, model=cfg.model, max_tokens=cfg.max_tokens)
