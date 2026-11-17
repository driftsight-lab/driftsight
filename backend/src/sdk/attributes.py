"""자체 속성(`app.*`)과 본문 크기 상한·금지 속성 (telemetry.md > 4.2 · 4.3 · 4.4).

표준 키는 `semconv.py`, 자체 키는 이 파일에 둔다 (ADR-002).
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from opentelemetry.util.types import AttributeValue

# app.* (telemetry.md > 4.2)
VERSION_PROMPT = "app.version.prompt"
VERSION_MODEL = "app.version.model"
VERSION_RETRIEVAL = "app.version.retrieval"
VERSION_PROMPT_ID = "app.version.prompt_id"
VERSION_MODEL_ID = "app.version.model_id"
VERSION_RETRIEVAL_ID = "app.version.retrieval_id"
CONTENT_QUESTION = "app.content.question"
CONTENT_ANSWER = "app.content.answer"
CONTENT_CONTEXTS = "app.content.contexts"
COST_USD = "app.cost.usd"
COST_PRICING_VERSION = "app.cost.pricing_version"
LLM_RETRY_COUNT = "app.llm.retry_count"
INJECTION_RUN_ID = "app.injection.run_id"
RETRIEVAL_TOP_K = "app.retrieval.top_k"
RETRIEVAL_CHUNK_SIZE = "app.retrieval.chunk_size"
RETRIEVAL_DOC_COUNT = "app.retrieval.doc_count"
RETRIEVAL_DOC_IDS = "app.retrieval.doc_ids"
RETRIEVAL_TOP_SCORE = "app.retrieval.top_score"
PROMPT_TEMPLATE_HASH = "app.prompt.template_hash"
PROMPT_CHAR_COUNT = "app.prompt.char_count"
TRACE_REF = "app.trace_ref"

# telemetry.md > 4.3 본문 속성 크기 상한 (UTF-8 바이트)
QUESTION_MAX_BYTES = 8 * 1024
ANSWER_MAX_BYTES = 32 * 1024
CONTEXTS_MAX_BYTES = 128 * 1024

# telemetry.md > 4.4 금지 속성 — 비밀값·사용자 식별자·예외 메시지 원문
# 토큰 "수"(gen_ai.usage.input_tokens 등)는 허용하고, 자격 증명 토큰만 막는다.
_FORBIDDEN_KEY = re.compile(
    r"(api[_.-]?key|(access|auth|bearer|refresh|session|id)[_.-]?token|secret|password"
    r"|authorization|webhook|cookie|client\.address|user\.(id|ip)"
    r"|exception\.message|exception\.stacktrace)",
    re.IGNORECASE,
)


def truncate_utf8(text: str, max_bytes: int) -> tuple[str, bool]:
    """UTF-8 바이트 상한으로 뒤를 자른다. 멀티바이트 문자를 깨지 않는다."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def content_attributes(question: str, answer: str | None) -> dict[str, AttributeValue]:
    """`rag.request`의 질문·응답 본문. 상한 초과 시 `*_truncated=true`."""
    attrs: dict[str, AttributeValue] = {}
    q, q_cut = truncate_utf8(question, QUESTION_MAX_BYTES)
    attrs[CONTENT_QUESTION] = q
    if q_cut:
        attrs[f"{CONTENT_QUESTION}_truncated"] = True
    if answer is not None:  # 생성 실패 시 미기록 (telemetry.md > 3.2)
        a, a_cut = truncate_utf8(answer, ANSWER_MAX_BYTES)
        attrs[CONTENT_ANSWER] = a
        if a_cut:
            attrs[f"{CONTENT_ANSWER}_truncated"] = True
    return attrs


def contexts_attributes(contexts: Sequence[Mapping[str, Any]]) -> dict[str, AttributeValue]:
    """`rag.retrieve`의 검색 문맥 JSON. 상한 초과 시 문서 단위로 뒤에서부터 제외한다."""
    docs = list(contexts)
    truncated = False
    while True:
        payload = json.dumps(docs, ensure_ascii=False)
        if len(payload.encode("utf-8")) <= CONTEXTS_MAX_BYTES or not docs:
            break
        docs.pop()
        truncated = True
    attrs: dict[str, AttributeValue] = {CONTENT_CONTEXTS: payload}
    if truncated:
        attrs[f"{CONTENT_CONTEXTS}_truncated"] = True
    return attrs


def version_attributes(
    *,
    prompt: str,
    model: str,
    retrieval: str,
    prompt_id: int,
    model_id: int,
    retrieval_id: int,
) -> dict[str, AttributeValue]:
    """`rag.request`의 버전 3종 — 이름(사람용)과 `versions.id`(Ingest FK용)를 함께 기록."""
    return {
        VERSION_PROMPT: prompt,
        VERSION_MODEL: model,
        VERSION_RETRIEVAL: retrieval,
        VERSION_PROMPT_ID: prompt_id,
        VERSION_MODEL_ID: model_id,
        VERSION_RETRIEVAL_ID: retrieval_id,
    }


def sanitize(attrs: Mapping[str, AttributeValue | None]) -> dict[str, AttributeValue]:
    """금지 키와 None 값을 뺀다. 모든 스팬 속성은 기록 전에 이 함수를 거친다."""
    return {k: v for k, v in attrs.items() if v is not None and not _FORBIDDEN_KEY.search(k)}
