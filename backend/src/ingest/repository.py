"""트레이스·스팬·검사 작업 INSERT (erd.md > 5.1 · 5.3). 트랜잭션 경계는 service가 정한다.

- `traces`는 `ON CONFLICT (trace_id) DO NOTHING` — 재수신은 행을 만들지 않는다(policies.md > 3.1)
- 스팬·검사 작업은 새로 만든 트레이스에만 붙인다
"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingest.otlp import TraceRecord
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


async def insert_spans(
    session: AsyncSession, trace_pk: int, rec: TraceRecord, now: datetime
) -> None:
    session.add_all(
        Span(
            trace_pk=trace_pk,
            span_id=s.span_id,
            parent_span_id=s.parent_span_id,
            name=s.name,
            kind=s.kind,
            attributes=s.attributes,
            started_at=s.started_at,
            ended_at=s.ended_at,
            created_at=now,
        )
        for s in rec.spans
    )
    await session.flush()


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
