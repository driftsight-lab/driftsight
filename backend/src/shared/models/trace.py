"""수집 도메인 — traces, spans (erd.md > 5.1). 둘 다 [IMMUTABLE]."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR

from src.shared.db import Base
from src.shared.models.enums import SpanKind, TraceStatus, check_in
from src.shared.models.version import TIMESTAMPTZ


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("trace_id", name="uq_traces_trace_id"),
        CheckConstraint(check_in("status", TraceStatus), name="ck_traces_status"),
        CheckConstraint("input_tokens >= 0", name="ck_traces_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_traces_output_tokens"),
        CheckConstraint("cost_usd >= 0", name="ck_traces_cost_usd"),
        CheckConstraint("latency_ms >= 0", name="ck_traces_latency_ms"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trace_id: Mapped[str] = mapped_column(CHAR(32))
    service_name: Mapped[str] = mapped_column(String(100))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    contexts: Mapped[list[Any] | None] = mapped_column(JSONB)
    provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT")
    )
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT")
    )
    retrieval_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT")
    )
    # injection_runs(실험 도메인)는 후속 리비전에서 생성한다. FK는 그때 추가한다.
    injection_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    ended_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


Index("idx_traces_started_at", Trace.started_at.desc())
Index("idx_traces_prompt_version", Trace.prompt_version_id, Trace.started_at)
Index("idx_traces_retrieval_version", Trace.retrieval_version_id, Trace.started_at)
Index(
    "idx_traces_injection_run",
    Trace.injection_run_id,
    postgresql_where=Trace.injection_run_id.is_not(None),
)


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("trace_pk", "span_id", name="uq_spans_span_id"),
        CheckConstraint(check_in("kind", SpanKind), name="ck_spans_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trace_pk: Mapped[int] = mapped_column(ForeignKey("traces.id", ondelete="RESTRICT"))
    span_id: Mapped[str] = mapped_column(CHAR(16))
    parent_span_id: Mapped[str | None] = mapped_column(CHAR(16))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    ended_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


Index("idx_spans_trace_pk", Span.trace_pk, Span.started_at)
