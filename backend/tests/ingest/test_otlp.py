"""OTLP JSON → 트레이스 레코드 — 실제 Collector 캡처·조립 규칙·거부 사유 (api.md > 10.2)."""

import json
import uuid
from decimal import Decimal
from pathlib import Path

from src.ingest.otlp import parse_batch
from tests.ingest.otlp_factory import payload, rag_trace, span

FIXTURE = Path(__file__).parent / "fixtures" / "collector_payload.json"


def test_real_collector_payload_is_parsed() -> None:
    # S-3-1에서 Collector 0.111.0이 실제로 보낸 본문 (rag.request + gen_ai.chat)
    records, rejected = parse_batch(json.loads(FIXTURE.read_text(encoding="utf-8")))

    assert rejected == []
    (rec,) = records
    assert rec.service_name == "rag"
    assert rec.question == "q?" and rec.answer == "a"
    assert rec.prompt_version_id == 1
    assert rec.input_tokens == 3
    assert {s.name for s in rec.spans} == {"rag.request", "gen_ai.chat"}


def test_full_trace_is_assembled() -> None:
    tid = uuid.uuid4().hex
    (rec,), rejected = parse_batch(payload(rag_trace(tid)))

    assert rejected == []
    assert rec.trace_id == tid
    assert rec.status == "OK"
    assert (rec.prompt_version_id, rec.model_version_id, rec.retrieval_version_id) == (1, 2, 3)
    assert rec.provider == "anthropic"
    assert rec.model_name == "claude-haiku-4-5-20251001"  # 실제 응답 모델 우선
    assert (rec.input_tokens, rec.output_tokens) == (120, 8)
    assert rec.cost_usd == Decimal("0.0")
    assert rec.latency_ms == 900
    assert rec.contexts == [{"doc_id": "d1", "text": "paris is the capital"}]
    kinds = {s.name: s.kind for s in rec.spans}
    assert kinds == {
        "rag.request": "OTHER",
        "rag.retrieve": "RETRIEVAL",
        "rag.build_prompt": "PROMPT",
        "gen_ai.chat": "LLM",
    }


def test_failed_request_becomes_error_trace() -> None:
    (rec,), _ = parse_batch(payload(rag_trace(answer=None, status_code=503)))

    assert rec.status == "ERROR"
    assert rec.answer is None


def test_missing_versions_are_null() -> None:
    (rec,), _ = parse_batch(payload(rag_trace(versions=None)))

    assert rec.prompt_version_id is None and rec.retrieval_version_id is None


def test_partial_batch_rejects_only_bad_traces() -> None:
    good = rag_trace()
    orphan_tid = uuid.uuid4().hex
    orphan = [span(orphan_tid, "gen_ai.chat", parent="a" * 16)]  # 루트가 다른 배치로 감
    no_question = [span(uuid.uuid4().hex, "rag.request", attrs={"http.response.status_code": 200})]
    bad_id = [span("not-hex", "rag.request", attrs={"app.content.question": "q"})]

    records, rejected = parse_batch(payload(good, orphan, no_question, bad_id))

    assert len(records) == 1
    reasons = {r.reason for r in rejected}
    assert reasons == {"ROOT_SPAN_MISSING", "MISSING_QUESTION", "INVALID_TRACE_ID"}
    assert next(r for r in rejected if r.reason == "ROOT_SPAN_MISSING").trace_id == orphan_tid
