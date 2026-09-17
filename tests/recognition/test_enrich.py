import asyncio
from unittest import mock

import numpy as np

from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.enrich import recognize_with_cover_art


class _FakeRecognizer:
    def __init__(self, result):
        self._result = result

    async def recognize(self, audio, sample_rate):
        return self._result


def _run(coro):
    return asyncio.run(coro)


def test_enrich_replaces_cover_with_musicbrainz_when_found():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value="https://coverartarchive.org/release/x/front"),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=None),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.cover_url == "https://coverartarchive.org/release/x/front"
    assert result.title == "Song"  # unchanged


def test_enrich_falls_back_to_shazam_cover_when_musicbrainz_finds_nothing():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value=None),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=None),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.cover_url == "shazam-cover"


def test_enrich_returns_none_when_recognition_fails():
    recognizer = _FakeRecognizer(None)
    result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))
    assert result is None


def test_enrich_populates_duration_from_musicbrainz():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value=None),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=238.0),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.duration == 238.0
    assert result.cover_url == "shazam-cover"  # unchanged, MB found no cover


def test_enrich_leaves_duration_none_when_musicbrainz_finds_nothing():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value=None),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=None),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.duration is None
