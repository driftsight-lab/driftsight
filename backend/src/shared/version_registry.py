"""버전 등록·변경 이력 (ADR-005, erd.md > 7. 정합성 규칙 > 버전·변경, policies.md > 3.3).

- 같은 (kind, 내용 해시)는 버전 1개 — `uq_versions_kind_hash`로 중복 INSERT를 흡수한다
- 원본 경로별 "현재 버전"과 다를 때만 `version_changes`를 남긴다(재배포 0건, 되돌림은 1건)
- 여러 서비스가 동시에 기동해도 원본 경로 단위 advisory lock으로 이력이 겹치지 않는다
"""

from collections.abc import Iterable, Mapping
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db import utc_now
from src.shared.models import Version, VersionChange
from src.shared.models.enums import ChangeSource, VersionKind
from src.shared.versioning import ConfigSnapshot, VersionContext, VersionRef

# --- repository -------------------------------------------------------------


async def _lock_source(session: AsyncSession, kind: str, source_path: str) -> None:
    key = func.hashtext(f"aisv.version:{kind}:{source_path}")
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def get_or_create_version(
    session: AsyncSession, snap: ConfigSnapshot, *, git_commit: str | None, now: datetime
) -> Version:
    stmt = (
        insert(Version)
        .values(
            kind=snap.kind.value,
            name=snap.name,
            content_hash=snap.content_hash,
            source_path=snap.source_path,
            git_commit=git_commit,
            config=snap.config,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_versions_kind_hash")
    )
    await session.execute(stmt)
    found = await session.execute(
        select(Version).where(
            Version.kind == snap.kind.value, Version.content_hash == snap.content_hash
        )
    )
    return found.scalar_one()


async def current_version_id(session: AsyncSession, kind: str, source_path: str) -> int | None:
    """원본 경로의 현재 버전 = 그 경로 버전을 가리키는 가장 최근 변경 이력의 to_version."""
    stmt = (
        select(VersionChange.to_version_id)
        .join(Version, Version.id == VersionChange.to_version_id)
        .where(VersionChange.kind == kind, Version.source_path == source_path)
        .order_by(VersionChange.changed_at.desc(), VersionChange.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def has_any_change_to(session: AsyncSession, version_id: int) -> bool:
    stmt = select(VersionChange.id).where(VersionChange.to_version_id == version_id).limit(1)
    return (await session.execute(stmt)).first() is not None


# --- service ----------------------------------------------------------------


async def sync_versions(
    session: AsyncSession,
    snapshots: Iterable[ConfigSnapshot],
    *,
    source: ChangeSource = ChangeSource.DEPLOY,
    actor: str | None = None,
    git_commit: str | None = None,
    now: datetime | None = None,
) -> dict[str, VersionRef]:
    """스냅샷을 등록하고 원본 경로별 `VersionRef`를 돌려준다. 트랜잭션은 호출자가 연다."""
    now = now or utc_now()
    refs: dict[str, VersionRef] = {}
    for snap in snapshots:
        await _lock_source(session, snap.kind.value, snap.source_path)
        version = await get_or_create_version(session, snap, git_commit=git_commit, now=now)
        current = await current_version_id(session, snap.kind.value, snap.source_path)
        is_new_change = current != version.id
        if current is None and await has_any_change_to(session, version.id):
            # 같은 내용의 다른 경로가 이미 이 버전을 등록·기록함 — 기동마다 중복 기록하지 않는다
            is_new_change = False
        if is_new_change:
            session.add(
                VersionChange(
                    kind=snap.kind.value,
                    from_version_id=current,
                    to_version_id=version.id,
                    source=source.value,
                    git_commit=git_commit,
                    actor=actor,
                    changed_at=now,
                )
            )
        refs[snap.source_path] = VersionRef(
            id=version.id,
            kind=VersionKind(version.kind),
            name=version.name,
            content_hash=version.content_hash,
        )
    await session.flush()
    return refs


def build_version_context(
    refs: Mapping[str, VersionRef], *, prompt: str, model: str, retrieval: str
) -> VersionContext:
    """원본 경로 3개로 요청 단위 버전 묶음을 만든다. 하나라도 없으면 기동 오류."""
    try:
        context = VersionContext(prompt=refs[prompt], model=refs[model], retrieval=refs[retrieval])
    except KeyError as exc:
        raise LookupError(f"version not registered for source {exc.args[0]!r}") from exc
    expected = (VersionKind.PROMPT, VersionKind.MODEL, VersionKind.RETRIEVAL)
    actual = (context.prompt.kind, context.model.kind, context.retrieval.kind)
    if actual != expected:
        raise LookupError(f"version kinds {actual} != {expected}")
    return context
