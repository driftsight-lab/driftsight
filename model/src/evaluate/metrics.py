"""과제 A 환각 탐지 평가 지표.

정의: docs/experiments/protocol.md > 과제 A > 지표, 토큰 단위 F1의 단어화·라벨 변환 규칙.
모든 지표는 "환각" 클래스를 양성으로 본 micro P/R/F1이다.

- 응답 단위: 정답·예측 구간이 하나라도 있으면 양성
- 단어 단위: 답변을 공백 기준으로 나눈 단어가 구간과 한 글자라도 겹치면 양성
- 문자 단위: 예측·정답 구간의 겹친 문자 수 기준 (LettuceDetect evaluate_detector_char_level과 동일)

구간(span)은 답변 기준 문자 오프셋 `{"start": int, "end": int}` 이며 end는 포함하지 않는다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass

Span = dict[str, int]

_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _prf(tp: int, fp: int, fn: int) -> PRF:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRF(precision, recall, f1, tp, fp, fn)


def _check_lengths(*seqs: Sequence) -> None:
    if len({len(s) for s in seqs}) != 1:
        raise ValueError("입력 목록의 길이가 서로 다르다")


def _overlaps(start: int, end: int, spans: Sequence[Span]) -> bool:
    return any(s["start"] < end and start < s["end"] for s in spans)


def example_level(gold: Sequence[Sequence[Span]], pred: Sequence[Sequence[Span]]) -> PRF:
    """응답 단위 F1. 응답에 구간이 하나라도 있으면 환각(양성)."""
    _check_lengths(gold, pred)
    tp = fp = fn = 0
    for g, p in zip(gold, pred, strict=True):
        tp += bool(g) and bool(p)
        fp += not g and bool(p)
        fn += bool(g) and not p
    return _prf(tp, fp, fn)


def word_spans(answer: str) -> list[tuple[int, int]]:
    """공백 기준 단어의 문자 범위 [start, end). 문장부호는 붙은 단어에 포함한다."""
    return [m.span() for m in _WORD.finditer(answer)]


def word_level(
    answers: Sequence[str], gold: Sequence[Sequence[Span]], pred: Sequence[Sequence[Span]]
) -> PRF:
    """단어 단위 F1. 단어가 구간과 한 글자라도 겹치면 그 단어를 양성으로 본다."""
    _check_lengths(answers, gold, pred)
    tp = fp = fn = 0
    for answer, g, p in zip(answers, gold, pred, strict=True):
        for start, end in word_spans(answer):
            is_gold, is_pred = _overlaps(start, end, g), _overlaps(start, end, p)
            tp += is_gold and is_pred
            fp += not is_gold and is_pred
            fn += is_gold and not is_pred
    return _prf(tp, fp, fn)


def merge_spans(spans: Sequence[Span]) -> list[Span]:
    """겹치는 구간을 하나로 합친다. RAGTruth 정답 구간은 서로 겹치는 경우가 있다."""
    merged: list[Span] = []
    for s in sorted(spans, key=lambda x: (x["start"], x["end"])):
        if merged and s["start"] < merged[-1]["end"]:
            merged[-1] = {"start": merged[-1]["start"], "end": max(merged[-1]["end"], s["end"])}
        else:
            merged.append({"start": s["start"], "end": s["end"]})
    return merged


def char_level(
    gold: Sequence[Sequence[Span]],
    pred: Sequence[Sequence[Span]],
    lettucedetect_compat: bool = False,
) -> PRF:
    """문자 겹침 F1 (LettuceDetect 논문 비교용 보조 지표).

    기본: 응답마다 구간을 합친 뒤 tp = 겹친 문자 수, fp = 예측 길이 − tp, fn = 정답 길이 − tp.
    lettucedetect_compat=True: LettuceDetect evaluate_detector_char_level과 똑같이 구간을 합치지
    않고 예측 × 정답 겹침을 모두 더한다. 정답 구간끼리 겹치면 같은 문자가 여러 번 세어져
    값이 1을 넘을 수 있다(RAGTruth test 기준 14개 응답).
    """
    _check_lengths(gold, pred)
    if not lettucedetect_compat:
        gold = [merge_spans(g) for g in gold]
        pred = [merge_spans(p) for p in pred]
    overlap = predicted = actual = 0
    for g, p in zip(gold, pred, strict=True):
        predicted += sum(s["end"] - s["start"] for s in p)
        actual += sum(s["end"] - s["start"] for s in g)
        for ps in p:
            for gs in g:
                overlap += max(0, min(ps["end"], gs["end"]) - max(ps["start"], gs["start"]))
    return _prf(overlap, predicted - overlap, actual - overlap)
