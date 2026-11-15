"""과제 B-1 채점자 신뢰도 1차 — MT-Bench 사람 판정과 Claude 채점자 판정의 일치도.

절차 (docs/experiments/protocol.md > 과제 B-1):
1. MT-Bench human 판정을 {A, B, tie}로 통일하고 question_id 단위로 조정용/보고용 분할(시드 42).
2. 보고용에서 (question_id, model_a, model_b, turn) 쌍을 sample_pairs개 뽑는다.
3. 쌍마다 채점자에게 A·B 순서를 바꿔 2번 판정시킨다 (judge-pairwise-v1 프롬프트).
4. 지표: 일치율(무승부 포함/제외), Cohen's kappa(3클래스), 순서 교환 일관성, 길이 편향,
   사람 간 일치율, GPT-4 판정 대비 일치율, 혼동 행렬, 불일치 사례.
결과는 api.md > 8.2 GET /api/v1/experiments/judge-reliability 응답 구조(camelCase)로 저장한다.

API 응답은 --cache에 쌓아 두고 다시 실행하면 재사용한다 (protocol.md > 0.1 응답 원문 캐시).
API 키는 환경 변수 ANTHROPIC_API_KEY 로만 받는다. 파일에 쓰지 않는다.

재현 명령 (model/ 에서):
    uv run python -m src.evaluate.judge_reliability --config configs/judge/b1_mtbench.yaml --resolve
    uv run python -m src.evaluate.judge_reliability --config configs/judge/b1_mtbench.yaml \
        --cache ../models/judge-b1-cache.jsonl --out ../models/judge-reliability-b1.json
    # 호출 없이 몇 건이 될지만 보기: --dry-run
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from src.convert.resolve_revision import is_pinned

LABELS = ("A", "B", "tie")
_WINNER = {"model_a": "A", "model_b": "B", "tie": "tie", "tie (bothbad)": "tie"}
_JSON = re.compile(r"\{.*\}", re.DOTALL)
_WINNER_TEXT = {"a": "A", "b": "B", "tie": "tie"}
_WINNER_FIELD = re.compile(r'"winner"\s*:\s*"(A|B|tie)"', re.IGNORECASE)
_REASON_FIELD = re.compile(r'"reason"\s*:\s*"(.*?)(?:"\s*}|$)', re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_REVISION_LINE = re.compile(r'^(\s*)revision:\s*""\s*$', re.MULTILINE)

Key = tuple[int, str, str, int]  # (question_id, model_a, model_b, turn)


# ---------- 데이터 준비 ----------


def normalize_winner(winner: str) -> str:
    """model_a→A, model_b→B, "tie"로 시작하는 값(tie, tie (bothbad), tie (inconsistent))→tie."""
    if winner in _WINNER:
        return _WINNER[winner]
    if winner.startswith("tie"):
        return "tie"
    raise ValueError(f"알 수 없는 winner 값: {winner}")


def pair_key(row: dict[str, Any]) -> Key:
    return (int(row["question_id"]), row["model_a"], row["model_b"], int(row["turn"]))


def split_questions(question_ids: Iterable[int], tune_ratio: float, seed: int) -> set[int]:
    """조정용(tune)으로 쓸 question_id 집합. 나머지가 보고용."""
    ids = sorted(set(question_ids))
    n_tune = round(len(ids) * tune_ratio)
    return set(random.Random(seed).sample(ids, n_tune))


def render_turn(conversation: Sequence[dict[str, str]], turn: int) -> tuple[str, str]:
    """(질문, 답변) 문자열. turn 2는 1·2턴을 이어 붙인다."""
    users = [m["content"] for m in conversation if m["role"] == "user"]
    bots = [m["content"] for m in conversation if m["role"] == "assistant"]
    if turn == 1:
        return users[0], bots[0]
    question = "\n".join(f"[Turn {i + 1}] {u}" for i, u in enumerate(users[:turn]))
    answer = "\n".join(f"[Turn {i + 1}] {b}" for i, b in enumerate(bots[:turn]))
    return question, answer


def load_prompt(path: Path) -> tuple[str, str]:
    """`## system` / `## user` 절로 나뉜 프롬프트 파일을 (system, user 템플릿)으로 읽는다."""
    text = _COMMENT.sub("", path.read_text(encoding="utf-8"))
    parts = re.split(r"^## (system|user)\s*$", text, flags=re.MULTILINE)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return sections["system"], sections["user"]


# ---------- 채점 호출 ----------


def parse_verdict(text: str) -> tuple[str, str]:
    """채점 응답에서 (winner, reason)을 꺼낸다.

    JSON 한 개로 읽는 것이 먼저다. max_tokens에 걸려 JSON이 중간에 잘렸거나 JSON이 여러 개
    붙은 경우에는, 맨 앞의 "winner" 값을 정규식으로 꺼낸다(판정은 이유보다 먼저 나온다).
    """
    match = _JSON.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
            winner = _WINNER_TEXT.get(str(data.get("winner", "")).strip().lower())
            if winner is not None:
                return winner, str(data.get("reason", ""))
        except json.JSONDecodeError:
            pass
    found = _WINNER_FIELD.search(text)
    if not found:
        raise ValueError("winner 없음" if match else "JSON 없음")
    reason = _REASON_FIELD.search(text)
    return _WINNER_TEXT[found.group(1).lower()], reason.group(1) if reason else ""


def swap_back(winner: str) -> str:
    """순서를 바꿔 물은 판정을 원래 (model_a, model_b) 기준으로 되돌린다."""
    return {"A": "B", "B": "A", "tie": "tie"}[winner]


def make_anthropic_call(model: str, max_tokens: int) -> Callable:
    import anthropic

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경 변수 사용

    def call(system: str, user: str) -> dict[str, Any]:
        start = time.perf_counter()
        # temperature는 보내지 않는다: anthropic 2.x(API 2026-10-21)는 받지 않는다.
        # 판정이 매번 같지 않을 수 있으므로 재현은 응답 원문 캐시로 한다 (judge_all).
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return {
            "text": "".join(b.text for b in msg.content if b.type == "text"),
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
            "latency_ms": round((time.perf_counter() - start) * 1000),
        }

    return call


def cache_id(key: Key, order: int) -> str:
    return "|".join(map(str, (*key, order)))


def judge_all(
    items: Sequence[dict[str, Any]],
    system: str,
    user_tmpl: str,
    call: Callable[[str, str], dict[str, Any]],
    cache_path: Path,
    workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """items마다 order 1(원래 순서)·2(바꾼 순서)를 판정. 캐시에 있으면 건너뛴다."""
    cache: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                cache[rec["id"]] = rec
    # 예전에 파싱에 실패한 기록은 저장된 응답 원문으로 다시 읽어 본다(추가 호출 없음).
    # 그래도 읽지 못하면 캐시에서 빼서 다시 호출하고, 앞선 호출의 토큰은 비용에 더한다.
    prev_tokens: dict[str, tuple[int, int]] = {}
    for cid, rec in list(cache.items()):
        if rec.get("winner") is not None:
            continue
        try:
            winner, reason = parse_verdict(rec.get("reason", ""))
        except ValueError:
            prev_tokens[cid] = (rec["input_tokens"], rec["output_tokens"])
            del cache[cid]
            continue
        order = int(cid.rsplit("|", 1)[1])
        rec.update(winner=winner if order == 1 else swap_back(winner), reason=reason)
        rec.update(error=None, recovered=True)
    jobs = []
    for item in items:
        for order in (1, 2):
            cid = cache_id(item["key"], order)
            if cid not in cache:
                jobs.append((cid, item, order))
    recovered = sum(1 for r in cache.values() if r.get("recovered"))
    print(
        f"판정 {len(items) * 2}건 중 캐시 {len(items) * 2 - len(jobs)}건"
        f"(잘린 응답에서 복구 {recovered}건), 새로 호출 {len(jobs)}건"
    )

    lock = threading.Lock()

    def work(job: tuple[str, dict[str, Any], int]) -> None:
        cid, item, order = job
        a, b = (
            (item["answer_a"], item["answer_b"])
            if order == 1
            else (
                item["answer_b"],
                item["answer_a"],
            )
        )
        user = user_tmpl.format(question=item["question"], answer_a=a, answer_b=b)
        rec: dict[str, Any] = {"id": cid}
        for attempt in range(2):  # 파싱 실패 시 1회 재시도 (interfaces.md > Judge)
            out = call(system, user)
            try:
                winner, reason = parse_verdict(out["text"])
                winner = winner if order == 1 else swap_back(winner)
                rec.update(winner=winner, reason=reason, error=None)
                break
            except (ValueError, json.JSONDecodeError) as e:
                rec.update(winner=None, reason=out["text"][:500], error=str(e))
        rec.update({k: out[k] for k in ("input_tokens", "output_tokens", "latency_ms")})
        if cid in prev_tokens:  # 다시 호출한 건은 앞선 실패 호출의 토큰도 비용에 넣는다
            rec["input_tokens"] += prev_tokens[cid][0]
            rec["output_tokens"] += prev_tokens[cid][1]
        rec["attempts"] = attempt + 1
        with lock:
            cache[cid] = rec
            with cache_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(work, jobs), 1):
            if i % 50 == 0:
                print(f"{i}/{len(jobs)}")
    return cache


# ---------- 지표 ----------


def cohens_kappa(a: Sequence[str], b: Sequence[str], labels: Sequence[str] = LABELS) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[label] * cb[label] for label in labels) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def agreement(judge: Sequence[str], human: Sequence[str], drop_human_ties: bool) -> float | None:
    pairs = [
        (j, h) for j, h in zip(judge, human, strict=True) if not (drop_human_ties and h == "tie")
    ]
    if not pairs:
        return None
    return sum(j == h for j, h in pairs) / len(pairs)


def human_human_agreement(votes_by_key: dict[Key, list[str]]) -> tuple[float | None, int]:
    """같은 쌍에 사람 판정이 2개 이상인 경우, 모든 판정 쌍의 일치 비율 (무승부 포함)."""
    same = total = 0
    for votes in votes_by_key.values():
        for x, y in itertools.combinations(votes, 2):
            same += x == y
            total += 1
    return (same / total if total else None), total


def longer_win_rate(
    verdicts: Sequence[str], len_a: Sequence[int], len_b: Sequence[int]
) -> float | None:
    """무승부가 아니고 길이가 다른 판정 중, 더 긴 답변이 이긴 비율."""
    wins = total = 0
    for v, la, lb in zip(verdicts, len_a, len_b, strict=True):
        if v == "tie" or la == lb:
            continue
        total += 1
        wins += (v == "A") == (la > lb)
    return wins / total if total else None


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, Any]:
    counts = Counter(zip(human, judge, strict=True))
    return {
        "labels": list(LABELS),
        "rows": "human",
        "cols": "judge",
        "matrix": [[counts[(h, j)] for j in LABELS] for h in LABELS],
    }


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def build_report(
    items: Sequence[dict[str, Any]],
    verdicts: dict[str, dict[str, Any]],
    votes_by_key: dict[Key, list[str]],
    report_votes_by_key: dict[Key, list[str]],
    gpt4_by_key: dict[Key, str],
    judge_key: str,
    price_in: float,
    price_out: float,
    max_disagreements: int,
) -> dict[str, Any]:
    j_votes, h_votes, j_cons_votes = [], [], []
    j_items, len_a, len_b = [], [], []
    h_len_votes, h_len_a, h_len_b = [], [], []
    consistent = valid = parse_fail = 0
    cost = 0.0
    disagreements = []
    gpt4_same = gpt4_total = 0

    for item in items:
        key = item["key"]
        v1, v2 = verdicts[cache_id(key, 1)], verdicts[cache_id(key, 2)]
        for v in (v1, v2):
            cost += (v["input_tokens"] * price_in + v["output_tokens"] * price_out) / 1e6
        if v1["winner"] is None or v2["winner"] is None:
            parse_fail += 1
            continue
        valid += 1
        consistent += v1["winner"] == v2["winner"]
        j_cons = v1["winner"] if v1["winner"] == v2["winner"] else "tie"
        la, lb = len(item["answer_a"]), len(item["answer_b"])
        j_items.append(v1["winner"])
        len_a.append(la)
        len_b.append(lb)
        if key in gpt4_by_key:
            gpt4_total += 1
            gpt4_same += gpt4_by_key[key] == v1["winner"]
        for h in votes_by_key[key]:
            j_votes.append(v1["winner"])
            j_cons_votes.append(j_cons)
            h_votes.append(h)
            h_len_votes.append(h)
            h_len_a.append(la)
            h_len_b.append(lb)
            if h != v1["winner"] and len(disagreements) < max_disagreements:
                disagreements.append(
                    {
                        "questionId": key[0],
                        "modelA": key[1],
                        "modelB": key[2],
                        "turn": key[3],
                        "human": h,
                        "judge": v1["winner"],
                        "judgeSwapped": v2["winner"],
                        "reason": v1["reason"],
                    }
                )

    hh, hh_pairs = human_human_agreement(report_votes_by_key)
    return {
        "judgeKey": judge_key,
        "sampleCount": valid,
        "agreementRate": _r(agreement(j_votes, h_votes, drop_human_ties=True)),
        "agreementRateWithTies": _r(agreement(j_votes, h_votes, drop_human_ties=False)),
        "cohensKappa": _r(cohens_kappa(j_votes, h_votes)) if h_votes else None,
        "humanAgreementRate": _r(hh),
        "positionBias": {"swapConsistency": _r(consistent / valid if valid else None)},
        "lengthBias": {"longerWinRate": _r(longer_win_rate(j_items, len_a, len_b))},
        "confusionMatrix": confusion(h_votes, j_votes),
        "disagreements": disagreements,
        # 아래는 api.md 8.2 필드 밖의 보조 정보 (화면 필수 아님)
        "details": {
            "dataset": "MT-Bench human judgments (보고용 분할)",
            "humanVotes": len(h_votes),
            "parseFailures": parse_fail,
            "humanLongerWinRate": _r(longer_win_rate(h_len_votes, h_len_a, h_len_b)),
            "humanAgreementPairs": hh_pairs,
            "humanAgreementScope": "보고용 분할 전체에서 같은 쌍에 사람 판정이 2개 이상인 경우",
            "swapCorrected": {
                "note": "두 순서 판정이 다르면 tie로 본 보정 판정 (protocol.md B-1 보정 실험)",
                "agreementRate": _r(agreement(j_cons_votes, h_votes, drop_human_ties=True)),
                "agreementRateWithTies": _r(
                    agreement(j_cons_votes, h_votes, drop_human_ties=False)
                ),
                "cohensKappa": _r(cohens_kappa(j_cons_votes, h_votes)) if h_votes else None,
            },
            "gpt4Agreement": _r(gpt4_same / gpt4_total if gpt4_total else None),
            "gpt4Pairs": gpt4_total,
            "costUsd": round(cost, 4),
        },
    }


# ---------- 실행 ----------


def prepare_items(
    human_rows: Sequence[dict[str, Any]], tune_ids: set[int], sample_pairs: int, seed: int
) -> tuple[list[dict[str, Any]], dict[Key, list[str]]]:
    """보고용 분할의 쌍 목록에서 sample_pairs개를 뽑아 채점 입력으로 만든다."""
    by_key: dict[Key, dict[str, Any]] = {}
    votes: dict[Key, list[str]] = defaultdict(list)
    for row in human_rows:
        key = pair_key(row)
        if key[0] in tune_ids:
            continue
        votes[key].append(normalize_winner(row["winner"]))
        by_key.setdefault(key, row)
    keys = sorted(by_key)
    picked = sorted(random.Random(seed).sample(keys, min(sample_pairs, len(keys))))
    items = []
    for key in picked:
        row = by_key[key]
        question, answer_a = render_turn(row["conversation_a"], key[3])
        _, answer_b = render_turn(row["conversation_b"], key[3])
        items.append({"key": key, "question": question, "answer_a": answer_a, "answer_b": answer_b})
    return items, dict(votes)


def resolve(config_path: Path) -> None:
    from huggingface_hub import dataset_info

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sha = dataset_info(config["dataset"]["repo"]).sha
    print(f"{config['dataset']['repo']} hub main: {sha}")
    if is_pinned(config["dataset"].get("revision")):
        print("이미 고정됨 — 바꾸지 않음")
        return
    text = config_path.read_text(encoding="utf-8")
    new_text, n = _REVISION_LINE.subn(rf"\1revision: {sha}", text)
    if n != 1:
        raise ValueError(f'{config_path}: `revision: ""` 줄을 찾지 못함')
    config_path.write_text(new_text, encoding="utf-8")
    print(f"{config_path}에 기입함")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("../models/judge-b1-cache.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("../models/judge-reliability-b1.json"))
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 건수만 출력")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.resolve:
        resolve(args.config)
        return

    from datasets import load_dataset

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    dcfg, jcfg = config["dataset"], config["judge"]
    if not is_pinned(dcfg.get("revision")):
        raise SystemExit("dataset revision이 고정되지 않음. 먼저 --resolve 실행")

    human = list(load_dataset(dcfg["repo"], split=dcfg["human_split"], revision=dcfg["revision"]))
    gpt4 = list(load_dataset(dcfg["repo"], split=dcfg["gpt4_split"], revision=dcfg["revision"]))
    tune_ids = split_questions(
        (int(r["question_id"]) for r in human), dcfg["tune_ratio"], dcfg["seed"]
    )
    items, votes = prepare_items(human, tune_ids, config["sample_pairs"], dcfg["seed"])
    gpt4_by_key = {pair_key(r): normalize_winner(r["winner"]) for r in gpt4}
    print(
        f"사람 판정 {len(human)}건, 조정용 질문 {len(tune_ids)}개, 보고용 쌍 {len(votes)}개, "
        f"이번 채점 {len(items)}쌍 → API 호출 {len(items) * 2}회"
    )
    if args.dry_run:
        return

    system, user_tmpl = load_prompt(Path(jcfg["prompt"]))
    call = make_anthropic_call(jcfg["model"], jcfg["max_tokens"])
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    verdicts = judge_all(items, system, user_tmpl, call, args.cache, args.workers)
    report = build_report(
        items,
        verdicts,
        votes,
        votes,
        gpt4_by_key,
        f"{jcfg['model']}-{jcfg['prompt_version']}",
        jcfg["price_input_per_mtok"],
        jcfg["price_output_per_mtok"],
        config["max_disagreements"],
    )
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    summary = {k: v for k, v in report.items() if k not in ("disagreements", "confusionMatrix")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"저장: {args.out}")


if __name__ == "__main__":
    main()
