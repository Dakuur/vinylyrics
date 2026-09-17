# vinylyrics Phase 4 Implementation Plan — Audio Sources + Silence Detector

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the (not-yet-built) recognition pipeline something to read from — an
`AudioSource` abstraction (file-based for dev/eval, live line-in for the Pi),
a 20s circular buffer, and an RMS-based silence detector with hysteresis
that emits `TRACK_GAP`/`STOPPED` events calibrated against the actual
background noise floor rather than a hardcoded number.

**Architecture:** `FileSource` and `LineInSource` both implement the same
`AudioSource` protocol (`read(seconds) -> np.ndarray`, `sample_rate`),
always returning float32 mono at 16 kHz regardless of the underlying
source's native format — `FileSource` resamples with `scipy.signal.resample_poly`
once at load time, `LineInSource` opens the line-in device at exactly that
rate. A `CircularAudioBuffer` accumulates whatever a source produces, capped
at 20s, and hands back "the last N seconds" on demand — this is what a
later phase's sliding-window recognizer will read from. `SilenceDetector`
consumes a stream of per-100ms RMS-dBFS values (not raw audio) and applies
hysteresis (separate enter/exit thresholds relative to a *measured*
background floor) to decide when a `TRACK_GAP` (1–3s of silence) or
`STOPPED` (>10s) has occurred.

**Tech Stack:** `numpy` (already a dependency), `scipy` (new — fixed-ratio
resampling, the choice already recorded in docs/SPEC.md's "Decisiones
tomadas" as `librosa`'s replacement), `sounddevice` (new — line-in capture,
**imported lazily**, see Global Constraints), `soundfile` (already a
dependency, used by `FileSource`).

**Spec:** [docs/SPEC.md](../../SPEC.md) §"Arquitectura" (the `AudioSource`
protocol) and §2 "Audio y detección de estado". Also read
[docs/superpowers/plans/2026-09-17-vinylyrics-phase2-vinylizer.md](2026-09-17-vinylyrics-phase2-vinylizer.md)
for `rms_dbfs`/`to_dbfs`'s existing behavior — this plan relocates them,
see Task 1.

## Global Constraints

(Phase 1/2's constraints all still apply. This phase adds:)

- **`sounddevice` must be importable with zero audio hardware AND with the
  system `portaudio` library itself absent.** This was verified during
  planning: on this exact development machine, `import sounddevice` at
  the top of a module currently raises `OSError: PortAudio library not
  found`, because `portaudio19-dev`/`libportaudio2` has never been
  installed (`scripts/setup-ubuntu.sh` covers this but hasn't been run
  here). The spec's "must import without failing on a machine without
  input devices" requirement is therefore stricter than "no card plugged
  in" — it means **`import sounddevice` cannot appear at module top-level
  anywhere in this codebase.** Every use of `sounddevice` (in `LineInSource`
  and `list_devices()`) must do `import sounddevice as sd` *inside* the
  function/method body, so merely importing `vinylyrics.audio.source` (to
  use `FileSource`, or to run the test suite) never touches the library.
  Tests inject a fake module via `unittest.mock.patch.dict(sys.modules, {"sounddevice": fake})`
  before the lazy import runs — verified working during planning, no real
  portaudio needed to test `LineInSource`'s logic.
- **AudioSource contract:** every implementation returns **float32 mono at
  16000 Hz**, regardless of the source's native format. `FileSource`
  resamples via `scipy.signal.resample_poly` (exact ratio via `gcd`, not an
  approximate resampler) once when the file is loaded.
- **No new heavy dependency for the buffer/VAD.** `CircularAudioBuffer` and
  `SilenceDetector` are pure `numpy`, no `scipy`/`sounddevice` needed.
- **dBFS convention carries over unchanged from Phase 2:** RMS dBFS
  (`20*log10(rms)`), not peak. Reused, not reimplemented — see Task 1.
- **Silence detection is calibrated, never absolute.** `SilenceDetector`
  takes a `floor_dbfs` value from its caller (measured via `calibrate_floor`
  against a known-quiet segment — e.g. a recording's lead-in) rather than
  a hardcoded threshold. This plan's tests use synthetic floors; wiring
  real calibration into the live pipeline is a later phase's job.
- Every module and test in this plan was hand-verified end-to-end during
  planning (`FileSource` resampling + realtime timing, `LineInSource`'s
  lazy-import behavior via mock injection, `CircularAudioBuffer` capacity
  capping, and `SilenceDetector`'s hysteresis/gap/stopped logic against
  synthetic RMS sequences) — 23 new tests, all passing, plus the existing
  33 from Phases 1–2 re-run together with zero regressions after Task 1's
  refactor.

---

## Roadmap Context

This is the next phase after Phase 2 (vinylizer, merged). Per the spec's
"Orden de trabajo," it's step 4: "Fuentes de audio y detector de silencio,
con pruebas." Recognition (step 5), the clock+lyrics (step 6), the
server+interface (step 7), and evaluation (step 8) are not detailed here —
each gets its own plan when its turn comes. Also carried forward again
(third phase in a row): the spec §10 `justfile`/`Makefile` still has no
owning phase — claim it explicitly whenever a phase's CLI surface next
changes enough to be worth scripting.

---

## Task 1: Extract `rms_dbfs`/`to_dbfs` into `vinylyrics/audio/levels.py`

**Why this task exists:** the silence detector needs the exact same RMS/dBFS
math Phase 2's `vinylizer/noise.py` already implements and tests. Importing
`vinylizer.noise` directly from `audio.vad` would work today, but it's
backwards: `vinylizer` is a dev/offline tool (never runs on the Pi), while
`audio` is core runtime code (does run on the Pi) — a runtime module
importing a dev-tool module (and transitively requiring `pedalboard`, a
GPLv3 audio-effects library that has nothing to do with silence detection)
is the wrong direction of dependency. This task moves the two functions to
a neutral, dependency-free location both `vinylizer` and `audio` can use.

**Files:**
- Create: `vinylyrics/audio/levels.py`
- Modify: `vinylyrics/vinylizer/noise.py` (remove the two functions, import them instead)
- Test: `tests/audio/test_levels.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `def rms_dbfs(signal: np.ndarray) -> float`, `def to_dbfs(signal: np.ndarray, target_dbfs: float) -> np.ndarray` — Task 4 (`vad.py`) imports `rms_dbfs` from here; `vinylizer/noise.py` (Phase 2, already reviewed) imports both from here after this task.

**Verified during planning:** moved these exact two functions into a
standalone module, rewired `vinylizer/noise.py` to import them, and reran
Phase 1+2's full 33-test suite together with the new module in place —
all 33 still passed, zero regressions. The functions' bodies are copied
verbatim from Phase 2's `noise.py`, nothing about their behavior changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/audio/test_levels.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/audio/test_levels.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.audio.levels'`

- [ ] **Step 3: Create `vinylyrics/audio/levels.py`**

```python
# vinylyrics/audio/levels.py
from __future__ import annotations

import numpy as np


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/audio/test_levels.py -v`
Expected: `4 passed`

- [ ] **Step 5: Update `vinylyrics/vinylizer/noise.py` to import from the new module**

Open `vinylyrics/vinylizer/noise.py`. It currently starts like this:

```python
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
    ...
```

Delete the `rms_dbfs` and `to_dbfs` function bodies entirely (everything
from `def rms_dbfs` through the end of `to_dbfs`'s `return` line) and
replace the import block with:

```python
from __future__ import annotations

import numpy as np
from pedalboard import HighpassFilter, LowpassFilter, Pedalboard

from vinylyrics.audio.levels import rms_dbfs, to_dbfs


def pink_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    ...
```

Everything below `pink_noise` in the file (poisson_click_times, render_clicks,
rumble_noise, build_noise_layer) stays exactly as it is — they already call
`rms_dbfs`/`to_dbfs` by name, and Python resolves that to the imported
versions automatically.

- [ ] **Step 6: Run Phase 1+2's full suite to confirm no regression**

Run: `uv run pytest -v`
Expected: all 33 previously-passing tests still pass (this task adds 4 more
for `levels.py` itself, so 37 total after this step). Pay particular
attention to `tests/vinylizer/test_noise.py` — every one of its 9 tests
exercises `rms_dbfs`/`to_dbfs` indirectly through `pink_noise`/`to_dbfs`/
`rumble_noise`/`build_noise_layer`, so this is where an import mistake
would show up.

- [ ] **Step 7: Commit**

```bash
git add vinylyrics/audio/levels.py vinylyrics/vinylizer/noise.py tests/audio/test_levels.py tests/audio/__init__.py
git commit -m "refactor: move rms_dbfs/to_dbfs to vinylyrics.audio.levels"
```

(Create `tests/audio/__init__.py` as an empty file if it doesn't exist yet — this is the first test file in a new `tests/audio/` directory.)

---

## Task 2: `AudioSource` protocol, `FileSource`, `LineInSource` (`audio/source.py`)

**Files:**
- Modify: `pyproject.toml` (add `scipy>=1.11` and `sounddevice>=0.5` to `dependencies`)
- Create: `vinylyrics/audio/source.py`
- Test: `tests/audio/test_source.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `class AudioSource(Protocol)`: `def read(self, seconds: float) -> np.ndarray`, `@property def sample_rate(self) -> int`.
  - `class FileSource`: `__init__(self, path: Path, *, realtime: bool = False, sample_rate: int = 16000)`, implements `AudioSource`.
  - `class LineInSource`: `__init__(self, device: "int | str | None" = None, sample_rate: int = 16000)`, implements `AudioSource`.
  - `def list_devices() -> list[dict]`.
  - A later phase's sliding-window recognizer will hold one `AudioSource`
    (either kind) and call `.read(seconds)` in a loop, feeding a
    `CircularAudioBuffer` (Task 3).

**Verified during planning:** every test below was run for real, including
catching a test-design bug (a 440 Hz pure tone repeats exactly every
second, so two consecutive 1-second reads were bit-identical — not a
`FileSource` bug, a bad choice of test signal; fixed by using noise for
that specific test, kept below). `LineInSource`'s lazy-import behavior was
verified by injecting a fake `sounddevice` module into `sys.modules`
*without* real portaudio installed — proving the lazy-import pattern
actually solves the problem described in Global Constraints, not just in
theory.

- [ ] **Step 1: Write the failing tests**

```python
# tests/audio/test_source.py
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


def test_list_devices_uses_sounddevice_query():
    fake_sd = types.ModuleType("sounddevice")
    fake_sd.query_devices = mock.MagicMock(return_value=[{"name": "fake mic"}])

    with mock.patch.dict(sys.modules, {"sounddevice": fake_sd}):
        devices = list_devices()

    assert devices == [{"name": "fake mic"}]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/audio/test_source.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.audio.source'`

- [ ] **Step 3: Add the `scipy` and `sounddevice` dependencies**

```toml
dependencies = [
    "mutagen>=1.48",
    "python-dotenv>=1.0",
    "numpy>=1.26",
    "pedalboard>=0.9",
    "soundfile>=0.13",
    "scipy>=1.11",
    "sounddevice>=0.5",
]
```

Run: `uv sync` — confirm it installs both with no errors. (`sounddevice`
installs fine even though `import sounddevice` will fail at *runtime* on
this machine until `scripts/setup-ubuntu.sh` is run — the Python package
itself has no install-time dependency on the native library being present.)

- [ ] **Step 4: Implement `source.py`**

```python
# vinylyrics/audio/source.py
from __future__ import annotations

import time
from math import gcd
from pathlib import Path
from typing import Protocol

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


class AudioSource(Protocol):
    def read(self, seconds: float) -> np.ndarray: ...

    @property
    def sample_rate(self) -> int: ...


def _resample_fixed(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr == target_sr:
        return audio.astype(np.float32)
    g = gcd(source_sr, target_sr)
    up = target_sr // g
    down = source_sr // g
    return resample_poly(audio, up, down).astype(np.float32)


class FileSource:
    def __init__(self, path: Path, *, realtime: bool = False, sample_rate: int = 16000):
        audio, source_sr = sf.read(path, dtype="float32", always_2d=True)
        mono = audio.mean(axis=1).astype(np.float32)
        self._audio = _resample_fixed(mono, source_sr, sample_rate)
        self._sample_rate = sample_rate
        self._cursor = 0
        self._realtime = realtime

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def read(self, seconds: float) -> np.ndarray:
        n = int(seconds * self._sample_rate)
        start = self._cursor
        end = min(start + n, len(self._audio))
        chunk = self._audio[start:end]
        self._cursor = end
        if self._realtime:
            time.sleep(seconds)
        return chunk


def list_devices() -> list[dict]:
    import sounddevice as sd

    return list(sd.query_devices())


class LineInSource:
    def __init__(self, device: "int | str | None" = None, sample_rate: int = 16000):
        self._device = device
        self._sample_rate = sample_rate
        self._stream = None

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _ensure_stream(self):
        if self._stream is None:
            import sounddevice as sd

            self._stream = sd.InputStream(
                device=self._device, channels=1, samplerate=self._sample_rate, dtype="float32"
            )
            self._stream.start()

    def read(self, seconds: float) -> np.ndarray:
        self._ensure_stream()
        n = int(seconds * self._sample_rate)
        data, _overflowed = self._stream.read(n)
        return data[:, 0].astype(np.float32)
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/audio/test_source.py -v`
Expected: `10 passed`

- [ ] **Step 6: Verify the module imports cleanly without portaudio**

Run: `uv run python3 -c "from vinylyrics.audio.source import AudioSource, FileSource, LineInSource, list_devices; print('ok')"`
Expected: prints `ok` with no `OSError`, even though `sounddevice` itself
cannot be imported directly on this machine right now (confirm that
separately: `uv run python3 -c "import sounddevice"` IS expected to raise
`OSError: PortAudio library not found` here — that's fine, it's `source.py`
that must stay import-safe, not the `sounddevice` package itself).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/audio/source.py tests/audio/test_source.py
git commit -m "feat: add AudioSource protocol with FileSource and lazy-import LineInSource"
```

---

## Task 3: Circular audio buffer (`audio/buffer.py`)

**Files:**
- Create: `vinylyrics/audio/buffer.py`
- Test: `tests/audio/test_buffer.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: `class CircularAudioBuffer`: `__init__(self, sample_rate: int, max_seconds: float = 20.0)`,
  `def push(self, samples: np.ndarray) -> None`, `def read_last(self, seconds: float) -> np.ndarray`,
  `@property def sample_rate(self) -> int`, `@property def duration_available(self) -> float`.
  A later phase's sliding-window recognizer holds one of these, `push()`ing
  whatever an `AudioSource.read()` returns and `read_last(12.0)` to get the
  recognition window.

**Verified during planning:** all 6 tests below ran and passed on first
try — capacity capping, most-recent-first ordering, and the empty/
longer-than-available edge cases all behave as written.

- [ ] **Step 1: Write the failing tests**

```python
# tests/audio/test_buffer.py
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/audio/test_buffer.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.audio.buffer'`

- [ ] **Step 3: Implement `buffer.py`**

```python
# vinylyrics/audio/buffer.py
from __future__ import annotations

import numpy as np


class CircularAudioBuffer:
    def __init__(self, sample_rate: int, max_seconds: float = 20.0):
        self._sample_rate = sample_rate
        self._max_samples = int(max_seconds * sample_rate)
        self._data = np.zeros(0, dtype=np.float32)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def duration_available(self) -> float:
        return len(self._data) / self._sample_rate

    def push(self, samples: np.ndarray) -> None:
        if len(samples) == 0:
            return
        self._data = np.concatenate([self._data, samples.astype(np.float32)])
        if len(self._data) > self._max_samples:
            self._data = self._data[-self._max_samples :]

    def read_last(self, seconds: float) -> np.ndarray:
        n = int(seconds * self._sample_rate)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        return self._data[-n:]
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/audio/test_buffer.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/audio/buffer.py tests/audio/test_buffer.py
git commit -m "feat: add 20s circular audio buffer"
```

---

## Task 4: Silence detector with hysteresis (`audio/vad.py`)

**Files:**
- Create: `vinylyrics/audio/vad.py`
- Test: `tests/audio/test_vad.py`

**Interfaces:**
- Consumes: `rms_dbfs` from `vinylyrics.audio.levels` (Task 1).
- Produces:
  - `class AudioEvent(Enum)`: `TRACK_GAP`, `STOPPED`.
  - `def compute_rms_windows(audio: np.ndarray, sample_rate: int, window_sec: float = 0.1) -> np.ndarray`
  - `def calibrate_floor(calibration_audio: np.ndarray) -> float`
  - `@dataclass(frozen=True) class SilenceThresholds`: `enter_offset_db: float = 6.0`,
    `exit_offset_db: float = 10.0`, `gap_min_sec: float = 1.0`, `gap_max_sec: float = 3.0`,
    `stopped_sec: float = 10.0`, `window_sec: float = 0.1`.
  - `class SilenceDetector`: `__init__(self, floor_dbfs: float, thresholds: SilenceThresholds = SilenceThresholds())`,
    `def process_window(self, window_dbfs: float) -> "AudioEvent | None"`, `@property def is_silent -> bool`.
  - A later phase feeds `compute_rms_windows(buffer.read_last(...), sr)`'s
    output one value at a time into `SilenceDetector.process_window` and
    reacts to `TRACK_GAP`/`STOPPED`.

**Design note (why hysteresis has two thresholds, not one):** a single
threshold flickers when the signal hovers right at the boundary (noise
jitter causes rapid silent/not-silent toggling). Two thresholds create a
dead zone: you must drop below `floor + enter_offset_db` to be considered
newly silent, but must rise above the *higher* `floor + exit_offset_db` to
be considered "sound resumed." Anything in between the two thresholds
changes nothing — this plan's `test_silence_detector_does_not_flap_within_hysteresis_deadzone`
verifies exactly that.

**Verified during planning:** all 7 tests below were run against this exact
implementation and passed on the first attempt — no bugs found this time,
unlike Task 2's tone-repeats-every-second test-design issue.

- [ ] **Step 1: Write the failing tests**

```python
# tests/audio/test_vad.py
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/audio/test_vad.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.audio.vad'`

- [ ] **Step 3: Implement `vad.py`**

```python
# vinylyrics/audio/vad.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from vinylyrics.audio.levels import rms_dbfs


class AudioEvent(Enum):
    TRACK_GAP = auto()
    STOPPED = auto()


def compute_rms_windows(audio: np.ndarray, sample_rate: int, window_sec: float = 0.1) -> np.ndarray:
    window_samples = max(1, int(window_sec * sample_rate))
    n_windows = len(audio) // window_samples
    if n_windows == 0:
        return np.zeros(0, dtype=np.float32)
    trimmed = audio[: n_windows * window_samples]
    reshaped = trimmed.reshape(n_windows, window_samples)
    return np.array([rms_dbfs(row) for row in reshaped], dtype=np.float32)


def calibrate_floor(calibration_audio: np.ndarray) -> float:
    return rms_dbfs(calibration_audio)


@dataclass(frozen=True)
class SilenceThresholds:
    enter_offset_db: float = 6.0
    exit_offset_db: float = 10.0
    gap_min_sec: float = 1.0
    gap_max_sec: float = 3.0
    stopped_sec: float = 10.0
    window_sec: float = 0.1


class SilenceDetector:
    def __init__(self, floor_dbfs: float, thresholds: SilenceThresholds = SilenceThresholds()):
        self._floor = floor_dbfs
        self._thresholds = thresholds
        self._is_silent = False
        self._silence_elapsed = 0.0
        self._stopped_fired = False

    @property
    def is_silent(self) -> bool:
        return self._is_silent

    def process_window(self, window_dbfs: float) -> "AudioEvent | None":
        t = self._thresholds
        enter_threshold = self._floor + t.enter_offset_db
        exit_threshold = self._floor + t.exit_offset_db

        if not self._is_silent:
            if window_dbfs < enter_threshold:
                self._is_silent = True
                self._silence_elapsed = t.window_sec
                self._stopped_fired = False
            return None

        if window_dbfs > exit_threshold:
            duration = self._silence_elapsed
            self._is_silent = False
            self._silence_elapsed = 0.0
            if t.gap_min_sec <= duration <= t.gap_max_sec:
                return AudioEvent.TRACK_GAP
            return None

        self._silence_elapsed += t.window_sec
        if self._silence_elapsed >= t.stopped_sec and not self._stopped_fired:
            self._stopped_fired = True
            return AudioEvent.STOPPED
        return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/audio/test_vad.py -v`
Expected: `7 passed`

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass — Phase 1+2's 33, plus this phase's Task 1 (4) +
Task 2 (10) + Task 3 (6) + Task 4 (7) = 60 total.

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/audio/vad.py tests/audio/test_vad.py
git commit -m "feat: add RMS-based silence detector with hysteresis"
```

---

## Task 5: `--list-devices` script + README note

**Files:**
- Create: `scripts/list_audio_devices.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `list_devices` from `vinylyrics.audio.source` (Task 2).
- Produces: a standalone script David can run to see what `sounddevice`
  detects, once `scripts/setup-ubuntu.sh` has installed portaudio. There is
  no bigger runtime CLI yet to attach a `--list-devices` flag to (that
  arrives with the server in a later phase) — this fulfills the spec's
  explicit ask for one now, the same way `scripts/try_recognize.py`
  covered manual recognition testing ahead of the real module.

- [ ] **Step 1: Write `scripts/list_audio_devices.py`**

```python
#!/usr/bin/env python3
"""Lista los dispositivos de audio que ve sounddevice (para elegir --device
más adelante, cuando haya una tarjeta USB conectada).

Necesita portaudio instalado (scripts/setup-ubuntu.sh). Si ves
"OSError: PortAudio library not found", ejecuta ese script primero.
"""
from __future__ import annotations

from vinylyrics.audio.source import list_devices


def main() -> int:
    devices = list_devices()
    if not devices:
        print("No se detectó ningún dispositivo de audio.")
        return 0

    for i, device in enumerate(devices):
        name = device.get("name", "?")
        max_in = device.get("max_input_channels", 0)
        max_out = device.get("max_output_channels", 0)
        print(f"[{i}] {name}  (entradas: {max_in}, salidas: {max_out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify it fails cleanly (no portaudio on this machine)**

Run: `uv run scripts/list_audio_devices.py`
Expected: `OSError: PortAudio library not found` — this IS the expected
result on this machine right now, and confirms `list_devices()` really
does defer the `sounddevice` import to call time (if `source.py` imported
it eagerly, `list_devices` would have already failed to even be importable,
not just uncallable). Do not treat this error as a task failure — record
the exact output in your report as evidence the lazy-import contract holds
end-to-end, then move on. This script will work once someone runs
`scripts/setup-ubuntu.sh`.

- [ ] **Step 3: Add a short README note**

Open `README.md`. Find the "Uso" section (it currently documents `inspect`
and `build`). Add one short paragraph after them:

```markdown
### Dispositivos de audio (para más adelante)

Cuando haya una tarjeta USB conectada:

\`\`\`bash
uv run scripts/list_audio_devices.py
\`\`\`

Necesita `portaudio` instalado (`./scripts/setup-ubuntu.sh`).
```

- [ ] **Step 4: Commit**

```bash
git add scripts/list_audio_devices.py README.md
git commit -m "feat: add --list-devices script for future line-in setup"
```

---

## Self-Review Notes

- **Spec coverage:** the `AudioSource` protocol from "Arquitectura" → Task 2.
  §2's buffer circular de 20s → Task 3. RMS en ventanas de 100ms, detector
  con histéresis calibrado contra el fondo, TRACK_GAP/STOPPED → Task 4.
  "--list-devices" → Task 5. The sliding-window *scheduling* ("intento de
  reconocimiento cada 2s sobre los últimos 12s") is explicitly NOT built
  here — it's recognition-policy logic that belongs with the recognizer in
  the next phase, which will be the first real consumer of
  `CircularAudioBuffer.read_last(12.0)`.
- **No placeholders:** every step has real, planning-verified code.
- **Type/interface consistency:** `AudioSource` (Task 2) has no concrete
  base class — `FileSource`/`LineInSource` satisfy it structurally
  (`Protocol`), so nothing to keep in sync across tasks there.
  `rms_dbfs` (Task 1) is imported unchanged by both `vinylizer/noise.py`
  (Phase 2, refactored in Task 1) and `audio/vad.py` (Task 4).
  `SilenceThresholds`/`SilenceDetector`/`AudioEvent` (Task 4) are
  self-contained — no other task constructs them yet (a future recognition
  phase will).
- **Real discovery acted on, not hidden:** `sounddevice` cannot currently
  be imported on this development machine (missing native `portaudio`
  library, confirmed, not a "no device" situation) — this shaped Task 2's
  design (lazy import of the module itself) rather than being treated as
  an environment problem to work around later. Task 5's Step 2 exercises
  this live and records the actual failure as expected, passing evidence.
- **Carried forward again:** spec §10's `justfile`/`Makefile` — fourth
  phase in a row with no task claiming it (Phase 1, Phase 2's final review,
  and now this plan all note the same gap). If Phase 5's plan doesn't
  finally claim it, that's worth asking about directly rather than noting
  it a fifth time.
