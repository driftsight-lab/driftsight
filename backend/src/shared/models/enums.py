"""코드값 — docs/specs/erd.md > 8. 코드값 (Enum). DB는 VARCHAR + CHECK로 저장한다."""

from enum import StrEnum


class VersionKind(StrEnum):
    PROMPT = "prompt"
    MODEL = "model"
    RETRIEVAL = "retrieval"
    JUDGE_PROMPT = "judge_prompt"
    ROUTING = "routing"
    PRICING = "pricing"


class ChangeSource(StrEnum):
    DEPLOY = "deploy"
    INJECTION = "injection"
    CONSOLE = "console"


class TraceStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"


class SpanKind(StrEnum):
    RETRIEVAL = "RETRIEVAL"
    PROMPT = "PROMPT"
    LLM = "LLM"
    OTHER = "OTHER"


class EvalJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class EvalLabel(StrEnum):
    SUPPORTED = "SUPPORTED"
    HALLUCINATED = "HALLUCINATED"
    UNVERIFIABLE = "UNVERIFIABLE"


class RoutedReason(StrEnum):
    THRESHOLD = "threshold"
    SAMPLE = "sample"
    NONE = "none"


def check_in(column: str, enum: type[StrEnum]) -> str:
    """`column IN ('a','b')` CHECK 식."""
    values = ",".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"
