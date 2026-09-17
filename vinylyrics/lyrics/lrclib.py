from __future__ import annotations

import requests
from lrclib import LrcLibAPI
from lrclib.exceptions import NotFoundError

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import parse_lrc

DEFAULT_USER_AGENT = "vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)"
LRCLIB_TIMEOUT_SEC = 5.0


class _TimeoutSession(requests.Session):
    """Applies a default timeout to every request unless the caller overrides
    it. lrclibapi's LrcLibAPI never passes a timeout itself, so without this
    an unresponsive LRCLIB server would hang the calling thread forever."""

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", LRCLIB_TIMEOUT_SEC)
        return super().request(*args, **kwargs)


def _is_useful(item) -> bool:
    return bool(
        getattr(item, "synced_lyrics", None)
        or getattr(item, "plain_lyrics", None)
        or getattr(item, "instrumental", False)
    )


def _usefulness_tier(item) -> int:
    if getattr(item, "synced_lyrics", None):
        return 0
    if getattr(item, "plain_lyrics", None):
        return 1
    return 2  # instrumental-only


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
        self._api = api if api is not None else LrcLibAPI(user_agent=user_agent, session=_TimeoutSession())

    def fetch(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None":
        try:
            item = self._api.get_lyrics(
                track_name=title, artist_name=artist, album_name=album or "", duration=int(round(duration))
            )
            if _is_useful(item):
                return _to_lyrics_result(item)
        except NotFoundError:
            pass
        except Exception:
            return None

        try:
            results = self._api.search_lyrics(track_name=title, artist_name=artist)
        except Exception:
            return None

        candidates = [r for r in results if _is_useful(r)]
        if not candidates:
            return None
        best = min(
            candidates,
            key=lambda r: (_usefulness_tier(r), abs((getattr(r, "duration", None) or 0) - duration)),
        )
        return _to_lyrics_result(best)
