import numpy as np
import pytest

from src.evaluate.routing_grid import routing_metrics, run_grid, stage1_only, to_markdown
from src.evaluate.score_ragtruth import response_score


def test_response_score_uses_answer_tokens_only():
    logits = np.array([[0.0, 9.0], [2.0, 0.0], [0.0, 1.0]])  # 0번은 문맥 토큰
    mask = np.array([False, True, True])
    score, pred = response_score(logits, mask)
    assert score == pytest.approx(1 / (1 + np.exp(-1)))
    assert pred is True


def test_response_score_empty_answer():
    assert response_score(np.zeros((2, 2)), np.array([False, False])) == (0.0, False)


def test_threshold_only_routing():
    scores = np.array([0.9, 0.6, 0.2, 0.1])
    gold = np.array([True, False, True, False])
    m = routing_metrics(scores, gold, tau=0.5, r=0.0, seed=42)
    assert m["threshold_count"] == 2 and m["sample_count"] == 0
    assert m["stage2_rate"] == 0.5 and m["cost_saving"] == 0.5
    assert m["miss_rate"] == 0.5  # 환각 2건 중 0.2점짜리 1건 누락
    assert m["miss_rate_est"] is None  # r=0 이면 추정 불가
    assert m["threshold_precision"] == 0.5


def test_sample_routes_only_below_tau_and_is_seeded():
    scores = np.linspace(0, 1, 1000)
    gold = scores > 0.95
    a = routing_metrics(scores, gold, tau=0.5, r=0.1, seed=42)
    b = routing_metrics(scores, gold, tau=0.5, r=0.1, seed=42)
    assert a == b
    assert a["threshold_count"] == 500
    assert 20 < a["sample_count"] < 80  # 아래쪽 500건의 약 10%
    assert a["miss_rate"] == 0.0 and a["miss_rate_est"] == 0.0


def test_stage1_only_prf():
    scores = np.array([0.9, 0.6, 0.2])
    gold = np.array([True, False, True])
    s = stage1_only(scores, gold, 0.5)
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 1)


def test_run_grid_and_markdown():
    rows = [
        {"score": s, "gold_hallucinated": g, "latency_ms": 10.0}
        for s, g in [(0.9, True), (0.1, False), (0.4, True), (0.7, False)]
    ]
    report = run_grid(rows, [0.5], [0.0, 0.5], [42, 43])
    assert report["n"] == 4 and report["n_hallucinated"] == 2
    assert len(report["grid"]) == 2
    assert report["grid"][0]["miss_rate"] == {"mean": 0.5, "std": 0.0}
    assert "| 0.5 | 0% |" in to_markdown(report)
