from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from src.shared.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DB 접속 정보는 앱과 같은 공통 설정에서 읽는다 (환경 변수 DATABASE_URL).
# asyncpg(앱용) → psycopg2(alembic sync 마이그레이션용)로 드라이버만 교체한다.
_url = (
    get_settings()
    .database_url.get_secret_value()
    .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
)
# configparser 보간 문자(%)가 비밀번호에 있어도 깨지지 않게 이스케이프한다
config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))

import src.shared.models  # noqa: E402,F401 — 모든 모델을 Base.metadata에 등록
from src.shared.db import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
