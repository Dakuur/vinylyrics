# vinylyrics Phase 2 Implementation Plan — Vinylizer `build`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `vinylizer build` subcommand: it takes a folder of mp3s and
produces a WAV that simulates a vinyl side (speed drift, wow/flutter, surface
noise, clicks, a gentle high-frequency shelf) plus a `.truth.json` recording
exactly what was done, so later phases can be evaluated against ground truth
instead of guesses.

**Architecture:** Per selected track: load audio (`soundfile`, works
directly on the mp3s — confirmed, no ffmpeg/pydub decode step needed),
downmix to mono, resample it through a per-track `SpeedProfile` (constant
offset + wow LFO + flutter LFO, summed, applied as one variable-rate
resample via linear interpolation over an accumulated source-time index —
this is what changes pitch and duration together, exactly like a real
platter, and is NOT a pitch-preserving time-stretch). Build a continuous
noise layer (pink noise + Poisson-scheduled clicks + optional rumble) that
spans the *entire* side (lead-in, every gap, every track, lead-out) since
that's how a physical record's surface noise actually behaves — it doesn't
turn off between tracks. Overlay the resampled tracks into that layer at
the correct offsets, run the whole mix through one gentle high-shelf filter
(`pedalboard.HighShelfFilter`, modeling the whole playback chain's rolloff),
and write the WAV plus a `.truth.json` with per-track order/offsets/speed.

**Tech Stack:** `numpy` (speed-profile math, noise synthesis), `soundfile`
(mp3 read confirmed working directly, WAV write), `pedalboard` (`HighShelfFilter`,
`HighpassFilter`, `LowpassFilter` — GPLv3, already the project's license per
Phase 1's decision), stdlib `tomllib` (TOML params, read-only, no new
dependency needed for that).

**Spec:** [docs/SPEC.md](../../SPEC.md) §1 "Vinylizer" → "Subcomando build",
and the "Decisiones tomadas" section (GPLv3 via pedalboard). Also read
[docs/superpowers/plans/2026-09-17-vinylyrics.md](2026-09-17-vinylyrics.md)
(Phase 1's plan) for the `TrackMeta`/`scan_library` interface this phase
builds on — Phase 1 is merged to `main`, its code exists as-is.

## Global Constraints

(Phase 1's constraints all still apply — Python 3.11+/uv, GPLv3, no invented
metadata, `.env`/lyrics/media gitignored, offline pytest by default, reuse
recorded in `docs/REUSE.md` as introduced. This phase adds:)

- **No pitch-preserving time-stretch, ever.** Speed changes MUST come from
  the resampling approach in Task 1 (interpolating over an accumulated
  source-time index). This is explicit in the spec: a real turntable
  changes pitch and duration together.
- **Surface noise (pink noise, clicks, optional rumble) spans the whole
  side continuously** — lead-in, gaps, and under the music, not just
  between tracks. Gaps between tracks are "2.0 s de silencio con ruido de
  superficie", never digital silence.
- **dBFS convention:** every "target dBFS" value in this plan (surface
  noise -38 dBFS, rumble -45 dBFS) means **RMS dBFS** — `20*log10(rms)`
  relative to full scale (peak amplitude 1.0) — not peak dBFS. This is
  defined once in Task 2's `rms_dbfs`/`to_dbfs` and reused everywhere a
  level needs setting.
- **Reproducibility:** every source of randomness (track selection, per-track
  speed profile, noise/click generation) draws from ONE `numpy.random.Generator`
  seeded from the CLI's `--seed`, consumed in a fixed, deterministic order,
  so the same seed always produces byte-identical output.
- **New dependencies this phase introduces — record each in `docs/REUSE.md`
  when its task adds it to `pyproject.toml`:** `numpy` (BSD-3-Clause),
  `pedalboard` (GPLv3 — already the project's license, see Phase 1's
  rationale), `soundfile` (BSD-3-Clause, confirmed during this plan's
  research to read mp3 directly via bundled libsndfile 1.2.2 — no ffmpeg
  decode step needed for `vinylizer build`, even though ffmpeg is still a
  system dependency for other things).
- Every numeric algorithm in this plan (variable-rate resampling, pink
  noise, Poisson clicks, dBFS scaling) was hand-verified against real
  numpy/pedalboard/soundfile output during planning — see the "Verified
  during planning" note on each task. Implementers should still run the
  tests for real, not assume the numbers are right because they're written
  down.

---

## Roadmap Context

This is Phase 2 of the vinylyrics roadmap (Phase 1 — `inspect` — is merged).
Per the spec's "Orden de trabajo," after this phase David listens to the
generated WAV and validates it before Phase 3 (audio sources + silence
detector) begins. Phase 3 is not detailed here — it gets its own plan.

---

## Task 1: Speed profile + variable-rate resampling (`vinylizer/speed.py`)

**Files:**
- Modify: `pyproject.toml` (add `numpy>=1.26` to `dependencies`)
- Create: `vinylyrics/vinylizer/speed.py`
- Test: `tests/vinylizer/test_speed.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `@dataclasses.dataclass(frozen=True) class SpeedProfile`: fields
    `offset: float`, `wow_freq_hz: float`, `wow_depth: float`,
    `wow_phase: float`, `flutter_freq_hz: float`, `flutter_depth: float`,
    `flutter_phase: float`.
  - `def random_speed_profile(rng: np.random.Generator, params: "SpeedParams") -> SpeedProfile`
    — Task 3 defines `SpeedParams`; for THIS task, treat it as any object
    with float attributes `constant_offset_pct`, `wow_freq_min_hz`,
    `wow_freq_max_hz`, `wow_depth_pct`, `flutter_freq_min_hz`,
    `flutter_freq_max_hz`, `flutter_depth_pct` (a tiny local stand-in class
    in the test file is fine — Task 3 hasn't been built yet).
  - `def apply_speed_variation(audio: np.ndarray, source_sr: int, output_sr: int, profile: SpeedProfile) -> np.ndarray`
    — Task 4 (`build.py`) calls this directly with these exact names.

**Verified during planning:** this exact algorithm was run standalone and
checked: constant-speed duration scaling (1.1x → 1/1.1 length, 0.95x →
1/0.95 length), pitch shift via FFT peak (440 Hz × 1.05 → 462.0 Hz, exact),
sample-rate-only change (48000→44100 Hz, speed 1.0 → exact ratio), and wow
LFO bounds ([0.997, 1.003] for depth 0.003). All matched expectations
exactly. Transcribe the code below as given.

- [ ] **Step 1: Write the failing tests**

```python
# tests/vinylizer/test_speed.py
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/vinylizer/test_speed.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.vinylizer.speed'`

- [ ] **Step 3: Add the `numpy` dependency**

Edit `pyproject.toml`'s `dependencies` list (currently `["mutagen>=1.48", "python-dotenv>=1.0"]`) to add `"numpy>=1.26"`:

```toml
dependencies = [
    "mutagen>=1.48",
    "python-dotenv>=1.0",
    "numpy>=1.26",
]
```

Run: `uv sync` — confirm it installs numpy with no errors.

- [ ] **Step 4: Implement `speed.py`**

```python
# vinylyrics/vinylizer/speed.py
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
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/vinylizer/test_speed.py -v`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/vinylizer/speed.py tests/vinylizer/test_speed.py
git commit -m "feat: add speed/wow/flutter variable-rate resampling"
```

---

## Task 2: Noise layer (`vinylizer/noise.py`)

**Files:**
- Modify: `pyproject.toml` (add `pedalboard>=0.9` to `dependencies`)
- Create: `vinylyrics/vinylizer/noise.py`
- Test: `tests/vinylizer/test_noise.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pedalboard is an external library).
- Produces:
  - `def rms_dbfs(signal: np.ndarray) -> float`
  - `def to_dbfs(signal: np.ndarray, target_dbfs: float) -> np.ndarray`
  - `def pink_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray`
  - `def poisson_click_times(duration_sec: float, density_per_sec: float, rng: np.random.Generator) -> np.ndarray`
  - `def render_clicks(n_samples: int, sr: int, density_per_sec: float, rng: np.random.Generator, click_duration_ms: float = 3.0, amplitude: float = 0.6) -> np.ndarray`
  - `def rumble_noise(n_samples: int, sr: int, rng: np.random.Generator, cutoff_hz: float, target_dbfs: float) -> np.ndarray`
  - `def build_noise_layer(n_samples: int, sr: int, noise_params, rng: np.random.Generator) -> np.ndarray`
    — Task 3's `NoiseParams` provides `noise_params` at runtime; for this
    task's tests, a tiny local stand-in dataclass with the same field names
    is fine (see the test file below).
  - Task 4 (`build.py`) calls `build_noise_layer` directly with these names.

**Verified during planning:** `pink_noise` was checked to have ~65x more
energy in a 50-200 Hz band than a 5-10 kHz band on a 3-second sample
(white noise has ~1x — no spectral tilt), confirming it's actually pink,
not white. `to_dbfs(pink, -38.0)` measured back at exactly -38.0 dBFS RMS.
`poisson_click_times` over 100s at density 0.5/s produced 53 events
(expected ~50, monotonically increasing, all within `[0, duration)`).
An early version of `render_clicks` scaled each click's raw Gaussian burst
directly by `amplitude` with no per-click peak normalization — that let a
single unlucky Gaussian sample blow past `amplitude` (measured peak 1.155
for `amplitude=0.6` with seed 9, a real bug caught by actually running the
numbers, not just reading the code). The version below normalizes each
click's noise burst to peak 1.0 *before* applying the envelope and
amplitude scale, which bounds the pre-filter peak at `amplitude`. With
that fix, seed 9 over a 20s/0.5-per-sec window measured peak 0.395 and a
4.4% nonzero-sample fraction — both asserted with margin in the tests
below. Transcribe the code (with the normalization) as given.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/vinylizer/test_noise.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.vinylizer.noise'`

- [ ] **Step 3: Add the `pedalboard` dependency**

Edit `pyproject.toml`'s `dependencies` to add `"pedalboard>=0.9"`:

```toml
dependencies = [
    "mutagen>=1.48",
    "python-dotenv>=1.0",
    "numpy>=1.26",
    "pedalboard>=0.9",
]
```

Run: `uv sync` — confirm it installs pedalboard with no errors.

- [ ] **Step 4: Implement `noise.py`**

```python
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
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/vinylizer/test_noise.py -v`
Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/vinylizer/noise.py tests/vinylizer/test_noise.py
git commit -m "feat: add pink noise, Poisson clicks, and rumble generation"
```

---

## Task 3: Vinylizer parameters (`vinylizer/params.py` + default TOML)

**Files:**
- Create: `vinylyrics/vinylizer/default_params.toml`
- Create: `vinylyrics/vinylizer/params.py`
- Test: `tests/vinylizer/test_params.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (Task 4 and Task 5 both import these):
  - `@dataclass(frozen=True) class SpeedParams`: `constant_offset_pct: float`,
    `wow_freq_min_hz: float`, `wow_freq_max_hz: float`, `wow_depth_pct: float`,
    `flutter_freq_min_hz: float`, `flutter_freq_max_hz: float`,
    `flutter_depth_pct: float` — same field names Task 1's
    `random_speed_profile` reads.
  - `@dataclass(frozen=True) class NoiseParams`: `surface_dbfs: float`,
    `click_density_per_sec: float`, `click_duration_ms: float`,
    `click_amplitude: float`, `rumble_enabled: bool`, `rumble_dbfs: float`,
    `rumble_cutoff_hz: float` — same field names Task 2's `build_noise_layer` reads.
  - `@dataclass(frozen=True) class StructureParams`: `lead_in_sec: float`,
    `gap_sec: float`, `lead_out_sec: float`.
  - `@dataclass(frozen=True) class FilterParams`: `shelf_cutoff_hz: float`,
    `shelf_gain_db: float`.
  - `@dataclass(frozen=True) class OutputParams`: `sample_rate: int`.
  - `@dataclass(frozen=True) class VinylizerParams`: `speed: SpeedParams`,
    `noise: NoiseParams`, `structure: StructureParams`, `filter: FilterParams`,
    `output: OutputParams`.
  - `def load_params(path: "Path | None" = None) -> VinylizerParams` — `None`
    loads the bundled `default_params.toml` next to this module.

- [ ] **Step 1: Write `default_params.toml`**

```toml
# vinylyrics/vinylizer/default_params.toml
[speed]
constant_offset_pct = 0.8
wow_freq_min_hz = 0.5
wow_freq_max_hz = 2.0
wow_depth_pct = 0.3
flutter_freq_min_hz = 6.0
flutter_freq_max_hz = 10.0
flutter_depth_pct = 0.05

[noise]
surface_dbfs = -38.0
click_density_per_sec = 0.5
click_duration_ms = 3.0
click_amplitude = 0.6
rumble_enabled = false
rumble_dbfs = -45.0
rumble_cutoff_hz = 80.0

[structure]
lead_in_sec = 3.0
gap_sec = 2.0
lead_out_sec = 5.0

[filter]
shelf_cutoff_hz = 12000.0
shelf_gain_db = -6.0

[output]
sample_rate = 44100
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/vinylizer/test_params.py
from pathlib import Path

import pytest

from vinylyrics.vinylizer.params import VinylizerParams, load_params


def test_load_params_reads_the_bundled_default_file():
    params = load_params()
    assert isinstance(params, VinylizerParams)
    assert params.speed.constant_offset_pct == pytest.approx(0.8)
    assert params.speed.wow_freq_min_hz == pytest.approx(0.5)
    assert params.speed.wow_freq_max_hz == pytest.approx(2.0)
    assert params.noise.surface_dbfs == pytest.approx(-38.0)
    assert params.noise.rumble_enabled is False
    assert params.structure.lead_in_sec == pytest.approx(3.0)
    assert params.structure.gap_sec == pytest.approx(2.0)
    assert params.structure.lead_out_sec == pytest.approx(5.0)
    assert params.filter.shelf_cutoff_hz == pytest.approx(12000.0)
    assert params.filter.shelf_gain_db == pytest.approx(-6.0)
    assert params.output.sample_rate == 44100


def test_load_params_reads_a_custom_override_file(tmp_path: Path):
    custom = tmp_path / "custom.toml"
    custom.write_text(
        """
        [speed]
        constant_offset_pct = 1.5
        wow_freq_min_hz = 0.5
        wow_freq_max_hz = 2.0
        wow_depth_pct = 0.3
        flutter_freq_min_hz = 6.0
        flutter_freq_max_hz = 10.0
        flutter_depth_pct = 0.05

        [noise]
        surface_dbfs = -30.0
        click_density_per_sec = 1.0
        click_duration_ms = 3.0
        click_amplitude = 0.6
        rumble_enabled = true
        rumble_dbfs = -45.0
        rumble_cutoff_hz = 80.0

        [structure]
        lead_in_sec = 1.0
        gap_sec = 1.0
        lead_out_sec = 1.0

        [filter]
        shelf_cutoff_hz = 10000.0
        shelf_gain_db = -3.0

        [output]
        sample_rate = 48000
        """
    )
    params = load_params(custom)
    assert params.speed.constant_offset_pct == pytest.approx(1.5)
    assert params.noise.surface_dbfs == pytest.approx(-30.0)
    assert params.noise.rumble_enabled is True
    assert params.structure.lead_in_sec == pytest.approx(1.0)
    assert params.output.sample_rate == 48000
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/vinylizer/test_params.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.vinylizer.params'`

- [ ] **Step 4: Implement `params.py`**

```python
# vinylyrics/vinylizer/params.py
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpeedParams:
    constant_offset_pct: float
    wow_freq_min_hz: float
    wow_freq_max_hz: float
    wow_depth_pct: float
    flutter_freq_min_hz: float
    flutter_freq_max_hz: float
    flutter_depth_pct: float


@dataclass(frozen=True)
class NoiseParams:
    surface_dbfs: float
    click_density_per_sec: float
    click_duration_ms: float
    click_amplitude: float
    rumble_enabled: bool
    rumble_dbfs: float
    rumble_cutoff_hz: float


@dataclass(frozen=True)
class StructureParams:
    lead_in_sec: float
    gap_sec: float
    lead_out_sec: float


@dataclass(frozen=True)
class FilterParams:
    shelf_cutoff_hz: float
    shelf_gain_db: float


@dataclass(frozen=True)
class OutputParams:
    sample_rate: int


@dataclass(frozen=True)
class VinylizerParams:
    speed: SpeedParams
    noise: NoiseParams
    structure: StructureParams
    filter: FilterParams
    output: OutputParams


DEFAULT_PARAMS_PATH = Path(__file__).parent / "default_params.toml"


def load_params(path: "Path | None" = None) -> VinylizerParams:
    toml_path = path or DEFAULT_PARAMS_PATH
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return VinylizerParams(
        speed=SpeedParams(**data["speed"]),
        noise=NoiseParams(**data["noise"]),
        structure=StructureParams(**data["structure"]),
        filter=FilterParams(**data["filter"]),
        output=OutputParams(**data["output"]),
    )
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/vinylizer/test_params.py -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/vinylizer/default_params.toml vinylyrics/vinylizer/params.py tests/vinylizer/test_params.py
git commit -m "feat: load vinylizer DSP parameters from TOML"
```

---

## Task 4: Side builder (`vinylizer/build.py`)

**Files:**
- Modify: `pyproject.toml` (add `soundfile>=0.13` to `dependencies`)
- Create: `vinylyrics/vinylizer/build.py`
- Test: `tests/vinylizer/test_build.py`

**Interfaces:**
- Consumes:
  - `TrackMeta` (fields `path: Path`, `title`, `artist`, `album`,
    `duration_seconds`, `missing_fields`, property `usable`) and
    `scan_library` from `vinylyrics.vinylizer.library` (Phase 1 — already
    on `main`, do not modify).
  - `SpeedProfile`, `apply_speed_variation`, `random_speed_profile` from
    `vinylyrics.vinylizer.speed` (Task 1).
  - `build_noise_layer` from `vinylyrics.vinylizer.noise` (Task 2).
  - `VinylizerParams` (and its nested `SpeedParams`/`NoiseParams`/etc.)
    from `vinylyrics.vinylizer.params` (Task 3).
- Produces (Task 5's CLI imports these directly):
  - `def select_tracks(tracks: list[TrackMeta], n: int, rng: np.random.Generator) -> list[TrackMeta]`
  - `def partition_tracks(tracks: list[TrackMeta], n: int, rng: np.random.Generator) -> list[list[TrackMeta]]`
  - `def build_side(tracks: list[TrackMeta], params: VinylizerParams, rng: np.random.Generator, max_track_seconds: "float | None" = None) -> tuple[np.ndarray, dict]`
  - `def write_side(audio: np.ndarray, truth: dict, output_dir: Path, index: int) -> tuple[Path, Path]`

- [ ] **Step 1: Add the `soundfile` dependency**

Edit `pyproject.toml`'s `dependencies` to add `"soundfile>=0.13"`:

```toml
dependencies = [
    "mutagen>=1.48",
    "python-dotenv>=1.0",
    "numpy>=1.26",
    "pedalboard>=0.9",
    "soundfile>=0.13",
]
```

Run: `uv sync` — confirm it installs soundfile with no errors.

- [ ] **Step 2: Write the failing tests**

These use tiny synthetic tracks (generated on the fly with `soundfile`, not
the real mp3 library — keeps tests fast and hermetic) and a helper to build
a `VinylizerParams` with structure/speed values small enough to make exact
assertions.

```python
# tests/vinylizer/test_build.py
import json
from pathlib import Path

import numpy as np
import pytest

from vinylyrics.vinylizer.build import (
    build_side,
    partition_tracks,
    select_tracks,
    write_side,
)
from vinylyrics.vinylizer.library import TrackMeta
from vinylyrics.vinylizer.params import (
    FilterParams,
    NoiseParams,
    OutputParams,
    SpeedParams,
    StructureParams,
    VinylizerParams,
)


def _make_track(tmp_path: Path, name: str, seconds: float, sr: int = 44100, usable: bool = True) -> TrackMeta:
    import soundfile as sf

    path = tmp_path / name
    t = np.arange(int(sr * seconds))
    audio = (0.2 * np.sin(2 * np.pi * 220 * t / sr)).astype(np.float32)
    sf.write(path, audio, sr)
    missing = () if usable else ("title", "artist")
    return TrackMeta(
        path=path,
        title=None if not usable else f"Title {name}",
        artist=None if not usable else "Artist",
        album="Album",
        duration_seconds=seconds,
        missing_fields=missing,
    )


def _zero_speed_params(sample_rate: int = 44100, lead_in=0.1, gap=0.1, lead_out=0.1) -> VinylizerParams:
    return VinylizerParams(
        speed=SpeedParams(
            constant_offset_pct=0.0,
            wow_freq_min_hz=1.0,
            wow_freq_max_hz=1.0,
            wow_depth_pct=0.0,
            flutter_freq_min_hz=8.0,
            flutter_freq_max_hz=8.0,
            flutter_depth_pct=0.0,
        ),
        noise=NoiseParams(
            surface_dbfs=-38.0,
            click_density_per_sec=0.1,
            click_duration_ms=3.0,
            click_amplitude=0.3,
            rumble_enabled=False,
            rumble_dbfs=-45.0,
            rumble_cutoff_hz=80.0,
        ),
        structure=StructureParams(lead_in_sec=lead_in, gap_sec=gap, lead_out_sec=lead_out),
        filter=FilterParams(shelf_cutoff_hz=12000.0, shelf_gain_db=-6.0),
        output=OutputParams(sample_rate=sample_rate),
    )


def _default_speed_params(**kwargs) -> VinylizerParams:
    params = _zero_speed_params(**kwargs)
    return VinylizerParams(
        speed=SpeedParams(
            constant_offset_pct=0.8,
            wow_freq_min_hz=0.5,
            wow_freq_max_hz=2.0,
            wow_depth_pct=0.3,
            flutter_freq_min_hz=6.0,
            flutter_freq_max_hz=10.0,
            flutter_depth_pct=0.05,
        ),
        noise=params.noise,
        structure=params.structure,
        filter=params.filter,
        output=params.output,
    )


def test_select_tracks_picks_only_usable_and_is_seed_reproducible(tmp_path: Path):
    tracks = [
        _make_track(tmp_path, "a.wav", 1.0),
        _make_track(tmp_path, "b.wav", 1.0),
        _make_track(tmp_path, "c.wav", 1.0, usable=False),
        _make_track(tmp_path, "d.wav", 1.0),
    ]
    selected_a = select_tracks(tracks, 2, np.random.default_rng(5))
    selected_b = select_tracks(tracks, 2, np.random.default_rng(5))
    assert len(selected_a) == 2
    assert all(t.usable for t in selected_a)
    assert [t.path for t in selected_a] == [t.path for t in selected_b]


def test_select_tracks_caps_at_available_usable_count(tmp_path: Path):
    tracks = [_make_track(tmp_path, "a.wav", 1.0), _make_track(tmp_path, "b.wav", 1.0, usable=False)]
    selected = select_tracks(tracks, 5, np.random.default_rng(1))
    assert len(selected) == 1


def test_partition_tracks_covers_all_usable_tracks_exactly_once(tmp_path: Path):
    tracks = [_make_track(tmp_path, f"t{i}.wav", 1.0) for i in range(7)]
    groups = partition_tracks(tracks, 3, np.random.default_rng(2))
    assert [len(g) for g in groups] == [3, 3, 1]
    flattened = {t.path for g in groups for t in g}
    assert flattened == {t.path for t in tracks}


def test_build_side_structure_is_exact_with_zero_speed_variation(tmp_path: Path):
    track1 = _make_track(tmp_path, "one.wav", 2.0)
    track2 = _make_track(tmp_path, "two.wav", 3.0)
    params = _zero_speed_params(sample_rate=44100, lead_in=0.5, gap=0.2, lead_out=0.3)

    audio, truth = build_side([track1, track2], params, np.random.default_rng(9))

    sr = params.output.sample_rate
    expected_len = int(0.5 * sr) + int(2.0 * sr) + int(0.2 * sr) + int(3.0 * sr) + int(0.3 * sr)
    assert audio.shape[0] == pytest.approx(expected_len, abs=5)
    assert audio.dtype == np.float32

    assert len(truth["tracks"]) == 2
    assert truth["tracks"][0]["order"] == 0
    assert truth["tracks"][0]["title"] == "Title one.wav"
    assert truth["tracks"][0]["speed_offset"] == pytest.approx(1.0)
    assert truth["tracks"][0]["start_sec"] == pytest.approx(0.5, abs=0.01)
    assert truth["tracks"][0]["end_sec"] == pytest.approx(2.5, abs=0.02)
    assert truth["tracks"][1]["start_sec"] == pytest.approx(2.5 + 0.2, abs=0.02)
    assert truth["sample_rate"] == 44100


def test_build_side_applies_nonzero_speed_variation(tmp_path: Path):
    track = _make_track(tmp_path, "one.wav", 2.0)
    params = _default_speed_params(lead_in=0.1, gap=0.1, lead_out=0.1)

    _, truth = build_side([track], params, np.random.default_rng(3))

    offset = truth["tracks"][0]["speed_offset"]
    assert 1.0 - 0.008 <= offset <= 1.0 + 0.008


def test_build_side_dry_mode_truncates_tracks(tmp_path: Path):
    track = _make_track(tmp_path, "long.wav", 5.0)
    params = _zero_speed_params(lead_in=0.0, gap=0.0, lead_out=0.0)

    audio, truth = build_side([track], params, np.random.default_rng(4), max_track_seconds=2.0)

    sr = params.output.sample_rate
    assert audio.shape[0] == pytest.approx(int(2.0 * sr), abs=5)
    assert truth["tracks"][0]["end_sec"] == pytest.approx(2.0, abs=0.02)


def test_write_side_creates_wav_and_truth_json(tmp_path: Path):
    import soundfile as sf

    audio = np.zeros(44100, dtype=np.float32)
    truth = {"sample_rate": 44100, "duration_sec": 1.0, "tracks": []}

    wav_path, json_path = write_side(audio, truth, tmp_path / "out", index=1)

    assert wav_path.name == "cara_01.wav"
    assert json_path.name == "cara_01.truth.json"
    assert wav_path.exists() and json_path.exists()

    read_audio, read_sr = sf.read(wav_path)
    assert read_sr == 44100
    assert read_audio.shape[0] == pytest.approx(44100, abs=5)

    loaded_truth = json.loads(json_path.read_text())
    assert loaded_truth == truth
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/vinylizer/test_build.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.vinylizer.build'`

- [ ] **Step 4: Implement `build.py`**

```python
# vinylyrics/vinylizer/build.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from pedalboard import HighShelfFilter, Pedalboard

from vinylyrics.vinylizer.library import TrackMeta
from vinylyrics.vinylizer.noise import build_noise_layer
from vinylyrics.vinylizer.params import VinylizerParams
from vinylyrics.vinylizer.speed import apply_speed_variation, random_speed_profile


def select_tracks(tracks: list[TrackMeta], n: int, rng: np.random.Generator) -> list[TrackMeta]:
    usable = [t for t in tracks if t.usable]
    n = min(n, len(usable))
    indices = rng.choice(len(usable), size=n, replace=False)
    return [usable[i] for i in indices]


def partition_tracks(
    tracks: list[TrackMeta], n: int, rng: np.random.Generator
) -> list[list[TrackMeta]]:
    usable = [t for t in tracks if t.usable]
    order = rng.permutation(len(usable))
    shuffled = [usable[i] for i in order]
    return [shuffled[i : i + n] for i in range(0, len(shuffled), n)]


def _load_mono(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    return audio.mean(axis=1).astype(np.float32), sr


def build_side(
    tracks: list[TrackMeta],
    params: VinylizerParams,
    rng: np.random.Generator,
    max_track_seconds: "float | None" = None,
) -> tuple[np.ndarray, dict]:
    output_sr = params.output.sample_rate
    lead_in_samples = int(params.structure.lead_in_sec * output_sr)
    gap_samples = int(params.structure.gap_sec * output_sr)
    lead_out_samples = int(params.structure.lead_out_sec * output_sr)

    processed = []
    for track in tracks:
        audio, source_sr = _load_mono(track.path)
        if max_track_seconds is not None:
            audio = audio[: int(max_track_seconds * source_sr)]
        profile = random_speed_profile(rng, params.speed)
        resampled = apply_speed_variation(audio, source_sr, output_sr, profile)
        processed.append((track, profile, resampled))

    total_samples = (
        lead_in_samples
        + sum(len(a) for _, _, a in processed)
        + gap_samples * max(0, len(processed) - 1)
        + lead_out_samples
    )

    noise_layer = build_noise_layer(total_samples, output_sr, params.noise, rng)
    music_layer = np.zeros(total_samples, dtype=np.float32)

    offset = lead_in_samples
    truth_tracks = []
    for i, (track, profile, audio) in enumerate(processed):
        music_layer[offset : offset + len(audio)] += audio
        truth_tracks.append(
            {
                "order": i,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "source_path": str(track.path),
                "start_sec": offset / output_sr,
                "end_sec": (offset + len(audio)) / output_sr,
                "speed_offset": profile.offset,
                "wow_freq_hz": profile.wow_freq_hz,
                "wow_depth": profile.wow_depth,
                "flutter_freq_hz": profile.flutter_freq_hz,
                "flutter_depth": profile.flutter_depth,
            }
        )
        offset += len(audio) + gap_samples

    mixed = music_layer + noise_layer
    peak = float(np.max(np.abs(mixed))) if len(mixed) else 0.0
    if peak > 0.95:
        mixed = mixed * (0.95 / peak)

    board = Pedalboard(
        [HighShelfFilter(cutoff_frequency_hz=params.filter.shelf_cutoff_hz, gain_db=params.filter.shelf_gain_db)]
    )
    final = board(mixed, output_sr).astype(np.float32)

    truth = {
        "sample_rate": output_sr,
        "duration_sec": len(final) / output_sr,
        "tracks": truth_tracks,
    }
    return final, truth


def write_side(audio: np.ndarray, truth: dict, output_dir: Path, index: int) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"cara_{index:02d}.wav"
    json_path = output_dir / f"cara_{index:02d}.truth.json"
    sf.write(wav_path, audio, truth["sample_rate"])
    json_path.write_text(json.dumps(truth, indent=2, ensure_ascii=False))
    return wav_path, json_path
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/vinylizer/test_build.py -v`
Expected: `7 passed`

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass (Phase 1's 4 + Task 1's 6 + Task 2's 10 + Task 3's
2 + Task 4's 7 = 29 total).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/vinylizer/build.py tests/vinylizer/test_build.py
git commit -m "feat: assemble vinyl sides with noise, speed variation, and truth.json"
```

---

## Task 5: `build` CLI subcommand + reuse docs

**Files:**
- Modify: `vinylyrics/vinylizer/cli.py` (add the `build` subcommand)
- Modify: `docs/REUSE.md` (add `numpy`, `pedalboard`, `soundfile` entries)
- Test: `tests/vinylizer/test_cli.py` (add `build`-specific tests)

**Interfaces:**
- Consumes: `scan_library`, `TrackMeta` (already imported in `cli.py`),
  `select_tracks`, `partition_tracks`, `build_side`, `write_side` from
  `vinylyrics.vinylizer.build` (Task 4), `load_params` from
  `vinylyrics.vinylizer.params` (Task 3).
- Produces: `vinylizer build <directory> [--tracks N] [--all] [--dry]
  [--seed S] [--output-dir DIR] [--params PATH]` wired into the same
  `main(argv)` / `build_parser()` this module already exposes (Phase 1).

- [ ] **Step 1: Write the failing tests**

Append to the existing `tests/vinylizer/test_cli.py` (don't touch the
existing `inspect` test):

```python
# --- append to tests/vinylizer/test_cli.py ---
import soundfile as sf

from vinylyrics.vinylizer.cli import main


def _make_tagged_track(tmp_path: Path, name: str, seconds: float = 1.0) -> None:
    import subprocess

    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3

    p = tmp_path / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono", "-t", str(seconds),
            "-codec:a", "libmp3lame", "-qscale:a", "9", str(p),
        ],
        check=True,
    )
    audio = MP3(p)
    if audio.tags is None:
        audio.add_tags()
    audio.save()
    easy = EasyID3(p)
    easy["title"] = name
    easy["artist"] = "Test Artist"
    easy["album"] = "Test Album"
    easy.save()


def test_build_default_creates_one_side(tmp_path: Path):
    for i in range(3):
        _make_tagged_track(tmp_path, f"song{i}.mp3", seconds=1.0)
    out_dir = tmp_path / "out"

    exit_code = main([
        "build", str(tmp_path),
        "--tracks", "2",
        "--seed", "1",
        "--output-dir", str(out_dir),
    ])

    assert exit_code == 0
    assert (out_dir / "cara_01.wav").exists()
    assert (out_dir / "cara_01.truth.json").exists()
    truth = json.loads((out_dir / "cara_01.truth.json").read_text())
    assert len(truth["tracks"]) == 2


def test_build_all_splits_every_usable_track(tmp_path: Path):
    for i in range(5):
        _make_tagged_track(tmp_path, f"song{i}.mp3", seconds=1.0)
    out_dir = tmp_path / "out"

    exit_code = main([
        "build", str(tmp_path),
        "--tracks", "2",
        "--all",
        "--seed", "2",
        "--output-dir", str(out_dir),
    ])

    assert exit_code == 0
    sides = sorted(out_dir.glob("cara_*.truth.json"))
    assert len(sides) == 3  # 5 tracks split into groups of 2: [2, 2, 1]
    total_tracks = sum(len(json.loads(p.read_text())["tracks"]) for p in sides)
    assert total_tracks == 5


def test_build_dry_generates_a_short_side(tmp_path: Path):
    for i in range(3):
        _make_tagged_track(tmp_path, f"song{i}.mp3", seconds=2.0)
    out_dir = tmp_path / "out"

    exit_code = main(["build", str(tmp_path), "--dry", "--seed", "3", "--output-dir", str(out_dir)])

    assert exit_code == 0
    truth = json.loads((out_dir / "dry.truth.json").read_text())
    assert len(truth["tracks"]) == 3


def test_build_rejects_all_and_dry_together(tmp_path: Path, capsys):
    _make_tagged_track(tmp_path, "song.mp3")
    exit_code = main(["build", str(tmp_path), "--all", "--dry"])
    assert exit_code == 1
    assert "--all" in capsys.readouterr().out
```

Add `import json` and `from pathlib import Path` at the top of
`tests/vinylizer/test_cli.py` if not already present (the existing file
already imports `Path`; check before adding a duplicate).

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/vinylizer/test_cli.py -v`
Expected: failures on the four new `test_build_*` tests (no `build`
subcommand yet — argparse will error with "invalid choice: 'build'" or
similar); the pre-existing `inspect` test still passes.

- [ ] **Step 3: Add the `build` subcommand to `cli.py`**

Add these imports near the top of `vinylyrics/vinylizer/cli.py` (alongside
the existing `from vinylyrics.vinylizer.library import TrackMeta, scan_library`):

```python
import numpy as np

from vinylyrics.vinylizer.build import build_side, partition_tracks, select_tracks, write_side
from vinylyrics.vinylizer.params import load_params
```

Add this function (anywhere after the existing `_cmd_inspect`):

```python
def _cmd_build(args: argparse.Namespace) -> int:
    if args.all and args.dry:
        print("--all y --dry no se pueden combinar.")
        return 1

    tracks = scan_library(Path(args.directory))
    rng = np.random.default_rng(args.seed)
    params = load_params(Path(args.params) if args.params else None)
    output_dir = Path(args.output_dir)

    if args.dry:
        selected = select_tracks(tracks, 3, rng)
        audio, truth = build_side(selected, params, rng, max_track_seconds=30.0)
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = output_dir / "dry.wav"
        json_path = output_dir / "dry.truth.json"
        import soundfile as sf
        sf.write(wav_path, audio, truth["sample_rate"])
        json_path.write_text(json.dumps(truth, indent=2, ensure_ascii=False))
        print(f"Generado {wav_path} ({truth['duration_sec']:.1f}s, {len(selected)} pistas)")
        return 0

    if args.all:
        groups = partition_tracks(tracks, args.tracks, rng)
        for i, group in enumerate(groups, start=1):
            audio, truth = build_side(group, params, rng)
            wav_path, _ = write_side(audio, truth, output_dir, i)
            print(f"Generado {wav_path} ({truth['duration_sec']:.1f}s, {len(group)} pistas)")
        return 0

    selected = select_tracks(tracks, args.tracks, rng)
    audio, truth = build_side(selected, params, rng)
    wav_path, _ = write_side(audio, truth, output_dir, 1)
    print(f"Generado {wav_path} ({truth['duration_sec']:.1f}s, {len(selected)} pistas)")
    return 0
```

Add `import json` at the top of `cli.py` if it isn't already imported.

Register the subcommand inside `build_parser()`, right after the existing
`inspect_parser` block:

```python
    build_parser = subparsers.add_parser("build", help="Genera un WAV que simula una cara de vinilo")
    build_parser.add_argument("directory", help="Carpeta con archivos .mp3")
    build_parser.add_argument("--tracks", type=int, default=6, help="Pistas por cara (por defecto 6)")
    build_parser.add_argument("--all", action="store_true", help="Reparte todas las pistas usables en varias caras")
    build_parser.add_argument("--dry", action="store_true", help="Genera ~90s de prueba (3 fragmentos de 30s)")
    build_parser.add_argument("--seed", type=int, default=None, help="Semilla para reproducibilidad")
    build_parser.add_argument("--output-dir", default="data/vinylizer_output", help="Carpeta de salida")
    build_parser.add_argument("--params", default=None, help="Ruta a un TOML de parámetros alternativo")
    build_parser.set_defaults(func=_cmd_build)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/vinylizer/test_cli.py -v`
Expected: all `inspect` + `build` tests pass (5 pre-existing checks — 1
`inspect` test plus whatever Phase 1 left — plus the 4 new `build` tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Update `docs/REUSE.md`**

Read the existing `docs/REUSE.md` first (Phase 1 created it with a table
for `mutagen`, `python-dotenv`, `pytest`, `hatchling`). Add three rows to
that same table (matching its existing format — read the file to match
style exactly) for:
- **numpy** — BSD-3-Clause. DSP math: LFO generation, cumulative time
  integration for variable-rate resampling, FFT-based pink noise, Poisson
  click scheduling.
- **pedalboard** (Spotify) — GPLv3 (see this project's license rationale,
  already recorded above in this file). Used for `HighShelfFilter` (the
  vinylizer's 12kHz rolloff), `HighpassFilter` (click shaping), and
  `LowpassFilter` (rumble shaping) — audio effects on top of JUCE, exactly
  the reuse the original spec called for instead of hand-rolled biquads.
- **soundfile** — BSD-3-Clause. Reads the source mp3s directly (confirmed
  during Phase 2 planning: bundled libsndfile 1.2.2 decodes MP3 natively,
  no ffmpeg/pydub step needed for this path) and writes the output WAV.

- [ ] **Step 7: Manual smoke test against the real library**

Run against the real 47-song directory to confirm nothing about real mp3s
(variable sample rates, stereo/mono, VBR encoding) breaks the pipeline:

```bash
uv run vinylizer build /home/dakur/Downloads/songs --dry --seed 42 --output-dir /tmp/vinylizer-smoke
```

Expected: exits 0, prints a line like "Generado /tmp/vinylizer-smoke/dry.wav
(...)", and `/tmp/vinylizer-smoke/dry.wav` + `dry.truth.json` both exist.
Report the actual printed output and file sizes in your report — David
will listen to this file himself before Phase 3 starts, so don't delete it.

- [ ] **Step 8: Commit**

```bash
git add vinylyrics/vinylizer/cli.py tests/vinylizer/test_cli.py docs/REUSE.md
git commit -m "feat: add vinylizer build CLI subcommand"
```

---

## Self-Review Notes

- **Spec coverage:** §1 "Subcomando build" — every bullet has a task:
  short sides by default / `--tracks` / `--all` / `--dry` → Task 5;
  constant speed deviation + wow + flutter, resampling not time-stretch →
  Task 1; pink noise + clicks + rumble → Task 2; frequency shelf → Task 4
  (`build_side`'s final `HighShelfFilter` pass); lead-in/gap-with-noise/
  lead-out structure → Task 4; `.truth.json` with order/offsets/speed/ID3
  metadata → Task 4; TOML params, fixable seed → Task 3 + Task 5's `--seed`.
- **No placeholders:** every step has real, planning-verified code.
- **Type/interface consistency:** `SpeedProfile` (Task 1) → consumed
  unchanged by `build_side` (Task 4). `NoiseParams`/`SpeedParams`/etc.
  (Task 3) → consumed unchanged by `random_speed_profile` (Task 1) and
  `build_noise_layer` (Task 2) via duck typing (attribute access only, no
  isinstance checks), and constructed directly by Task 4/5. `TrackMeta`
  (Phase 1, unmodified) → consumed by `select_tracks`/`partition_tracks`/
  `build_side` (Task 4) exactly as Phase 1 defined it (`.path`, `.title`,
  `.artist`, `.album`, `.usable`).
- **Gap acknowledged, not silently dropped:** the real 47-song library's
  ID3 metadata quality (YouTube-scrape artifacts) that the Phase 1 final
  review surfaced is NOT addressed by this plan — David said he'll assess
  it himself directly. This phase's `.truth.json` will faithfully echo
  whatever `TrackMeta.title`/`.artist`/`.album` say, messy or not; no task
  here normalizes or fabricates cleaner values.
- **Not yet claimed by any phase (carried forward, same gap Phase 1's
  final review flagged):** the `justfile`/`Makefile` from spec §10. Still
  nobody's task. Flag again when planning Phase 3.
