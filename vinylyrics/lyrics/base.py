from __future__ import annotations

from dataclasses import dataclass

from vinylyrics.lyrics.parser import LyricLine


@dataclass(frozen=True)
class LyricsResult:
    synced_lines: "tuple[LyricLine, ...]"
    plain_lyrics: "str | None"
    instrumental: bool

    @property
    def has_synced(self) -> bool:
        return len(self.synced_lines) > 0
