# vinylyrics Phase 5 Implementation Plan — Recognition

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the real `Recognizer` module the spec asks for — a
`ShazamIORecognizer` with retries/backoff and a disk cache keyed by audio
hash, a call-cadence policy (never two simultaneous calls, ≥8s between
attempts, immediate after `TRACK_GAP`, 45s resync once locked), and cover
art enrichment via MusicBrainz + Cover Art Archive with Shazam's own art as
fallback — replacing the throwaway `scripts/try_recognize.py` smoke-test
script from earlier this session with the module the spec actually
describes.

**Architecture:** A `Recognizer` protocol (`async def recognize(audio,
sample_rate) -> RecognitionResult | None`) is implemented by
`ShazamIORecognizer`, which hashes the audio fragment, checks a
`DiskRecognitionCache` before ever calling the network, and on a cache
miss calls `shazamio` with retry+backoff (3 attempts, then gives up —
"UNIDENTIFIED" is `None`, not an exception). A separate `CallCadencePolicy`
is a pure state machine (no I/O) that a later phase's orchestration loop
will consult before calling `recognize()` at all — it doesn't call
`recognize()` itself. `find_cover_url`/`find_cover_url_async` search
MusicBrainz (ISRC lookup first when Shazam gave one, since it's exact;
fuzzy artist+title+album search as fallback) and probe Cover Art Archive's
fixed URL pattern for each candidate release until one resolves.
`recognize_with_cover_art` composes a `Recognizer` with cover-art lookup,
preferring MusicBrainz/CAA's art and falling back to Shazam's own — exactly
the spec's stated preference.

**Tech Stack:** `shazamio` (already a dependency — added this session for
the throwaway smoke-test script, retroactively documented in `docs/REUSE.md`
by this plan's Task 6), `musicbrainzngs` (new), `requests` (new — for the
Cover Art Archive HEAD check; already present transitively but not a
declared direct dependency until this phase).

**Spec:** [docs/SPEC.md](../../SPEC.md) §3 "Reconocimiento". Also read
[docs/superpowers/plans/2026-09-17-vinylyrics-phase4-audio-sources.md](2026-09-17-vinylyrics-phase4-audio-sources.md)
for the corrected note on how a later phase should read `AudioSource`
chunks (not `CircularAudioBuffer.read_last()`'s overlapping tail) — this
phase's `Recognizer` is exactly the kind of consumer that note was written
for, though wiring `CallCadencePolicy`+`Recognizer` into the actual
sliding-window loop is itself a *later* phase's job (see Roadmap Context).

## Global Constraints

(Phases 1/2/4's constraints all still apply. This phase adds:)

- **No API keys.** `shazamio` needs none. `musicbrainzngs`/Cover Art Archive
  need only a descriptive User-Agent (already confirmed during Phase 1's
  reuse research). Never integrate AudD/ACRCloud/Discogs/Last.fm/Spotify —
  the spec requires asking first, and nothing in this phase needs them.
- **musicbrainzngs User-Agent:** set once via `mb.set_useragent("vinylyrics",
  "0.1", "https://github.com/Dakuur/vinylyrics")` in `cover_art.py` — these
  three literal values must stay in sync with `.env.example`'s
  `VINYLYRICS_USER_AGENT="vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)"`
  from Phase 1 (that env var is consumed by LRCLIB in a later phase, which
  wants one combined string; MusicBrainz's client wants three separate
  fields, so this phase hardcodes the same values rather than parsing the
  env var apart — a comment in the code should say so).
- **A "failure" that triggers retry+backoff is a network/API exception —
  NOT a clean "no match" response.** Shazam responding successfully but
  finding nothing does not mean "try again," it means "this fragment isn't
  in Shazam's database" — retrying identical audio against the same service
  would just waste a call. Only `client.recognize()` *raising* counts
  toward the 3-attempt limit.
- **The disk cache is keyed by a hash of the actual audio bytes sent to
  Shazam** (the WAV-encoded fragment), not by track title or any recognized
  metadata — the point is to avoid re-querying Shazam for a fragment
  captured at the same buffer position, before you know what's in it.
- **`CallCadencePolicy` does no I/O and calls nothing.** It only tracks
  timestamps and a locked/in-flight flag and answers "should I call now?" —
  wiring it to an actual `AudioSource`/`Recognizer` loop is later-phase
  orchestration work, out of scope here (see Roadmap Context).
- **Cover art lookup assumes clean, already-Shazam-identified artist/title
  strings, not raw/unverified input.** MusicBrainz's fuzzy search can match
  garbage input against unrelated recordings (verified during planning —
  feeding it a nonsense string still returned a "confident" 100/100-scored
  false match on an embedded number). A `MIN_SEARCH_SCORE = 90` filter is a
  cheap safety net, not a guarantee; it's acceptable because in real use
  this function is only ever called with a title/artist Shazam already
  confirmed, not arbitrary text.
- **`docs/REUSE.md` gets `shazamio` retroactively (it was added mid-session
  without being logged there — a process gap this plan closes) plus
  `musicbrainzngs` and `requests` as they're introduced — Task 6, not
  batched to the end.**
- Every module and function in this plan was hand-verified by actually
  running it before the plan was written: `ShazamIORecognizer` against
  both a fake injectable client (9 offline tests covering retry/backoff/
  cache logic) and the real `shazamio` client against a real song (one
  `@pytest.mark.network` test, passed); `find_cover_url` against both mocked
  MusicBrainz/CAA responses (6 offline tests) and the real APIs (found the
  correct release + cover for "Bonito" / "Jarabe de Palo" via ISRC lookup,
  via fuzzy fallback, and via an album-name hint); `recognize_with_cover_art`
  composing the two correctly (3 tests). 26 new tests total, all passing
  together in one sandbox run before this plan was written down.

---

## Roadmap Context

This is the next phase after Phase 4 (audio sources + silence detector,
merged). Per the spec's "Orden de trabajo," it's step 5: "Reconocimiento,
contra un fragmento suelto primero" — this plan builds the module and
proves it works against loose fragments (offline unit tests plus real
network tests against real songs and the vinylized `dry.wav`), but does
**not** wire `CallCadencePolicy` + `ShazamIORecognizer` + `AudioSource` +
`CircularAudioBuffer` into one running loop — that's the sliding-window
orchestration the spec's §2 "cada 2s sobre los últimos 12s" describes, and
it belongs with whatever later phase builds the actual runtime engine (the
spec's step 6 "Reloj + letras" is the natural place, since the clock is
what actually needs continuous anchors). Building that loop now, before the
clock exists to consume its output, would mean designing it twice.

Also carried forward for the **sixth** time: spec §10's `justfile`/
`Makefile` still has no owning phase. This plan does not claim it either —
if Phase 6's plan doesn't, that's the point to stop deferring and ask
directly instead of writing this sentence again.

---

## Task 1: `RecognitionResult` + `Recognizer` protocol (`recognition/base.py`)

**Files:**
- Create: `vinylyrics/recognition/base.py`
- Test: `tests/recognition/test_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) class RecognitionResult`: `title: str`,
    `artist: str`, `album: str | None`, `cover_url: str | None`,
    `offset: float | None`, `timeskew: float | None`,
    `frequencyskew: float | None`, `isrc: str | None`.
  - `class Recognizer(Protocol)`: `async def recognize(self, audio: np.ndarray, sample_rate: int) -> RecognitionResult | None`.
  - Task 4 (`shazam.py`) implements `Recognizer` and returns
    `RecognitionResult` instances built from these exact fields. Task 6
    (`enrich.py`) type-hints against `Recognizer` and reads/replaces
    `RecognitionResult.cover_url`/`.artist`/`.title`/`.album`/`.isrc`.

- [ ] **Step 1: Write the failing test**

```python
# tests/recognition/test_base.py
import dataclasses

import pytest

from vinylyrics.recognition.base import RecognitionResult


def test_recognition_result_is_frozen_and_has_expected_fields():
    result = RecognitionResult(
        title="t", artist="a", album=None, cover_url=None,
        offset=None, timeskew=None, frequencyskew=None, isrc=None,
    )
    assert result.title == "t"
    assert result.artist == "a"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.title = "x"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/recognition/test_base.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.recognition'`
(this is the first file in a new package — create
`vinylyrics/recognition/__init__.py` and `tests/recognition/__init__.py`
as empty files too, in this step)

- [ ] **Step 3: Implement `base.py`**

```python
# vinylyrics/recognition/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class RecognitionResult:
    title: str
    artist: str
    album: "str | None"
    cover_url: "str | None"
    offset: "float | None"
    timeskew: "float | None"
    frequencyskew: "float | None"
    isrc: "str | None"


class Recognizer(Protocol):
    async def recognize(self, audio: np.ndarray, sample_rate: int) -> "RecognitionResult | None": ...
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/recognition/test_base.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/recognition/__init__.py vinylyrics/recognition/base.py tests/recognition/__init__.py tests/recognition/test_base.py
git commit -m "feat: add RecognitionResult and Recognizer protocol"
```

---

## Task 2: Disk cache keyed by audio hash (`recognition/cache.py`)

**Files:**
- Create: `vinylyrics/recognition/cache.py`
- Test: `tests/recognition/test_cache.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `def hash_audio(wav_bytes: bytes) -> str`,
  `class DiskRecognitionCache`: `__init__(self, cache_dir: Path)`,
  `def get(self, audio_hash: str) -> dict | None`,
  `def set(self, audio_hash: str, response: dict) -> None`. Task 4
  (`shazam.py`) hashes the WAV bytes it's about to send to Shazam and
  checks/populates this cache with the *raw* Shazam response dict (not a
  parsed `RecognitionResult` — caching the raw dict means a later change to
  `_parse_response` doesn't invalidate old cache entries).

- [ ] **Step 1: Write the failing tests**

```python
# tests/recognition/test_cache.py
from pathlib import Path

from vinylyrics.recognition.cache import DiskRecognitionCache, hash_audio


def test_hash_audio_is_deterministic_and_sensitive_to_content():
    a = b"hello world"
    b = b"hello world"
    c = b"different"
    assert hash_audio(a) == hash_audio(b)
    assert hash_audio(a) != hash_audio(c)


def test_cache_roundtrip(tmp_path: Path):
    cache = DiskRecognitionCache(tmp_path / "cache")
    audio_hash = hash_audio(b"fragment")
    assert cache.get(audio_hash) is None

    cache.set(audio_hash, {"track": {"title": "Foo"}})
    assert cache.get(audio_hash) == {"track": {"title": "Foo"}}


def test_cache_creates_directory_if_missing(tmp_path: Path):
    cache_dir = tmp_path / "nested" / "cache"
    assert not cache_dir.exists()
    DiskRecognitionCache(cache_dir)
    assert cache_dir.exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/recognition/test_cache.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.recognition.cache'`

- [ ] **Step 3: Implement `cache.py`**

```python
# vinylyrics/recognition/cache.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_audio(wav_bytes: bytes) -> str:
    return hashlib.sha256(wav_bytes).hexdigest()


class DiskRecognitionCache:
    def __init__(self, cache_dir: Path):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, audio_hash: str) -> Path:
        return self._cache_dir / f"{audio_hash}.json"

    def get(self, audio_hash: str) -> "dict | None":
        path = self._path_for(audio_hash)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def set(self, audio_hash: str, response: dict) -> None:
        path = self._path_for(audio_hash)
        path.write_text(json.dumps(response))
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/recognition/test_cache.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/recognition/cache.py tests/recognition/test_cache.py
git commit -m "feat: add disk cache for recognition responses keyed by audio hash"
```

---

## Task 3: Call cadence policy (`recognition/cadence.py`)

**Files:**
- Create: `vinylyrics/recognition/cadence.py`
- Test: `tests/recognition/test_cadence.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `@dataclass(frozen=True) class CadenceConfig`:
  `min_interval_sec: float = 8.0`, `resync_interval_sec: float = 45.0`.
  `class CallCadencePolicy`: `__init__(self, config: CadenceConfig = CadenceConfig())`,
  `def on_track_gap(self) -> None`, `def set_locked(self, locked: bool) -> None`,
  `@property def in_flight -> bool`, `def should_call(self, now: float) -> bool`,
  `def mark_call_started(self, now: float) -> None`, `def mark_call_finished(self) -> None`.
  A later phase's orchestration loop (not this one) calls `should_call(time.monotonic())`
  before invoking a `Recognizer`, then `mark_call_started`/`mark_call_finished`
  around the actual call, and `on_track_gap()`/`set_locked()` in response to
  VAD events (Phase 4) and clock-lock state (a later phase).

**Design note:** this is a pure state machine with no I/O, deliberately —
it's tested with plain float timestamps, not real wall-clock waits, the
same way Phase 4's `SilenceDetector` is tested with synthetic dBFS values
instead of real audio.

- [ ] **Step 1: Write the failing tests**

```python
# tests/recognition/test_cadence.py
from vinylyrics.recognition.cadence import CadenceConfig, CallCadencePolicy


def test_allows_first_call_immediately():
    policy = CallCadencePolicy()
    assert policy.should_call(now=0.0) is True


def test_blocks_second_call_before_min_interval():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0, resync_interval_sec=45.0))
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()
    assert policy.should_call(now=5.0) is False
    assert policy.should_call(now=8.0) is True


def test_never_two_simultaneous_calls():
    policy = CallCadencePolicy()
    policy.mark_call_started(now=0.0)
    assert policy.in_flight is True
    assert policy.should_call(now=100.0) is False
    policy.mark_call_finished()
    assert policy.in_flight is False


def test_track_gap_forces_immediate_call_allowed():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0))
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()
    assert policy.should_call(now=1.0) is False
    policy.on_track_gap()
    assert policy.should_call(now=1.0) is True


def test_locked_state_uses_resync_interval():
    policy = CallCadencePolicy(CadenceConfig(min_interval_sec=8.0, resync_interval_sec=45.0))
    policy.set_locked(True)
    policy.mark_call_started(now=0.0)
    policy.mark_call_finished()
    assert policy.should_call(now=10.0) is False
    assert policy.should_call(now=45.0) is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/recognition/test_cadence.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.recognition.cadence'`

- [ ] **Step 3: Implement `cadence.py`**

```python
# vinylyrics/recognition/cadence.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CadenceConfig:
    min_interval_sec: float = 8.0
    resync_interval_sec: float = 45.0


class CallCadencePolicy:
    def __init__(self, config: CadenceConfig = CadenceConfig()):
        self._config = config
        self._last_call_at: "float | None" = None
        self._locked = False
        self._in_flight = False

    def on_track_gap(self) -> None:
        self._last_call_at = None

    def set_locked(self, locked: bool) -> None:
        self._locked = locked

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    def should_call(self, now: float) -> bool:
        if self._in_flight:
            return False
        if self._last_call_at is None:
            return True
        interval = self._config.resync_interval_sec if self._locked else self._config.min_interval_sec
        return (now - self._last_call_at) >= interval

    def mark_call_started(self, now: float) -> None:
        self._in_flight = True
        self._last_call_at = now

    def mark_call_finished(self) -> None:
        self._in_flight = False
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/recognition/test_cadence.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/recognition/cadence.py tests/recognition/test_cadence.py
git commit -m "feat: add recognition call cadence policy"
```

---

## Task 4: `ShazamIORecognizer` (`recognition/shazam.py`)

**Files:**
- Create: `vinylyrics/recognition/shazam.py`
- Test: `tests/recognition/test_shazam.py`
- Test: `tests/recognition/test_shazam_network.py`

**Interfaces:**
- Consumes: `RecognitionResult` (Task 1), `DiskRecognitionCache`/`hash_audio`
  (Task 2).
- Produces: `class ShazamIORecognizer` implementing `Recognizer`:
  `__init__(self, cache: DiskRecognitionCache | None = None, client=None, max_retries: int = 3, backoff_base_sec: float = 1.0)`,
  `async def recognize(self, audio: np.ndarray, sample_rate: int) -> RecognitionResult | None`.
  The `client` parameter exists so tests can inject a fake object with an
  async `recognize(bytes) -> dict` method — production code leaves it
  `None` and a real `shazamio.Shazam()` is constructed lazily on first use.
  Task 6 (`enrich.py`) type-hints against `Recognizer`, not this concrete
  class, so it works with the fake client in tests too.

**Verified during planning:** ran all 9 offline tests (retry-on-exception,
no-retry-on-clean-no-match, gives up after `max_retries` exhausted,
cache-hit skips the client entirely, unmatched responses are never
cached) against this exact implementation with a fake injectable client —
all passed. Separately ran the real `shazamio.Shazam()` client (no fake)
against a real 12s fragment of a real song from `/home/dakur/Downloads/songs`
and got a correct match in ~0.5s including `isrc`, confirming the real
client's response shape matches what `_parse_response` expects — this is
the one `@pytest.mark.network` test in this task.

- [ ] **Step 1: Write the failing offline tests**

```python
# tests/recognition/test_shazam.py
import asyncio
from pathlib import Path

import numpy as np
import pytest

from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.cache import DiskRecognitionCache
from vinylyrics.recognition.shazam import ShazamIORecognizer, _extract_album, _parse_response


FAKE_RESPONSE = {
    "matches": [{"id": "1", "offset": 12.5, "timeskew": 0.001, "frequencyskew": -0.0005}],
    "track": {
        "title": "Test Song",
        "subtitle": "Test Artist",
        "isrc": "US1234567890",
        "images": {"coverart": "https://example.com/cover.jpg"},
        "sections": [
            {"type": "SONG", "metadata": [{"title": "Album", "text": "Test Album"}, {"title": "Label", "text": "X"}]},
            {"type": "RELATED"},
        ],
    },
}

UNMATCHED_RESPONSE = {"matches": [], "location": {}, "timestamp": 0}


def test_parse_response_extracts_all_fields():
    result = _parse_response(FAKE_RESPONSE)
    assert result == RecognitionResult(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        cover_url="https://example.com/cover.jpg",
        offset=12.5,
        timeskew=0.001,
        frequencyskew=-0.0005,
        isrc="US1234567890",
    )


def test_parse_response_returns_none_when_no_track():
    assert _parse_response(UNMATCHED_RESPONSE) is None


def test_extract_album_returns_none_when_no_song_section():
    assert _extract_album({"sections": [{"type": "RELATED"}]}) is None


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def recognize(self, data: bytes) -> dict:
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _run(coro):
    return asyncio.run(coro)


def test_recognize_returns_parsed_result_on_success():
    client = _FakeClient([FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(client=client)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result.title == "Test Song"
    assert client.calls == 1


def test_recognize_returns_none_on_unmatched_response_without_retrying():
    client = _FakeClient([UNMATCHED_RESPONSE])
    recognizer = ShazamIORecognizer(client=client)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result is None
    assert client.calls == 1  # no retry on a clean "no match" response


def test_recognize_retries_on_exception_then_succeeds():
    client = _FakeClient([ConnectionError("boom"), FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(client=client, backoff_base_sec=0.001)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result.title == "Test Song"
    assert client.calls == 2


def test_recognize_returns_none_after_max_retries_all_failing():
    client = _FakeClient([ConnectionError("a"), ConnectionError("b"), ConnectionError("c")])
    recognizer = ShazamIORecognizer(client=client, max_retries=3, backoff_base_sec=0.001)
    audio = np.zeros(16000, dtype=np.float32)

    result = _run(recognizer.recognize(audio, 16000))

    assert result is None
    assert client.calls == 3


def test_recognize_uses_cache_and_skips_client_on_hit(tmp_path: Path):
    cache = DiskRecognitionCache(tmp_path / "cache")
    client = _FakeClient([FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(cache=cache, client=client)
    audio = np.zeros(16000, dtype=np.float32)

    first = _run(recognizer.recognize(audio, 16000))
    assert client.calls == 1

    second = _run(recognizer.recognize(audio, 16000))
    assert client.calls == 1  # cache hit, client not called again
    assert second == first


def test_recognize_does_not_cache_unmatched_responses(tmp_path: Path):
    cache = DiskRecognitionCache(tmp_path / "cache")
    client = _FakeClient([UNMATCHED_RESPONSE, FAKE_RESPONSE])
    recognizer = ShazamIORecognizer(cache=cache, client=client)
    audio = np.zeros(16000, dtype=np.float32)

    first = _run(recognizer.recognize(audio, 16000))
    assert first is None
    assert client.calls == 1

    second = _run(recognizer.recognize(audio, 16000))
    assert second.title == "Test Song"
    assert client.calls == 2  # not served from cache, since nothing was cached
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/recognition/test_shazam.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.recognition.shazam'`

- [ ] **Step 3: Implement `shazam.py`**

```python
# vinylyrics/recognition/shazam.py
from __future__ import annotations

import asyncio
import io

import numpy as np
import soundfile as sf

from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.cache import DiskRecognitionCache, hash_audio


def _to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV")
    return buffer.getvalue()


def _extract_album(track: dict) -> "str | None":
    for section in track.get("sections", []):
        if section.get("type") != "SONG":
            continue
        for meta in section.get("metadata", []):
            if meta.get("title") == "Album":
                return meta.get("text")
    return None


def _parse_response(response: dict) -> "RecognitionResult | None":
    track = response.get("track")
    if not track:
        return None
    matches = response.get("matches", [])
    match = matches[0] if matches else {}
    return RecognitionResult(
        title=track.get("title", ""),
        artist=track.get("subtitle", ""),
        album=_extract_album(track),
        cover_url=track.get("images", {}).get("coverart"),
        offset=match.get("offset"),
        timeskew=match.get("timeskew"),
        frequencyskew=match.get("frequencyskew"),
        isrc=track.get("isrc"),
    )


class ShazamIORecognizer:
    def __init__(
        self,
        cache: "DiskRecognitionCache | None" = None,
        client=None,
        max_retries: int = 3,
        backoff_base_sec: float = 1.0,
    ):
        self._cache = cache
        self._client = client
        self._max_retries = max_retries
        self._backoff_base_sec = backoff_base_sec

    async def _get_client(self):
        if self._client is None:
            from shazamio import Shazam

            self._client = Shazam()
        return self._client

    async def recognize(self, audio: np.ndarray, sample_rate: int) -> "RecognitionResult | None":
        wav_bytes = _to_wav_bytes(audio, sample_rate)
        audio_hash = hash_audio(wav_bytes)

        if self._cache is not None:
            cached = self._cache.get(audio_hash)
            if cached is not None:
                return _parse_response(cached)

        client = await self._get_client()

        for attempt in range(self._max_retries):
            try:
                response = await client.recognize(wav_bytes)
            except Exception:
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._backoff_base_sec * (2**attempt))
                    continue
                return None
            else:
                if self._cache is not None and response.get("track"):
                    self._cache.set(audio_hash, response)
                return _parse_response(response)

        return None
```

- [ ] **Step 4: Run to verify the offline tests pass**

Run: `uv run pytest tests/recognition/test_shazam.py -v`
Expected: `9 passed`

- [ ] **Step 5: Write the network test**

```python
# tests/recognition/test_shazam_network.py
import asyncio
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from vinylyrics.recognition.shazam import ShazamIORecognizer


@pytest.mark.network
def test_recognize_identifies_a_real_track():
    path = Path("/home/dakur/Downloads/songs/Bonito.mp3")
    info = sf.info(path)
    sr = info.samplerate
    audio, _ = sf.read(path, dtype="float32", always_2d=True, start=int(30 * sr), frames=int(12 * sr))
    mono = audio.mean(axis=1).astype(np.float32)

    recognizer = ShazamIORecognizer()
    result = asyncio.run(recognizer.recognize(mono, sr))

    assert result is not None
    assert "bonito" in result.title.lower()
    assert "jarabe" in result.artist.lower()
    assert result.offset is not None
    assert result.isrc is not None
```

- [ ] **Step 6: Run the network test**

Run: `uv run pytest tests/recognition/test_shazam_network.py -v -m network`
Expected: `1 passed` (needs internet access; this is the one test in this
task that does — the default `uv run pytest -v` run excludes it via
`pyproject.toml`'s `-m "not network"` addopts, same as every other network
test in this project)

- [ ] **Step 7: Commit**

```bash
git add vinylyrics/recognition/shazam.py tests/recognition/test_shazam.py tests/recognition/test_shazam_network.py
git commit -m "feat: add ShazamIORecognizer with retry/backoff and disk cache"
```

---

## Task 5: Cover art via MusicBrainz + Cover Art Archive (`recognition/cover_art.py`)

**Files:**
- Modify: `pyproject.toml` (add `musicbrainzngs>=0.7` and `requests>=2.32` to `dependencies`)
- Create: `vinylyrics/recognition/cover_art.py`
- Test: `tests/recognition/test_cover_art.py`
- Test: `tests/recognition/test_cover_art_network.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-4 (works with plain `str` arguments, not
  `RecognitionResult` directly — kept decoupled so it's independently
  testable and reusable).
- Produces: `def find_cover_url(artist: str, title: str, album: str | None = None, isrc: str | None = None) -> str | None`,
  `async def find_cover_url_async(artist: str, title: str, album: str | None = None, isrc: str | None = None) -> str | None`.
  Task 6 (`enrich.py`) calls `find_cover_url_async` with fields taken from
  a `RecognitionResult` (Task 1).

**Verified during planning:** ISRC lookup (`mb.get_recordings_by_isrc`) is
tried first when an ISRC is available — confirmed it can 404 for real,
non-obscure-but-not-catalogued tracks (verified with a real ISRC from a
real Shazam response), which is why the fallback to fuzzy
`search_recordings` (artist+title, optionally narrowed by `release=album`)
exists and was independently exercised too — including finding a
*different, more precise* release when an album hint was added. The
`MIN_SEARCH_SCORE = 90` filter was added after observing MusicBrainz's
fuzzy search return a 100/100-scored false match against a deliberately
nonsensical query (it matched on an embedded number) — documented as a
known, acceptable limitation in Global Constraints, not something this
task tries to fully solve. Cover Art Archive's `/release/{mbid}/front`
endpoint was confirmed to 307-redirect to a real image when art exists and
404 when it doesn't — `find_cover_url` returns the stable CAA URL itself
(not the redirect target), which is what a consumer should embed and let
resolve. All 6 offline tests (mocked MusicBrainz/CAA) and one real network
test (found the correct cover for "Bonito"/"Jarabe de Palo" via the real
APIs) passed.

- [ ] **Step 1: Add the `musicbrainzngs` and `requests` dependencies**

```toml
dependencies = [
    "mutagen>=1.48",
    "python-dotenv>=1.0",
    "numpy>=1.26",
    "pedalboard>=0.9",
    "soundfile>=0.13",
    "shazamio>=0.8.1",
    "scipy>=1.11",
    "sounddevice>=0.5",
    "musicbrainzngs>=0.7",
    "requests>=2.32",
]
```

Run: `uv sync` — confirm both install with no errors.

- [ ] **Step 2: Write the failing offline tests**

```python
# tests/recognition/test_cover_art.py
from unittest import mock

from vinylyrics.recognition import cover_art


def _fake_head_response(status_code: int):
    resp = mock.MagicMock()
    resp.status_code = status_code
    return resp


def test_find_cover_url_uses_isrc_when_available():
    isrc_result = {"isrc": {"recording-list": [{"release-list": [{"id": "mbid-from-isrc"}]}]}}
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", return_value=isrc_result) as isrc_mock, \
         mock.patch.object(cover_art.mb, "search_recordings") as search_mock, \
         mock.patch.object(cover_art.requests, "head", return_value=_fake_head_response(200)):
        url = cover_art.find_cover_url("Artist", "Title", isrc="US1234567890")

    isrc_mock.assert_called_once()
    search_mock.assert_not_called()
    assert url == "https://coverartarchive.org/release/mbid-from-isrc/front"


def test_find_cover_url_falls_back_to_search_when_isrc_lookup_fails():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(
             cover_art.mb, "search_recordings",
             return_value={"recording-list": [{"ext:score": "95", "release-list": [{"id": "mbid-from-search"}]}]},
         ) as search_mock, \
         mock.patch.object(cover_art.requests, "head", return_value=_fake_head_response(200)):
        url = cover_art.find_cover_url("Artist", "Title", isrc="US1234567890")

    search_mock.assert_called_once()
    assert url == "https://coverartarchive.org/release/mbid-from-search/front"


def test_find_cover_url_skips_low_score_search_results():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(
             cover_art.mb, "search_recordings",
             return_value={"recording-list": [{"ext:score": "40", "release-list": [{"id": "low-score-mbid"}]}]},
         ), \
         mock.patch.object(cover_art.requests, "head") as head_mock:
        url = cover_art.find_cover_url("Artist", "Title")

    head_mock.assert_not_called()
    assert url is None


def test_find_cover_url_tries_next_mbid_when_first_has_no_cover_art():
    search_result = {
        "recording-list": [
            {"ext:score": "95", "release-list": [{"id": "mbid-no-art"}, {"id": "mbid-with-art"}]},
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result), \
         mock.patch.object(cover_art.requests, "head", side_effect=[_fake_head_response(404), _fake_head_response(200)]):
        url = cover_art.find_cover_url("Artist", "Title")

    assert url == "https://coverartarchive.org/release/mbid-with-art/front"


def test_find_cover_url_returns_none_when_nothing_found():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value={"recording-list": []}), \
         mock.patch.object(cover_art.requests, "head") as head_mock:
        url = cover_art.find_cover_url("Artist", "Title")

    head_mock.assert_not_called()
    assert url is None


def test_find_cover_url_handles_network_error_gracefully():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(
             cover_art.mb, "search_recordings",
             return_value={"recording-list": [{"ext:score": "95", "release-list": [{"id": "some-mbid"}]}]},
         ), \
         mock.patch.object(cover_art.requests, "head", side_effect=cover_art.requests.RequestException("timeout")):
        url = cover_art.find_cover_url("Artist", "Title")

    assert url is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/recognition/test_cover_art.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.recognition.cover_art'`

- [ ] **Step 4: Implement `cover_art.py`**

```python
# vinylyrics/recognition/cover_art.py
from __future__ import annotations

import asyncio

import musicbrainzngs as mb
import requests

# Must stay in sync with .env.example's VINYLYRICS_USER_AGENT
# ("vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)") — MusicBrainz's
# client wants app/version/contact as three separate fields rather than one
# combined string, so this hardcodes the same values instead of parsing the
# env var apart.
mb.set_useragent("vinylyrics", "0.1", "https://github.com/Dakuur/vinylyrics")

CAA_TIMEOUT_SEC = 5.0
MIN_SEARCH_SCORE = 90


def _mbids_from_isrc(isrc: str) -> list[str]:
    try:
        result = mb.get_recordings_by_isrc(isrc, includes=["releases"])
    except mb.MusicBrainzError:
        return []
    mbids = []
    for rec in result.get("isrc", {}).get("recording-list", []):
        for rel in rec.get("release-list", []):
            mbids.append(rel["id"])
    return mbids


def _mbids_from_search(artist: str, title: str, album: "str | None" = None) -> list[str]:
    search_kwargs = {"recording": title, "artist": artist, "limit": 10}
    if album:
        search_kwargs["release"] = album
    try:
        result = mb.search_recordings(**search_kwargs)
    except mb.MusicBrainzError:
        return []
    mbids = []
    for rec in result.get("recording-list", []):
        score = int(rec.get("ext:score", 0))
        if score < MIN_SEARCH_SCORE:
            continue
        for rel in rec.get("release-list", []):
            mbids.append(rel["id"])
    return mbids


def _caa_front_url_if_exists(mbid: str) -> "str | None":
    url = f"https://coverartarchive.org/release/{mbid}/front"
    try:
        response = requests.head(url, allow_redirects=True, timeout=CAA_TIMEOUT_SEC)
    except requests.RequestException:
        return None
    return url if response.status_code == 200 else None


def find_cover_url(artist: str, title: str, album: "str | None" = None, isrc: "str | None" = None) -> "str | None":
    mbids = []
    if isrc:
        mbids.extend(_mbids_from_isrc(isrc))
    if not mbids:
        mbids.extend(_mbids_from_search(artist, title, album))

    for mbid in mbids:
        url = _caa_front_url_if_exists(mbid)
        if url is not None:
            return url
    return None


async def find_cover_url_async(
    artist: str, title: str, album: "str | None" = None, isrc: "str | None" = None
) -> "str | None":
    return await asyncio.to_thread(find_cover_url, artist, title, album, isrc)
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/recognition/test_cover_art.py -v`
Expected: `6 passed`

- [ ] **Step 6: Write and run the network test**

```python
# tests/recognition/test_cover_art_network.py
import pytest

from vinylyrics.recognition.cover_art import find_cover_url


@pytest.mark.network
def test_find_cover_url_finds_a_real_release():
    url = find_cover_url("Jarabe de Palo", "Bonito", isrc="ES96A0800012")
    assert url is not None
    assert url.startswith("https://coverartarchive.org/release/")
```

Run: `uv run pytest tests/recognition/test_cover_art_network.py -v -m network`
Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/recognition/cover_art.py tests/recognition/test_cover_art.py tests/recognition/test_cover_art_network.py
git commit -m "feat: add MusicBrainz + Cover Art Archive cover lookup"
```

---

## Task 6: Compose recognition + cover art, retroactive REUSE.md, and a real smoke test (`recognition/enrich.py`)

**Files:**
- Create: `vinylyrics/recognition/enrich.py`
- Test: `tests/recognition/test_enrich.py`
- Modify: `docs/REUSE.md` (add `shazamio` retroactively, plus `musicbrainzngs` and `requests`)
- Modify: `scripts/try_recognize.py` (use the real module instead of raw `shazamio`)

**Interfaces:**
- Consumes: `Recognizer`, `RecognitionResult` (Task 1), `find_cover_url_async`
  (Task 5).
- Produces: `async def recognize_with_cover_art(recognizer: Recognizer, audio: np.ndarray, sample_rate: int) -> RecognitionResult | None`
  — this is the function a later phase's orchestration loop actually calls,
  not `ShazamIORecognizer.recognize()` directly, since it's the one that
  applies the spec's "MusicBrainz/CAA cover preferred, Shazam's as fallback"
  rule.

**Verified during planning:** all 3 tests below passed against this exact
implementation, using a fake `Recognizer` and a mocked
`find_cover_url_async` (patched at `vinylyrics.recognition.enrich.find_cover_url_async`,
not at its definition site, since that's where `enrich.py` looks it up).

- [ ] **Step 1: Write the failing tests**

```python
# tests/recognition/test_enrich.py
import asyncio
from unittest import mock

import numpy as np

from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.enrich import recognize_with_cover_art


class _FakeRecognizer:
    def __init__(self, result):
        self._result = result

    async def recognize(self, audio, sample_rate):
        return self._result


def _run(coro):
    return asyncio.run(coro)


def test_enrich_replaces_cover_with_musicbrainz_when_found():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value="https://coverartarchive.org/release/x/front"),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.cover_url == "https://coverartarchive.org/release/x/front"
    assert result.title == "Song"  # unchanged


def test_enrich_falls_back_to_shazam_cover_when_musicbrainz_finds_nothing():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value=None),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.cover_url == "shazam-cover"


def test_enrich_returns_none_when_recognition_fails():
    recognizer = _FakeRecognizer(None)
    result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))
    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/recognition/test_enrich.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.recognition.enrich'`

- [ ] **Step 3: Implement `enrich.py`**

```python
# vinylyrics/recognition/enrich.py
from __future__ import annotations

from dataclasses import replace

import numpy as np

from vinylyrics.recognition.base import RecognitionResult, Recognizer
from vinylyrics.recognition.cover_art import find_cover_url_async


async def recognize_with_cover_art(
    recognizer: Recognizer, audio: np.ndarray, sample_rate: int
) -> "RecognitionResult | None":
    result = await recognizer.recognize(audio, sample_rate)
    if result is None:
        return None

    better_cover = await find_cover_url_async(result.artist, result.title, result.album, result.isrc)
    if better_cover:
        return replace(result, cover_url=better_cover)
    return result
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/recognition/test_enrich.py -v`
Expected: `3 passed`

- [ ] **Step 5: Run the full offline suite**

Run: `uv run pytest -v`
Expected: all tests pass — Phases 1/2/4's 74, plus this phase's Task 1 (1)
+ Task 2 (3) + Task 3 (5) + Task 4 (9 offline) + Task 5 (6 offline) +
Task 6 (3) = 101 total offline. The 2 network tests (Task 4, Task 5) are
excluded by default and run separately with `-m network`.

- [ ] **Step 6: Update `docs/REUSE.md`**

Read the existing file first (it has rows for `mutagen`, `python-dotenv`,
`pytest`, `hatchling`, `numpy`, `pedalboard`, `soundfile` already). Add
three more rows matching its format:
- **shazamio** — MIT. The Shazam recognition client (unofficial API — the
  spec explicitly notes this). Added earlier this session for a throwaway
  manual smoke-test script (`scripts/try_recognize.py`) without being
  logged here at the time; this phase is where it becomes a real,
  load-bearing dependency (`ShazamIORecognizer`), so it's documented now.
- **musicbrainzngs** — BSD 2-Clause. Looks up a track's MusicBrainz release
  (by ISRC first, fuzzy artist/title/album search as fallback) to find a
  release ID for Cover Art Archive.
- **requests** — Apache-2.0. A single `HEAD` request per Cover Art Archive
  candidate to confirm cover art exists before returning its URL.

- [ ] **Step 7: Replace `scripts/try_recognize.py` with the real module**

This throwaway script currently constructs `shazamio.Shazam()` directly and
hand-parses its raw response. Replace its entire content with this — it
keeps the same CLI (`audio_file`, `--offset`, `--duration`) but now goes
through `ShazamIORecognizer` (backed by a `DiskRecognitionCache` at
`shazam_cache/`, already gitignored since Phase 1) composed with
`recognize_with_cover_art`:

```python
#!/usr/bin/env python3
"""Prueba manual: reconoce un fragmento de audio con el módulo real de la
Fase 5 (ShazamIORecognizer + caché en disco + portada vía MusicBrainz/Cover
Art Archive) y mide cuánto tarda.

Uso:
    uv run scripts/try_recognize.py "/home/dakur/Downloads/songs/Bonito.mp3"
    uv run scripts/try_recognize.py data/vinylizer_smoke/dry.wav --offset 5 --duration 12
"""
from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from vinylyrics.recognition.cache import DiskRecognitionCache
from vinylyrics.recognition.enrich import recognize_with_cover_art
from vinylyrics.recognition.shazam import ShazamIORecognizer


def extract_clip(path: Path, offset: float, duration: float) -> tuple[np.ndarray, int]:
    info = sf.info(path)
    sr = info.samplerate
    audio, _ = sf.read(
        path, dtype="float32", always_2d=True,
        start=int(offset * sr), frames=int(duration * sr),
    )
    if len(audio) == 0:
        raise ValueError(f"El offset {offset}s está más allá del final de {path.name} ({info.duration:.1f}s)")
    return audio.mean(axis=1).astype(np.float32), sr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_file", help="Ruta a un .mp3 o .wav")
    parser.add_argument("--offset", type=float, default=30.0, help="Segundo de inicio del fragmento (por defecto 30s)")
    parser.add_argument("--duration", type=float, default=12.0, help="Duración del fragmento en segundos (por defecto 12s, como la ventana deslizante de la Fase 4)")
    args = parser.parse_args()

    path = Path(args.audio_file)
    print(f"Extrayendo {args.duration}s desde el segundo {args.offset} de {path.name}...")
    clip, sr = extract_clip(path, args.offset, args.duration)

    print("Enviando a Shazam...")
    cache = DiskRecognitionCache(Path("shazam_cache"))
    recognizer = ShazamIORecognizer(cache=cache)

    start = time.monotonic()
    result = asyncio.run(recognize_with_cover_art(recognizer, clip, sr))
    elapsed = time.monotonic() - start

    print(f"\nTiempo de reconocimiento: {elapsed:.2f}s")

    if result is None:
        print("No identificado. Prueba con otro --offset (evita intros silenciosas o habladas).")
        return 1

    print(f"Título:  {result.title}")
    print(f"Artista: {result.artist}")
    print(f"Álbum:   {result.album or '-'}")
    print(f"Portada: {result.cover_url or '-'}")
    print(f"offset={result.offset}  timeskew={result.timeskew}  frequencyskew={result.frequencyskew}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8: Run the smoke test twice to demonstrate the cache**

```bash
rm -rf shazam_cache  # start clean
uv run scripts/try_recognize.py "/home/dakur/Downloads/songs/Bonito.mp3" --offset 30
uv run scripts/try_recognize.py "/home/dakur/Downloads/songs/Bonito.mp3" --offset 30
```

Expected: the first run takes ~0.4-0.5s (a real Shazam call, same as
before) and prints title/artist/album/cover/offset info; the second run
(same file, same offset → same audio bytes → same hash) should be
noticeably faster since it's served from `shazam_cache/` without any
network call — report both elapsed times in your report. Then run once
against the vinylized WAV to confirm it still works on degraded audio:

```bash
uv run scripts/try_recognize.py data/vinylizer_smoke/dry.wav --offset 5
```

- [ ] **Step 9: Commit**

```bash
git add vinylyrics/recognition/enrich.py tests/recognition/test_enrich.py docs/REUSE.md scripts/try_recognize.py
git commit -m "feat: compose recognition with cover art lookup, wire into smoke-test script"
```

(`shazam_cache/` itself is already gitignored from Phase 1 — do not add it.)

---

## Self-Review Notes

- **Spec coverage:** §3's `Recognizer`/`ShazamIORecognizer` → Task 4. Call
  cadence (≥8s / immediate after `TRACK_GAP` / 45s resync) → Task 3
  (policy only, not wired to a real loop — see Roadmap Context for why).
  Title/artist/album/cover/`matches[0].offset/timeskew/frequencyskew` →
  Task 4's `_parse_response`. Retries with backoff, 3 failures →
  UNIDENTIFIED (`None`) → Task 4. Disk cache keyed by audio-fragment hash →
  Task 2. MusicBrainz + Cover Art Archive with Shazam fallback → Task 5 +
  Task 6. AudD/ACRCloud extension point: satisfied structurally by the
  `Recognizer` protocol (Task 1) — anything implementing
  `async recognize(audio, sample_rate) -> RecognitionResult | None` can
  substitute for `ShazamIORecognizer`, but no such implementation is built
  here and none should be without asking first, per the spec.
- **No placeholders:** every step has real, planning-verified code.
- **Type/interface consistency:** `RecognitionResult` (Task 1) is
  constructed identically by `shazam.py`'s `_parse_response` (Task 4) and
  consumed/replaced (`dataclasses.replace`) unchanged by `enrich.py`
  (Task 6). `Recognizer` (Task 1) is satisfied structurally by
  `ShazamIORecognizer` (Task 4) and by every fake/test double used in
  Tasks 4 and 6's tests — never redefined.
- **Real discoveries acted on, not hidden:** MusicBrainz ISRC lookup can
  genuinely 404 even for real tracks (shaped the isrc→fallback-search
  chain in Task 5, not an afterthought); fuzzy search can return a
  confidently-scored false match on nonsense input (shaped the
  `MIN_SEARCH_SCORE` filter and the explicit Global Constraint documenting
  its limits, rather than either ignoring the problem or over-engineering
  a fix for an input shape — arbitrary text — this function never actually
  receives in this project).
- **Carried forward again (sixth time):** spec §10's `justfile`/`Makefile`.
