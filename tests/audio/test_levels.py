import numpy as np
import pytest

from vinylyrics.audio.levels import rms_dbfs, to_dbfs


def test_rms_dbfs_of_full_scale_sine_is_close_to_minus_3db():
    sr = 44100
    t = np.arange(sr) / sr
    sine = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    # RMS of a full-amplitude sine is amplitude/sqrt(2) -> ~-3.01 dBFS
    assert rms_dbfs(sine) == pytest.approx(-3.01, abs=0.05)


def test_rms_dbfs_of_silence_is_negative_infinity():
    silence = np.zeros(1000, dtype=np.float32)
    assert rms_dbfs(silence) == float("-inf")


def test_to_dbfs_hits_target_level():
    rng = np.random.default_rng(1)
    signal = rng.standard_normal(44100).astype(np.float32)
    scaled = to_dbfs(signal, -20.0)
    assert rms_dbfs(scaled) == pytest.approx(-20.0, abs=0.05)


def test_to_dbfs_leaves_silence_untouched():
    silence = np.zeros(1000, dtype=np.float32)
    result = to_dbfs(silence, -20.0)
    assert np.all(result == 0.0)
    assert result.dtype == np.float32
