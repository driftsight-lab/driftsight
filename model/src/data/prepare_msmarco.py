"""MS MARCO v1.1에서 실험 질문 집합 msmarco_eval_v1과 코퍼스를 만든다.

규칙 (docs/experiments/data.md > 3.3 MS MARCO > 전처리):
1. 정답이 있는 질문만 쓴다. answers가 비었거나 "No Answer Present."만 있으면 제외.
2. RAGTruth QA 질문과 (소문자·공백 정리 후) 같은 질문은 제외한다.
3. 질문은 원문 그대로 쓴다.
4. 시드 42로 count개를 뽑는다.
코퍼스 = 뽑힌 질문의 후보 문단(passages) 전체.

출력: src/data/processed/ms_marco/{questions_eval_v1.jsonl, corpus.jsonl, stats.json}

재현 명령 (model/ 에서):
    uv run python -m src.data.prepare_msmarco --config configs/data/msmarco.yaml --resolve
    uv run python -m src.data.prepare_msmarco --config configs/data/msmarco.yaml \
        --out-dir src/data/processed/ms_marco
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml

from src.convert.resolve_revision import is_pinned
from src.data.preprocess_ragtruth import read_jsonl, write_jsonl

_SPACE = re.compile(r"\s+")
_REVISION_LINE = re.compile(r'^(\s*)revision:\s*""\s*$', re.MULTILINE)


def normalize(question: str) -> str:
    return _SPACE.sub(" ", question).strip().lower().rstrip("?").strip()


def has_answer(answers: Sequence[str], no_answer_markers: Sequence[str]) -> bool:
    real = [a for a in answers if a.strip() and a.strip() not in no_answer_markers]
    return bool(real)


def ragtruth_qa_questions(source_rows: Iterable[dict[str, Any]]) -> set[str]:
    """RAGTruth source_info에서 QA 과제의 질문을 정규화해 모은다."""
    questions = set()
    for row in source_rows:
        if row.get("task_type") != "QA":
            continue
        info = row.get("source_info")
        if isinstance(info, dict) and isinstance(info.get("question"), str):
            questions.add(normalize(info["question"]))
    return questions


def select_questions(
    rows: Sequence[dict[str, Any]],
    exclude: set[str],
    count: int,
    seed: int,
    no_answer_markers: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """규칙 1·2를 적용한 뒤 시드로 count개를 뽑는다. (뽑힌 행, 단계별 개수)."""
    answerable = [r for r in rows if has_answer(r["answers"], no_answer_markers)]
    kept = [r for r in answerable if normalize(r["query"]) not in exclude]
    kept.sort(key=lambda r: int(r["query_id"]))  # 입력 순서와 무관하게 같은 결과
    if count > len(kept):
        raise ValueError(f"뽑을 수 있는 질문이 {len(kept)}개뿐이라 {count}개를 뽑을 수 없음")
    picked = random.Random(seed).sample(kept, count)
    picked.sort(key=lambda r: int(r["query_id"]))
    stats = {
        "total": len(rows),
        "answerable": len(answerable),
        "after_ragtruth_exclusion": len(kept),
        "selected": len(picked),
    }
    return picked, stats


def to_question(row: dict[str, Any], no_answer_markers: Sequence[str]) -> dict[str, Any]:
    return {
        "question_id": str(row["query_id"]),
        "question": row["query"],
        "query_type": row["query_type"],
        "answers": [a for a in row["answers"] if a.strip() not in no_answer_markers],
    }


def to_corpus(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """질문별 후보 문단을 문서 1건씩으로 편다. doc_id = {query_id}-{순번}."""
    docs = []
    for row in rows:
        p = row["passages"]
        for i, (text, url, selected) in enumerate(
            zip(p["passage_text"], p["url"], p["is_selected"], strict=True)
        ):
            docs.append(
                {
                    "doc_id": f"{row['query_id']}-{i}",
                    "question_id": str(row["query_id"]),
                    "text": text,
                    "url": url,
                    "is_selected": bool(selected),
                }
            )
    return docs


def resolve(config_path: Path) -> None:
    from huggingface_hub import dataset_info

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sha = dataset_info(config["source"]["repo"]).sha
    print(f"{config['source']['repo']} hub main: {sha}")
    if is_pinned(config["source"].get("revision")):
        print("이미 고정됨 — 바꾸지 않음")
        return
    text = config_path.read_text(encoding="utf-8")
    new_text, n = _REVISION_LINE.subn(rf"\1revision: {sha}", text)
    if n != 1:
        raise ValueError(f'{config_path}: `revision: ""` 줄을 찾지 못함')
    config_path.write_text(new_text, encoding="utf-8")
    print(f"{config_path}에 기입함")


def prepare(config_path: Path, out_dir: Path) -> dict[str, Any]:
    from datasets import load_dataset

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    src, qcfg = config["source"], config["questions"]
    if not is_pinned(src.get("revision")):
        raise SystemExit("revision이 고정되지 않음. 먼저 --resolve 실행")

    ds = load_dataset(src["repo"], src["config"], split=src["split"], revision=src["revision"])
    rows = list(ds)
    exclude = ragtruth_qa_questions(read_jsonl(Path(config["exclude_ragtruth_source_info"])))
    picked, stats = select_questions(
        rows, exclude, qcfg["count"], qcfg["seed"], qcfg["no_answer_markers"]
    )
    markers = qcfg["no_answer_markers"]
    questions = [to_question(r, markers) for r in picked]
    corpus = to_corpus(picked)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "questions_eval_v1.jsonl", questions)
    write_jsonl(out_dir / "corpus.jsonl", corpus)
    report = {
        "name": qcfg["name"],
        "source": src,
        "ragtruth_qa_questions": len(exclude),
        **stats,
        "corpus_docs": len(corpus),
        "query_type": dict(sorted(Counter(q["query_type"] for q in questions).items())),
    }
    (out_dir / "stats.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("src/data/processed/ms_marco"))
    parser.add_argument("--resolve", action="store_true", help="데이터셋 커밋 해시 확인·기입만")
    args = parser.parse_args()
    if args.resolve:
        resolve(args.config)
        return
    print(json.dumps(prepare(args.config, args.out_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
