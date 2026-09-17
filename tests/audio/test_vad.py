import numpy as np
import pytest

from vinylyrics.audio.levels import rms_dbfs
from vinylyrics.audio.vad import (
    AudioEvent,
    SilenceDetector,
    SilenceThresholds,
    calibrate_floor,
    compute_rms_windows,
)


def test_compute_rms_windows_matches_manual_calculation():
    sr = 16000
    window_sec = 0.1
    audio = np.concatenate([
        np.full(int(sr * window_sec), 0.5, dtype=np.float32),
        np.zeros(int(sr * window_sec), dtype=np.float32),
    ])
    windows = compute_rms_windows(audio, sr, window_sec=window_sec)
    assert windows.shape[0] == 2
    assert windows[0] == pytest.approx(rms_dbfs(np.full(int(sr * window_sec), 0.5, dtype=np.float32)))
    assert windows[1] == -np.inf or windows[1] < -100


def test_calibrate_floor_returns_rms_dbfs_of_calibration_segment():
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(16000).astype(np.float32) * 0.01
    floor = calibrate_floor(noise)
    assert floor == pytest.approx(rms_dbfs(noise))


def _feed(detector: SilenceDetector, dbfs_sequence: list[float]) -> list["AudioEvent | None"]:
    return [detector.process_window(v) for v in dbfs_sequence]


def test_silence_detector_no_event_when_always_loud():
    thresholds = SilenceThresholds(window_sec=0.1)
    detector = SilenceDetector(floor_dbfs=-60.0, thresholds=thresholds)
    events = _feed(detector, [-20.0] * 50)
    assert all(e is None for e in events)


def test_silence_detector_emits_track_gap_for_short_silence():
    thresholds = SilenceThresholds(
        enter_offset_db=6.0, exit_offset_db=10.0,
        gap_min_sec=1.0, gap_max_sec=3.0, stopped_sec=10.0, window_sec=0.1,
    )
    floor = -60.0
    detector = SilenceDetector(floor_dbfs=floor, thresholds=thresholds)

    loud = floor + 20.0
    silent = floor - 5.0

    events = []
    events += _feed(detector, [loud] * 5)          # 0.5s of sound
    events += _feed(detector, [silent] * 15)        # 1.5s of silence -> should be a gap
    events += _feed(detector, [loud] * 5)           # sound resumes -> TRACK_GAP fires here

    fired = [e for e in events if e is not None]
    assert fired == [AudioEvent.TRACK_GAP]


def test_silence_detector_emits_stopped_for_long_silence():
    thresholds = SilenceThresholds(window_sec=0.1, stopped_sec=10.0)
    floor = -60.0
    detector = SilenceDetector(floor_dbfs=floor, thresholds=thresholds)

    loud = floor + 20.0
    silent = floor - 5.0

    events = _feed(detector, [loud] * 5)
    events += _feed(detector, [silent] * 105)  # 10.5s of silence -> STOPPED fires once

    fired = [e for e in events if e is not None]
    assert fired == [AudioEvent.STOPPED]


def test_silence_detector_does_not_flap_within_hysteresis_deadzone():
    thresholds = SilenceThresholds(enter_offset_db=6.0, exit_offset_db=10.0, window_sec=0.1)
    floor = -60.0
    detector = SilenceDetector(floor_dbfs=floor, thresholds=thresholds)

    loud = floor + 20.0
    detector.process_window(loud)

    deadzone_level = floor + 8.0  # between enter (+6) and exit (+10) thresholds
    events = _feed(detector, [deadzone_level] * 50)

    assert all(e is None for e in events)
    assert detector.is_silent is False


def test_silence_detector_medium_silence_produces_no_gap_event():
    thresholds = SilenceThresholds(gap_min_sec=1.0, gap_max_sec=3.0, stopped_sec=10.0, window_sec=0.1)
    floor = -60.0
    detector = SilenceDetector(floor_dbfs=floor, thresholds=thresholds)
    loud = floor + 20.0
    silent = floor - 5.0

    events = _feed(detector, [loud] * 5)
    events += _feed(detector, [silent] * 50)  # 5s of silence: not a gap (too long), not stopped (too short)
    events += _feed(detector, [loud] * 5)

    fired = [e for e in events if e is not None]
    assert fired == []
