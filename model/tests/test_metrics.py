import pytest

from src.evaluate.metrics import char_level, example_level, word_level, word_spans


def test_example_level_counts():
    gold = [[{"start": 0, "end": 3}], [], [{"start": 1, "end": 2}], []]
    pred = [[{"start": 0, "end": 1}], [{"start": 0, "end": 1}], [], []]
    r = example_level(gold, pred)
    assert (r.tp, r.fp, r.fn) == (1, 1, 1)
    assert r.precision == r.recall == r.f1 == 0.5


def test_word_spans_keep_punctuation():
    assert word_spans("Paris is  big.") == [(0, 5), (6, 8), (10, 14)]


def test_word_level_partial_overlap_marks_whole_word():
    answer = "Paris is in Germany."
    gold = [[{"start": 12, "end": 20}]]  # "Germany."
    pred = [[{"start": 9, "end": 13}]]  # "in G" -> words "in", "Germany."
    r = word_level([answer], gold, pred)
    assert (r.tp, r.fp, r.fn) == (1, 1, 0)


def test_char_level_matches_lettucedetect_formula():
    gold = [[{"start": 0, "end": 10}]]
    pred = [[{"start": 5, "end": 15}]]
    r = char_level(gold, pred)
    assert (r.tp, r.fp, r.fn) == (5, 5, 5)
    assert r.f1 == pytest.approx(0.5)


def test_char_level_merges_overlapping_gold_spans():
    gold = [[{"start": 0, "end": 10}, {"start": 5, "end": 10}]]
    assert char_level(gold, gold).f1 == pytest.approx(1.0)
    compat = char_level(gold, gold, lettucedetect_compat=True)
    assert compat.precision > 1.0  # LettuceDetect 원본 계산은 겹친 문자를 두 번 센다


def test_no_predictions_gives_zero_without_error():
    r = example_level([[{"start": 0, "end": 1}]], [[]])
    assert r.precision == 0.0 and r.f1 == 0.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        example_level([[]], [[], []])
