# vinylyrics/vinylizer/noise.py
from __future__ import annotations

import numpy as np
from pedalboard import HighpassFilter, LowpassFilter, Pedalboard


def rms_dbfs(signal: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(signal.astype(np.float64) ** 2)))
    if rms <= 0:
        return float("-inf")
    return 20 * np.log10(rms)


def to_dbfs(signal: np.ndarray, target_dbfs: float) -> np.ndarray:
    current = rms_dbfs(signal)
    if current == float("-inf"):
        return signal.astype(np.float32)
    gain = 10 ** ((target_dbfs - current) / 20)
    return (signal * gain).astype(np.float32)


def pink_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n_samples)
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples)
    if len(freqs) > 1:
        freqs[0] = freqs[1]
    else:
        freqs[0] = 1.0
    fft = fft / np.sqrt(freqs)
    pink = np.fft.irfft(fft, n=n_samples)
    peak = np.max(np.abs(pink))
    if peak > 0:
        pink = pink / peak
    return pink.astype(np.float32)


def poisson_click_times(
    duration_sec: float,
    density_per_sec: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if density_per_sec <= 0:
        return np.array([])
    times = []
    t = 0.0
    while True:
        t += rng.exponential(1.0 / density_per_sec)
        if t >= duration_sec:
            break
        times.append(t)
    return np.array(times)


def render_clicks(
    n_samples: int,
    sr: int,
    density_per_sec: float,
    rng: np.random.Generator,
    click_duration_ms: float = 3.0,
    amplitude: float = 0.6,
) -> np.ndarray:
    buf = np.zeros(n_samples, dtype=np.float32)
    click_len = max(1, int(sr * click_duration_ms / 1000))
    envelope = np.exp(-np.linspace(0, 8, click_len)).astype(np.float32)
    duration_sec = n_samples / sr

    for t in poisson_click_times(duration_sec, density_per_sec, rng):
        start = int(t * sr)
        end = min(start + click_len, n_samples)
        seg_len = end - start
        if seg_len <= 0:
            continue
        noise = rng.standard_normal(seg_len).astype(np.float32)
        peak = np.max(np.abs(noise))
        if peak > 0:
            noise = noise / peak  # bound each burst to peak 1.0 before scaling
        buf[start:end] += noise * envelope[:seg_len] * amplitude * rng.uniform(0.5, 1.0)

    board = Pedalboard([HighpassFilter(cutoff_frequency_hz=1000.0)])
    return board(buf, sr)


def rumble_noise(
    n_samples: int,
    sr: int,
    rng: np.random.Generator,
    cutoff_hz: float,
    target_dbfs: float,
) -> np.ndarray:
    white = rng.standard_normal(n_samples).astype(np.float32)
    board = Pedalboard([LowpassFilter(cutoff_frequency_hz=cutoff_hz)])
    filtered = board(white, sr)
    return to_dbfs(filtered, target_dbfs)


def build_noise_layer(
    n_samples: int,
    sr: int,
    noise_params,
    rng: np.random.Generator,
) -> np.ndarray:
    layer = to_dbfs(pink_noise(n_samples, rng), noise_params.surface_dbfs)
    layer = layer + render_clicks(
        n_samples,
        sr,
        noise_params.click_density_per_sec,
        rng,
        click_duration_ms=noise_params.click_duration_ms,
        amplitude=noise_params.click_amplitude,
    )
    if noise_params.rumble_enabled:
        layer = layer + rumble_noise(
            n_samples, sr, rng, noise_params.rumble_cutoff_hz, noise_params.rumble_dbfs
        )
    return layer.astype(np.float32)
