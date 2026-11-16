"""OTLP/HTTP JSON(`resourceSpans`) → 트레이스 단위 레코드 (api.md > 10.2 `traces[]` 모델).

Collector는 표준 OTLP만 보낸다(infra/otel-collector/config.yaml). 여기서 traceId별로 스팬을 묶고
루트 스팬(부모 없음)의 속성으로 `traces` 행을, 나머지로 `spans` 행을 만든다.
형식 위반은 `TraceRejected(reason)` — 그 트레이스만 거부하고 배치의 나머지는 저장한다.
"""

import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from src.shared.models.enums import SpanKind, TraceStatus

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
ROOT_SPAN_NAME = "rag.request"
STATUS_CODE_ERROR = 2  # OTLP Status.code


class TraceRejected(ValueError):
    def __init__(self, trace_id: str, reason: str) -> None:
        super().__init__(reason)
        self.trace_id = trace_id
        self.reason = reason


@dataclass(frozen=True)
class SpanRecord:
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    attributes: dict[str, Any]
    started_at: datetime
    ended_at: datetime


@dataclass
class TraceRecord:
    trace_id: str
    service_name: str
    question: str
    answer: str | None
    contexts: list[Any] | None
    provider: str
    model_name: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int
    prompt_version_id: int | None
    model_version_id: int | None
    retrieval_version_id: int | None
    injection_run_id: uuid.UUID | None
    status: str
    error_message: str | None
    started_at: datetime
    ended_at: datetime
    spans: list[SpanRecord] = field(default_factory=list)


def _value(v: dict[str, Any]) -> Any:
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])  # OTLP JSON은 int64를 문자열로 보낸다
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "arrayValue" in v:
        return [_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {a["key"]: _value(a.get("value", {})) for a in items or []}


def _time(nanos: str | int) -> datetime:
    return datetime.fromtimestamp(int(nanos) / 1_000_000_000, tz=UTC)


def _span_kind(name: str) -> str:
    if name == "rag.retrieve":
        return SpanKind.RETRIEVAL.value
    if name == "rag.build_prompt":
        return SpanKind.PROMPT.value
    if name.startswith("gen_ai."):
        return SpanKind.LLM.value
    return SpanKind.OTHER.value


def _opt_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _opt_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def group_spans(body: dict[str, Any]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """traceId → [(service.name, OTLP span)]. 순서는 수신 순서."""
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for rs in body.get("resourceSpans", []):
        service = str(_attrs(rs.get("resource", {}).get("attributes")).get("service.name", ""))
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                grouped[str(span.get("traceId", "")).lower()].append((service, span))
    return grouped


def _span_record(trace_id: str, span: dict[str, Any]) -> SpanRecord:
    span_id = str(span.get("spanId", "")).lower()
    parent = str(span.get("parentSpanId", "") or "").lower() or None
    if not _HEX16.match(span_id) or (parent and not _HEX16.match(parent)):
        raise TraceRejected(trace_id, "INVALID_SPAN_ID")
    try:
        started, ended = _time(span["startTimeUnixNano"]), _time(span["endTimeUnixNano"])
    except (KeyError, ValueError) as exc:
        raise TraceRejected(trace_id, "INVALID_TIMESTAMP") from exc
    name = str(span.get("name", ""))[:100]
    return SpanRecord(
        span_id, parent, name, _span_kind(name), _attrs(span.get("attributes")), started, ended
    )


def build_trace(trace_id: str, items: list[tuple[str, dict[str, Any]]]) -> TraceRecord:
    """한 traceId의 스팬들로 트레이스 레코드를 만든다."""
    if not _HEX32.match(trace_id):
        raise TraceRejected(trace_id, "INVALID_TRACE_ID")
    roots = [(svc, s) for svc, s in items if not s.get("parentSpanId")]
    if len(roots) != 1:
        raise TraceRejected(trace_id, "ROOT_SPAN_MISSING")
    service, root_raw = roots[0]
    spans = [_span_record(trace_id, s) for _, s in items]
    root = next(s for s in spans if s.parent_span_id is None)
    attrs = root.attributes

    question = attrs.get("app.content.question")
    if not isinstance(question, str) or not question:
        raise TraceRejected(trace_id, "MISSING_QUESTION")
    if root.ended_at < root.started_at:
        raise TraceRejected(trace_id, "INVALID_TIMESTAMP")

    llm = next((s.attributes for s in spans if s.kind == SpanKind.LLM.value), {})
    retrieve = next((s.attributes for s in spans if s.kind == SpanKind.RETRIEVAL.value), {})
    try:
        contexts = json.loads(retrieve["app.content.contexts"]) if retrieve else None
    except (KeyError, TypeError, json.JSONDecodeError):
        contexts = None

    status_code = attrs.get("http.response.status_code")
    failed = root_raw.get("status", {}).get("code") == STATUS_CODE_ERROR or (
        isinstance(status_code, int) and status_code >= 400
    )
    answer = attrs.get("app.content.answer")
    return TraceRecord(
        trace_id=trace_id,
        service_name=(service or str(attrs.get("service.name", "unknown")))[:100],
        question=question,
        answer=answer if isinstance(answer, str) else None,
        contexts=contexts if isinstance(contexts, list) else None,
        provider=str(llm.get("gen_ai.provider.name", "unknown"))[:50],
        model_name=str(
            llm.get("gen_ai.response.model") or llm.get("gen_ai.request.model") or "unknown"
        )[:100],
        input_tokens=max(int(llm.get("gen_ai.usage.input_tokens", 0) or 0), 0),
        output_tokens=max(int(llm.get("gen_ai.usage.output_tokens", 0) or 0), 0),
        cost_usd=max(Decimal(str(attrs.get("app.cost.usd", 0) or 0)), Decimal(0)),
        latency_ms=int((root.ended_at - root.started_at).total_seconds() * 1000),
        prompt_version_id=_opt_int(attrs.get("app.version.prompt_id")),
        model_version_id=_opt_int(attrs.get("app.version.model_id")),
        retrieval_version_id=_opt_int(attrs.get("app.version.retrieval_id")),
        injection_run_id=_opt_uuid(attrs.get("app.injection.run_id")),
        status=TraceStatus.ERROR.value if failed or answer is None else TraceStatus.OK.value,
        error_message=attrs.get("exception.type") if failed else None,
        started_at=root.started_at,
        ended_at=root.ended_at,
        spans=spans,
    )


def parse_batch(body: dict[str, Any]) -> tuple[list[TraceRecord], list[TraceRejected]]:
    """배치 → (정상 레코드, 거부 목록)."""
    records: list[TraceRecord] = []
    rejected: list[TraceRejected] = []
    for trace_id, items in group_spans(body).items():
        try:
            records.append(build_trace(trace_id, items))
        except TraceRejected as exc:
            rejected.append(exc)
    return records, rejected
