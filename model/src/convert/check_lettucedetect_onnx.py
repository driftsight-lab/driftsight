"""LettuceDetect를 고정 리비전으로 받아 ONNX로 내보내고, PyTorch 결과와 같은지 확인한다.

확인하는 것:
- ONNX Runtime(CPU)에서 로드·추론이 되는지
- RAGTruth test 앞쪽 N개에서 PyTorch와 ONNX의 logit 최대 차이, 답변 토큰 argmax 일치율,
  응답 단위 판정(환각 토큰이 하나라도 있는가) 일치 수
- ONNX 파일 크기(MiB), 응답 1개씩 넣었을 때 CPU 지연 p50/p95(ms) — 측정한 PC 기준 참고값

입력은 LettuceDetect와 같게 tokenizer(prompt, answer, truncation="only_first")로 만든다.
결과는 --report에 JSON으로 저장한다. ONNX 파일은 --onnx-dir에 저장하며 Git에 올리지 않는다.

재현 명령 (model/ 에서):
    uv run python -m src.convert.check_lettucedetect_onnx \
        --config configs/models/lettucedetect.yaml \
        --test-file src/data/processed/ragtruth/test.jsonl \
        --onnx-dir ../models/lettucedetect-onnx --report ../models/lettucedetect-onnx-check.json
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from importlib.metadata import version
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import yaml

from src.convert.resolve_revision import is_pinned
from src.data.preprocess_ragtruth import read_jsonl


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def onnx_size_mib(onnx_dir: Path) -> float:
    files = [p for p in onnx_dir.iterdir() if p.name.endswith((".onnx", ".onnx_data"))]
    if not files:
        raise FileNotFoundError(f"{onnx_dir}에 ONNX 파일이 없음")
    return round(sum(p.stat().st_size for p in files) / 2**20, 1)


def run_check(
    repo: str,
    revision: str | None,
    rows: list[dict[str, Any]],
    onnx_dir: Path,
    max_length: int,
    warmup: int,
) -> dict[str, Any]:
    import onnxruntime
    import torch
    import transformers
    from optimum.onnxruntime import ORTModelForTokenClassification
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(repo, revision=revision)
    pt_model = AutoModelForTokenClassification.from_pretrained(repo, revision=revision).eval()
    ort_model = ORTModelForTokenClassification.from_pretrained(
        repo, revision=revision, export=True, provider="CPUExecutionProvider"
    )
    ort_model.save_pretrained(onnx_dir)
    tokenizer.save_pretrained(onnx_dir)
    # 저장한 파일을 다시 읽어 실제 워커처럼 "파일에서 로드"가 되는지 확인한다.
    ort_model = ORTModelForTokenClassification.from_pretrained(
        onnx_dir, provider="CPUExecutionProvider"
    )

    encoded = []
    truncated = 0
    for row in rows:
        enc = tokenizer(
            row["prompt"],
            row["answer"],
            truncation="only_first",
            max_length=max_length,
            return_tensors="pt",
        )
        full = len(tokenizer(row["prompt"], row["answer"], truncation=False)["input_ids"])
        truncated += full > max_length
        answer_mask = np.array([sid == 1 for sid in enc.sequence_ids(0)])
        encoded.append((enc, answer_mask))

    for enc, _ in encoded[:warmup]:
        ort_model(**enc)

    max_abs_diff = 0.0
    agree_tokens = total_tokens = 0
    agree_examples = 0
    latencies_ms: list[float] = []
    for enc, answer_mask in encoded:
        with torch.no_grad():
            pt_logits = pt_model(**enc).logits[0].numpy()
        start = time.perf_counter()
        ort_logits = ort_model(**enc).logits[0]
        latencies_ms.append((time.perf_counter() - start) * 1000)
        ort_logits = np.asarray(ort_logits)

        max_abs_diff = max(max_abs_diff, float(np.abs(pt_logits - ort_logits).max()))
        pt_pred = pt_logits.argmax(-1)[answer_mask]
        ort_pred = ort_logits.argmax(-1)[answer_mask]
        agree_tokens += int((pt_pred == ort_pred).sum())
        total_tokens += int(answer_mask.sum())
        agree_examples += bool((pt_pred == 1).any()) == bool((ort_pred == 1).any())

    return {
        "model": {"repo": repo, "revision": revision},
        "versions": {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "optimum": version("optimum"),
            "optimum-onnx": version("optimum-onnx"),
            "onnxruntime": onnxruntime.__version__,
        },
        "machine": {"platform": platform.platform(), "processor": platform.processor()},
        "samples": len(encoded),
        "max_length": max_length,
        "samples_over_max_length": truncated,
        "onnx_size_mib": onnx_size_mib(onnx_dir),
        "max_abs_logit_diff": max_abs_diff,
        "answer_token_argmax_agreement": round(agree_tokens / total_tokens, 6),
        "example_prediction_agreement": f"{agree_examples}/{len(encoded)}",
        "cpu_latency_ms_batch1": {
            "p50": round(median(latencies_ms), 1),
            "p95": round(_p95(latencies_ms), 1),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--test-file", type=Path, required=True)
    parser.add_argument("--onnx-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not is_pinned(config.get("revision")):
        parser.error(f"{args.config}의 revision이 40자리 커밋 해시가 아님. resolve_revision 먼저")

    rows = sorted(read_jsonl(args.test_file), key=lambda r: int(r["id"]))
    rows = rows[: config["check"]["samples"]]
    args.onnx_dir.mkdir(parents=True, exist_ok=True)
    report = run_check(
        config["repo"],
        config["revision"],
        rows,
        args.onnx_dir,
        config["max_length"],
        config["check"]["warmup"],
    )
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
