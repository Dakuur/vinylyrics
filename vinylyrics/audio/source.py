from __future__ import annotations

import time
from math import gcd
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


class AudioSource(Protocol):
    def read(self, seconds: float) -> np.ndarray: ...

    @property
    def sample_rate(self) -> int: ...


def _resample_fixed(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr == target_sr:
        return audio.astype(np.float32)
    g = gcd(source_sr, target_sr)
    up = target_sr // g
    down = source_sr // g
    return resample_poly(audio, up, down).astype(np.float32)


class FileSource:
    def __init__(self, path: Path, *, realtime: bool = False, sample_rate: int = 16000):
        audio, source_sr = sf.read(path, dtype="float32", always_2d=True)
        mono = audio.mean(axis=1).astype(np.float32)
        self._audio = _resample_fixed(mono, source_sr, sample_rate)
        self._sample_rate = sample_rate
        self._cursor = 0
        self._realtime = realtime

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def read(self, seconds: float) -> np.ndarray:
        n = int(seconds * self._sample_rate)
        start = self._cursor
        end = min(start + n, len(self._audio))
        chunk = self._audio[start:end]
        self._cursor = end
        if self._realtime:
            time.sleep(seconds)
        return chunk


def list_devices() -> list[dict]:
    import sounddevice as sd

    return list(sd.query_devices())


class LineInSource:
    def __init__(self, device: "int | str | None" = None, sample_rate: int = 16000):
        self._device = device
        self._sample_rate = sample_rate
        self._stream = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _ensure_stream(self):
        if self._stream is None:
            import sounddevice as sd

            self._stream = sd.InputStream(
                device=self._device, channels=1, samplerate=self._sample_rate, dtype="float32"
            )
            self._stream.start()

    def read(self, seconds: float) -> np.ndarray:
        self._ensure_stream()
        n = int(seconds * self._sample_rate)
        data, _overflowed = self._stream.read(n)
        return data[:, 0].astype(np.float32)
