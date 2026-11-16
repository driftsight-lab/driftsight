"""backend 공통 실행 설정.

모든 서비스 설정은 `BaseAppSettings`를 상속한다. 이 클래스는 DB 접속과
시간 정책 값만 맡고, 서비스별 값·검증은 각 서비스 설정 클래스에서 추가한다.

- 변수명·기본값: docs/ops/env-setup.md
- 설정 관계 불변식: docs/specs/policies.md > 2.2 불변식
"""

from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    """DB 접속과 시간 정책 값. 기동 시 설정 관계 불변식을 검증한다."""

    model_config = SettingsConfigDict(
        extra="ignore",
        # 검증 오류에 입력값(비밀값 포함)을 싣지 않는다 (ADR-021)
        hide_input_in_errors=True,
    )

    # DB 접속 — 비밀번호를 포함하므로 기본값 없이 필수
    database_url: SecretStr

    # 시간 정책 (policies.md > 2.1 TTL 표)
    worker_batch_wait_seconds: int = 2
    worker_stale_lock_seconds: int = 300
    drift_window_minutes: int = 5
    drift_incident_cooldown_minutes: int = 15
    drift_notify_cooldown_minutes: int = 30
    llm_timeout_seconds: int = 30
    llm_judge_timeout_seconds: int = 60

    @property
    def drift_window_seconds(self) -> int:
        return self.drift_window_minutes * 60

    @property
    def drift_incident_cooldown_seconds(self) -> int:
        return self.drift_incident_cooldown_minutes * 60

    @property
    def drift_notify_cooldown_seconds(self) -> int:
        return self.drift_notify_cooldown_minutes * 60

    @property
    def llm_max_timeout_seconds(self) -> int:
        return max(self.llm_timeout_seconds, self.llm_judge_timeout_seconds)

    @model_validator(mode="after")
    def _check_time_policy(self) -> Self:
        """policies.md > 2.2 — DB 제약으로 표현할 수 없는 설정값 관계 4종."""
        window = self.drift_window_seconds
        violations: list[str] = []

        if not self.worker_batch_wait_seconds < window:
            violations.append(
                f"WORKER_BATCH_WAIT_SECONDS({self.worker_batch_wait_seconds}s) "
                f"must be < DRIFT_WINDOW_MINUTES({window}s)"
            )
        if not self.drift_notify_cooldown_seconds >= window:
            violations.append(
                f"DRIFT_NOTIFY_COOLDOWN_MINUTES({self.drift_notify_cooldown_seconds}s) "
                f"must be >= DRIFT_WINDOW_MINUTES({window}s)"
            )
        if not self.drift_incident_cooldown_seconds >= window:
            violations.append(
                f"DRIFT_INCIDENT_COOLDOWN_MINUTES({self.drift_incident_cooldown_seconds}s) "
                f"must be >= DRIFT_WINDOW_MINUTES({window}s)"
            )
        if not self.worker_stale_lock_seconds > self.llm_max_timeout_seconds:
            violations.append(
                f"WORKER_STALE_LOCK_SECONDS({self.worker_stale_lock_seconds}s) "
                f"must be > max(LLM_TIMEOUT_SECONDS, LLM_JUDGE_TIMEOUT_SECONDS)"
                f"({self.llm_max_timeout_seconds}s)"
            )

        if violations:
            raise ValueError("; ".join(violations))
        return self


@lru_cache(maxsize=1)
def get_settings() -> BaseAppSettings:
    """설정을 처음 요청될 때 한 번 생성한다. 테스트는 `get_settings.cache_clear()`로 초기화."""
    return BaseAppSettings()  # type: ignore[call-arg]  # 값은 환경 변수에서 채운다
