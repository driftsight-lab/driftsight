"""RAGTruth test 응답마다 LettuceDetect(ONNX) 1단계 점수를 계산해 jsonl로 저장한다.

점수 = 답변 토큰별 "환각" 클래스 확률(softmax)의 최댓값. 0.0~1.0, 높을수록 환각 의심.
(docs/specs/erd.md > 점수 방향, configs/routing/b2_ragtruth.yaml > score)

입력은 check_lettucedetect_onnx와 같게 tokenizer(prompt, answer, truncation="only_first")로 만든다.
ONNX는 check_lettucedetect_onnx가 저장한 폴더(--onnx-dir)를 그대로 읽는다.
오래 걸리므로(응답 1개당 약 1초) 중간에 멈춰도 다시 실행하면 이미 계산한 id는 건너뛴다.

재현 명령 (model/ 에서):
    uv run python -m src.evaluate.score_ragtruth \
        --onnx-dir ../models/lettucedetect-onnx \
        --config configs/models/lettucedetect.yaml \
        --test-file src/data/processed/ragtruth/test.jsonl \
        --out ../models/stage1-scores-ragtruth-test.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from src.data.preprocess_ragtruth import read_jsonl


def softmax_last(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def response_score(logits: np.ndarray, answer_mask: np.ndarray) -> tuple[float, bool]:
    """(답변 토큰 환각 확률 최댓값, 답변 토큰 중 argmax가 환각인 토큰이 있는가)."""
    if not answer_mask.any():
        return 0.0, False
    answer_logits = logits[answer_mask]
    probs = softmax_last(answer_logits)[:, 1]
    return float(probs.max()), bool((answer_logits.argmax(-1) == 1).any())


def done_ids(out: Path) -> set[str]:
    if not out.exists():
        return set()
    return {str(row["id"]) for row in read_jsonl(out)}


def run(rows: list[dict[str, Any]], onnx_dir: Path, max_length: int, out: Path) -> int:
    from optimum.onnxruntime import ORTModelForTokenClassification
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(onnx_dir)
    model = ORTModelForTokenClassification.from_pretrained(
        onnx_dir, provider="CPUExecutionProvider"
    )
    skip = done_ids(out)
    todo = [r for r in rows if str(r["id"]) not in skip]
    print(f"전체 {len(rows)}건 중 이미 계산 {len(skip)}건, 남은 {len(todo)}건")

    with out.open("a", encoding="utf-8") as f:
        for i, row in enumerate(todo, 1):
            enc = tokenizer(
                row["prompt"],
                row["answer"],
                truncation="only_first",
                max_length=max_length,
                return_tensors="pt",
            )
            answer_mask = np.array([sid == 1 for sid in enc.sequence_ids(0)])
            start = time.perf_counter()
            logits = np.asarray(model(**enc).logits[0])
            latency_ms = (time.perf_counter() - start) * 1000
            score, pred_hallucinated = response_score(logits, answer_mask)
            record = {
                "id": str(row["id"]),
                "task_type": row["task_type"],
                "model": row["model"],
                "score": round(score, 6),
                "pred_hallucinated": pred_hallucinated,
                "gold_hallucinated": bool(row["labels"]),
                "latency_ms": round(latency_ms, 1),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if i % 100 == 0:
                f.flush()
                print(f"{i}/{len(todo)}")
    return len(todo)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onnx-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--test-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N건만 (시험용)")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    rows = sorted(read_jsonl(args.test_file), key=lambda r: int(r["id"]))
    if args.limit:
        rows = rows[: args.limit]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    run(rows, args.onnx_dir, config["max_length"], args.out)
    print(f"저장: {args.out}")


if __name__ == "__main__":
    main()
