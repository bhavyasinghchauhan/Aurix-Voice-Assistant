"""Audio processing helpers."""
import struct
from typing import Iterable, List

import numpy as np


def pcm_bytes_to_int16(pcm_bytes: bytes) -> List[int]:
    """Convert raw PCM byte buffer to a list of int16 samples."""
    count = len(pcm_bytes) // 2
    return list(struct.unpack_from("h" * count, pcm_bytes))


def rms_level(samples: Iterable[int]) -> float:
    """Compute RMS amplitude for a buffer of int16 samples."""
    arr = np.asarray(list(samples), dtype=np.float32)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


def is_silence(samples: Iterable[int], threshold: float = 500.0) -> bool:
    """Detect whether a frame is below the silence threshold."""
    return rms_level(samples) < threshold


def normalize(samples: Iterable[int]) -> np.ndarray:
    """Normalize int16 samples to float32 in [-1, 1]."""
    arr = np.asarray(list(samples), dtype=np.float32)
    return arr / 32768.0
