from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from vinylyrics.audio.levels import rms_dbfs


class AudioEvent(Enum):
    TRACK_GAP = auto()
    STOPPED = auto()


def compute_rms_windows(audio: np.ndarray, sample_rate: int, window_sec: float = 0.1) -> np.ndarray:
    window_samples = max(1, int(round(window_sec * sample_rate)))
    actual_window_sec = window_samples / sample_rate
    if not math.isclose(actual_window_sec, window_sec, rel_tol=1e-6, abs_tol=1e-9):
        raise ValueError(
            f"window_sec={window_sec} does not evenly divide into samples at "
            f"sample_rate={sample_rate} (closest achievable: {actual_window_sec})"
        )
    n_windows = len(audio) // window_samples
    if n_windows == 0:
        return np.zeros(0, dtype=np.float32)
    trimmed = audio[: n_windows * window_samples]
    reshaped = trimmed.reshape(n_windows, window_samples)
    return np.array([rms_dbfs(row) for row in reshaped], dtype=np.float32)


def calibrate_floor(calibration_audio: np.ndarray) -> float:
    return rms_dbfs(calibration_audio)


@dataclass(frozen=True)
class SilenceThresholds:
    enter_offset_db: float = 6.0
    exit_offset_db: float = 10.0
    gap_min_sec: float = 1.0
    gap_max_sec: float = 3.0
    stopped_sec: float = 10.0
    window_sec: float = 0.1


class SilenceDetector:
    def __init__(self, floor_dbfs: float, thresholds: SilenceThresholds = SilenceThresholds()):
        if not math.isfinite(floor_dbfs):
            raise ValueError(f"floor_dbfs must be finite, got {floor_dbfs!r}")
        self._floor = floor_dbfs
        self._thresholds = thresholds
        self._is_silent = False
        self._silence_windows = 0
        self._stopped_fired = False

    @property
    def is_silent(self) -> bool:
        return self._is_silent

    def process_window(self, window_dbfs: float) -> "AudioEvent | None":
        t = self._thresholds
        enter_threshold = self._floor + t.enter_offset_db
        exit_threshold = self._floor + t.exit_offset_db

        if not self._is_silent:
            if window_dbfs < enter_threshold:
                self._is_silent = True
                self._silence_windows = 1
                self._stopped_fired = False
            return None

        if window_dbfs > exit_threshold:
            duration = self._silence_windows * t.window_sec
            self._is_silent = False
            self._silence_windows = 0
            if t.gap_min_sec <= duration <= t.gap_max_sec:
                return AudioEvent.TRACK_GAP
            return None

        self._silence_windows += 1
        duration = self._silence_windows * t.window_sec
        if duration >= t.stopped_sec and not self._stopped_fired:
            self._stopped_fired = True
            return AudioEvent.STOPPED
        return None
