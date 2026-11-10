import pytest

from src.data.preprocess_ragtruth import build_splits, split_dev_sources


def _config(include_implicit_true=True, drop_quality=()):
    return {
        "split": {"dev_ratio": 0.5, "seed": 42},
        "labels": {
            "include_implicit_true": include_implicit_true,
            "drop_quality": list(drop_quality),
        },
    }


def _response(rid, source_id, split, labels=(), quality="good", text="Paris is in Germany."):
    return {
        "id": str(rid),
        "source_id": source_id,
        "model": "m",
        "temperature": 0.7,
        "split": split,
        "quality": quality,
        "response": text,
        "labels": list(labels),
    }


def _label(start, end, text="Paris is in Germany.", implicit_true=False):
    return {
        "start": start,
        "end": end,
        "text": text[start:end],
        "label_type": "Evident Conflict",
        "meta": "",
        "implicit_true": implicit_true,
        "due_to_null": False,
    }


SOURCES = [
    {"source_id": sid, "task_type": "QA", "prompt": f"prompt {sid}"}
    for sid in ("s1", "s2", "s3", "s4", "t1")
]


def _responses():
    rows = []
    rid = 0
    for sid in ("s1", "s2", "s3", "s4"):
        for _ in range(2):
            rows.append(_response(rid, sid, "train", labels=[_label(12, 19)]))
            rid += 1
    rows.append(_response(rid, "t1", "test"))
    return rows


def test_dev_split_is_deterministic():
    ids = {f"s{i}" for i in range(100)}
    assert split_dev_sources(ids, 0.1, 42) == split_dev_sources(ids, 0.1, 42)
    assert len(split_dev_sources(ids, 0.1, 42)) == 10


def test_no_source_shared_between_splits():
    splits = build_splits(_responses(), SOURCES, _config())
    seen = [{r["source_id"] for r in rows} for rows in splits.values()]
    assert not (seen[0] & seen[1]) and not (seen[0] & seen[2]) and not (seen[1] & seen[2])
    assert {r["source_id"] for r in splits["test"]} == {"t1"}


def test_implicit_true_included_by_default_and_excluded_when_configured():
    text = "Paris is in Germany."
    responses = [_response(0, "t1", "test", labels=[_label(0, 5, text, implicit_true=True)])]
    included = build_splits(responses, SOURCES, _config())
    excluded = build_splits(responses, SOURCES, _config(include_implicit_true=False))
    assert included["test"][0]["labels"][0]["implicit_true"] is True
    assert excluded["test"][0]["labels"] == []


def test_quality_filter():
    responses = [_response(0, "t1", "test", quality="truncated")]
    assert len(build_splits(responses, SOURCES, _config())["test"]) == 1
    assert build_splits(responses, SOURCES, _config(drop_quality=["truncated"]))["test"] == []


def test_offset_mismatch_raises():
    bad = _label(0, 5)
    bad["text"] = "Wrong"
    with pytest.raises(ValueError):
        build_splits([_response(0, "t1", "test", labels=[bad])], SOURCES, _config())
