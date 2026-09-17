# tests/lyrics/test_cache.py
from pathlib import Path

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.parser import LyricLine


def test_cache_returns_none_on_miss(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    assert cache.get("Jarabe de Palo", "Bonito", 238.0) is None


def test_cache_roundtrip_with_synced_lines(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(
        synced_lines=(LyricLine(ms=1000, text="hola"), LyricLine(ms=2000, text="mundo")),
        plain_lyrics=None,
        instrumental=False,
    )
    cache.set("Jarabe de Palo", "Bonito", 238.0, result)

    fetched = cache.get("Jarabe de Palo", "Bonito", 238.0)
    assert fetched == result


def test_cache_roundtrip_with_plain_lyrics_only(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(synced_lines=(), plain_lyrics="letra sin sincronizar", instrumental=False)
    cache.set("Artist", "Title", 200.0, result)

    fetched = cache.get("Artist", "Title", 200.0)
    assert fetched == result


def test_cache_roundtrip_instrumental(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(synced_lines=(), plain_lyrics=None, instrumental=True)
    cache.set("Artist", "Instrumental Track", 180.0, result)

    fetched = cache.get("Artist", "Instrumental Track", 180.0)
    assert fetched.instrumental is True


def test_cache_key_rounds_duration_to_nearest_second(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(synced_lines=(), plain_lyrics="x", instrumental=False)
    cache.set("Artist", "Title", 200.4, result)

    assert cache.get("Artist", "Title", 200.0) == result
    assert cache.get("Artist", "Title", 200.49) == result


def test_cache_creates_db_file_if_missing(tmp_path: Path):
    db_path = tmp_path / "nested" / "lyrics.sqlite3"
    assert not db_path.exists()
    LyricsCache(db_path)
    assert db_path.exists()
