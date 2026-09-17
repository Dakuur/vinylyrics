# vinylyrics/lyrics/cache.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine


class LyricsCache:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lyrics_cache (
                artist TEXT NOT NULL,
                title TEXT NOT NULL,
                duration INTEGER NOT NULL,
                synced_lines_json TEXT NOT NULL,
                plain_lyrics TEXT,
                instrumental INTEGER NOT NULL,
                PRIMARY KEY (artist, title, duration)
            )
            """
        )
        self._conn.commit()

    def get(self, artist: str, title: str, duration: float) -> "LyricsResult | None":
        row = self._conn.execute(
            "SELECT synced_lines_json, plain_lyrics, instrumental FROM lyrics_cache "
            "WHERE artist = ? AND title = ? AND duration = ?",
            (artist, title, round(duration)),
        ).fetchone()
        if row is None:
            return None
        synced_lines_json, plain_lyrics, instrumental = row
        lines = tuple(LyricLine(ms=item["ms"], text=item["text"]) for item in json.loads(synced_lines_json))
        return LyricsResult(synced_lines=lines, plain_lyrics=plain_lyrics, instrumental=bool(instrumental))

    def set(self, artist: str, title: str, duration: float, result: "LyricsResult") -> None:
        synced_lines_json = json.dumps([{"ms": l.ms, "text": l.text} for l in result.synced_lines])
        self._conn.execute(
            "INSERT OR REPLACE INTO lyrics_cache VALUES (?, ?, ?, ?, ?, ?)",
            (artist, title, round(duration), synced_lines_json, result.plain_lyrics, int(result.instrumental)),
        )
        self._conn.commit()
