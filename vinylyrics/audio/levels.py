from __future__ import annotations

import numpy as np


def rms_dbfs(signal: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(signal.astype(np.float64) ** 2)))
    if rms <= 0:
        return float("-inf")
    return 20 * np.log10(rms)


def to_dbfs(signal: np.ndarray, target_dbfs: float) -> np.ndarray:
    current = rms_dbfs(signal)
    if current == float("-inf"):
        return signal.astype(np.float32)
    gain = 10 ** ((target_dbfs - current) / 20)
    return (signal * gain).astype(np.float32)
