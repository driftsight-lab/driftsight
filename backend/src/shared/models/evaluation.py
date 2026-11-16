"""검사 도메인 — eval_jobs, evaluations, embeddings (erd.md > 5.3).

eval_jobs만 상태가 바뀐다. evaluations·embeddings는 [IMMUTABLE].
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db import Base
from src.shared.models.enums import EvalJobStatus, EvalLabel, RoutedReason, check_in
from src.shared.models.version import TIMESTAMPTZ

# all-MiniLM-L6-v2 출력 차원 (erd.md > 5.3 embeddings)
EMBEDDING_DIM = 384


class EvalJob(Base):
    __tablename__ = "eval_jobs"
    __table_args__ = (
        UniqueConstraint("trace_pk", name="uq_eval_jobs_trace"),
        CheckConstraint(check_in("status", EvalJobStatus), name="ck_eval_jobs_status"),
        CheckConstraint("attempts >= 0", name="ck_eval_jobs_attempts"),
        Index(
            "idx_eval_jobs_queue",
            "status",
            "available_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("idx_eval_jobs_stale", "locked_at", postgresql_where=text("status = 'RUNNING'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trace_pk: Mapped[int] = mapped_column(ForeignKey("traces.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(SmallInteger)
    available_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    locked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    locked_by: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint(
            "trace_pk", "stage", "evaluator_key", name="uq_evaluations_trace_stage_evaluator"
        ),
        CheckConstraint("stage IN (1, 2)", name="ck_evaluations_stage"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_evaluations_score"),
        CheckConstraint(
            f"label IS NULL OR {check_in('label', EvalLabel)}", name="ck_evaluations_label"
        ),
        CheckConstraint(check_in("routed_reason", RoutedReason), name="ck_evaluations_routed"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="ck_evaluations_input_tokens"
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="ck_evaluations_output_tokens"
        ),
        CheckConstraint("cost_usd >= 0", name="ck_evaluations_cost_usd"),
        CheckConstraint("latency_ms >= 0", name="ck_evaluations_latency_ms"),
        Index("idx_evaluations_stage_routed", "stage", "routed_reason"),
        Index("idx_evaluations_trace", "trace_pk"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trace_pk: Mapped[int] = mapped_column(ForeignKey("traces.id", ondelete="RESTRICT"))
    stage: Mapped[int] = mapped_column(SmallInteger)
    evaluator_key: Mapped[str] = mapped_column(String(100))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    label: Mapped[str | None] = mapped_column(String(20))
    hallucination_spans: Mapped[list[Any] | None] = mapped_column(JSONB)
    routed_reason: Mapped[str] = mapped_column(String(20))
    reason_text: Mapped[str | None] = mapped_column(Text)
    judge_prompt_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT")
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


Index("idx_evaluations_created_at", Evaluation.created_at.desc())


class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (Index("idx_embeddings_created_at", "created_at"),)

    trace_pk: Mapped[int] = mapped_column(
        ForeignKey("traces.id", ondelete="RESTRICT"), primary_key=True
    )
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    model_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
