"""ORM 모델 — 테이블 정의의 원본은 docs/specs/erd.md > 10. DDL.

모든 모델을 여기서 import해 `Base.metadata`에 등록한다 (Alembic autogenerate 대상).
"""

from src.shared.models.evaluation import Embedding, EvalJob, Evaluation
from src.shared.models.trace import Span, Trace
from src.shared.models.version import Version, VersionChange

__all__ = [
    "Embedding",
    "EvalJob",
    "Evaluation",
    "Span",
    "Trace",
    "Version",
    "VersionChange",
]
