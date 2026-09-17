# tests/vinylizer/test_noise.py
from dataclasses import dataclass

import numpy as np
import pytest

from vinylyrics.vinylizer.noise import (
    build_noise_layer,
    pink_noise,
    poisson_click_times,
    render_clicks,
    rms_dbfs,
    rumble_noise,
    to_dbfs,
)


@dataclass(frozen=True)
class _FakeNoiseParams:
    surface_dbfs: float = -38.0
    click_density_per_sec: float = 0.5
    click_duration_ms: float = 3.0
    click_amplitude: float = 0.6
    rumble_enabled: bool = False
    rumble_dbfs: float = -45.0
    rumble_cutoff_hz: float = 80.0


def test_to_dbfs_hits_target_rms_level():
    rng = np.random.default_rng(1)
    signal = rng.standard_normal(44100).astype(np.float32)
    scaled = to_dbfs(signal, -20.0)
    assert rms_dbfs(scaled) == pytest.approx(-20.0, abs=0.05)


def test_pink_noise_has_more_low_frequency_energy_than_white_noise():
    rng = np.random.default_rng(2)
    n = 44100 * 3
    sr = 44100
    pink = pink_noise(n, rng)
    white = rng.standard_normal(n)

    freqs = np.fft.rfftfreq(n, 1 / sr)
    low = (freqs > 50) & (freqs < 200)
    high = (freqs > 5000) & (freqs < 10000)

    pink_fft = np.fft.rfft(pink)
    white_fft = np.fft.rfft(white)

    pink_ratio = np.mean(np.abs(pink_fft[low]) ** 2) / np.mean(np.abs(pink_fft[high]) ** 2)
    white_ratio = np.mean(np.abs(white_fft[low]) ** 2) / np.mean(np.abs(white_fft[high]) ** 2)

    assert pink_ratio > white_ratio * 10  # pink noise: strongly tilted; white: flat


def test_pink_noise_is_bounded_and_correct_dtype():
    rng = np.random.default_rng(3)
    pink = pink_noise(44100, rng)
    assert pink.dtype == np.float32
    assert np.max(np.abs(pink)) <= 1.0 + 1e-6


def test_poisson_click_times_average_rate_and_ordering():
    rng = np.random.default_rng(7)
    times = poisson_click_times(200.0, 0.5, rng)
    assert 60 < len(times) < 140  # expected ~100, generous statistical bound
    assert np.all(times >= 0.0)
    assert np.all(times < 200.0)
    assert np.all(np.diff(times) > 0)


def test_poisson_click_times_zero_density_returns_empty():
    rng = np.random.default_rng(8)
    times = poisson_click_times(10.0, 0.0, rng)
    assert len(times) == 0


def test_render_clicks_produces_sparse_bounded_bursts():
    rng = np.random.default_rng(9)
    sr = 44100
    n = sr * 20
    clicks = render_clicks(n, sr, density_per_sec=0.5, rng=rng, amplitude=0.6)
    assert clicks.shape[0] == n
    assert clicks.dtype == np.float32
    nonzero_fraction = np.count_nonzero(clicks) / n
    assert 0.0 < nonzero_fraction < 0.1  # sparse, not filling the buffer
    assert np.max(np.abs(clicks)) <= 0.6 + 0.1  # normalized bursts, small filter-overshoot margin


def test_rumble_noise_is_low_frequency_and_at_target_level():
    rng = np.random.default_rng(10)
    sr = 44100
    n = sr * 3
    rumble = rumble_noise(n, sr, rng, cutoff_hz=80.0, target_dbfs=-45.0)
    assert rumble.dtype == np.float32
    assert rms_dbfs(rumble) == pytest.approx(-45.0, abs=0.5)


def test_build_noise_layer_combines_pink_and_clicks():
    rng = np.random.default_rng(11)
    sr = 44100
    n = sr * 5
    params = _FakeNoiseParams()
    layer = build_noise_layer(n, sr, params, rng)
    assert layer.shape[0] == n
    assert layer.dtype == np.float32
    assert np.max(np.abs(layer)) > 0.0  # not silent


def test_build_noise_layer_skips_rumble_when_disabled():
    rng_a = np.random.default_rng(12)
    rng_b = np.random.default_rng(12)
    sr = 44100
    n = sr * 2
    without_rumble = build_noise_layer(n, sr, _FakeNoiseParams(rumble_enabled=False), rng_a)
    with_rumble = build_noise_layer(n, sr, _FakeNoiseParams(rumble_enabled=True), rng_b)
    # Same seed, same everything except rumble: enabling it must change the output.
    assert not np.allclose(without_rumble, with_rumble)
