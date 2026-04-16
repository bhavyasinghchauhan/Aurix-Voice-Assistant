"""Latency monitoring helpers."""
import time
from contextlib import contextmanager
from typing import Dict, List

from utils.logger import get_logger

logger = get_logger(__name__)


class PerfTimer:
    """
    Lightweight latency tracker. Use as a context manager:

        with PerfTimer("llm_call") as t:
            ...
        print(t.elapsed)
    """

    _samples: Dict[str, List[float]] = {}

    def __init__(self, label: str):
        self.label = label
        self.start = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> "PerfTimer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.elapsed = time.perf_counter() - self.start
        PerfTimer._samples.setdefault(self.label, []).append(self.elapsed)
        logger.debug(f"{self.label}: {self.elapsed * 1000:.1f}ms")

    @classmethod
    def stats(cls, label: str) -> Dict[str, float]:
        samples = cls._samples.get(label, [])
        if not samples:
            return {"count": 0}
        return {
            "count": len(samples),
            "avg_ms": sum(samples) / len(samples) * 1000,
            "min_ms": min(samples) * 1000,
            "max_ms": max(samples) * 1000,
        }

    @classmethod
    def reset(cls) -> None:
        cls._samples.clear()


@contextmanager
def measure(label: str):
    with PerfTimer(label) as t:
        yield t
