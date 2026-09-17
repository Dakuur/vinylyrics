from __future__ import annotations

import numpy as np


class CircularAudioBuffer:
    def __init__(self, sample_rate: int, max_seconds: float = 20.0):
        if sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {sample_rate}")
        if max_seconds <= 0:
            raise ValueError(f"max_seconds must be positive, got {max_seconds}")
        self._sample_rate = sample_rate
        self._max_samples = int(max_seconds * sample_rate)
        self._data = np.zeros(0, dtype=np.float32)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def duration_available(self) -> float:
        return len(self._data) / self._sample_rate

    def push(self, samples: np.ndarray) -> None:
        if len(samples) == 0:
            return
        self._data = np.concatenate([self._data, samples.astype(np.float32)])
        if self._max_samples <= 0:
            self._data = self._data[len(self._data):]
        elif len(self._data) > self._max_samples:
            self._data = self._data[-self._max_samples :]

    def read_last(self, seconds: float) -> np.ndarray:
        n = int(seconds * self._sample_rate)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        return self._data[-n:].copy()
