from __future__ import annotations

import asyncio
import io

import numpy as np
import soundfile as sf

from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.cache import DiskRecognitionCache, hash_audio


def _to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV")
    return buffer.getvalue()


def _extract_album(track: dict) -> "str | None":
    for section in track.get("sections", []):
        if section.get("type") != "SONG":
            continue
        for meta in section.get("metadata", []):
            if meta.get("title") == "Album":
                return meta.get("text")
    return None


def _parse_response(response: dict) -> "RecognitionResult | None":
    track = response.get("track")
    if not track:
        return None
    matches = response.get("matches", [])
    match = matches[0] if matches else {}
    return RecognitionResult(
        title=track.get("title", ""),
        artist=track.get("subtitle", ""),
        album=_extract_album(track),
        cover_url=track.get("images", {}).get("coverart"),
        offset=match.get("offset"),
        timeskew=match.get("timeskew"),
        frequencyskew=match.get("frequencyskew"),
        isrc=track.get("isrc"),
    )


class ShazamIORecognizer:
    def __init__(
        self,
        cache: "DiskRecognitionCache | None" = None,
        client=None,
        max_retries: int = 3,
        backoff_base_sec: float = 1.0,
    ):
        self._cache = cache
        self._client = client
        self._max_retries = max_retries
        self._backoff_base_sec = backoff_base_sec

    async def _get_client(self):
        if self._client is None:
            from shazamio import Shazam

            self._client = Shazam()
        return self._client

    async def recognize(self, audio: np.ndarray, sample_rate: int) -> "RecognitionResult | None":
        wav_bytes = _to_wav_bytes(audio, sample_rate)
        audio_hash = hash_audio(wav_bytes)

        if self._cache is not None:
            cached = self._cache.get(audio_hash)
            if cached is not None:
                return _parse_response(cached)

        client = await self._get_client()

        for attempt in range(self._max_retries):
            try:
                response = await client.recognize(wav_bytes)
            except Exception:
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._backoff_base_sec * (2**attempt))
                    continue
                return None
            else:
                if self._cache is not None and response.get("track"):
                    self._cache.set(audio_hash, response)
                return _parse_response(response)

        return None
