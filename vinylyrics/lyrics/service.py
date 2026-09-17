from __future__ import annotations

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.lrclib import LrcLibClient


class LyricsService:
    def __init__(self, client: LrcLibClient, cache: LyricsCache):
        self._client = client
        self._cache = cache

    def get_lyrics(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None":
        cached = self._cache.get(artist, title, duration)
        if cached is not None:
            return cached

        result = self._client.fetch(artist, title, album, duration)
        if result is not None:
            self._cache.set(artist, title, duration, result)
        return result
