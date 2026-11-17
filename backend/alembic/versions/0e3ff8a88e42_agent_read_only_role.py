"""agent read-only role

원인 분석 에이전트 전용 읽기 전용 계정 `aisv_ro` (ADR-007, backend/CLAUDE.md > 8,
docs/ops/env-setup.md > Agent "`aisv_ro` 계정은 Alembic 마이그레이션에서 생성").

- 역할은 항상 NOLOGIN으로 만들고 `public` 스키마 SELECT만 준다. 이후 생기는 테이블에도
  기본 권한으로 SELECT가 붙는다.
- 로그인 비밀번호는 마이그레이션 시점의 `AGENT_DB_DSN`에서 읽어 설정한다. 비밀값은 파일에 남기지
  않고, `--sql`(오프라인) 출력에도 쓰지 않는다. 변수가 없으면 NOLOGIN으로 남는다.

Revision ID: 0e3ff8a88e42
Revises: 2cb72c655250
Create Date: 2026-11-17

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from alembic import context, op

revision: str = "0e3ff8a88e42"
down_revision: str | Sequence[str] | None = "2cb72c655250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "aisv_ro"


def _agent_password() -> str | None:
    dsn = os.environ.get("AGENT_DB_DSN")
    if not dsn or context.is_offline_mode():
        return None
    return make_url(dsn).password


def _literal(value: str) -> str:
    """비밀번호 문자열을 SQL 리터럴로 안전하게 인용한다(ALTER ROLE은 바인드 파라미터 불가)."""
    return str(
        sa.literal(value, sa.String()).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def upgrade() -> None:
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') "
        f"THEN CREATE ROLE {ROLE} NOLOGIN; END IF; END $$"
    )
    op.execute(
        f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {ROLE}', "
        f"current_database()); END $$"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {ROLE}")
    password = _agent_password()
    if password:
        op.execute(f"ALTER ROLE {ROLE} LOGIN PASSWORD {_literal(password)}")


def downgrade() -> None:
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM {ROLE}")
    op.execute(f"REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    op.execute(
        f"DO $$ BEGIN EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM {ROLE}', "
        f"current_database()); END $$"
    )
    op.execute(f"DROP ROLE IF EXISTS {ROLE}")
