"""수집 service — 트레이스 저장과 검사 작업 등록을 같은 트랜잭션으로 (ADR-004, policies.md > 3.1).

- 트레이스 1건 = SAVEPOINT 1개: `traces`·`spans`·`eval_jobs` INSERT가 함께 성공하거나 함께 롤백된다
  (test-plan 8.2-1 "traces는 있는데 eval_jobs가 없는 상태 없음")
- 이미 있는 trace id → `duplicated` (8.2-4). 형식·제약 위반 건만 `rejected`, 나머지는 저장
- 루트 없이 늦게 온 스팬은 이미 저장된 트레이스에 붙인다(`accepted`). 트레이스가 없으면 거부
- `status='ERROR'` 트레이스는 저장하되 검사 작업을 등록하지 않는다
- 존재하지 않는 버전 id는 NULL로 저장한다(원인 분석 모집단에서만 빠짐, policies.md > 3.1)
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ingest import repository as repo
from src.ingest.otlp import OrphanSpans, ParsedBatch, TraceRecord
from src.shared.db import utc_now, with_db_retry
from src.shared.models.enums import TraceStatus

logger = logging.getLogger(__name__)

EvalJobInserter = Callable[[AsyncSession, int, datetime], Awaitable[None]]


@dataclass
class IngestResult:
    accepted: int = 0
    duplicated: int = 0
    rejected: list[dict[str, str]] = field(default_factory=list)

    def reject(self, trace_id: str, reason: str) -> None:
        self.rejected.append({"traceId": trace_id, "reason": reason})


async def _store_one(
    session: AsyncSession,
    rec: TraceRecord,
    known_versions: set[int],
    now: datetime,
    insert_eval_job: EvalJobInserter,
) -> bool:
    """새로 저장했으면 True, 중복이면 False."""
    for attr in ("prompt_version_id", "model_version_id", "retrieval_version_id"):
        if getattr(rec, attr) not in known_versions:
            setattr(rec, attr, None)
    trace_pk = await repo.insert_trace_if_new(session, rec, now)
    if trace_pk is None:
        # 재수신: 트레이스는 그대로 두고, 앞서 빠졌던 스팬만 붙인다
        existing = await repo.find_trace_pk(session, rec.trace_id)
        if existing is not None:
            await repo.insert_spans(session, existing, rec.spans, now)
        return False
    await repo.insert_spans(session, trace_pk, rec.spans, now)
    if rec.status == TraceStatus.OK.value:
        await insert_eval_job(session, trace_pk, now)
    return True


async def _attach_orphan(
    session: AsyncSession, orphan: OrphanSpans, now: datetime, result: IngestResult
) -> None:
    """루트 없이 온 스팬: 트레이스가 이미 있으면 붙이고(accepted), 없으면 거부한다."""
    async with session.begin_nested():
        trace_pk = await repo.find_trace_pk(session, orphan.trace_id)
        if trace_pk is None:
            result.reject(orphan.trace_id, "ROOT_SPAN_MISSING")
            return
        await repo.insert_spans(session, trace_pk, orphan.spans, now)
        result.accepted += 1


async def ingest(
    session_factory: async_sessionmaker[AsyncSession],
    batch: ParsedBatch,
    *,
    insert_eval_job: EvalJobInserter = repo.insert_eval_job,
) -> IngestResult:
    """파싱된 배치를 저장한다. 연결 오류는 배치 전체를 재시도한다(INSERT가 멱등)."""
    records = batch.records

    async def op() -> IngestResult:
        result = IngestResult()
        for r in batch.rejected:
            result.reject(r.trace_id, r.reason)
        now = utc_now()
        async with session_factory() as session, session.begin():
            known = await repo.existing_version_ids(
                session,
                (
                    v
                    for rec in records
                    for v in (rec.prompt_version_id, rec.model_version_id, rec.retrieval_version_id)
                    if v is not None
                ),
            )
            for rec in records:
                try:
                    async with session.begin_nested():
                        stored = await _store_one(session, rec, known, now, insert_eval_job)
                except IntegrityError as exc:
                    logger.warning("trace rejected by constraint: %s", type(exc.orig).__name__)
                    result.reject(rec.trace_id, "CONSTRAINT_VIOLATION")
                    continue
                if stored:
                    result.accepted += 1
                else:
                    result.duplicated += 1
            for orphan in batch.orphans:
                await _attach_orphan(session, orphan, now, result)
        return result

    return await with_db_retry(op)
