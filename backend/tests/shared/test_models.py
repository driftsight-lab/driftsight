"""ORM 메타데이터 — 테이블·제약·인덱스가 erd.md > 10. DDL과 일치하는지 (DB 불필요)."""

from sqlalchemy import CheckConstraint, UniqueConstraint

from src.shared.db import Base
from src.shared.models import (  # noqa: F401 — metadata 등록
    Embedding,
    EvalJob,
    Evaluation,
    Span,
    Trace,
    Version,
    VersionChange,
)
from src.shared.models.enums import VersionKind, check_in

CORE_TABLES = {
    "traces",
    "spans",
    "versions",
    "version_changes",
    "eval_jobs",
    "evaluations",
    "embeddings",
}


def _constraint_names(table_name: str, kind: type) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {c.name for c in table.constraints if isinstance(c, kind) and c.name}


def test_core_tables_registered() -> None:
    assert set(Base.metadata.tables) >= CORE_TABLES


def test_unique_constraints_match_erd() -> None:
    assert "uq_traces_trace_id" in _constraint_names("traces", UniqueConstraint)
    assert "uq_spans_span_id" in _constraint_names("spans", UniqueConstraint)
    assert "uq_versions_kind_hash" in _constraint_names("versions", UniqueConstraint)
    assert "uq_eval_jobs_trace" in _constraint_names("eval_jobs", UniqueConstraint)
    assert "uq_evaluations_trace_stage_evaluator" in _constraint_names(
        "evaluations", UniqueConstraint
    )


def test_code_value_checks_present() -> None:
    assert "ck_versions_kind" in _constraint_names("versions", CheckConstraint)
    assert "ck_traces_status" in _constraint_names("traces", CheckConstraint)
    assert "ck_eval_jobs_status" in _constraint_names("eval_jobs", CheckConstraint)
    assert "ck_evaluations_routed" in _constraint_names("evaluations", CheckConstraint)


def test_check_in_renders_all_values() -> None:
    expr = check_in("kind", VersionKind)

    assert expr == ("kind IN ('prompt','model','retrieval','judge_prompt','routing','pricing')")


def test_immutable_tables_have_no_updated_at() -> None:
    # erd.md > 1. 설계 원칙 — [IMMUTABLE] 테이블은 updated_at을 두지 않는다
    for name in ("traces", "spans", "versions", "version_changes", "evaluations", "embeddings"):
        assert "updated_at" not in Base.metadata.tables[name].c
    assert "updated_at" in Base.metadata.tables["eval_jobs"].c


def test_partial_queue_index() -> None:
    index = next(
        i for i in Base.metadata.tables["eval_jobs"].indexes if i.name == "idx_eval_jobs_queue"
    )

    assert str(index.dialect_options["postgresql"]["where"]) == "status = 'PENDING'"
