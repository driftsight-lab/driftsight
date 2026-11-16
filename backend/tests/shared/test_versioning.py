"""설정 스냅샷 — 해시 규칙·kind 판정·파싱 실패 (ADR-005)."""

from pathlib import Path

import pytest

from src.shared.models.enums import VersionKind
from src.shared.versioning import ConfigParseError, content_hash, load_snapshot, scan_configs


def _write(root: Path, rel: str, data: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_hash_ignores_crlf() -> None:
    assert content_hash(b"a\r\nb\n") == content_hash(b"a\nb\n")


def test_hash_changes_on_one_byte() -> None:
    assert content_hash(b"answer briefly") != content_hash(b"answer briefly.")


def test_kind_from_directory_and_text_config(tmp_path: Path) -> None:
    path = _write(tmp_path, "configs/prompts/qa-v1.md", b"Answer: {question}\r\n")

    snap = load_snapshot(path, root=tmp_path)

    assert snap.kind == VersionKind.PROMPT
    assert snap.name == "qa-v1"
    assert snap.source_path == "configs/prompts/qa-v1.md"
    assert snap.config == {"text": "Answer: {question}\n"}


def test_kind_header_overrides_directory(tmp_path: Path) -> None:
    path = _write(tmp_path, "configs/prompts/judge-v1.md", b"<!--\njudge (kind: judge_prompt)\n-->")

    assert load_snapshot(path, root=tmp_path).kind == VersionKind.JUDGE_PROMPT


def test_yaml_and_json_are_parsed(tmp_path: Path) -> None:
    y = _write(tmp_path, "configs/retrieval/r-v1.yaml", b"top_k: 4\nchunk_size: 512\n")
    j = _write(tmp_path, "configs/models/m-v1.json", b'{"model": "claude-haiku"}')

    assert load_snapshot(y, root=tmp_path).config == {"top_k": 4, "chunk_size": 512}
    assert load_snapshot(j, root=tmp_path).kind == VersionKind.MODEL


@pytest.mark.parametrize(
    ("rel", "data"),
    [
        ("configs/models/bad.json", b"{not json"),
        ("configs/models/list.yaml", b"- a\n- b\n"),
        ("configs/unknown/x.md", b"text"),
        ("configs/prompts/x.md", b"kind: nonsense\n"),
        ("configs/prompts/bin.md", b"\xff\xfe"),
    ],
)
def test_parse_failures_raise(tmp_path: Path, rel: str, data: bytes) -> None:
    with pytest.raises(ConfigParseError):
        load_snapshot(_write(tmp_path, rel, data), root=tmp_path)


def test_scan_skips_unsupported_files(tmp_path: Path) -> None:
    _write(tmp_path, "configs/prompts/.gitkeep", b"")
    _write(tmp_path, "configs/prompts/a.md", b"a")
    _write(tmp_path, "configs/models/b.yaml", b"model: x\n")

    snaps = scan_configs([tmp_path / "configs"], root=tmp_path)

    assert [s.source_path for s in snaps] == ["configs/models/b.yaml", "configs/prompts/a.md"]


def test_repository_configs_are_loadable() -> None:
    # 저장소의 실제 configs/ 가 기동 시 파싱 실패로 막히지 않는지 확인 (읽기만 함)
    repo = Path(__file__).resolve().parents[3]
    snaps = scan_configs([repo / "configs"], root=repo)

    assert {s.kind for s in snaps} <= set(VersionKind)
    assert all(s.source_path.startswith("configs/") for s in snaps)
    judge = [s for s in snaps if s.name.startswith("judge")]
    assert judge and all(s.kind == VersionKind.JUDGE_PROMPT for s in judge)
