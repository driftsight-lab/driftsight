"""RAGTruth 원본을 train/dev/test JSONL로 전처리한다.

- response.jsonl과 source_info.jsonl을 source_id로 조인한다.
- 공식 split의 train에서 source_id 단위로 dev를 분리한다.
- 환각 라벨은 답변 기준 문자 오프셋으로 유지하고, 원문과 일치하는지 검증한다.

재현 명령 (model/ 에서):
    uv run python -m src.data.preprocess_ragtruth \
        --config configs/data/ragtruth.yaml \
        --raw-dir src/data/raw/ragtruth --out-dir src/data/processed/ragtruth
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

SPLITS = ("train", "dev", "test")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def split_dev_sources(train_source_ids: set[str], dev_ratio: float, seed: int) -> set[str]:
    """source_id를 정렬한 뒤 시드로 섞어 앞쪽 dev_ratio 만큼을 dev로 고른다."""
    ordered = sorted(train_source_ids)
    random.Random(seed).shuffle(ordered)
    n_dev = int(len(ordered) * dev_ratio)
    return set(ordered[:n_dev])


def convert_labels(response: dict[str, Any], include_implicit_true: bool) -> list[dict[str, Any]]:
    answer = response["response"]
    labels = []
    for label in response["labels"]:
        if answer[label["start"] : label["end"]] != label["text"]:
            raise ValueError(f"라벨 오프셋 불일치: response id={response['id']}")
        if label.get("implicit_true") and not include_implicit_true:
            continue
        labels.append(
            {
                "start": label["start"],
                "end": label["end"],
                "label_type": label["label_type"],
                "implicit_true": bool(label.get("implicit_true")),
                "due_to_null": bool(label.get("due_to_null")),
            }
        )
    return sorted(labels, key=lambda lb: (lb["start"], lb["end"]))


def build_splits(
    responses: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    sources_by_id = {s["source_id"]: s for s in sources}
    split_cfg, label_cfg = config["split"], config["labels"]
    drop_quality = set(label_cfg["drop_quality"])

    train_source_ids = {r["source_id"] for r in responses if r["split"] == "train"}
    test_source_ids = {r["source_id"] for r in responses if r["split"] == "test"}
    if train_source_ids & test_source_ids:
        raise ValueError("공식 train과 test에 같은 source_id가 있다")
    dev_source_ids = split_dev_sources(train_source_ids, split_cfg["dev_ratio"], split_cfg["seed"])

    out: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLITS}
    for response in responses:
        if response["quality"] in drop_quality:
            continue
        source = sources_by_id[response["source_id"]]
        if response["split"] == "test":
            split = "test"
        elif response["source_id"] in dev_source_ids:
            split = "dev"
        else:
            split = "train"
        out[split].append(
            {
                "id": response["id"],
                "source_id": response["source_id"],
                "task_type": source["task_type"],
                "model": response["model"],
                "quality": response["quality"],
                "prompt": source["prompt"],
                "answer": response["response"],
                "labels": convert_labels(response, label_cfg["include_implicit_true"]),
            }
        )
    for rows in out.values():
        rows.sort(key=lambda row: int(row["id"]))
    return out


def summarize(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, rows in splits.items():
        summary[name] = {
            "responses": len(rows),
            "sources": len({r["source_id"] for r in rows}),
            "hallucinated_responses": sum(1 for r in rows if r["labels"]),
            "spans": sum(len(r["labels"]) for r in rows),
            "task_type": dict(sorted(Counter(r["task_type"] for r in rows).items())),
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    responses = read_jsonl(args.raw_dir / "response.jsonl")
    sources = read_jsonl(args.raw_dir / "source_info.jsonl")
    splits = build_splits(responses, sources, config)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        write_jsonl(args.out_dir / f"{name}.jsonl", rows)
    summary = summarize(splits)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
