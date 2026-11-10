from src.data.eda_ragtruth import summarize, to_markdown


def _row(source_id, task, labels):
    return {
        "id": "0",
        "source_id": source_id,
        "task_type": task,
        "model": "m",
        "quality": "good",
        "prompt": "Context: Paris is in France.",
        "answer": "Paris is in Germany.",
        "labels": labels,
    }


LABEL = {
    "start": 12,
    "end": 20,
    "label_type": "Evident Conflict",
    "implicit_true": True,
    "due_to_null": False,
}


def test_summarize_counts_and_rates():
    splits = {
        "train": [_row("s1", "QA", [LABEL]), _row("s1", "QA", [])],
        "dev": [_row("s2", "Summary", [])],
        "test": [_row("t1", "QA", [LABEL, {**LABEL, "start": 15}])],
    }
    s = summarize(splits)
    assert s["splits"]["train"] == {"responses": 2, "sources": 1, "hallucinated_ratio": 0.5}
    assert s["by_task_type"]["test"]["QA"]["hallucinated_ratio"] == 1.0
    assert s["implicit_true_spans"] == 3
    assert s["responses_only_implicit_true"] == 2
    assert s["responses_with_overlapping_spans"]["test"] == 1
    assert "RAGTruth EDA" in to_markdown(s)
