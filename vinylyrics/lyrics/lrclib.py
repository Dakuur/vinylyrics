from __future__ import annotations

from lrclib import LrcLibAPI
from lrclib.exceptions import NotFoundError

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import parse_lrc

DEFAULT_USER_AGENT = "vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)"


def _to_lyrics_result(item) -> LyricsResult:
    synced = getattr(item, "synced_lyrics", None)
    lines = tuple(parse_lrc(synced)) if synced else ()
    return LyricsResult(
        synced_lines=lines,
        plain_lyrics=getattr(item, "plain_lyrics", None),
        instrumental=bool(getattr(item, "instrumental", False)),
    )


class LrcLibClient:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, api=None):
        self._api = api if api is not None else LrcLibAPI(user_agent=user_agent)

    def fetch(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None":
        try:
            item = self._api.get_lyrics(
                track_name=title, artist_name=artist, album_name=album or "", duration=int(round(duration))
            )
            return _to_lyrics_result(item)
        except NotFoundError:
            pass
        except Exception:
            return None

        try:
            results = self._api.search_lyrics(track_name=title, artist_name=artist)
        except Exception:
            return None

        candidates = [
            r for r in results
            if getattr(r, "synced_lyrics", None) or getattr(r, "plain_lyrics", None) or getattr(r, "instrumental", False)
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda r: abs((getattr(r, "duration", None) or 0) - duration))
        return _to_lyrics_result(best)
