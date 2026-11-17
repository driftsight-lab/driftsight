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
    batch = parse_batch(json.loads(FIXTURE.read_text(encoding="utf-8")))

    assert batch.rejected == [] and batch.orphans == []
    (rec,) = batch.records
    assert rec.service_name == "rag"
    assert rec.question == "q?" and rec.answer == "a"
    assert rec.prompt_version_id == 1
    assert rec.input_tokens == 3
    assert {s.name for s in rec.spans} == {"rag.request", "gen_ai.chat"}


def test_full_trace_is_assembled() -> None:
    tid = uuid.uuid4().hex
    batch = parse_batch(payload(rag_trace(tid)))
    (rec,) = batch.records

    assert batch.rejected == []
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
    (rec,) = parse_batch(payload(rag_trace(answer=None, status_code=503))).records

    assert rec.status == "ERROR"
    assert rec.answer is None


def test_missing_versions_are_null() -> None:
    (rec,) = parse_batch(payload(rag_trace(versions=None))).records

    assert rec.prompt_version_id is None and rec.retrieval_version_id is None


def test_partial_batch_rejects_only_bad_traces() -> None:
    good = rag_trace()
    orphan_tid = uuid.uuid4().hex
    orphan = [span(orphan_tid, "gen_ai.chat", parent="a" * 16)]  # 루트가 다른 배치로 감
    no_question = [span(uuid.uuid4().hex, "rag.request", attrs={"http.response.status_code": 200})]
    bad_id = [span("not-hex", "rag.request", attrs={"app.content.question": "q"})]

    batch = parse_batch(payload(good, orphan, no_question, bad_id))

    assert len(batch.records) == 1
    assert {r.reason for r in batch.rejected} == {"MISSING_QUESTION", "INVALID_TRACE_ID"}
    (o,) = batch.orphans  # 루트 없는 스팬은 거부 대신 지연 조립 대상으로 넘긴다
    assert o.trace_id == orphan_tid
    assert [s.name for s in o.spans] == ["gen_ai.chat"]


def test_auto_instrumented_spans_above_rag_request() -> None:
    # compose 검증에서 캡처: FastAPI(`POST /chat`, `fastapi.*`)·anthropic SDK 스팬이 함께 오고
    # `POST /chat`이 부모 없는 루트가 된다. 트레이스는 rag.request 기준으로 조립해야 한다
    body = json.loads((FIXTURE.parent / "collector_payload_autoinstr.json").read_text("utf-8"))

    batch = parse_batch(body)

    assert batch.rejected == [] and batch.orphans == []
    (rec,) = batch.records
    assert rec.question == "Where is the Louvre?"
    assert rec.status == "ERROR"  # 가짜 키 → 502
    assert rec.contexts and rec.contexts[0]["doc_id"].startswith("m")
    names = {s.name: s.kind for s in rec.spans}
    assert names["POST /chat"] == "OTHER" and names["anthropic.messages.create"] == "OTHER"
    assert names["gen_ai.chat"] == "LLM"
    assert len(rec.spans) == 8
