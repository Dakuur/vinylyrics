from dataclasses import dataclass, field
from unittest import mock

from vinylyrics.lyrics.lrclib import LrcLibClient
from lrclib.exceptions import NotFoundError


def _not_found_error() -> NotFoundError:
    # NotFoundError.__init__ reads .status_code/.reason/.url/.text/.headers
    # off its argument (expects a real requests.Response) — a MagicMock
    # satisfies that without needing a real HTTP response object.
    return NotFoundError(mock.MagicMock())


@dataclass
class _FakeLyricsItem:
    synced_lyrics: "str | None" = None
    plain_lyrics: "str | None" = None
    duration: "float | None" = None
    instrumental: bool = False


class _FakeApi:
    def __init__(self, get_result=None, get_raises=None, search_results=None, search_raises=None):
        self._get_result = get_result
        self._get_raises = get_raises
        self._search_results = search_results or []
        self._search_raises = search_raises
        self.get_calls = 0
        self.search_calls = 0

    def get_lyrics(self, track_name, artist_name, album_name, duration):
        self.get_calls += 1
        if self._get_raises is not None:
            raise self._get_raises
        return self._get_result

    def search_lyrics(self, track_name, artist_name):
        self.search_calls += 1
        if self._search_raises is not None:
            raise self._search_raises
        return self._search_results


def test_fetch_uses_get_result_when_found():
    api = _FakeApi(get_result=_FakeLyricsItem(synced_lyrics="[00:01.00]hola\n", plain_lyrics=None, instrumental=False))
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result.has_synced
    assert result.synced_lines[0].text == "hola"
    assert api.search_calls == 0  # /get succeeded, /search never tried


def test_fetch_falls_back_to_search_on_not_found():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[
            _FakeLyricsItem(synced_lyrics="[00:01.00]lejos\n", duration=100.0),
            _FakeLyricsItem(synced_lyrics="[00:01.00]cerca\n", duration=201.0),
        ],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert api.get_calls == 1
    assert api.search_calls == 1
    assert result.synced_lines[0].text == "cerca"  # duration 201 is closer to 200 than 100


def test_fetch_returns_none_when_search_finds_nothing_useful():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[_FakeLyricsItem(synced_lyrics=None, plain_lyrics=None, instrumental=False, duration=200.0)],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result is None


def test_fetch_returns_none_when_search_itself_fails():
    api = _FakeApi(get_raises=_not_found_error(), search_raises=ConnectionError("boom"))
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result is None


def test_fetch_prefers_instrumental_candidate_over_nothing():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[_FakeLyricsItem(instrumental=True, duration=200.0)],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result is not None
    assert result.instrumental is True
    assert result.has_synced is False


def test_fetch_falls_back_to_search_when_get_result_is_empty():
    empty_get_result = _FakeLyricsItem(synced_lyrics=None, plain_lyrics=None, instrumental=False, duration=None)
    api = _FakeApi(
        get_result=empty_get_result,
        search_results=[_FakeLyricsItem(synced_lyrics="[00:01.00]encontrado\n", duration=200.0)],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert api.search_calls == 1  # the empty /get result must not short-circuit the fallback
    assert result is not None
    assert result.synced_lines[0].text == "encontrado"


def test_fetch_prefers_synced_candidate_over_closer_duration_plain_only():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[
            _FakeLyricsItem(plain_lyrics="letra plana", duration=200.0),  # closest duration, but no sync
            _FakeLyricsItem(synced_lyrics="[00:01.00]sincronizado\n", duration=205.0),  # farther, but synced
        ],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result.has_synced
    assert result.synced_lines[0].text == "sincronizado"
