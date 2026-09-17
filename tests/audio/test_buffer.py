import numpy as np
import pytest

from vinylyrics.audio.buffer import CircularAudioBuffer


def test_buffer_starts_empty():
    buf = CircularAudioBuffer(sample_rate=16000, max_seconds=20.0)
    assert buf.duration_available == 0.0
    assert buf.read_last(5.0).shape[0] == 0


def test_buffer_accumulates_pushed_samples():
    buf = CircularAudioBuffer(sample_rate=16000, max_seconds=20.0)
    buf.push(np.ones(16000, dtype=np.float32))
    assert buf.duration_available == pytest.approx(1.0)
    buf.push(np.ones(16000, dtype=np.float32) * 2)
    assert buf.duration_available == pytest.approx(2.0)


def test_buffer_caps_at_max_seconds():
    buf = CircularAudioBuffer(sample_rate=16000, max_seconds=2.0)
    for i in range(5):
        buf.push(np.full(16000, float(i), dtype=np.float32))
    assert buf.duration_available == pytest.approx(2.0)
    tail = buf.read_last(2.0)
    assert tail[0] == pytest.approx(3.0)
    assert tail[-1] == pytest.approx(4.0)


def test_buffer_read_last_returns_most_recent_samples():
    buf = CircularAudioBuffer(sample_rate=16000, max_seconds=20.0)
    buf.push(np.full(16000, 1.0, dtype=np.float32))
    buf.push(np.full(16000, 2.0, dtype=np.float32))
    buf.push(np.full(16000, 3.0, dtype=np.float32))

    last_one_sec = buf.read_last(1.0)
    assert np.all(last_one_sec == 3.0)

    last_two_sec = buf.read_last(2.0)
    assert np.all(last_two_sec[:16000] == 2.0)
    assert np.all(last_two_sec[16000:] == 3.0)


def test_buffer_read_last_longer_than_available_returns_what_exists():
    buf = CircularAudioBuffer(sample_rate=16000, max_seconds=20.0)
    buf.push(np.full(8000, 1.0, dtype=np.float32))
    result = buf.read_last(5.0)
    assert result.shape[0] == 8000


def test_buffer_push_ignores_empty_arrays():
    buf = CircularAudioBuffer(sample_rate=16000, max_seconds=20.0)
    buf.push(np.zeros(0, dtype=np.float32))
    assert buf.duration_available == 0.0
