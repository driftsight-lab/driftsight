"""RAG 테스트용 가짜 구현 — 네트워크·모델 다운로드 없이 결정적으로 동작한다."""

import hashlib
from collections.abc import Sequence

import numpy as np

DIM = 32


class HashEmbedder:
    """단어 해시 bag-of-words → L2 정규화. 같은 단어를 공유하면 코사인이 높다."""

    name = "hash-embedder"

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim  # pgvector 테스트는 384 (corpus_chunks.embedding 차원)

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.lower().split():
                out[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1.0, norms)
