from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class RecognitionResult:
    title: str
    artist: str
    album: "str | None"
    cover_url: "str | None"
    offset: "float | None"
    timeskew: "float | None"
    frequencyskew: "float | None"
    isrc: "str | None"


class Recognizer(Protocol):
    async def recognize(self, audio: np.ndarray, sample_rate: int) -> "RecognitionResult | None": ...
