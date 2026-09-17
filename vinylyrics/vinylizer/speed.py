from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpeedProfile:
    offset: float
    wow_freq_hz: float
    wow_depth: float
    wow_phase: float
    flutter_freq_hz: float
    flutter_depth: float
    flutter_phase: float


def random_speed_profile(rng: np.random.Generator, params) -> SpeedProfile:
    offset = 1.0 + rng.uniform(-params.constant_offset_pct, params.constant_offset_pct) / 100.0
    return SpeedProfile(
        offset=offset,
        wow_freq_hz=rng.uniform(params.wow_freq_min_hz, params.wow_freq_max_hz),
        wow_depth=params.wow_depth_pct / 100.0,
        wow_phase=rng.uniform(0.0, 2 * np.pi),
        flutter_freq_hz=rng.uniform(params.flutter_freq_min_hz, params.flutter_freq_max_hz),
        flutter_depth=params.flutter_depth_pct / 100.0,
        flutter_phase=rng.uniform(0.0, 2 * np.pi),
    )


def apply_speed_variation(
    audio: np.ndarray,
    source_sr: int,
    output_sr: int,
    profile: SpeedProfile,
) -> np.ndarray:
    n_source = len(audio)
    source_duration = n_source / source_sr

    # Generous upper bound on output length, then truncate once the
    # cumulative source-time index reaches the end of the source audio.
    est_output_samples = int(source_duration / profile.offset * output_sr * 1.05) + 10
    t_out = np.arange(est_output_samples) / output_sr

    speed = profile.offset * (
        1.0
        + profile.wow_depth * np.sin(2 * np.pi * profile.wow_freq_hz * t_out + profile.wow_phase)
        + profile.flutter_depth * np.sin(2 * np.pi * profile.flutter_freq_hz * t_out + profile.flutter_phase)
    )

    dt_out = 1.0 / output_sr
    source_time = np.cumsum(speed) * dt_out
    valid_len = int(np.searchsorted(source_time, source_duration, side="right"))
    source_time = source_time[:valid_len]

    source_indices = source_time * source_sr
    output = np.interp(source_indices, np.arange(n_source), audio)
    return output.astype(np.float32)
