"""전처리된 RAGTruth(train/dev/test.jsonl)의 분포를 요약한다.

결과는 out-dir에 eda.json(전체 수치)과 eda.md(표)로 저장한다. --tokenizer를 주면 토큰 길이 분포와
최대 길이 초과 비율도 계산한다(학습 시 최대 길이·자르기 방식 결정용).

재현 명령 (model/ 에서):
    uv run python -m src.data.eda_ragtruth \
        --processed-dir src/data/processed/ragtruth --out-dir src/data/processed/ragtruth/eda \
        --tokenizer KRLabsOrg/lettucedect-base-modernbert-en-v1 --revision bbd77832f52f9bd87546a3924c032467921f5c34 --max-length 4096
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from src.data.preprocess_ragtruth import SPLITS, read_jsonl
from src.evaluate.metrics import merge_spans, word_spans


def _pct(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _length_stats(values: list[int]) -> dict[str, float]:
    return {
        "median": median(values),
        "p90": _pct(values, 0.90),
        "p95": _pct(values, 0.95),
        "p99": _pct(values, 0.99),
        "max": max(values),
    }


def _rate(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {
        name: {
            "responses": len(g),
            "hallucinated_ratio": round(sum(1 for r in g if r["labels"]) / len(g), 4),
        }
        for name, g in sorted(groups.items())
    }


def summarize(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    all_rows = [r for rows in splits.values() for r in rows]
    labels = [lb for r in all_rows for lb in r["labels"]]
    span_chars = [lb["end"] - lb["start"] for lb in labels]
    hallucinated_words = []
    for r in all_rows:
        if r["labels"]:
            merged = merge_spans(r["labels"])
            words = word_spans(r["answer"])
            hit = sum(1 for s, e in words if any(m["start"] < e and s < m["end"] for m in merged))
            hallucinated_words.append(hit / len(words) if words else 0.0)
    overlapping = {
        name: sum(1 for r in rows if len(merge_spans(r["labels"])) < len(r["labels"]))
        for name, rows in splits.items()
    }
    return {
        "splits": {
            name: {
                "responses": len(rows),
                "sources": len({r["source_id"] for r in rows}),
                "hallucinated_ratio": round(sum(1 for r in rows if r["labels"]) / len(rows), 4),
            }
            for name, rows in splits.items()
        },
        "by_task_type": {name: _rate(rows, "task_type") for name, rows in splits.items()},
        "by_model": _rate(all_rows, "model"),
        "label_type": dict(Counter(lb["label_type"] for lb in labels).most_common()),
        "implicit_true_spans": sum(lb["implicit_true"] for lb in labels),
        "due_to_null_spans": sum(lb["due_to_null"] for lb in labels),
        "responses_only_implicit_true": sum(
            1 for r in all_rows if r["labels"] and all(lb["implicit_true"] for lb in r["labels"])
        ),
        "responses_with_overlapping_spans": overlapping,
        "quality": dict(Counter(r["quality"] for r in all_rows).most_common()),
        "chars": {
            "prompt": _length_stats([len(r["prompt"]) for r in all_rows]),
            "answer": _length_stats([len(r["answer"]) for r in all_rows]),
            "span": _length_stats(span_chars),
        },
        "answer_words": _length_stats([len(word_spans(r["answer"])) for r in all_rows]),
        "hallucinated_word_share_in_hallucinated_answers": round(
            sum(hallucinated_words) / len(hallucinated_words), 4
        ),
    }


def token_stats(
    splits: dict[str, list[dict[str, Any]]], tokenizer_name: str, revision: str, max_length: int
) -> dict[str, Any]:
    from transformers import AutoTokenizer  # 토큰 통계를 낼 때만 필요

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, revision=revision)
    out: dict[str, Any] = {"tokenizer": f"{tokenizer_name}@{revision}", "max_length": max_length}
    for name, rows in splits.items():
        lengths = [
            len(tokenizer(r["prompt"], r["answer"], truncation=False)["input_ids"]) for r in rows
        ]
        out[name] = {
            **_length_stats(lengths),
            "over_max_length": sum(1 for n in lengths if n > max_length),
        }
    return out


def to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# RAGTruth EDA",
        "",
        "| 분할 | 응답 | 문서 | 환각 응답 비율 |",
        "| --- | --- | --- | --- |",
    ]
    for name, s in summary["splits"].items():
        lines.append(
            f"| {name} | {s['responses']:,} | {s['sources']:,} | {s['hallucinated_ratio']:.1%} |"
        )
    lines += ["", "| 분할 | 과제 유형 | 응답 | 환각 응답 비율 |", "| --- | --- | --- | --- |"]
    for split, groups in summary["by_task_type"].items():
        for task, s in groups.items():
            lines.append(
                f"| {split} | {task} | {s['responses']:,} | {s['hallucinated_ratio']:.1%} |"
            )
    lines += ["", "| 생성 모델 | 응답 | 환각 응답 비율 |", "| --- | --- | --- |"]
    for model, s in summary["by_model"].items():
        lines.append(f"| {model} | {s['responses']:,} | {s['hallucinated_ratio']:.1%} |")
    lines += ["", "| 라벨 유형 | 구간 수 |", "| --- | --- |"]
    lines += [f"| {k} | {v:,} |" for k, v in summary["label_type"].items()]
    lines += [
        "",
        "| 길이 | 중앙값 | p90 | p95 | p99 | 최대 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key, s in summary["chars"].items():
        lines.append(
            f"| {key} (문자) | {s['median']:,} | {s['p90']:,} | {s['p95']:,} "
            f"| {s['p99']:,} | {s['max']:,} |"
        )
    if "tokens" in summary:
        tok = summary["tokens"]
        for name in SPLITS:
            s = tok[name]
            lines.append(
                f"| {name} 입력 (토큰) | {s['median']:,} | {s['p90']:,} | {s['p95']:,} "
                f"| {s['p99']:,} | {s['max']:,} |"
            )
        lines += [
            "",
            f"최대 길이 {tok['max_length']} 초과 응답: "
            + ", ".join(f"{n} {tok[n]['over_max_length']}" for n in SPLITS),
        ]
    lines += [
        "",
        (
            f"- implicit_true 구간: {summary['implicit_true_spans']:,}"
            f" / 라벨이 모두 implicit_true인 응답: {summary['responses_only_implicit_true']:,}"
        ),
        f"- 정답 구간끼리 겹치는 응답: {summary['responses_with_overlapping_spans']}",
        f"- quality: {summary['quality']}",
        (
            "- 환각 응답에서 환각 단어 비율(평균): "
            f"{summary['hallucinated_word_share_in_hallucinated_answers']:.1%}"
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tokenizer", help="토큰 길이 통계를 낼 토크나이저 (HF 저장소)")
    parser.add_argument("--revision", help="--tokenizer의 고정 커밋 해시")
    parser.add_argument("--max-length", type=int, default=4096)
    args = parser.parse_args()
    if args.tokenizer and (not args.revision or args.revision == "main"):
        parser.error("--tokenizer를 쓸 때는 --revision에 커밋 해시를 준다 (main 금지)")

    splits = {name: read_jsonl(args.processed_dir / f"{name}.jsonl") for name in SPLITS}
    summary = summarize(splits)
    if args.tokenizer:
        summary["tokens"] = token_stats(splits, args.tokenizer, args.revision, args.max_length)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "eda.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = to_markdown(summary)
    (args.out_dir / "eda.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
