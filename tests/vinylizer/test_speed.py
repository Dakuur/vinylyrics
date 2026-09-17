from dataclasses import dataclass

import numpy as np
import pytest

from vinylyrics.vinylizer.speed import (
    SpeedProfile,
    apply_speed_variation,
    random_speed_profile,
)


@dataclass(frozen=True)
class _FakeSpeedParams:
    constant_offset_pct: float = 0.8
    wow_freq_min_hz: float = 0.5
    wow_freq_max_hz: float = 2.0
    wow_depth_pct: float = 0.3
    flutter_freq_min_hz: float = 6.0
    flutter_freq_max_hz: float = 10.0
    flutter_depth_pct: float = 0.05


def test_random_speed_profile_stays_within_configured_bounds():
    rng = np.random.default_rng(123)
    params = _FakeSpeedParams()
    for _ in range(200):
        profile = random_speed_profile(rng, params)
        assert 1.0 - 0.008 <= profile.offset <= 1.0 + 0.008
        assert 0.5 <= profile.wow_freq_hz <= 2.0
        assert profile.wow_depth == pytest.approx(0.003)
        assert 6.0 <= profile.flutter_freq_hz <= 10.0
        assert profile.flutter_depth == pytest.approx(0.0005)


def test_random_speed_profile_is_reproducible_with_same_seed():
    params = _FakeSpeedParams()
    profile_a = random_speed_profile(np.random.default_rng(42), params)
    profile_b = random_speed_profile(np.random.default_rng(42), params)
    assert profile_a == profile_b


def _flat_profile(offset: float = 1.0) -> SpeedProfile:
    return SpeedProfile(
        offset=offset,
        wow_freq_hz=1.0,
        wow_depth=0.0,
        wow_phase=0.0,
        flutter_freq_hz=8.0,
        flutter_depth=0.0,
        flutter_phase=0.0,
    )


def test_apply_speed_variation_scales_duration_with_constant_speed():
    sr = 1000
    n = sr * 10
    audio = np.sin(2 * np.pi * 50 * np.arange(n) / sr).astype(np.float32)

    faster = apply_speed_variation(audio, sr, sr, _flat_profile(1.1))
    slower = apply_speed_variation(audio, sr, sr, _flat_profile(0.95))

    assert faster.shape[0] == pytest.approx(n / 1.1, abs=2)
    assert slower.shape[0] == pytest.approx(n / 0.95, abs=2)


def test_apply_speed_variation_shifts_pitch_not_just_duration():
    sr = 44100
    n = sr * 2
    f0 = 440.0
    audio = np.sin(2 * np.pi * f0 * np.arange(n) / sr).astype(np.float32)

    out = apply_speed_variation(audio, sr, sr, _flat_profile(1.05))

    fft = np.fft.rfft(out * np.hanning(len(out)))
    freqs = np.fft.rfftfreq(len(out), 1 / sr)
    peak_freq = freqs[np.argmax(np.abs(fft))]
    assert peak_freq == pytest.approx(f0 * 1.05, abs=1.0)


def test_apply_speed_variation_handles_sample_rate_change_alone():
    source_sr = 48000
    output_sr = 44100
    n_source = source_sr * 3
    rng = np.random.default_rng(0)
    audio = rng.standard_normal(n_source).astype(np.float32)

    out = apply_speed_variation(audio, source_sr, output_sr, _flat_profile(1.0))

    expected_len = int(n_source * output_sr / source_sr)
    assert out.shape[0] == pytest.approx(expected_len, abs=2)


def test_apply_speed_variation_output_is_float32():
    sr = 8000
    audio = np.zeros(sr, dtype=np.float32)
    out = apply_speed_variation(audio, sr, sr, _flat_profile(1.0))
    assert out.dtype == np.float32
