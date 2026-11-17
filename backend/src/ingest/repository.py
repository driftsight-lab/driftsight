"""트레이스·스팬·검사 작업 INSERT (erd.md > 5.1 · 5.3). 트랜잭션 경계는 service가 정한다.

- `traces`는 `ON CONFLICT (trace_id) DO NOTHING` — 재수신은 행을 만들지 않는다(policies.md > 3.1)
- 스팬·검사 작업은 새로 만든 트레이스에만 붙인다
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingest.otlp import SpanRecord, TraceRecord
from src.shared.models import EvalJob, Span, Trace, Version
from src.shared.models.enums import EvalJobStatus


async def existing_version_ids(session: AsyncSession, ids: Iterable[int]) -> set[int]:
    wanted = {i for i in ids if i}
    if not wanted:
        return set()
    rows = await session.execute(select(Version.id).where(Version.id.in_(wanted)))
    return set(rows.scalars())


async def insert_trace_if_new(session: AsyncSession, rec: TraceRecord, now: datetime) -> int | None:
    """새로 저장했으면 `traces.id`, 이미 있으면 None."""
    stmt = (
        insert(Trace)
        .values(
            trace_id=rec.trace_id,
            service_name=rec.service_name,
            question=rec.question,
            answer=rec.answer,
            contexts=rec.contexts,
            provider=rec.provider,
            model_name=rec.model_name,
            input_tokens=rec.input_tokens,
            output_tokens=rec.output_tokens,
            cost_usd=rec.cost_usd,
            latency_ms=rec.latency_ms,
            prompt_version_id=rec.prompt_version_id,
            model_version_id=rec.model_version_id,
            retrieval_version_id=rec.retrieval_version_id,
            injection_run_id=rec.injection_run_id,
            status=rec.status,
            error_message=rec.error_message,
            started_at=rec.started_at,
            ended_at=rec.ended_at,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_traces_trace_id")
        .returning(Trace.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_trace_pk(session: AsyncSession, trace_id: str) -> int | None:
    stmt = select(Trace.id).where(Trace.trace_id == trace_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def insert_spans(
    session: AsyncSession, trace_pk: int, spans: Sequence[SpanRecord], now: datetime
) -> int:
    """스팬을 저장하고 새로 들어간 수를 돌려준다. 이미 있는 (trace_pk, span_id)는 건너뛴다."""
    if not spans:
        return 0
    stmt = (
        insert(Span)
        .values(
            [
                {
                    "trace_pk": trace_pk,
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "name": s.name,
                    "kind": s.kind,
                    "attributes": s.attributes,
                    "started_at": s.started_at,
                    "ended_at": s.ended_at,
                    "created_at": now,
                }
                for s in spans
            ]
        )
        .on_conflict_do_nothing(constraint="uq_spans_span_id")
        .returning(Span.id)
    )
    return len((await session.execute(stmt)).all())


async def insert_eval_job(session: AsyncSession, trace_pk: int, now: datetime) -> None:
    session.add(
        EvalJob(
            trace_pk=trace_pk,
            status=EvalJobStatus.PENDING.value,
            attempts=0,
            available_at=now,
            created_at=now,
        )
    )
    await session.flush()


async def pending_job_count(session: AsyncSession) -> int:
    stmt = (
        select(func.count())
        .select_from(EvalJob)
        .where(EvalJob.status == EvalJobStatus.PENDING.value)
    )
    return (await session.execute(stmt)).scalar_one()
