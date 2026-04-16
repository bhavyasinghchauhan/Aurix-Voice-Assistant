"""Semantic embedding generation with caching."""
from functools import lru_cache
from typing import List

import numpy as np


class Embedder:
    """Wraps sentence-transformers with an LRU cache."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self._cache: dict[str, List[float]] = {}

    def encode(self, text: str) -> List[float]:
        if text in self._cache:
            return self._cache[text]
        vec = self.model.encode(text).tolist()
        self._cache[text] = vec
        return vec

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.encode(t) for t in texts]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    av, bv = np.asarray(a), np.asarray(b)
    denom = np.linalg.norm(av) * np.linalg.norm(bv)
    if denom == 0:
        return 0.0
    return float(np.dot(av, bv) / denom)


@lru_cache(maxsize=1024)
def hash_text(text: str) -> int:
    """Stable hash for text — used as a cheap dedup key."""
    return hash(text)
