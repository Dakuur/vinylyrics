import sys
import time
import types
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import soundfile as sf

from vinylyrics.audio.source import FileSource, LineInSource, list_devices


def _make_wav(tmp_path: Path, seconds: float = 3.0, sr: int = 44100, freq: float = 440.0) -> Path:
    t = np.arange(int(sr * seconds)) / sr
    audio = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    path = tmp_path / "test.wav"
    sf.write(path, audio, sr)
    return path


def test_file_source_resamples_to_target_rate(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=2.0, sr=44100)
    source = FileSource(path, sample_rate=16000)
    assert source.sample_rate == 16000

    chunk = source.read(1.0)
    assert chunk.dtype == np.float32
    assert chunk.shape[0] == pytest.approx(16000, abs=2)


def test_file_source_preserves_frequency_after_resampling(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=2.0, sr=44100, freq=440.0)
    source = FileSource(path, sample_rate=16000)
    chunk = source.read(2.0)

    fft = np.fft.rfft(chunk * np.hanning(len(chunk)))
    freqs = np.fft.rfftfreq(len(chunk), 1 / 16000)
    peak = freqs[np.argmax(np.abs(fft))]
    assert peak == pytest.approx(440.0, abs=2.0)


def test_file_source_advances_cursor_across_reads(tmp_path: Path):
    rng = np.random.default_rng(0)
    sr = 16000
    audio = rng.standard_normal(sr * 3).astype(np.float32) * 0.1
    path = tmp_path / "noise.wav"
    sf.write(path, audio, sr)
    source = FileSource(path, sample_rate=16000, realtime=False)

    first = source.read(1.0)
    second = source.read(1.0)
    assert first.shape[0] == pytest.approx(16000, abs=2)
    assert second.shape[0] == pytest.approx(16000, abs=2)
    assert not np.array_equal(first, second)


def test_file_source_returns_short_chunk_at_end_of_file(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=1.5, sr=16000)
    source = FileSource(path, sample_rate=16000)

    source.read(1.0)
    remainder = source.read(1.0)
    assert 0 < remainder.shape[0] < 16000

    empty = source.read(1.0)
    assert empty.shape[0] == 0


def test_file_source_non_realtime_does_not_sleep(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=5.0, sr=16000)
    source = FileSource(path, sample_rate=16000, realtime=False)

    start = time.monotonic()
    source.read(2.0)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


def test_file_source_realtime_respects_wall_clock(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=5.0, sr=16000)
    source = FileSource(path, sample_rate=16000, realtime=True)

    start = time.monotonic()
    source.read(0.3)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.28


def test_file_source_read_returns_a_copy_not_a_view(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=2.0, sr=16000)
    source = FileSource(path, sample_rate=16000)
    chunk = source.read(1.0)
    chunk[:] = 99.0
    # a second read from the same region (rewind not supported, so just check
    # internal audio wasn't mutated by re-reading is not directly testable via
    # public API; instead assert the returned array's flags show it owns its data)
    assert chunk.base is None or chunk.flags["OWNDATA"]


def test_file_source_realtime_does_not_oversleep_past_end_of_file(tmp_path: Path):
    path = _make_wav(tmp_path, seconds=0.5, sr=16000)
    source = FileSource(path, sample_rate=16000, realtime=True)

    source.read(0.5)  # consume everything
    start = time.monotonic()
    empty = source.read(2.0)  # nothing left; must not sleep ~2s
    elapsed = time.monotonic() - start

    assert empty.shape[0] == 0
    assert elapsed < 0.5


def test_line_in_source_does_not_touch_hardware_at_construction():
    fake_sd = types.ModuleType("sounddevice")
    fake_sd.InputStream = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        source = LineInSource(device=3, sample_rate=16000)
        assert source.sample_rate == 16000
        fake_sd.InputStream.assert_not_called()


def test_line_in_source_opens_stream_lazily_on_first_read():
    fake_sd = types.ModuleType("sounddevice")
    fake_stream = mock.MagicMock()
    fake_stream.read.return_value = (np.zeros((1600, 1), dtype=np.float32), False)
    fake_sd.InputStream = mock.MagicMock(return_value=fake_stream)

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        source = LineInSource(device=3, sample_rate=16000)
        fake_sd.InputStream.assert_not_called()

        chunk = source.read(0.1)

        fake_sd.InputStream.assert_called_once_with(device=3, channels=1, samplerate=16000, dtype="float32")
        fake_stream.start.assert_called_once()
        assert chunk.shape[0] == 1600
        assert chunk.dtype == np.float32


def test_line_in_source_reuses_stream_across_reads():
    fake_sd = types.ModuleType("sounddevice")
    fake_stream = mock.MagicMock()
    fake_stream.read.return_value = (np.zeros((1600, 1), dtype=np.float32), False)
    fake_sd.InputStream = mock.MagicMock(return_value=fake_stream)

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        source = LineInSource(device=None, sample_rate=16000)
        source.read(0.1)
        source.read(0.1)
        fake_sd.InputStream.assert_called_once()


def test_line_in_source_close_stops_and_closes_stream():
    fake_sd = types.ModuleType("sounddevice")
    fake_stream = mock.MagicMock()
    fake_stream.read.return_value = (np.zeros((1600, 1), dtype=np.float32), False)
    fake_sd.InputStream = mock.MagicMock(return_value=fake_stream)

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        source = LineInSource(device=None, sample_rate=16000)
        source.read(0.1)
        source.close()

        fake_stream.stop.assert_called_once()
        fake_stream.close.assert_called_once()


def test_line_in_source_works_as_context_manager():
    fake_sd = types.ModuleType("sounddevice")
    fake_stream = mock.MagicMock()
    fake_stream.read.return_value = (np.zeros((1600, 1), dtype=np.float32), False)
    fake_sd.InputStream = mock.MagicMock(return_value=fake_stream)

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        with LineInSource(device=None, sample_rate=16000) as source:
            source.read(0.1)
        fake_stream.stop.assert_called_once()
        fake_stream.close.assert_called_once()


def test_line_in_source_counts_overflows():
    fake_sd = types.ModuleType("sounddevice")
    fake_stream = mock.MagicMock()
    fake_stream.read.side_effect = [
        (np.zeros((1600, 1), dtype=np.float32), False),
        (np.zeros((1600, 1), dtype=np.float32), True),
        (np.zeros((1600, 1), dtype=np.float32), True),
    ]
    fake_sd.InputStream = mock.MagicMock(return_value=fake_stream)

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        source = LineInSource(device=None, sample_rate=16000)
        assert source.overflow_count == 0
        source.read(0.1)
        assert source.overflow_count == 0
        source.read(0.1)
        assert source.overflow_count == 1
        source.read(0.1)
        assert source.overflow_count == 2


def test_list_devices_uses_sounddevice_query():
    fake_sd = types.ModuleType("sounddevice")
    fake_sd.query_devices = mock.MagicMock(return_value=[{"name": "fake mic"}])

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        devices = list_devices()

    assert devices == [{"name": "fake mic"}]
