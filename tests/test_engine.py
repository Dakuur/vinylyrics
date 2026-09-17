import asyncio
from unittest import mock

import numpy as np
import pytest

from vinylyrics.engine import Engine, EngineConfig
from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine
from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.cadence import CadenceConfig
from vinylyrics.state.session import DisplayState, PlaybackSession


class _FakeClock:
    """Manually-advanced now_fn for deterministic cadence tests."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _FakeSource:
    """Yields a fixed sequence of chunks, raising StopAsyncIteration-like
    signal via a sentinel once exhausted so tests can await engine.run()
    for a bounded number of iterations."""

    def __init__(self, chunks: list[np.ndarray], sample_rate: int = 16000):
        self._chunks = list(chunks)
        self._sample_rate = sample_rate
        self.reads = 0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def read(self, seconds: float) -> np.ndarray:
        self.reads += 1
        if self._chunks:
            return self._chunks.pop(0)
        raise asyncio.CancelledError()  # test's cue to stop the loop


class _FakeRecognizer:
    def __init__(self, result: "RecognitionResult | None"):
        self._result = result
        self.calls = 0

    async def recognize(self, audio, sample_rate):
        self.calls += 1
        return self._result


class _FakeLyricsService:
    def __init__(self, result: "LyricsResult | None"):
        self._result = result

    def get_lyrics(self, artist, title, album, duration):
        return self._result


def _loud_chunk(sample_rate: int, seconds: float, amplitude: float = 0.3) -> np.ndarray:
    n = int(seconds * sample_rate)
    rng = np.random.default_rng(42)
    return (rng.standard_normal(n) * amplitude).astype(np.float32)


def _quiet_chunk(sample_rate: int, seconds: float, amplitude: float = 0.001) -> np.ndarray:
    # NOT all-zero: SilenceDetector.__init__ requires a finite calibration
    # floor, and rms_dbfs(all-zero) is exactly float("-inf") (verified —
    # calibrate_floor(np.zeros(...)) raises inside SilenceDetector's own
    # finiteness check). Low-amplitude noise gives a realistic, finite
    # "quiet surface noise" floor instead, matching spec §2's own point
    # that the calibration floor is never digital silence.
    n = int(seconds * sample_rate)
    rng = np.random.default_rng(7)
    return (rng.standard_normal(n) * amplitude).astype(np.float32)


@pytest.fixture(autouse=True)
def _no_real_network_enrichment():
    # Engine._recognize_and_update calls the REAL recognize_with_cover_art,
    # which — whenever a test's fake recognizer returns a non-None result —
    # goes on to call the REAL find_cover_url_async/find_track_duration_async
    # against MusicBrainz. Verified live during planning: without this,
    # several of this file's tests silently made real network calls (one
    # measured at 7+ seconds, occasionally flaky depending on network
    # conditions) despite this being part of the OFFLINE suite. These are
    # the same two functions Task 1's own enrich tests mock, for the same
    # reason — applied here too since the engine exercises the same code
    # path.
    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async", new=mock.AsyncMock(return_value=None)
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async", new=mock.AsyncMock(return_value=None)
    ):
        yield


def _run_engine_until_cancelled(engine: Engine) -> None:
    # run() is cancelled once the fake source's chunks are exhausted, but
    # any recognition it fired is a background task (asyncio.ensure_future,
    # never awaited by run() itself — by design, so the audio loop never
    # blocks on a network call). Verified live during planning: without
    # also awaiting that task here, run() being cancelled races ahead of
    # the (even though non-blocking) recognition coroutine ever getting a
    # chance to execute, and assertions on session state see stale data —
    # two of this file's tests failed on the first run for exactly this
    # reason before this helper awaited the pending task too.
    async def runner():
        with pytest.raises(asyncio.CancelledError):
            await engine.run()
        if engine._recognition_task is not None:
            await engine._recognition_task
    asyncio.run(runner())


def test_engine_transitions_to_listening_on_start():
    sr = 16000
    # first chunk is consumed by calibration, the rest by window reads —
    # all quiet, so no recognition should ever be triggered
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [_quiet_chunk(sr, 0.1)] * 3, sample_rate=sr)
    session = PlaybackSession()
    engine = Engine(
        source=source, recognizer=_FakeRecognizer(None), lyrics_service=_FakeLyricsService(None),
        session=session, on_change=lambda: None, now_fn=_FakeClock(),
    )
    _run_engine_until_cancelled(engine)
    assert session.to_payload(now=0.0)["state"] in (DisplayState.LISTENING, DisplayState.IDLE)


def test_engine_calls_recognizer_once_loud_audio_is_seen_and_updates_session():
    sr = 16000
    loud = _loud_chunk(sr, 0.1)
    # first chunk (calibration) is quiet, so the floor sits well below the
    # loud chunks that follow — otherwise the floor would equal the loud
    # level itself and the detector would misclassify loud audio as silence
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [loud] * 5, sample_rate=sr)
    result = RecognitionResult(
        title="Bonito", artist="Jarabe de Palo", album="Depende", cover_url=None,
        offset=10.0, timeskew=0.0, frequencyskew=0.0, isrc=None, duration=238.0,
    )
    recognizer = _FakeRecognizer(result)
    lyrics = LyricsResult(synced_lines=(LyricLine(ms=0, text="hola"),), plain_lyrics=None, instrumental=False)
    lyrics_service = _FakeLyricsService(lyrics)
    session = PlaybackSession()
    changes = []

    engine = Engine(
        source=source, recognizer=recognizer, lyrics_service=lyrics_service, session=session,
        on_change=lambda: changes.append(session.to_payload(now=0.0)["state"]),
        now_fn=_FakeClock(),
    )
    _run_engine_until_cancelled(engine)

    assert recognizer.calls >= 1
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["track"]["title"] == "Bonito"
    assert DisplayState.PLAYING in changes


def test_engine_respects_min_call_interval_between_recognitions():
    sr = 16000
    loud = _loud_chunk(sr, 0.1)
    # first chunk (calibration) is quiet; the rest are loud and
    # recognition-eligible if cadence allows it
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [loud] * 20, sample_rate=sr)
    result = RecognitionResult(
        title="Song", artist="Artist", album=None, cover_url=None,
        offset=0.0, timeskew=0.0, frequencyskew=0.0, isrc=None, duration=None,
    )
    recognizer = _FakeRecognizer(result)
    session = PlaybackSession()
    clock = _FakeClock()

    engine = Engine(
        source=source, recognizer=recognizer, lyrics_service=_FakeLyricsService(None), session=session,
        on_change=lambda: None, cadence_config=CadenceConfig(min_interval_sec=8.0), now_fn=clock,
    )

    async def drive():
        task = asyncio.ensure_future(engine.run())
        for _ in range(20):
            await asyncio.sleep(0)  # let queued callbacks/tasks progress
            clock.advance(0.1)  # matches window_sec, simulates real time passing
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(drive())
    # 20 iterations * 0.1s = 2.0s of simulated time — well under the 8s
    # minimum interval, so the recognizer must have been called at most once
    assert recognizer.calls <= 1


def test_debug_snapshot_reports_last_recognition_and_speed():
    sr = 16000
    result = RecognitionResult(
        title="Song", artist="Artist", album=None, cover_url=None,
        offset=5.0, timeskew=0.01, frequencyskew=0.0, isrc=None, duration=None,
    )
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [_loud_chunk(sr, 0.1)] * 3, sample_rate=sr)
    session = PlaybackSession()
    engine = Engine(
        source=source, recognizer=_FakeRecognizer(result), lyrics_service=_FakeLyricsService(None),
        session=session, on_change=lambda: None, now_fn=_FakeClock(),
    )
    _run_engine_until_cancelled(engine)

    snapshot = engine.debug_snapshot()
    assert snapshot["last_recognition"]["title"] == "Song"
    assert snapshot["speed"] == pytest.approx(1.01)
    assert "rms_dbfs" in snapshot
    assert isinstance(snapshot["anchor_history"], list)


class _EofSource:
    """Mimics FileSource's real end-of-stream behavior: returns real chunks,
    then an empty array forever once exhausted (never raises)."""

    def __init__(self, chunks: list[np.ndarray], sample_rate: int = 16000):
        self._chunks = list(chunks)
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def read(self, seconds: float) -> np.ndarray:
        if self._chunks:
            return self._chunks.pop(0)
        return np.zeros(0, dtype=np.float32)


def test_engine_stops_cleanly_on_end_of_stream_instead_of_spinning():
    sr = 16000
    source = _EofSource([_quiet_chunk(sr, 3.0)] + [_quiet_chunk(sr, 0.1)] * 3, sample_rate=sr)
    session = PlaybackSession()
    engine = Engine(
        source=source, recognizer=_FakeRecognizer(None), lyrics_service=_FakeLyricsService(None),
        session=session, on_change=lambda: None, now_fn=_FakeClock(),
    )

    async def run_with_timeout():
        await asyncio.wait_for(engine.run(), timeout=2.0)

    # run() must return on its own (end of stream), not hang — verified
    # live that without an explicit empty-chunk check, this would spin
    # forever computing NaN rms_dbfs on empty arrays instead of returning
    # (see the Global Constraints note and the `run()` implementation below).
    asyncio.run(run_with_timeout())

    assert session.to_payload(now=0.0)["state"] == DisplayState.IDLE
