"""RAG 설정 — 빈 선택값은 미설정 (compose 검증에서 발견: `EMBEDDING_REVISION=` → revision "")."""

import pytest

from src.rag.main import RagSettings


def test_empty_optional_values_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    for name in ("EMBEDDING_REVISION", "RAG_CORPUS_PATH", "ANTHROPIC_API_KEY", "GIT_COMMIT"):
        monkeypatch.setenv(name, "")

    settings = RagSettings()  # type: ignore[call-arg]

    assert settings.embedding_revision is None
    assert settings.rag_corpus_path is None
    assert settings.anthropic_api_key is None
    assert settings.git_commit is None


def test_revision_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("EMBEDDING_REVISION", "0000000000000000000000000000000000000000")

    assert RagSettings().embedding_revision == "0000000000000000000000000000000000000000"  # type: ignore[call-arg]
