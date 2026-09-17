from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

from vinylyrics.audio.buffer import CircularAudioBuffer
from vinylyrics.audio.levels import rms_dbfs
from vinylyrics.audio.vad import AudioEvent, SilenceDetector, SilenceThresholds, calibrate_floor
from vinylyrics.lyrics.service import LyricsService
from vinylyrics.recognition.base import Recognizer
from vinylyrics.recognition.cadence import CadenceConfig, CallCadencePolicy
from vinylyrics.recognition.enrich import recognize_with_cover_art
from vinylyrics.state.session import PlaybackSession


class _AudioSource(Protocol):
    def read(self, seconds: float) -> np.ndarray: ...
    @property
    def sample_rate(self) -> int: ...


@dataclass(frozen=True)
class EngineConfig:
    window_sec: float = 0.1
    recognition_window_sec: float = 12.0
    calibration_sec: float = 3.0
    max_consecutive_failures: int = 3


class Engine:
    def __init__(
        self,
        source: _AudioSource,
        recognizer: Recognizer,
        lyrics_service: LyricsService,
        session: PlaybackSession,
        on_change: Callable[[], None],
        thresholds: SilenceThresholds = SilenceThresholds(),
        cadence_config: CadenceConfig = CadenceConfig(),
        config: EngineConfig = EngineConfig(),
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self._source = source
        self._recognizer = recognizer
        self._lyrics_service = lyrics_service
        self._session = session
        self._on_change = on_change
        self._thresholds = thresholds
        self._cadence = CallCadencePolicy(cadence_config)
        self._config = config
        self._now_fn = now_fn

        self._buffer = CircularAudioBuffer(source.sample_rate, max_seconds=20.0)
        self._detector: "SilenceDetector | None" = None
        self._consecutive_failures = 0
        self._last_rms_dbfs = float("-inf")
        self._last_recognition: "dict | None" = None
        self._recognition_task: "asyncio.Task | None" = None

    def debug_snapshot(self) -> dict:
        clock = self._session._clock
        return {
            "last_recognition": self._last_recognition,
            "speed": clock.speed if clock is not None and clock.is_anchored else None,
            "rms_dbfs": self._last_rms_dbfs,
            "anchor_history": list(clock._history) if clock is not None else [],
        }

    async def run(self) -> None:
        self._session.on_listening_started()
        self._on_change()

        calibration = await asyncio.to_thread(self._source.read, self._config.calibration_sec)
        if len(calibration) == 0:
            raise ValueError(
                "audio source returned no samples for calibration — the source is "
                "empty (e.g. a FileSource shorter than calibration_sec)"
            )
        floor = calibrate_floor(calibration)
        self._detector = SilenceDetector(floor, self._thresholds)

        while True:
            chunk = await asyncio.to_thread(self._source.read, self._config.window_sec)
            if len(chunk) == 0:
                # End of stream — only a finite source (FileSource past EOF)
                # can produce this; a live LineInSource read blocks until it
                # has samples and never returns empty. Verified live: without
                # this check, the loop spins forever computing rms_dbfs on
                # empty arrays (NaN, with a RuntimeWarning on every
                # iteration), pegging a CPU core and never registering
                # silence (NaN < threshold is always False), since the
                # SilenceDetector never sees a real STOPPED condition — this
                # is exactly what `--file dry.wav` (a finite ~90s recording)
                # would hit in Task 6's own manual verification step.
                self._session.on_stopped()
                self._on_change()
                return
            self._buffer.push(chunk)
            self._last_rms_dbfs = rms_dbfs(chunk)

            event = self._detector.process_window(self._last_rms_dbfs)
            if event == AudioEvent.TRACK_GAP:
                self._cadence.on_track_gap()
                self._session.on_track_gap()
                self._on_change()
            elif event == AudioEvent.STOPPED:
                self._session.on_stopped()
                self._consecutive_failures = 0
                self._on_change()

            now = self._now_fn()
            if self._cadence.should_call(now) and not self._detector.is_silent:
                self._cadence.mark_call_started(now)
                self._recognition_task = asyncio.ensure_future(self._recognize_and_update(now))

    async def _recognize_and_update(self, called_at: float) -> None:
        clip = self._buffer.read_last(self._config.recognition_window_sec)
        try:
            result = await recognize_with_cover_art(self._recognizer, clip, self._buffer.sample_rate)
        finally:
            self._cadence.mark_call_finished()

        if result is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._config.max_consecutive_failures:
                self._session.on_unidentified()
                self._on_change()
            return

        self._consecutive_failures = 0
        self._cadence.set_locked(True)
        self._last_recognition = {"title": result.title, "artist": result.artist}

        lyrics = None
        if result.duration is not None:
            lyrics = self._lyrics_service.get_lyrics(result.artist, result.title, result.album, result.duration)

        # anchor_wall marks when the recognized BUFFER STARTED, not when the
        # response arrived — spec §5's latency-subtraction requirement.
        anchor_wall = called_at - self._config.recognition_window_sec
        self._session.on_recognized(result, lyrics, wall_time=anchor_wall)
        self._on_change()
