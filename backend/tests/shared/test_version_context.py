"""`build_version_context` — 버전 3종 묶음, 누락·종류 불일치는 기동 오류 (DB 불필요)."""

import pytest

from src.shared.models.enums import VersionKind
from src.shared.version_registry import build_version_context
from src.shared.versioning import VersionRef

REFS = {
    "p.md": VersionRef(1, VersionKind.PROMPT, "p", "h1"),
    "m.yaml": VersionRef(2, VersionKind.MODEL, "m", "h2"),
    "r.yaml": VersionRef(3, VersionKind.RETRIEVAL, "r", "h3"),
}


def test_builds_context() -> None:
    ctx = build_version_context(REFS, prompt="p.md", model="m.yaml", retrieval="r.yaml")

    assert (ctx.prompt.id, ctx.model.id, ctx.retrieval.id) == (1, 2, 3)


def test_missing_source_raises() -> None:
    with pytest.raises(LookupError, match="x.md"):
        build_version_context(REFS, prompt="x.md", model="m.yaml", retrieval="r.yaml")


def test_kind_mismatch_raises() -> None:
    with pytest.raises(LookupError):
        build_version_context(REFS, prompt="m.yaml", model="p.md", retrieval="r.yaml")
