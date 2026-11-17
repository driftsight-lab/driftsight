"""테스트용 OTLP/HTTP JSON 생성 — Collector `encoding: json` 출력과 같은 모양."""

import json
import uuid
from typing import Any

T0 = 1_794_864_000_000_000_000  # ns


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        v: dict[str, Any] = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    elif isinstance(value, list):
        v = {"arrayValue": {"values": [{"stringValue": str(x)} for x in value]}}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


def span(
    trace_id: str,
    name: str,
    *,
    span_id: str | None = None,
    parent: str | None = None,
    attrs: dict[str, Any] | None = None,
    start_ms: int = 0,
    end_ms: int = 100,
    error: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id or uuid.uuid4().hex[:16],
        "name": name,
        "kind": 2,
        "startTimeUnixNano": str(T0 + start_ms * 1_000_000),
        "endTimeUnixNano": str(T0 + end_ms * 1_000_000),
        "attributes": [_attr(k, v) for k, v in (attrs or {}).items()],
        "status": {"code": 2} if error else {},
    }
    if parent:
        out["parentSpanId"] = parent
    return out


def rag_trace(
    trace_id: str | None = None,
    *,
    versions: tuple[int, int, int] | None = (1, 2, 3),
    answer: str | None = "Paris.",
    status_code: int = 200,
) -> list[dict[str, Any]]:
    """`rag.request` 루트 + retrieve·build_prompt·gen_ai.chat 자식 4개."""
    tid = trace_id or uuid.uuid4().hex
    root_id = uuid.uuid4().hex[:16]
    root_attrs: dict[str, Any] = {
        "app.content.question": "capital of france?",
        "http.response.status_code": status_code,
        "app.cost.usd": 0.0,
    }
    if answer is not None:
        root_attrs["app.content.answer"] = answer
    if versions:
        root_attrs |= dict(
            zip(
                ("app.version.prompt_id", "app.version.model_id", "app.version.retrieval_id"),
                versions,
                strict=True,
            )
        )
    contexts = json.dumps([{"doc_id": "d1", "text": "paris is the capital"}])
    return [
        span(
            tid,
            "rag.request",
            span_id=root_id,
            attrs=root_attrs,
            end_ms=900,
            error=status_code >= 400,
        ),
        span(
            tid,
            "rag.retrieve",
            parent=root_id,
            attrs={"app.content.contexts": contexts, "app.retrieval.top_k": 4},
            start_ms=10,
            end_ms=50,
        ),
        span(tid, "rag.build_prompt", parent=root_id, start_ms=50, end_ms=60),
        span(
            tid,
            "gen_ai.chat",
            parent=root_id,
            start_ms=60,
            end_ms=850,
            attrs={
                "gen_ai.provider.name": "anthropic",
                "gen_ai.request.model": "claude-haiku",
                "gen_ai.response.model": "claude-haiku-4-5-20251001",
                "gen_ai.usage.input_tokens": 120,
                "gen_ai.usage.output_tokens": 8,
            },
        ),
    ]


def payload(*spans_lists: list[dict[str, Any]], service: str = "rag") -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [_attr("service.name", service)]},
                "scopeSpans": [
                    {
                        "scope": {"name": "aisv.rag"},
                        "spans": [s for spans in spans_lists for s in spans],
                    }
                ],
            }
        ]
    }
