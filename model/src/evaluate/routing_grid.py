"""과제 B-2 2단 라우팅 1차 수치 — RAGTruth test에서 τ·r 격자별 지표를 계산한다.

라우팅 규칙 (docs/specs/policies.md, docs/experiments/protocol.md > 과제 B-2):
    1단계 score >= τ  → 2단계 (routed_reason=threshold)
    나머지 중 비율 r 무작위 추첨 → 2단계 (routed_reason=sample)

1차 분석의 가정 (protocol.md B-2 정의와 다른 점):
- 2단계 채점 결과 대신 RAGTruth 사람 라벨(응답에 환각 구간이 있는가)을 정답으로 쓴다.
  즉 "2단계 채점자가 사람 라벨과 똑같이 판정한다"고 가정한 상한값이다.
- 비용 절감률 = 1 − 2단계 호출 비율. 2단계 1건 비용이 같다고 보고, 1단계 서버 비용은 포함하지 않는다.
- 정확도 유지율(LLM 전수 채점 F1 대비)은 LLM 채점이 필요하므로 이번에는 계산하지 않는다.

지표:
- stage2_rate: (threshold + sample) / 전체
- cost_saving: 1 − stage2_rate
- miss_rate: 사람 라벨상 환각 응답 중 2단계로 가지 않은 비율 (누락률)
- miss_rate_est: 표본(r)만으로 추정한 누락률. r=0 이면 추정 불가(None)
- miss_rate_est_error: miss_rate_est − miss_rate
- threshold_precision: τ로 보낸 응답 중 실제 환각 비율
- stage1_only: 1단계 단독 판정(score >= τ)의 응답 단위 P/R/F1 (참고)

재현 명령 (model/ 에서, score_ragtruth 실행 후):
    uv run python -m src.evaluate.routing_grid \
        --config configs/routing/b2_ragtruth.yaml \
        --scores ../models/stage1-scores-ragtruth-test.jsonl \
        --out ../models/routing-b2-ragtruth-test.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import numpy as np
import yaml

from src.data.preprocess_ragtruth import read_jsonl
from src.evaluate.metrics import _prf


def route(
    scores: np.ndarray, tau: float, r: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """(threshold로 보낸 마스크, sample로 보낸 마스크)."""
    by_threshold = scores >= tau
    draw = rng.random(len(scores)) < r
    by_sample = ~by_threshold & draw
    return by_threshold, by_sample


def routing_metrics(
    scores: np.ndarray, gold: np.ndarray, tau: float, r: float, seed: int
) -> dict[str, Any]:
    """격자 한 칸(τ, r, seed)의 지표."""
    rng = np.random.default_rng(seed)
    by_threshold, by_sample = route(scores, tau, r, rng)
    routed = by_threshold | by_sample
    n, n_hall = len(scores), int(gold.sum())

    missed = int((gold & ~routed).sum())
    miss_rate = missed / n_hall if n_hall else 0.0

    miss_rate_est: float | None = None
    n_sample = int(by_sample.sum())
    if n_sample:
        p_hat = float(gold[by_sample].mean())
        not_routed = int((~routed).sum())
        est_missed = p_hat * not_routed
        found = int((gold & routed).sum())
        est_total = found + est_missed
        miss_rate_est = est_missed / est_total if est_total else 0.0

    n_thr = int(by_threshold.sum())
    stage2_rate = (n_thr + n_sample) / n
    return {
        "tau": tau,
        "r": r,
        "seed": seed,
        "n": n,
        "threshold_count": n_thr,
        "sample_count": n_sample,
        "stage2_rate": stage2_rate,
        "cost_saving": 1 - stage2_rate,
        "miss_rate": miss_rate,
        "miss_rate_est": miss_rate_est,
        "miss_rate_est_error": None if miss_rate_est is None else miss_rate_est - miss_rate,
        "threshold_precision": float(gold[by_threshold].mean()) if n_thr else None,
    }


def stage1_only(scores: np.ndarray, gold: np.ndarray, tau: float) -> dict[str, float | int]:
    pred = scores >= tau
    tp = int((pred & gold).sum())
    fp = int((pred & ~gold).sum())
    fn = int((~pred & gold).sum())
    return _prf(tp, fp, fn).to_dict()


def _summary(values: Sequence[float | None]) -> dict[str, float] | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return {"mean": round(mean(vals), 4), "std": round(pstdev(vals), 4)}


def run_grid(
    rows: list[dict[str, Any]], taus: Sequence[float], rs: Sequence[float], seeds: Sequence[int]
) -> dict[str, Any]:
    scores = np.array([row["score"] for row in rows], dtype=float)
    gold = np.array([bool(row["gold_hallucinated"]) for row in rows])
    cells = []
    for tau in taus:
        for r in rs:
            runs = [routing_metrics(scores, gold, tau, r, s) for s in seeds]
            cell: dict[str, Any] = {"tau": tau, "r": r, "seeds": list(seeds)}
            for key in (
                "stage2_rate",
                "cost_saving",
                "miss_rate",
                "miss_rate_est",
                "miss_rate_est_error",
                "threshold_precision",
            ):
                cell[key] = _summary([run[key] for run in runs])
            cell["threshold_count"] = runs[0]["threshold_count"]
            cell["sample_count_mean"] = round(mean(run["sample_count"] for run in runs), 1)
            cells.append(cell)

    latencies = sorted(row["latency_ms"] for row in rows if "latency_ms" in row)
    return {
        "dataset": "RAGTruth test",
        "n": len(rows),
        "n_hallucinated": int(gold.sum()),
        "assumption": "2단계 판정 = 사람 라벨(상한). 비용 절감률은 1단계 서버 비용 제외",
        "stage1_latency_ms_batch1": (
            {
                "p50": round(median(latencies), 1),
                "p95": round(latencies[int(0.95 * (len(latencies) - 1))], 1),
            }
            if latencies
            else None
        ),
        "stage1_only": [{"tau": t, **stage1_only(scores, gold, t)} for t in taus],
        "grid": cells,
    }


def _fmt(cell_value: dict[str, float] | None, pct: bool = True) -> str:
    if cell_value is None:
        return "-"
    m, s = cell_value["mean"], cell_value["std"]
    if pct:
        return f"{m * 100:.1f}%" if s == 0 else f"{m * 100:.1f}% ±{s * 100:.1f}"
    return f"{m:.3f}"


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        (
            f"RAGTruth test {report['n']}건 (환각 {report['n_hallucinated']}건), "
            f"가정: {report['assumption']}"
        ),
        "",
        "| τ | r | 2단계 호출 비율 | 비용 절감률 | 누락률 | 누락률 추정(표본) | τ 전달분 중 환각 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in report["grid"]:
        lines.append(
            f"| {c['tau']} | {c['r']:.0%} | {_fmt(c['stage2_rate'])} | {_fmt(c['cost_saving'])} "
            f"| {_fmt(c['miss_rate'])} | {_fmt(c['miss_rate_est'])} "
            f"| {_fmt(c['threshold_precision'])} |"
        )
    lines += ["", "| τ | 1단계 단독 P | R | F1 |", "| --- | --- | --- | --- |"]
    for s in report["stage1_only"]:
        lines.append(f"| {s['tau']} | {s['precision']:.3f} | {s['recall']:.3f} | {s['f1']:.3f} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    rows = read_jsonl(args.scores)
    report = run_grid(rows, config["grid"]["tau"], config["grid"]["r"], config["seeds"])
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    args.out.with_suffix(".md").write_text(to_markdown(report) + "\n", "utf-8")
    print(to_markdown(report))


if __name__ == "__main__":
    main()
