import asyncio
from pathlib import Path

import numpy as np
import pytest

from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.cache import DiskRecognitionCache
from vinylyrics.recognition.shazam import ShazamIORecognizer, _extract_album, _parse_response


FAKE_RESPONSE = {
    "matches": [{"id": "1", "offset": 12.5, "timeskew": 0.001, "frequencyskew": -0.0005}],
    "track": {
        "title": "Test Song",
        "subtitle": "Test Artist",
        "isrc": "US1234567890",
        "images": {"coverart": "https://example.com/cover.jpg"},
        "sections": [
            {"type": "SONG", "metadata": [{"title": "Album", "text": "Test Album"}, {"title": "Label", "text": "X"}]},
            {"type": "RELATED"},
        ],
    },
}

UNMATCHED_RESPONSE = {"matches": [], "location": {}, "timestamp": 0}


def test_parse_response_extracts_all_fields():
    result = _parse_response(FAKE_RESPONSE)
    assert result == RecognitionResult(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        cover_url="https://example.com/cover.jpg",
        offset=12.5,
        timeskew=0.001,
        frequencyskew=-0.0005,
        isrc="US1234567890",
    )


def test_parse_response_returns_none_when_no_track():
    assert _parse_response(UNMATCHED_RESPONSE) is None


def test_extract_album_returns_none_when_no_song_section():
    assert _extract_album({"sections": [{"type": "RELATED"}]}) is None


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def recognize(self, data: bytes) -> dict:
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _run(coro):
    return asyncio.run(coro)


def test_recognize_returns_parsed_result_on_success():
    client = _FakeClient([FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(client=client)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result.title == "Test Song"
    assert client.calls == 1


def test_recognize_returns_none_on_unmatched_response_without_retrying():
    client = _FakeClient([UNMATCHED_RESPONSE])
    recognizer = ShazamIORecognizer(client=client)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result is None
    assert client.calls == 1  # no retry on a clean "no match" response


def test_recognize_retries_on_exception_then_succeeds():
    client = _FakeClient([ConnectionError("boom"), FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(client=client, backoff_base_sec=0.001)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result.title == "Test Song"
    assert client.calls == 2


def test_recognize_returns_none_after_max_retries_all_failing():
    client = _FakeClient([ConnectionError("a"), ConnectionError("b"), ConnectionError("c")])
    recognizer = ShazamIORecognizer(client=client, max_retries=3, backoff_base_sec=0.001)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result is None
    assert client.calls == 3


def test_recognize_uses_cache_and_skips_client_on_hit(tmp_path: Path):
    cache = DiskRecognitionCache(tmp_path / "cache")
    client = _FakeClient([FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(cache=cache, client=client)
    audio = np.zeros(16000, dtype=np.float32)

    first = _run(recognizer.recognize(audio, 16000))
    assert client.calls == 1

    second = _run(recognizer.recognize(audio, 16000))
    assert client.calls == 1  # cache hit, client not called again
    assert second == first


def test_recognize_does_not_cache_unmatched_responses(tmp_path: Path):
    cache = DiskRecognitionCache(tmp_path / "cache")
    client = _FakeClient([UNMATCHED_RESPONSE, FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(cache=cache, client=client)
    audio = np.zeros(16000, dtype=np.float32)

    first = _run(recognizer.recognize(audio, 16000))
    assert first is None
    assert client.calls == 1

    second = _run(recognizer.recognize(audio, 16000))
    assert second.title == "Test Song"
    assert client.calls == 2  # not served from cache, since nothing was cached
