"""공통 설정 — 기본값·설정 관계 불변식(policies.md > 2.2)·비밀값 비노출."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.shared.config import BaseAppSettings, get_settings

DUMMY_PASSWORD = "dummy-secret-pw"
DUMMY_URL = f"postgresql+asyncpg://aisv:{DUMMY_PASSWORD}@localhost:5432/aisv"

TIME_POLICY_ENV = (
    "WORKER_BATCH_WAIT_SECONDS",
    "WORKER_STALE_LOCK_SECONDS",
    "DRIFT_WINDOW_MINUTES",
    "DRIFT_INCIDENT_COOLDOWN_MINUTES",
    "DRIFT_NOTIFY_COOLDOWN_MINUTES",
    "LLM_TIMEOUT_SECONDS",
    "LLM_JUDGE_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """실행 환경의 값이 테스트에 섞이지 않게 한다."""
    for name in TIME_POLICY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", DUMMY_URL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_pass_validation() -> None:
    settings = BaseAppSettings()  # type: ignore[call-arg]

    assert settings.drift_window_seconds == 300
    assert settings.drift_incident_cooldown_seconds == 900
    assert settings.drift_notify_cooldown_seconds == 1800
    assert settings.llm_max_timeout_seconds == 60
    assert settings.database_url.get_secret_value() == DUMMY_URL


def test_missing_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ValidationError, match="database_url"):
        BaseAppSettings()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("env", "expected_var"),
    [
        # 배치 대기 = 판정 창 → 위반 (< 이어야 함)
        ({"WORKER_BATCH_WAIT_SECONDS": "60", "DRIFT_WINDOW_MINUTES": "1"}, "WORKER_BATCH_WAIT"),
        # 알림 쿨다운 < 판정 창
        ({"DRIFT_NOTIFY_COOLDOWN_MINUTES": "4"}, "DRIFT_NOTIFY_COOLDOWN"),
        # 인시던트 쿨다운 < 판정 창
        ({"DRIFT_INCIDENT_COOLDOWN_MINUTES": "4"}, "DRIFT_INCIDENT_COOLDOWN"),
        # 점유 만료 = 큰 LLM 타임아웃 → 위반 (> 이어야 함)
        ({"WORKER_STALE_LOCK_SECONDS": "60"}, "WORKER_STALE_LOCK"),
        # 점유 만료가 RAG 타임아웃이 더 클 때도 큰 값과 비교
        (
            {"LLM_TIMEOUT_SECONDS": "400", "LLM_JUDGE_TIMEOUT_SECONDS": "60"},
            "WORKER_STALE_LOCK",
        ),
    ],
)
def test_time_policy_violation_fails(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected_var: str
) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match=expected_var):
        BaseAppSettings()  # type: ignore[call-arg]


def test_cooldown_equal_to_window_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    # 쿨다운 = 판정 창은 허용 (>=)
    monkeypatch.setenv("DRIFT_WINDOW_MINUTES", "15")
    monkeypatch.setenv("DRIFT_INCIDENT_COOLDOWN_MINUTES", "15")
    monkeypatch.setenv("DRIFT_NOTIFY_COOLDOWN_MINUTES", "15")

    settings = BaseAppSettings()  # type: ignore[call-arg]

    assert settings.drift_window_seconds == 900


def test_multiple_violations_reported_together(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIFT_WINDOW_MINUTES", "60")  # 두 쿨다운 모두 위반

    with pytest.raises(ValidationError) as exc_info:
        BaseAppSettings()  # type: ignore[call-arg]

    message = str(exc_info.value)
    assert "DRIFT_NOTIFY_COOLDOWN" in message
    assert "DRIFT_INCIDENT_COOLDOWN" in message


def test_secret_not_exposed_in_error_or_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_STALE_LOCK_SECONDS", "10")

    with pytest.raises(ValidationError) as exc_info:
        BaseAppSettings()  # type: ignore[call-arg]
    assert DUMMY_PASSWORD not in str(exc_info.value)

    monkeypatch.delenv("WORKER_STALE_LOCK_SECONDS")
    settings = BaseAppSettings()  # type: ignore[call-arg]
    assert DUMMY_PASSWORD not in repr(settings)
    assert DUMMY_PASSWORD not in str(settings.model_dump())


def test_get_settings_is_cached_and_resettable(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_settings()
    assert get_settings() is first

    monkeypatch.setenv("DRIFT_WINDOW_MINUTES", "10")
    assert get_settings().drift_window_minutes == 5  # 캐시 유지

    get_settings.cache_clear()
    assert get_settings().drift_window_minutes == 10


def test_import_does_not_require_env() -> None:
    # 모듈 import만으로는 설정을 만들지 않는다 — 별도 프로세스에서 확인해 이 프로세스의
    # 모듈 상태(get_settings 캐시·클래스 객체)를 건드리지 않는다
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    done = subprocess.run(
        [sys.executable, "-c", "import src.shared.config, src.shared.db"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 0, done.stderr
