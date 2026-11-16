"""설정 파일 → 버전 스냅샷 계산과 요청 단위 버전 묶음 (ADR-005, erd.md > 5.2).

- 같은 내용 해시 = 같은 버전 (줄바꿈은 LF로 정규화한 뒤 SHA-256)
- 종류(kind)는 상위 디렉토리로 정하고, 파일 머리 주석의 `kind: <값>`이 있으면 그것을 우선한다
  (`prompts/` 아래 `judge*` 파일은 `judge_prompt`)
- 파싱할 수 없는 설정은 `ConfigParseError` — 기동을 중단한다
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.shared.models.enums import VersionKind

# 원본 디렉토리 이름 → kind (configs/ 아래 구조)
DIRECTORY_KIND: dict[str, VersionKind] = {
    "prompts": VersionKind.PROMPT,
    "models": VersionKind.MODEL,
    "retrieval": VersionKind.RETRIEVAL,
    "routing": VersionKind.ROUTING,
    "pricing": VersionKind.PRICING,
}
SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
_KIND_HEADER = re.compile(r"(?:^|[\s(])kind:\s*([a-z_]+)")
_HEADER_SCAN_CHARS = 2_000


class ConfigParseError(ValueError):
    """설정 파일을 버전으로 만들 수 없다. 기동 시 발생하면 서비스를 띄우지 않는다."""


@dataclass(frozen=True)
class ConfigSnapshot:
    """파일 하나의 버전 후보 (아직 DB에 등록되지 않음)."""

    kind: VersionKind
    name: str
    content_hash: str
    source_path: str
    config: dict[str, Any]


@dataclass(frozen=True)
class VersionRef:
    """등록된 버전 — 스팬 속성(`app.version.*`)과 트레이스 FK에 쓴다."""

    id: int
    kind: VersionKind
    name: str
    content_hash: str


@dataclass(frozen=True)
class VersionContext:
    """요청 시점의 버전 묶음 (SDD T1-02). 3종이 모두 있어야 원인 분석 모집단에 든다."""

    prompt: VersionRef
    model: VersionRef
    retrieval: VersionRef


def content_hash(raw: bytes) -> str:
    """LF 정규화 후 SHA-256 hex. Windows CRLF 체크아웃이 새 버전을 만들지 않게 한다."""
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def _detect_kind(path: Path, text: str) -> VersionKind:
    header = _KIND_HEADER.search(text[:_HEADER_SCAN_CHARS])
    if header:
        try:
            return VersionKind(header.group(1))
        except ValueError as exc:
            raise ConfigParseError(f"{path}: unknown kind {header.group(1)!r}") from exc
    kind = DIRECTORY_KIND.get(path.parent.name)
    if kind == VersionKind.PROMPT and path.stem.startswith("judge"):
        return VersionKind.JUDGE_PROMPT  # 채점 프롬프트는 서비스 프롬프트와 구분한다 (erd.md > 5.2)
    if kind is None:
        raise ConfigParseError(f"{path}: cannot infer kind from directory {path.parent.name!r}")
    return kind


def _parse(path: Path, text: str) -> dict[str, Any]:
    try:
        if path.suffix == ".json":
            data = json.loads(text)
        elif path.suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(text)
        else:
            return {"text": text.replace("\r\n", "\n")}
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigParseError(f"{path}: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise ConfigParseError(f"{path}: top-level must be a mapping")
    return data


def load_snapshot(path: Path, *, root: Path) -> ConfigSnapshot:
    """파일 하나를 스냅샷으로 만든다. `source_path`는 저장소 루트 기준 상대 경로."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigParseError(f"{path}: not UTF-8") from exc
    return ConfigSnapshot(
        kind=_detect_kind(path, text),
        name=path.stem[:100],
        content_hash=content_hash(raw),
        source_path=path.resolve().relative_to(root.resolve()).as_posix(),
        config=_parse(path, text),
    )


def scan_configs(directories: list[Path], *, root: Path) -> list[ConfigSnapshot]:
    """디렉토리들 아래 지원 확장자 파일을 모두 스냅샷으로 만든다(경로 순)."""
    files = sorted(
        p
        for d in directories
        if d.is_dir()
        for p in d.rglob("*")
        if p.is_file() and p.suffix in SUPPORTED_SUFFIXES
    )
    return [load_snapshot(p, root=root) for p in files]
