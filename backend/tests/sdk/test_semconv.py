"""시맨틱 컨벤션 고정 — configs/otel/semconv.lock과 매핑 계층 일치 (telemetry.md > 9, ADR-002)."""

from pathlib import Path

import pytest

from src.sdk.semconv import SEMCONV_VERSION, check_semconv_lock

REPO_CONFIGS = Path(__file__).resolve().parents[3] / "configs"


def test_repository_lock_matches_mapping() -> None:
    check_semconv_lock(REPO_CONFIGS)  # 저장소의 실제 lock과 SDK 상수가 같다


def test_mismatch_stops_startup(tmp_path: Path) -> None:
    (tmp_path / "otel").mkdir()
    (tmp_path / "otel" / "semconv.lock").write_text("1.99.0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="1.99.0"):
        check_semconv_lock(tmp_path)


def test_constant_is_pinned_version() -> None:
    assert SEMCONV_VERSION.count(".") == 2
