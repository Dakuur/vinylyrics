from pathlib import Path
from unittest import mock

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.parser import LyricLine
from vinylyrics.lyrics.service import LyricsService


def test_service_returns_cached_result_without_calling_client(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    cached_result = LyricsResult(synced_lines=(LyricLine(ms=0, text="cached"),), plain_lyrics=None, instrumental=False)
    cache.set("Artist", "Title", 200.0, cached_result)

    fake_client = mock.MagicMock()
    service = LyricsService(client=fake_client, cache=cache)

    result = service.get_lyrics("Artist", "Title", "Album", 200.0)

    assert result == cached_result
    fake_client.fetch.assert_not_called()


def test_service_fetches_and_caches_on_miss(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    fetched_result = LyricsResult(synced_lines=(LyricLine(ms=0, text="fresh"),), plain_lyrics=None, instrumental=False)
    fake_client = mock.MagicMock()
    fake_client.fetch.return_value = fetched_result
    service = LyricsService(client=fake_client, cache=cache)

    result = service.get_lyrics("Artist", "Title", "Album", 200.0)

    assert result == fetched_result
    fake_client.fetch.assert_called_once_with("Artist", "Title", "Album", 200.0)
    assert cache.get("Artist", "Title", 200.0) == fetched_result


def test_service_does_not_cache_a_failed_fetch(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    fake_client = mock.MagicMock()
    fake_client.fetch.return_value = None
    service = LyricsService(client=fake_client, cache=cache)

    result = service.get_lyrics("Artist", "Title", "Album", 200.0)

    assert result is None
    assert cache.get("Artist", "Title", 200.0) is None
    assert fake_client.fetch.call_count == 1

    # a second call should retry the client, not be stuck with a cached failure
    service.get_lyrics("Artist", "Title", "Album", 200.0)
    assert fake_client.fetch.call_count == 2
