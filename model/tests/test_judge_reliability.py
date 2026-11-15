import json
from pathlib import Path

import pytest

from src.evaluate.judge_reliability import (
    agreement,
    build_report,
    cohens_kappa,
    human_human_agreement,
    judge_all,
    load_prompt,
    longer_win_rate,
    normalize_winner,
    parse_verdict,
    prepare_items,
    render_turn,
    split_questions,
    swap_back,
)

ROOT = Path(__file__).resolve().parents[2]


def _conv(q1, a1, q2="q2", a2="a2"):
    return [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": a1},
        {"role": "user", "content": q2},
        {"role": "assistant", "content": a2},
    ]


def test_normalize_winner():
    assert normalize_winner("tie (bothbad)") == "tie"
    assert normalize_winner("model_b") == "B"
    assert normalize_winner("tie (inconsistent)") == "tie"  # gpt4_pair 분할에 있는 값
    with pytest.raises(ValueError):
        normalize_winner("x")


def test_split_questions_seeded():
    a = split_questions(range(80), 0.2, 42)
    assert a == split_questions(reversed(range(80)), 0.2, 42)
    assert len(a) == 16


def test_render_turn():
    conv = _conv("Q1", "A1", "Q2", "A2")
    assert render_turn(conv, 1) == ("Q1", "A1")
    q, a = render_turn(conv, 2)
    assert q == "[Turn 1] Q1\n[Turn 2] Q2" and a == "[Turn 1] A1\n[Turn 2] A2"


def test_prompts_load():
    for name in ("judge-pairwise-v1.md", "judge-v1.md"):
        system, user = load_prompt(ROOT / "configs" / "prompts" / name)
        assert "JSON" in system and "{question}" in user
    _, user = load_prompt(ROOT / "configs" / "prompts" / "judge-pairwise-v1.md")
    user.format(question="q", answer_a="a", answer_b="b")  # 자리표시자 외 중괄호 없음


def test_parse_verdict():
    assert parse_verdict('xx {"winner": "a", "reason": "r"} yy') == ("A", "r")
    with pytest.raises(ValueError):
        parse_verdict('{"winner": "C"}')
    with pytest.raises(ValueError):
        parse_verdict("no json")


def test_swap_back():
    assert [swap_back(x) for x in ("A", "B", "tie")] == ["B", "A", "tie"]


def test_kappa_and_agreement():
    assert cohens_kappa(["A", "B", "tie"], ["A", "B", "tie"]) == pytest.approx(1.0)
    assert cohens_kappa(["A", "A"], ["B", "B"]) == pytest.approx(0.0)
    assert agreement(["A", "B", "A"], ["A", "tie", "B"], drop_human_ties=True) == 0.5
    assert agreement(["A", "B", "A"], ["A", "tie", "B"], drop_human_ties=False) == pytest.approx(
        1 / 3
    )


def test_human_human_and_length():
    hh, pairs = human_human_agreement({(1, "x", "y", 1): ["A", "A", "B"], (2, "x", "y", 1): ["A"]})
    assert pairs == 3 and hh == pytest.approx(1 / 3)
    assert longer_win_rate(["A", "B", "tie", "A"], [10, 10, 5, 3], [5, 20, 1, 3]) == 1.0


def test_end_to_end_with_fake_judge(tmp_path):
    rows = [
        {
            "question_id": q,
            "model_a": "m1",
            "model_b": "m2",
            "turn": 1,
            "winner": w,
            "conversation_a": _conv(f"q{q}", "long answer here"),
            "conversation_b": _conv(f"q{q}", "short"),
        }
        for q, w in [(1, "model_a"), (2, "model_b"), (3, "tie"), (3, "model_a")]
    ]
    items, votes = prepare_items(rows, tune_ids=set(), sample_pairs=10, seed=42)
    assert len(items) == 3 and votes[(3, "m1", "m2", 1)] == ["tie", "A"]

    # 가짜 채점자: 항상 더 긴 답변(A 자리)이 이긴다고 판정 → 순서를 바꾸면 B
    def fake_call(system, user):
        a = user.split("[Assistant A's Answer]\n")[1].split("\n\n[Assistant B")[0]
        winner = "A" if a.startswith("long") else "B"
        return {
            "text": f'{{"winner": "{winner}", "reason": "ok"}}',
            "input_tokens": 1000,
            "output_tokens": 100,
            "latency_ms": 1,
        }

    system, user_tmpl = load_prompt(ROOT / "configs" / "prompts" / "judge-pairwise-v1.md")
    cache = tmp_path / "cache.jsonl"
    verdicts = judge_all(items, system, user_tmpl, fake_call, cache, workers=2)
    assert len(verdicts) == 6
    # 다시 실행하면 전부 캐시에서 읽는다
    calls = []
    judge_all(items, system, user_tmpl, lambda s, u: calls.append(1), cache)
    assert calls == []

    report = build_report(
        items,
        verdicts,
        votes,
        votes,
        {(1, "m1", "m2", 1): "A"},
        "fake-judge-pairwise-v1",
        3.0,
        15.0,
        30,
    )
    assert report["sampleCount"] == 3
    assert report["positionBias"]["swapConsistency"] == 1.0
    assert report["agreementRateWithTies"] == pytest.approx(0.5)  # 4표 중 A가 맞은 2표
    assert report["agreementRate"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["lengthBias"]["longerWinRate"] == 1.0
    assert report["details"]["gpt4Agreement"] == 1.0
    assert report["details"]["costUsd"] == pytest.approx(6 * (1000 * 3 + 100 * 15) / 1e6)
    assert sum(map(sum, report["confusionMatrix"]["matrix"])) == 4
    assert len(report["disagreements"]) == 2


def test_parse_verdict_truncated_or_extra_json():
    # max_tokens에 걸려 닫는 괄호 없이 잘린 응답
    cut = '{"winner": "A", "reason": "Assistant A gives a longer and more vivid answer that'
    winner, reason = parse_verdict(cut)
    assert winner == "A" and reason.startswith("Assistant A gives")
    # JSON이 두 개 붙은 응답
    assert parse_verdict('{"winner": "tie", "reason": "x"}\n{"note": 1}')[0] == "tie"
    with pytest.raises(ValueError):
        parse_verdict('{"winner": null, "reason": "x"}')


def test_cache_recovers_truncated_and_recalls_rest(tmp_path):
    items = [{"key": (1, "m1", "m2", 1), "question": "q", "answer_a": "a", "answer_b": "b"}]
    cache = tmp_path / "cache.jsonl"
    old = [
        # order 1: 잘린 응답 → 다시 읽어 복구
        {
            "id": "1|m1|m2|1|1",
            "winner": None,
            "reason": '{"winner": "A", "reason": "cut',
            "error": "JSON 없음",
            "input_tokens": 100,
            "output_tokens": 300,
            "latency_ms": 1,
        },
        # order 2: 판정이 없는 응답 → 다시 호출, 앞선 토큰을 비용에 더함
        {
            "id": "1|m1|m2|1|2",
            "winner": None,
            "reason": "no verdict",
            "error": "JSON 없음",
            "input_tokens": 100,
            "output_tokens": 50,
            "latency_ms": 1,
        },
    ]
    cache.write_text("\n".join(json.dumps(r) for r in old) + "\n", encoding="utf-8")
    calls = []

    def fake_call(system, user):
        calls.append(1)
        return {
            "text": '{"winner": "B", "reason": "ok"}',
            "input_tokens": 10,
            "output_tokens": 5,
            "latency_ms": 1,
        }

    verdicts = judge_all(items, "s", "{question}{answer_a}{answer_b}", fake_call, cache)
    assert len(calls) == 1
    assert verdicts["1|m1|m2|1|1"]["winner"] == "A" and verdicts["1|m1|m2|1|1"]["recovered"]
    v2 = verdicts["1|m1|m2|1|2"]
    assert v2["winner"] == "A"  # 바꾼 순서에서 B → 원래 기준 A
    assert (v2["input_tokens"], v2["output_tokens"]) == (110, 55)
