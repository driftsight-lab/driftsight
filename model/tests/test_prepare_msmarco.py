import pytest

from src.data.prepare_msmarco import (
    has_answer,
    normalize,
    ragtruth_qa_questions,
    select_questions,
    to_corpus,
    to_question,
)

MARKERS = ["No Answer Present."]


def _row(qid, query, answers=("yes",)):
    return {
        "query_id": qid,
        "query": query,
        "query_type": "DESCRIPTION",
        "answers": list(answers),
        "passages": {
            "passage_text": ["p0", "p1"],
            "url": ["u0", "u1"],
            "is_selected": [0, 1],
        },
    }


def test_normalize():
    assert normalize("  What IS  python? ") == "what is python"


def test_has_answer():
    assert has_answer(["42"], MARKERS)
    assert not has_answer([], MARKERS)
    assert not has_answer(["No Answer Present."], MARKERS)
    assert not has_answer([" "], MARKERS)


def test_ragtruth_qa_questions_only_qa():
    rows = [
        {"task_type": "QA", "source_info": {"question": "What is X?", "passages": "..."}},
        {"task_type": "Summary", "source_info": "some text"},
    ]
    assert ragtruth_qa_questions(rows) == {"what is x"}


def test_select_excludes_and_is_seeded():
    rows = [_row(i, f"q{i}") for i in range(20)]
    rows.append(_row(100, "no answer", ["No Answer Present."]))
    rows.append(_row(101, "In RagTruth?"))
    a, stats = select_questions(rows, {"in ragtruth"}, 5, 42, MARKERS)
    b, _ = select_questions(list(reversed(rows)), {"in ragtruth"}, 5, 42, MARKERS)
    assert [r["query_id"] for r in a] == [r["query_id"] for r in b]
    assert stats == {"total": 22, "answerable": 21, "after_ragtruth_exclusion": 20, "selected": 5}
    assert all(r["query_id"] < 100 for r in a)


def test_select_too_many():
    with pytest.raises(ValueError):
        select_questions([_row(1, "q")], set(), 2, 42, MARKERS)


def test_question_and_corpus_format():
    row = _row(7, "q7", ["a", "No Answer Present."])
    assert to_question(row, MARKERS)["answers"] == ["a"]
    docs = to_corpus([row])
    assert [d["doc_id"] for d in docs] == ["7-0", "7-1"]
    assert docs[1]["is_selected"] is True and docs[0]["question_id"] == "7"
