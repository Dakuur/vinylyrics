from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vinylyrics.audio.buffer import CircularAudioBuffer
from vinylyrics.audio.source import FileSource
from vinylyrics.audio.vad import AudioEvent, SilenceDetector, SilenceThresholds, calibrate_floor, compute_rms_windows


def _build_synthetic_signal(sr: int, rng: np.random.Generator) -> np.ndarray:
    def noise(seconds: float, level: float = 0.01) -> np.ndarray:
        return (rng.standard_normal(int(seconds * sr)) * level).astype(np.float32)

    def tone(seconds: float, freq: float = 440.0, level: float = 0.3) -> np.ndarray:
        t = np.arange(int(seconds * sr)) / sr
        return (level * np.sin(2 * np.pi * freq * t)).astype(np.float32)

    return np.concatenate([
        noise(3.0),   # lead-in / calibration
        tone(5.0),    # track 1
        noise(2.0),   # gap between tracks
        tone(5.0),    # track 2
        noise(12.0),  # needle lifted
    ])


def test_source_buffer_vad_pipeline_detects_gap_and_stopped(tmp_path: Path):
    sr = 16000
    rng = np.random.default_rng(42)
    signal = _build_synthetic_signal(sr, rng)
    path = tmp_path / "synthetic.wav"
    sf.write(path, signal, sr)

    source = FileSource(path, sample_rate=sr, realtime=False)
    buffer = CircularAudioBuffer(sample_rate=sr, max_seconds=20.0)

    calibration_chunk = source.read(2.0)
    buffer.push(calibration_chunk)
    floor = calibrate_floor(calibration_chunk)

    detector = SilenceDetector(floor_dbfs=floor, thresholds=SilenceThresholds())

    events = []
    elapsed = 2.0  # already consumed 2s for calibration
    chunk_seconds = 0.5
    while True:
        chunk = source.read(chunk_seconds)
        if len(chunk) == 0:
            break
        buffer.push(chunk)
        windows = compute_rms_windows(chunk, sr, window_sec=0.1)
        for w in windows:
            event = detector.process_window(w)
            elapsed += 0.1
            if event is not None:
                events.append((elapsed, event))

    gap_events = [t for t, e in events if e == AudioEvent.TRACK_GAP]
    stopped_events = [t for t, e in events if e == AudioEvent.STOPPED]

    assert len(gap_events) >= 1
    # the gap is between track1 (ends ~8s in) and track2 (starts ~10s in)
    assert any(8.0 <= t <= 11.0 for t in gap_events)

    assert len(stopped_events) >= 1
    # STOPPED should fire ~10s into the final 12s silence, which starts at ~15s
    assert any(t >= 24.0 for t in stopped_events)
