"""RAG 질의 API (:8000) — `rag.request` 루트 스팬 아래 검색·조립·생성 (telemetry.md > 3.1·3.2).

- `POST /chat {question}` → `{answer, traceId}`. traceId가 수집 후 `traces.trace_id`가 된다
- 오류 코드: api.md > 0.5 (400 INVALID_REQUEST · 502 EXTERNAL_API_ERROR ·
  503 EXTERNAL_API_UNAVAILABLE · 500 INTERNAL_ERROR). 내부 예외 메시지는 응답에 넣지 않는다
- 기동 시 설정 파일을 버전으로 등록한다. DB가 없어도 서비스는 응답한다(계측 버전 id만 빠짐)
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from src.rag.generate import (
    AnthropicClient,
    Generator,
    LlmCallError,
    LlmUnavailableError,
    ModelConfig,
    PromptTemplate,
    build_prompt,
)
from src.rag.retrieve import (
    RetrievalConfig,
    Retriever,
    SentenceTransformerEmbedder,
    VectorIndex,
    load_corpus_jsonl,
)
from src.sdk import attributes as A
from src.sdk import semconv
from src.sdk.attributes import content_attributes, sanitize, version_attributes
from src.sdk.tracer import setup_tracing
from src.shared.config import BaseAppSettings
from src.shared.db import get_sessionmaker, with_db_retry
from src.shared.version_registry import build_version_context, sync_versions
from src.shared.versioning import ConfigSnapshot, VersionContext, scan_configs

logger = logging.getLogger(__name__)

DEFAULTS_DIR = Path(__file__).parent / "defaults"
PROMPT_SOURCE = "prompts/rag-qa-v1.md"
MODEL_SOURCE = "models/rag-gen-v1.yaml"
RETRIEVAL_SOURCE = "retrieval/rag-retrieval-v1.yaml"
CHAT_ROUTE = "/chat"
# 단가표 기반 비용 계산(후속 작업) 전까지 비용 0, 단가표 버전 없음
UNPRICED = "unpriced"


class RagSettings(BaseAppSettings):
    """RAG 서비스 설정 — 변수명은 docs/ops/env-setup.md."""

    anthropic_api_key: SecretStr | None = None
    llm_gen_model: str | None = None  # 원본은 버전 관리 모델 설정 (policies.md 미결정 P-8)
    embedding_repo: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str | None = None
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4318"
    otel_service_name: str = "rag"
    configs_dir: Path = Path("configs")
    rag_corpus_path: Path | None = None


@dataclass
class RagRuntime:
    retriever: Retriever
    generator: Generator
    template: PromptTemplate
    versions: VersionContext | None
    service_name: str
    tracer: trace.Tracer


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=32_000)


class ChatResponse(BaseModel):
    answer: str
    traceId: str  # noqa: N815 — API 응답은 camelCase (api.md > 0.1)


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code})


def _snapshots(settings: RagSettings) -> tuple[list[ConfigSnapshot], dict[str, ConfigSnapshot]]:
    """저장소 configs/ + RAG 기본 설정을 스냅샷으로. source_path는 공통 상위 기준."""
    dirs = [d for d in (settings.configs_dir, DEFAULTS_DIR) if d.is_dir()]
    root = Path(os.path.commonpath([d.resolve() for d in dirs]))
    snaps = scan_configs(dirs, root=root)
    defaults_rel = DEFAULTS_DIR.resolve().relative_to(root).as_posix()
    by_source = {s.source_path.removeprefix(f"{defaults_rel}/"): s for s in snaps}
    return snaps, by_source


async def _register_versions(
    snaps: list[ConfigSnapshot], by_source: dict[str, ConfigSnapshot], actor: str
) -> VersionContext | None:
    async def op() -> VersionContext:
        async with get_sessionmaker()() as session, session.begin():
            refs = await sync_versions(session, snaps, actor=actor)
        refs_by_short = {k: refs[s.source_path] for k, s in by_source.items()}
        return build_version_context(
            refs_by_short, prompt=PROMPT_SOURCE, model=MODEL_SOURCE, retrieval=RETRIEVAL_SOURCE
        )

    try:
        return await with_db_retry(op)
    except Exception as exc:  # noqa: BLE001 — 감시가 감시 대상을 멈추지 않는다 (policies.md > 6.2)
        logger.warning("version registration skipped: %s", type(exc).__name__)
        return None


async def build_runtime(settings: RagSettings) -> RagRuntime:
    snaps, by_source = _snapshots(settings)
    template = PromptTemplate(
        by_source[PROMPT_SOURCE].name, str(by_source[PROMPT_SOURCE].config["text"])
    )
    model_cfg = ModelConfig.from_config(by_source[MODEL_SOURCE].config)
    retrieval_cfg = RetrievalConfig.from_config(by_source[RETRIEVAL_SOURCE].config)

    provider = setup_tracing(settings.otel_service_name, settings.otel_exporter_otlp_endpoint)
    index = VectorIndex(
        SentenceTransformerEmbedder(settings.embedding_repo, settings.embedding_revision),
        retrieval_cfg,
    )
    if settings.rag_corpus_path and settings.rag_corpus_path.is_file():
        index.build(load_corpus_jsonl(settings.rag_corpus_path))
    else:
        logger.warning("RAG corpus not found — answering without context")
    if settings.anthropic_api_key is None:
        raise RuntimeError("ANTHROPIC_API_KEY is required for the RAG service")
    client = AnthropicClient(
        settings.anthropic_api_key.get_secret_value(), settings.llm_timeout_seconds
    )
    return RagRuntime(
        retriever=Retriever(index, provider.get_tracer("aisv.rag")),
        generator=Generator(client, model_cfg, tracer_provider=provider),
        template=template,
        versions=await _register_versions(snaps, by_source, settings.otel_service_name),
        service_name=settings.otel_service_name,
        tracer=provider.get_tracer("aisv.rag"),
    )


def _version_attrs(runtime: RagRuntime) -> dict[str, object]:
    v = runtime.versions
    if v is None:
        return {A.VERSION_PROMPT: runtime.template.name}
    return dict(
        version_attributes(
            prompt=v.prompt.name,
            model=v.model.name,
            retrieval=v.retrieval.name,
            prompt_id=v.prompt.id,
            model_id=v.model.id,
            retrieval_id=v.retrieval.id,
        )
    )


def create_app(runtime: RagRuntime | None = None) -> FastAPI:
    """`runtime`을 주면 그대로 쓰고(테스트), 없으면 기동 시 설정에서 만든다."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime or await build_runtime(RagSettings())  # type: ignore[call-arg]
        yield

    app = FastAPI(title="aisv-rag", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()]
        return JSONResponse(status_code=400, content={"error": "INVALID_REQUEST", "fields": fields})

    @app.post(CHAT_ROUTE, response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
        rt: RagRuntime = request.app.state.runtime
        with rt.tracer.start_as_current_span(
            "rag.request", kind=SpanKind.SERVER, record_exception=False
        ) as span:
            span.set_attributes(
                sanitize(
                    {
                        semconv.HTTP_REQUEST_METHOD: "POST",
                        semconv.HTTP_ROUTE: CHAT_ROUTE,
                        semconv.SERVICE_NAME: rt.service_name,
                        A.COST_USD: 0.0,
                        A.COST_PRICING_VERSION: UNPRICED,
                        **_version_attrs(rt),  # type: ignore[dict-item]
                    }
                )
            )
            status: int = 200
            answer: str | None = None
            error: tuple[str, BaseException] | None = None
            try:
                hits = rt.retriever.retrieve(body.question)
                prompt = build_prompt(rt.template, body.question, hits, rt.tracer)
                answer = (await rt.generator.generate(prompt)).text
            except LlmUnavailableError as exc:
                status, error = 503, ("EXTERNAL_API_UNAVAILABLE", exc)
            except LlmCallError as exc:
                status, error = 502, ("EXTERNAL_API_ERROR", exc)
            except Exception as exc:  # noqa: BLE001 — 내부 오류는 메시지 없이 500
                status, error = 500, ("INTERNAL_ERROR", exc)
            span.set_attributes(
                sanitize(
                    {
                        semconv.HTTP_RESPONSE_STATUS_CODE: status,
                        **content_attributes(body.question, answer),
                    }
                )
            )
            if error is not None:
                code, failure = error
                span.set_attribute(semconv.EXCEPTION_TYPE, type(failure).__name__)
                span.set_status(Status(StatusCode.ERROR))
                logger.warning("chat failed: %s", type(failure).__name__)
                return _error(status, code)
            trace_id = format(span.get_span_context().trace_id, "032x")
        return ChatResponse(answer=answer or "", traceId=trace_id)

    return app


app = create_app()
