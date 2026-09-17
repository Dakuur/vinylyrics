from __future__ import annotations

from enum import Enum

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.palette import FALLBACK_PALETTE, Palette, extract_palette
from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.state.clock import ClockConfig, PlaybackClock


class DisplayState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PLAYING = "PLAYING"
    UNIDENTIFIED = "UNIDENTIFIED"


def _same_track(a: "RecognitionResult | None", b: RecognitionResult) -> bool:
    return a is not None and a.title == b.title and a.artist == b.artist


class PlaybackSession:
    def __init__(self, clock_config: ClockConfig = ClockConfig()):
        self._clock_config = clock_config
        self._state = DisplayState.IDLE
        self._track: "RecognitionResult | None" = None
        self._lyrics: "LyricsResult | None" = None
        self._palette: Palette = FALLBACK_PALETTE
        self._clock: "PlaybackClock | None" = None

    def on_listening_started(self) -> None:
        self._state = DisplayState.LISTENING

    def on_recognized(self, result: RecognitionResult, lyrics: "LyricsResult | None", wall_time: float) -> None:
        if not _same_track(self._track, result) or self._clock is None:
            self._clock = PlaybackClock(self._clock_config)
            self._palette = extract_palette(result.cover_url)

        self._clock.add_anchor(wall_time=wall_time, position_sec=result.offset or 0.0, timeskew=result.timeskew or 0.0)
        self._track = result
        self._lyrics = lyrics
        self._state = DisplayState.PLAYING

    def on_unidentified(self) -> None:
        self._state = DisplayState.UNIDENTIFIED

    def on_track_gap(self) -> None:
        pass  # a signal, not a trigger — see spec §2; nothing to clear here

    def on_stopped(self) -> None:
        self._state = DisplayState.IDLE
        self._track = None
        self._lyrics = None
        self._palette = FALLBACK_PALETTE
        self._clock = None

    def to_payload(self, now: float) -> dict:
        track_payload = None
        if self._track is not None:
            track_payload = {
                "title": self._track.title,
                "artist": self._track.artist,
                "album": self._track.album,
                "cover_url": self._track.cover_url,
            }

        lyrics_payload = []
        if self._lyrics is not None and self._lyrics.has_synced:
            lyrics_payload = [{"ms": line.ms, "text": line.text} for line in self._lyrics.synced_lines]

        clock_payload = None
        if self._clock is not None and self._clock.is_anchored:
            clock_payload = {
                "anchor_wall": self._clock._anchor_wall,
                "anchor_ms": self._clock._anchor_position * 1000.0,
                "speed": self._clock.speed,
            }

        return {
            "state": self._state,
            "track": track_payload,
            "palette": {"bg": self._palette.bg, "fg": self._palette.fg, "dim": self._palette.dim},
            "lyrics": lyrics_payload,
            "clock": clock_payload,
        }
