from __future__ import annotations

from dataclasses import replace

import numpy as np

from vinylyrics.recognition.base import RecognitionResult, Recognizer
from vinylyrics.recognition.cover_art import find_cover_url_async


async def recognize_with_cover_art(
    recognizer: Recognizer, audio: np.ndarray, sample_rate: int
) -> "RecognitionResult | None":
    result = await recognizer.recognize(audio, sample_rate)
    if result is None:
        return None

    better_cover = await find_cover_url_async(result.artist, result.title, result.album, result.isrc)
    if better_cover:
        return replace(result, cover_url=better_cover)
    return result
