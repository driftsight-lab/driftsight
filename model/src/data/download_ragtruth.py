"""RAGTruth 원본을 고정된 커밋에서 내려받고 sha256으로 검증한다.

재현 명령 (model/ 에서):
    uv run python -m src.data.download_ragtruth \
        --config configs/data/ragtruth.yaml --out-dir src/data/raw/ragtruth
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import yaml

RAW_URL = "https://raw.githubusercontent.com/{owner_repo}/{revision}/{path}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(config_path: Path, out_dir: Path) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    source = config["source"]
    owner_repo = source["repo"].removeprefix("https://github.com/")
    out_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, expected_sha in source["files"].items():
        target = out_dir / Path(rel_path).name
        url = RAW_URL.format(owner_repo=owner_repo, revision=source["revision"], path=rel_path)
        if not target.exists() or sha256_of(target) != expected_sha:
            urllib.request.urlretrieve(url, target)
        actual_sha = sha256_of(target)
        if actual_sha != expected_sha:
            raise ValueError(
                f"sha256 불일치: {target.name} (기대 {expected_sha}, 실제 {actual_sha})"
            )

    (out_dir / "SOURCE.txt").write_text(
        "\n".join(
            [
                f"repo: {source['repo']}",
                f"revision: {source['revision']}",
                f"downloaded: {datetime.now(UTC).date().isoformat()}",
                "license: MIT",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    download(args.config, args.out_dir)


if __name__ == "__main__":
    main()
