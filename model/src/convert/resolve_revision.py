"""Hugging Face 저장소의 현재 커밋 해시를 확인해 configs/models/*.yaml에 고정한다.

재현 명령 (model/ 에서):
    uv run python -m src.convert.resolve_revision configs/models/lettucedetect.yaml \
        configs/models/embedding.yaml            # 확인만 (파일은 그대로)
    uv run python -m src.convert.resolve_revision configs/models/*.yaml --write   # revision 기입

이미 revision이 들어 있는 파일은 --write를 줘도 바꾸지 않는다(고정값을 실수로 덮어쓰지 않도록).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_REVISION_LINE = re.compile(r'^revision:\s*""\s*$', re.MULTILINE)


def is_pinned(revision: str | None) -> bool:
    return bool(revision) and bool(COMMIT_SHA.match(revision))


def write_revision(path: Path, sha: str) -> None:
    """주석을 지키려고 yaml을 다시 쓰지 않고 `revision: ""` 한 줄만 바꾼다."""
    text = path.read_text(encoding="utf-8")
    new_text, count = _REVISION_LINE.subn(f"revision: {sha}", text)
    if count != 1:
        raise ValueError(f'{path}: `revision: ""` 줄을 찾지 못함')
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configs", nargs="+", type=Path)
    parser.add_argument("--write", action="store_true", help="비어 있는 revision에 해시를 기입")
    args = parser.parse_args()

    from huggingface_hub import model_info  # 네트워크가 필요한 부분만 지연 import

    for path in args.configs:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        info = model_info(config["repo"])
        current = config.get("revision") or ""
        status = "고정됨" if is_pinned(current) else "비어 있음"
        print(f"{config['repo']}\n  hub main: {info.sha}\n  last_modified: {info.last_modified}")
        print(f"  config: {current or '(없음)'} [{status}]")
        if is_pinned(current) and current != info.sha:
            print("  주의: hub main이 고정값과 다름. 바꾸려면 PR에서 결정한다.")
        if args.write and not current:
            write_revision(path, info.sha)
            print(f"  -> {path}에 기입")


if __name__ == "__main__":
    main()
