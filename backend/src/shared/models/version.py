"""버전 도메인 — versions, version_changes (erd.md > 5.2). 둘 다 [IMMUTABLE]."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR, TIMESTAMP

from src.shared.db import Base
from src.shared.models.enums import ChangeSource, VersionKind, check_in

TIMESTAMPTZ = TIMESTAMP(timezone=True)


class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (
        CheckConstraint(check_in("kind", VersionKind), name="ck_versions_kind"),
        UniqueConstraint("kind", "content_hash", name="uq_versions_kind_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    source_path: Mapped[str | None] = mapped_column(String(300))
    git_commit: Mapped[str | None] = mapped_column(CHAR(40))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


class VersionChange(Base):
    __tablename__ = "version_changes"
    __table_args__ = (
        CheckConstraint(check_in("kind", VersionKind), name="ck_version_changes_kind"),
        CheckConstraint(check_in("source", ChangeSource), name="ck_version_changes_source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    from_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("versions.id", ondelete="RESTRICT")
    )
    to_version_id: Mapped[int] = mapped_column(ForeignKey("versions.id", ondelete="RESTRICT"))
    source: Mapped[str] = mapped_column(String(20))
    git_commit: Mapped[str | None] = mapped_column(CHAR(40))
    actor: Mapped[str | None] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)


Index("idx_versions_kind_created", Version.kind, Version.created_at.desc())
Index("idx_version_changes_changed_at", VersionChange.changed_at.desc())
Index("idx_version_changes_kind_changed", VersionChange.kind, VersionChange.changed_at.desc())
