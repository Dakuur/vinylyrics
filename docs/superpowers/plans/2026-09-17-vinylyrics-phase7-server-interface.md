# vinylyrics Phase 7 Implementation Plan — Server + Interface

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the live, runnable system: an orchestration engine that wires
audio capture, silence detection, Shazam recognition, the playback clock, and
the lyrics pipeline into one running loop; a FastAPI server that broadcasts
that state over a WebSocket; and a single static HTML/CSS/JS page that
renders it as a full-screen karaoke display. This is the phase that turns
five phases of standalone, tested modules into something David can actually
point a phone speaker and a laptop microphone at and watch work.

**Architecture:** `vinylyrics/engine.py`'s `Engine` reads from an
`AudioSource` in a loop, feeds a `CircularAudioBuffer`, runs
`SilenceDetector` on 100ms RMS windows, and — gated by `CallCadencePolicy` —
fires an async, non-blocking Shazam recognition against the last 12s of
buffered audio. A successful recognition updates a `PlaybackClock` anchor,
triggers a `LyricsService` fetch (needs a track duration, which Shazam's own
response never includes — confirmed by inspecting a real response live
during planning; MusicBrainz's recording search already returns one, so this
phase adds a small, separate duration lookup alongside Phase 5's existing
cover-art lookup) and a palette extraction, and updates a `PlaybackSession`
that owns the exact WebSocket JSON contract from spec §6.
`vinylyrics/server/app.py` wraps the engine in FastAPI: a `/ws` endpoint
broadcasts the session payload to every connected client on change (never
the current lyric line — the browser interpolates that itself from the
clock fields at 60fps, so a network hiccup never shows on screen), plus
`/health` and a `/debug` endpoint with the last recognition, speed estimate,
current RMS, and anchor history. `vinylyrics/web/` is one HTML page with
inline CSS/JS (no build step) implementing spec §8's karaoke rules exactly:
solid-color background from the palette, 8% safe margins, step-advance
(never continuous scroll) with a 250ms transform transition.
`vinylyrics/server/cli.py` is the actual command David runs — it wires a
`LineInSource` (default) or `FileSource` (`--file`, for testing without a
turntable), starts the engine as a background task, and serves the app with
`uvicorn` bound to `0.0.0.0`, so his phone or projector — both on the same
WiFi, neither plugged into anything — can open the page from another device.

**Tech Stack:** `Pillow` (new — dominant-color extraction from the cover
image; `colorthief`, the spec's other suggested option, hasn't been released
since 2017 and is unmaintained, confirmed via PyPI during planning, so this
plan uses Pillow's `quantize()` instead, verified against a real cover image
during planning), `fastapi` + `uvicorn` (new — the server), `httpx` (new,
dev-only — required by FastAPI's `TestClient` for the WebSocket tests in
this plan), `colorsys`/`sqlite3`-adjacent stdlib for the palette math, all
of Phases 1–6's existing modules used as libraries, not modified except
where this plan says so.

**Spec:** [docs/SPEC.md](../../SPEC.md) §6 "Servidor", §7 "Paleta", §8
"Interfaz", plus the sliding-window loop described in §2 and the anchor
model in §5 (both already built as standalone pieces; this phase is what
finally drives them with live data).

## Global Constraints

(Phases 1/2/4/5/6's constraints all still apply. This phase adds:)

- **No API keys.** Every new dependency in this phase (`Pillow`, `fastapi`,
  `uvicorn`, `httpx`) needs none. The duration lookup reuses the same
  MusicBrainz User-Agent already configured in `cover_art.py` — no new
  credential of any kind.
- **The server binds to `0.0.0.0`, never `127.0.0.1`/`localhost`.** David's
  projector has its own WiFi and browser — it and his phone connect to the
  Raspberry Pi's (or, for now, his laptop's) server over the LAN, exactly
  like any other browser tab. There is no HDMI-attached kiosk browser to
  build for the primary use case. (Recorded as a project memory from an
  earlier conversation — this plan is the first to act on it.)
- **The WebSocket sends the clock, never the current line.** Spec §6 is
  explicit: "Manda el reloj, no la línea actual." The browser's `app.js`
  must compute which lyric line is active locally, from
  `performance.now()` and the pushed `{anchor_wall, anchor_ms, speed}`
  triple, at 60fps. Pushing a pre-computed "current line" index instead
  would make any network hiccup visible as a stutter on the wall — exactly
  what this design avoids.
- **No pitch-preserving anything, no position jump — still true here.**
  This phase doesn't touch `PlaybackClock`'s math, only calls
  `add_anchor()`/`position()` from the engine loop exactly as Phase 6 built
  them.
- **A new, verified gap: Shazam's response carries no track duration.**
  Confirmed by making a real recognition call during planning and
  recursively searching the entire raw response dict for any key containing
  "duration" or "length" — there is none, anywhere, on `track` or its
  nested `sections`/`hub`/`share` objects. `LyricsService.get_lyrics()`
  requires a `duration: float` (LRCLIB's own `/search` fallback picks the
  closest-duration candidate, so a wrong or missing duration silently
  degrades lyrics matching — see Phase 6's own bugfix for what "wrong
  duration ranking" costs). MusicBrainz's `search_recordings()` /
  `get_recordings_by_isrc()` — already called by Phase 5's
  `cover_art.py` for cover art — return a `length` field in milliseconds
  on the matching recording, confirmed live during planning against the
  real API. This phase adds a **separate, additive**
  `find_track_duration`/`find_track_duration_async` pair to `cover_art.py`
  reusing its existing `_recording_matches`/`MIN_SEARCH_SCORE` filtering,
  rather than modifying the already-tested `find_cover_url` — accepting one
  extra MusicBrainz round-trip (recognition happens every 8–45s per
  `CallCadencePolicy`, not in a tight loop, so this is not a
  latency-sensitive path) in exchange for zero risk to Phase 5's tested
  code.
- **Naming note, flagged rather than silently fixed:** Phase 5's
  `recognize_with_cover_art()` gets a second job in this phase (also
  fetching duration) without a rename, to avoid rippling a name change
  through `scripts/try_recognize.py` and Phase 5's own tests for a
  cosmetic gain. If this bothers David, it's a trivial rename later.
- **Evaluation tooling (`eval`/`eval-full`, spec §9's aggregate report
  across all 47 songs) is explicitly OUT of scope for this phase.** The
  spec's own "Orden de trabajo" lists step 7 as "Servidor + interfaz" and
  step 8 as "Evaluación" separately — two different phases. This phase's
  only test of the *whole* engine is a scoped integration test using a
  `FileSource` and fakes for the recognizer/lyrics service (below); it does
  not run real Shazam calls against all 47 songs or produce the stdout/JSON
  report spec §9 describes for the project website. That is Phase 8's job.
- **The `justfile` (spec §10) is added THIS phase, ending the streak.**
  Every plan since Phase 4 has carried forward a note that this is
  unclaimed and unowned; Phase 6's plan said the next phase should either
  claim it or ask David directly rather than defer an eighth time. This
  plan claims it, with recipes for everything that has a real command
  today (`inspect`, `vinylize`, `dev` — this phase's live server —, `test`,
  `lint`) and two recipes intentionally NOT added yet (`eval`, `eval-full`)
  because the commands they'd wrap don't exist until Phase 8 — a `just
  eval` recipe pointing at a non-existent subcommand would be a broken
  placeholder, which this project's review culture treats as a defect.
  This is called out explicitly in Task 8 rather than silently omitted.
- **Palette math, hand-verified during planning, not just designed:** the
  real dominant color extracted from a live cover during planning
  (`RGB(216,0,1)`, a saturated red) was run through the exact
  clamp-then-darken pipeline below and produced a passing 12.24:1 contrast
  ratio with zero darkening steps needed. Separately, scanning all hues at
  the clamp's boundary values (`l=0.20, s=0.5` — the least-dark, most
  saturated corner the clamp allows) found a real worst case at hue 60°
  (`RGB(77,77,25)`, a dark olive) landing at exactly 7.52:1 — confirming
  the "clamp isn't always enough, keep the darken-loop" design is not
  decorative; it has real, if narrow, margin to protect.

---

## Roadmap Context

This is the next phase after Phase 6 (clock + lyrics, merged). Per the
spec's "Orden de trabajo," it's step 7: "Servidor + interfaz." Phase 6's
plan correctly deferred the sliding-window orchestration loop here, since an
engine with nothing to observe its output was hard to build or verify in
isolation — this phase gives it a server and a page to actually watch it
work end-to-end.

Phase 8 ("Evaluación," spec's step 8) is next after this: the `eval`/
`eval-full` CLI subcommands, running all 47 songs through the real pipeline,
and the aggregate stdout/JSON report spec §9 wants for the project website.

## Task 1: Track duration lookup (`recognition/cover_art.py`, `recognition/base.py`, `recognition/enrich.py`)

**Files:**
- Modify: `vinylyrics/recognition/base.py` (add `duration` field to `RecognitionResult`)
- Modify: `vinylyrics/recognition/cover_art.py` (add `find_track_duration`/`find_track_duration_async`)
- Modify: `vinylyrics/recognition/enrich.py` (call the new lookup)
- Test: `tests/recognition/test_cover_art.py` (add duration-lookup tests, same file, same mocking pattern as its existing cover-art tests)
- Test: `tests/recognition/test_enrich.py` (extend for duration)

**Interfaces:**
- Consumes: `mb` (musicbrainzngs, already imported in `cover_art.py`),
  `_recording_matches`/`MIN_SEARCH_SCORE` (already defined there).
- Produces:
  - `RecognitionResult.duration: "float | None" = None` (new field, default
    keeps every existing Phase 5 test's keyword-only construction working
    unchanged).
  - `def find_track_duration(artist: str, title: str, isrc: "str | None" = None) -> "float | None"`
  - `def find_track_duration_async(artist: str, title: str, isrc: "str | None" = None) -> "float | None"` (async wrapper via `asyncio.to_thread`, matching `find_cover_url_async`'s existing pattern exactly)
  - `recognize_with_cover_art()` (unchanged name — see Global Constraints)
    now also populates `duration` on its returned `RecognitionResult`.
    Task 5 (the engine) calls this one function to get title/artist/album/
    cover/duration all in one await.

**Verified during planning:** made a real Shazam recognition call against
`Bonito.mp3` and recursively searched the entire raw response dict for any
key containing "duration" or "length" — none exists anywhere in the
response (checked `track`'s top-level keys and every nested object).
Separately, ran `musicbrainzngs.search_recordings(recording="Bonito",
artist="Jarabe de Palo")` live and confirmed each returned recording dict
has a `length` key in milliseconds (`211000`, `271000`, etc.) — this is
the field this task extracts.

- [ ] **Step 1: Add the `duration` field**

In `vinylyrics/recognition/base.py`, add one field to the frozen dataclass:

```python
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
    duration: "float | None" = None
```

- [ ] **Step 2: Write the failing tests for `find_track_duration`**

Add to `tests/recognition/test_cover_art.py` (same file — it already
imports `cover_art` and `mock`, and already has a `_fake_head_response`
helper you don't need for these):

```python
def test_find_track_duration_uses_isrc_when_available():
    isrc_result = {"isrc": {"recording-list": [{"length": "238000"}]}}
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", return_value=isrc_result) as isrc_mock, \
         mock.patch.object(cover_art.mb, "search_recordings") as search_mock:
        duration = cover_art.find_track_duration("Artist", "Title", isrc="ISRC1")

    assert duration == 238.0
    isrc_mock.assert_called_once()
    search_mock.assert_not_called()


def test_find_track_duration_falls_back_to_search_when_isrc_lookup_fails():
    search_result = {
        "recording-list": [
            {"title": "Title", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "100", "length": "200000"},
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result) as search_mock:
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration == 200.0
    search_mock.assert_called_once()


def test_find_track_duration_skips_low_score_and_mismatched_results():
    search_result = {
        "recording-list": [
            {"title": "Title", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "50", "length": "200000"},
            {"title": "Different Song", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "100", "length": "999000"},
            {"title": "Title", "artist-credit": [{"artist": {"name": "Artist"}}], "ext:score": "95", "length": "205000"},
        ]
    }
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value=search_result):
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration == 205.0  # skips the low-score row and the title mismatch


def test_find_track_duration_returns_none_when_nothing_matches():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", return_value={"recording-list": []}):
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration is None


def test_find_track_duration_handles_network_error_gracefully():
    with mock.patch.object(cover_art.mb, "get_recordings_by_isrc", side_effect=cover_art.mb.ResponseError("404")), \
         mock.patch.object(cover_art.mb, "search_recordings", side_effect=cover_art.mb.MusicBrainzError("boom")):
        duration = cover_art.find_track_duration("Artist", "Title")

    assert duration is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/recognition/test_cover_art.py -v -k duration`
Expected: `AttributeError: module 'vinylyrics.recognition.cover_art' has no attribute 'find_track_duration'`

- [ ] **Step 4: Implement `find_track_duration`/`find_track_duration_async`**

Append to `vinylyrics/recognition/cover_art.py` (below the existing
`find_cover_url_async`):

```python
def _duration_sec_from_recording(rec: dict) -> "float | None":
    length_ms = rec.get("length")
    return float(length_ms) / 1000.0 if length_ms else None


def find_track_duration(artist: str, title: str, isrc: "str | None" = None) -> "float | None":
    if isrc:
        try:
            result = mb.get_recordings_by_isrc(isrc)
        except mb.MusicBrainzError:
            result = None
        if result:
            for rec in result.get("isrc", {}).get("recording-list", []):
                duration = _duration_sec_from_recording(rec)
                if duration is not None:
                    return duration

    try:
        result = mb.search_recordings(recording=title, artist=artist, limit=10)
    except mb.MusicBrainzError:
        return None

    for rec in result.get("recording-list", []):
        score = int(rec.get("ext:score", 0))
        if score < MIN_SEARCH_SCORE:
            continue
        if not _recording_matches(rec, title, artist):
            continue
        duration = _duration_sec_from_recording(rec)
        if duration is not None:
            return duration
    return None


async def find_track_duration_async(artist: str, title: str, isrc: "str | None" = None) -> "float | None":
    return await asyncio.to_thread(find_track_duration, artist, title, isrc)
```

Add `import asyncio` to the top of `cover_art.py` if it isn't already there
(check first — `find_cover_url_async` already uses `asyncio.to_thread`, so
the import should already exist).

- [ ] **Step 5: Run to verify the new tests pass**

Run: `uv run pytest tests/recognition/test_cover_art.py -v`
Expected: all pass (Phase 5's existing cover-art tests plus the 5 new ones)

- [ ] **Step 6: Wire duration into `recognize_with_cover_art`**

Modify `vinylyrics/recognition/enrich.py`:

```python
from __future__ import annotations

from dataclasses import replace

import numpy as np

from vinylyrics.recognition.base import RecognitionResult, Recognizer
from vinylyrics.recognition.cover_art import find_cover_url_async, find_track_duration_async


async def recognize_with_cover_art(
    recognizer: Recognizer, audio: np.ndarray, sample_rate: int
) -> "RecognitionResult | None":
    result = await recognizer.recognize(audio, sample_rate)
    if result is None:
        return None

    better_cover = await find_cover_url_async(result.artist, result.title, result.album, result.isrc)
    duration = await find_track_duration_async(result.artist, result.title, result.isrc)

    updates = {}
    if better_cover:
        updates["cover_url"] = better_cover
    if duration is not None:
        updates["duration"] = duration
    return replace(result, **updates) if updates else result
```

- [ ] **Step 7: Extend the enrich tests — and fix the two pre-existing ones**

**This step has two parts, both required.** `recognize_with_cover_art` now
calls `find_track_duration_async` unconditionally, on every invocation.
Phase 5's two pre-existing tests
(`test_enrich_replaces_cover_with_musicbrainz_when_found`,
`test_enrich_falls_back_to_shazam_cover_when_musicbrainz_finds_nothing`)
only mock `find_cover_url_async` — they do NOT mock the new call, so as
written today they would each make a REAL MusicBrainz network request.
Verified live during planning: after making this exact change, those two
tests went from instant to **7.6 seconds each** (confirmed with
`--durations=0`), because they were silently hitting the real API instead
of staying offline. This is not a hypothetical risk — it reproduces
immediately.

**Part 1 — fix the two pre-existing tests.** In `tests/recognition/test_enrich.py`,
add a second `mock.patch(...)` for `find_track_duration_async` to each of
these two existing `with` blocks (the rest of each test is unchanged):

```python
def test_enrich_replaces_cover_with_musicbrainz_when_found():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value="https://coverartarchive.org/release/x/front"),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=None),
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
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=None),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.cover_url == "shazam-cover"
```

(`test_enrich_returns_none_when_recognition_fails` needs no change — it
returns before either lookup would ever be called.)

**Part 2 — add the two new tests.** Add to `tests/recognition/test_enrich.py`:

```python
def test_enrich_populates_duration_from_musicbrainz():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value=None),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=238.0),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.duration == 238.0
    assert result.cover_url == "shazam-cover"  # unchanged, MB found no cover


def test_enrich_leaves_duration_none_when_musicbrainz_finds_nothing():
    shazam_result = RecognitionResult(
        title="Song", artist="Artist", album="Album", cover_url="shazam-cover",
        offset=1.0, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1",
    )
    recognizer = _FakeRecognizer(shazam_result)

    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async",
        new=mock.AsyncMock(return_value=None),
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async",
        new=mock.AsyncMock(return_value=None),
    ):
        result = _run(recognize_with_cover_art(recognizer, np.zeros(16000, dtype=np.float32), 16000))

    assert result.duration is None
```

- [ ] **Step 8: Run the full offline suite**

Run: `uv run pytest -v`
Expected: all pre-existing tests still pass — the two Phase 5 enrich tests
fixed in Step 7 now stay offline and fast again (confirm none of
`tests/recognition/` takes more than a fraction of a second; a 7+ second
test there means Step 7's Part 1 was missed) — plus the 7 new tests
from this task.

- [ ] **Step 9: Commit**

```bash
git add vinylyrics/recognition/base.py vinylyrics/recognition/cover_art.py vinylyrics/recognition/enrich.py tests/recognition/test_cover_art.py tests/recognition/test_enrich.py
git commit -m "feat: look up track duration from MusicBrainz, needed for lyrics matching"
```

---

## Task 2: Palette extraction (`vinylyrics/palette.py`)

**Files:**
- Modify: `pyproject.toml` (add `Pillow>=10.0` to `dependencies`)
- Create: `vinylyrics/palette.py`
- Test: `tests/test_palette.py`
- Test: `tests/test_palette_network.py`

**Interfaces:**
- Consumes: nothing from earlier tasks in this phase (fully standalone —
  same independence pattern as Phase 5's `CallCadencePolicy` or Phase 6's
  `PlaybackClock`).
- Produces:
  - `@dataclass(frozen=True) class Palette`: `bg: str`, `fg: str`, `dim: str` (hex strings, e.g. `"#1a2733"`).
  - `FALLBACK_PALETTE: Palette` — used when there's no cover URL or the
    download/decode fails.
  - `def extract_palette(cover_url: "str | None") -> Palette`.
    Task 3 (`state/session.py`) calls this once per newly-identified track
    and stores the result on the session.

**Verified during planning:** downloaded a real cover image
(`https://is1-ssl.mzstatic.com/.../mzm.umknsjlj.jpg`) and ran it through
this exact pipeline live: `Image.open(...).convert("RGB").resize((100,
100)).quantize(colors=5, method=Image.Quantize.MEDIANCUT)` correctly
extracted a dominant color of `RGB(216,0,1)` (a saturated red), matching
the album's actual dominant tone. The HSL-clamp-then-darken pipeline (see
Global Constraints) was verified against this exact color and against a
synthetic worst-case hue scan.

- [ ] **Step 1: Add the `Pillow` dependency**

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
    "lrclibapi>=0.3.1",
    "Pillow>=10.0",
]
```

Run: `uv sync` — confirm it installs with no errors.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_palette.py
import colorsys

import pytest

from vinylyrics.palette import FALLBACK_PALETTE, Palette, _contrast_ratio, _dominant_rgb_from_bytes, _force_projectable, extract_palette


def _make_test_jpeg_bytes(rgb: tuple[int, int, int]) -> bytes:
    import io
    from PIL import Image

    img = Image.new("RGB", (50, 50), rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_extract_palette_returns_fallback_when_no_cover_url():
    palette = extract_palette(None)
    assert palette == FALLBACK_PALETTE


def test_extract_palette_returns_fallback_on_download_failure(monkeypatch):
    import vinylyrics.palette as palette_module

    def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(palette_module.requests, "get", _raise)
    palette = extract_palette("https://example.com/cover.jpg")
    assert palette == FALLBACK_PALETTE


def test_extract_palette_downloads_and_extracts_dominant_color(monkeypatch):
    import vinylyrics.palette as palette_module

    class _FakeResponse:
        content = _make_test_jpeg_bytes((30, 60, 200))  # a mid-blue, already dark

        def raise_for_status(self):
            pass

    monkeypatch.setattr(palette_module.requests, "get", lambda *a, **k: _FakeResponse())
    palette = extract_palette("https://example.com/cover.jpg")

    assert palette.bg.startswith("#")
    assert palette.fg == "#f0ede8"
    assert palette != FALLBACK_PALETTE


def test_dominant_rgb_from_bytes_finds_the_solid_fill_color():
    jpeg_bytes = _make_test_jpeg_bytes((10, 200, 80))
    r, g, b = _dominant_rgb_from_bytes(jpeg_bytes)
    # JPEG is lossy, allow a small tolerance
    assert abs(r - 10) < 15
    assert abs(g - 200) < 15
    assert abs(b - 80) < 15


def test_force_projectable_clamps_lightness_and_saturation():
    # a very bright, fully-saturated color: h doesn't matter for this check
    r, g, b = _force_projectable(255, 0, 0)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    # rounding to 8-bit RGB and back introduces small quantization error —
    # verified live during planning: clamping to exactly s=0.5 then
    # round-tripping through 8-bit RGB recovers s=0.5098, not exactly 0.5.
    # A 0.02 tolerance absorbs that without masking a real clamp failure
    # (the unclamped input here is fully saturated red, s=1.0 — an order
    # of magnitude past this tolerance if the clamp weren't applied).
    assert 0.12 - 0.02 <= l <= 0.20 + 0.02
    assert s <= 0.5 + 0.02


def test_force_projectable_raises_lightness_when_original_is_darker_than_range():
    r, g, b = _force_projectable(5, 5, 5)  # near-black
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    assert l >= 0.12 - 1e-6


def test_contrast_ratio_of_black_and_white_is_maximal():
    ratio = _contrast_ratio((255, 255, 255), (0, 0, 0))
    assert ratio == pytest.approx(21.0, abs=0.01)


def test_extract_palette_always_passes_wcag_contrast_against_fg():
    import vinylyrics.palette as palette_module

    # scan every hue at the clamp's least-favorable corner (l=0.20, s=0.5)
    # and confirm the final bg the module would emit always clears 7:1 —
    # this is the same scan run live during planning, now as a regression test.
    fg_rgb = (0xF0, 0xED, 0xE8)
    for hue_deg in range(0, 360, 15):
        h = hue_deg / 360
        r, g, b = (round(c * 255) for c in colorsys.hls_to_rgb(h, 0.20, 0.5))
        darkened = palette_module._darken_until_contrast((r, g, b), fg_rgb)
        assert _contrast_ratio(fg_rgb, darkened) >= 7.0 - 1e-6
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_palette.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.palette'`

- [ ] **Step 4: Implement `palette.py`**

```python
# vinylyrics/palette.py
from __future__ import annotations

import colorsys
import io
from dataclasses import dataclass

import requests
from PIL import Image

COVER_TIMEOUT_SEC = 5.0
MIN_CONTRAST = 7.0
TARGET_MIN_L = 0.12
TARGET_MAX_L = 0.20
MAX_SATURATION = 0.5
FG_RGB = (0xF0, 0xED, 0xE8)


@dataclass(frozen=True)
class Palette:
    bg: str
    fg: str
    dim: str


def _hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


FALLBACK_PALETTE = Palette(bg="#1a2733", fg=_hex(FG_RGB), dim="#8a99a5")


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def lin(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    l1 = _relative_luminance(rgb1) + 0.05
    l2 = _relative_luminance(rgb2) + 0.05
    return max(l1, l2) / min(l1, l2)


def _dominant_rgb_from_bytes(image_bytes: bytes) -> tuple[int, int, int]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((100, 100))
    quantized = img.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    counts = sorted(quantized.getcolors(), reverse=True)
    top_index = counts[0][1]
    palette_bytes = quantized.getpalette()
    r, g, b = palette_bytes[top_index * 3 : top_index * 3 + 3]
    return r, g, b


def _force_projectable(r: int, g: int, b: int) -> tuple[int, int, int]:
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = min(max(l, TARGET_MIN_L), TARGET_MAX_L)
    s = min(s, MAX_SATURATION)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return round(r2 * 255), round(g2 * 255), round(b2 * 255)


def _darken_until_contrast(rgb: tuple[int, int, int], fg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    while l > 0.0:
        candidate = tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s))
        if _contrast_ratio(fg_rgb, candidate) >= MIN_CONTRAST:
            return candidate
        l -= 0.01
    return (0, 0, 0)


def _blend(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int], weight: float) -> tuple[int, int, int]:
    return tuple(round(c1 * (1 - weight) + c2 * weight) for c1, c2 in zip(rgb1, rgb2))


def extract_palette(cover_url: "str | None") -> Palette:
    if not cover_url:
        return FALLBACK_PALETTE
    try:
        response = requests.get(cover_url, timeout=COVER_TIMEOUT_SEC)
        response.raise_for_status()
        dominant = _dominant_rgb_from_bytes(response.content)
    except Exception:
        return FALLBACK_PALETTE

    projectable = _force_projectable(*dominant)
    bg_rgb = _darken_until_contrast(projectable, FG_RGB)
    dim_rgb = _blend(bg_rgb, FG_RGB, weight=0.45)
    return Palette(bg=_hex(bg_rgb), fg=_hex(FG_RGB), dim=_hex(dim_rgb))
```

- [ ] **Step 5: Run to verify the offline tests pass**

Run: `uv run pytest tests/test_palette.py -v`
Expected: `8 passed`

- [ ] **Step 6: Write and run the network test**

```python
# tests/test_palette_network.py
import pytest

from vinylyrics.palette import FALLBACK_PALETTE, extract_palette


@pytest.mark.network
def test_extract_palette_against_a_real_cover_image():
    # A real Shazam cover art URL for "Bonito" by Jarabe de Palo, fetched
    # live during planning — dominant color there was a saturated red,
    # (216,0,1), which this test re-derives against the live URL.
    url = "https://is1-ssl.mzstatic.com/image/thumb/Music19/v4/ca/f5/b8/caf5b89c-d331-632d-c17b-0a1d576cc653/mzm.umknsjlj.jpg/400x400cc.jpg"
    palette = extract_palette(url)

    assert palette != FALLBACK_PALETTE
    assert palette.fg == "#f0ede8"
    assert palette.bg.startswith("#")
```

Run: `uv run pytest tests/test_palette_network.py -v -m network`
Expected: `1 passed` (needs internet access)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/palette.py tests/test_palette.py tests/test_palette_network.py
git commit -m "feat: add cover-art palette extraction forced into projectable HSL range"
```

---

## Task 3: Session state model (`vinylyrics/state/session.py`)

**Files:**
- Create: `vinylyrics/state/session.py`
- Test: `tests/state/test_session.py`

**Interfaces:**
- Consumes: `RecognitionResult` (Task 1), `Palette`/`extract_palette`
  (Task 2), `LyricsResult`/`LyricLine` (Phase 6's `lyrics/base.py`,
  `lyrics/parser.py`), `PlaybackClock` (Phase 6's `state/clock.py`).
- Produces:
  - `class DisplayState(str, Enum)`: `IDLE`, `LISTENING`, `PLAYING`, `UNIDENTIFIED` (spec §8's exact 4 states; `str` mixin so it JSON-serializes as its value directly, e.g. `"PLAYING"`, not `"DisplayState.PLAYING"`).
  - `class PlaybackSession`: `__init__(self)`.
    - `def on_listening_started(self) -> None` — sets state to `LISTENING` (no track yet, but audio is flowing).
    - `def on_recognized(self, result: RecognitionResult, lyrics: "LyricsResult | None", wall_time: float) -> None` — starts a new `PlaybackClock` if this is a different track than the current one (compared by title+artist), or reuses the existing clock and calls `add_anchor()` if it's the same track continuing; stores the lyrics and extracts+stores the palette; sets state to `PLAYING`.
    - `def on_unidentified(self) -> None` — sets state to `UNIDENTIFIED` (3 failed recognition attempts in a row, per spec §3).
    - `def on_track_gap(self) -> None` — does NOT reset the session (a gap is "a signal, not the main trigger" per spec §2); left as a no-op hook for the engine to call, since resetting `CallCadencePolicy`'s lock (Phase 5) is what actually matters here, not the session's own state.
    - `def on_stopped(self) -> None` — sets state to `IDLE`, clears the current track/clock/lyrics/palette (needle lifted, per spec §2's `STOPPED` event, `>10s` silence).
    - `def to_payload(self, now: float) -> dict` — returns exactly spec §6's JSON shape: `{"state": ..., "track": {...} | None, "palette": {...}, "lyrics": [...], "clock": {...} | None}`.
  - Task 5 (the engine) owns exactly one `PlaybackSession` and calls these
    methods as events happen; Task 6 (the server) calls `to_payload()` to
    build the WebSocket broadcast body.

**Design note — why "same track" is compared by title+artist, not object
identity:** the sliding-window loop (spec §2) re-recognizes the same
playing song every 8s while it's locked in, producing a NEW
`RecognitionResult` object each time (a fresh Shazam response) that should
extend the SAME `PlaybackClock` with a new anchor, not start a new one —
starting a fresh clock on every successful recognition would make
`add_anchor()`'s regression-over-history and no-jump guarantees meaningless
(every "anchor" would be a first anchor). A different title/artist means an
actual track change, which does need a fresh clock (spec §5's anchor model
is explicitly per-song, matching Phase 6's own design note for
`PlaybackClock`: "a NEW song means a NEW `PlaybackClock` instance").

- [ ] **Step 1: Write the failing tests**

```python
# tests/state/test_session.py
import pytest

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine
from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.state.session import DisplayState, PlaybackSession


def _result(title="Bonito", artist="Jarabe de Palo", duration=238.0, offset=27.79) -> RecognitionResult:
    return RecognitionResult(
        title=title, artist=artist, album="Depende", cover_url="https://example.com/cover.jpg",
        offset=offset, timeskew=0.0, frequencyskew=0.0, isrc="ISRC1", duration=duration,
    )


def _lyrics() -> LyricsResult:
    return LyricsResult(
        synced_lines=(LyricLine(ms=1000, text="hola"), LyricLine(ms=2000, text="mundo")),
        plain_lyrics=None, instrumental=False,
    )


def test_session_starts_idle():
    session = PlaybackSession()
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.IDLE
    assert payload["track"] is None
    assert payload["clock"] is None
    assert payload["lyrics"] == []


def test_on_listening_started_sets_listening_with_no_track():
    session = PlaybackSession()
    session.on_listening_started()
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.LISTENING
    assert payload["track"] is None


def test_on_recognized_sets_playing_with_track_and_lyrics():
    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=100.0)
    payload = session.to_payload(now=100.0)

    assert payload["state"] == DisplayState.PLAYING
    assert payload["track"]["title"] == "Bonito"
    assert payload["track"]["artist"] == "Jarabe de Palo"
    assert payload["track"]["album"] == "Depende"
    assert payload["track"]["cover_url"] == "https://example.com/cover.jpg"
    assert payload["lyrics"] == [{"ms": 1000, "text": "hola"}, {"ms": 2000, "text": "mundo"}]
    assert payload["clock"]["anchor_wall"] == 100.0
    assert payload["clock"]["anchor_ms"] == pytest.approx(27790.0, abs=1.0)
    assert payload["clock"]["speed"] == pytest.approx(1.0)
    assert payload["palette"]["fg"] == "#f0ede8"


def test_on_recognized_same_track_extends_existing_clock_not_a_new_one():
    session = PlaybackSession()
    session.on_recognized(_result(offset=27.79), _lyrics(), wall_time=0.0)

    # A second recognition of the SAME song 10s later, with the offset
    # advanced roughly by real playback time (~1x speed). Verified live
    # during planning: reusing the SAME offset unchanged here (as if the
    # song hadn't moved) makes this anchor imply the song jumped BACKWARDS
    # by 10s relative to the first anchor's prediction — PlaybackClock's
    # own >3s-jump guard then correctly REJECTS it, and this test's later
    # assertion (`anchor_wall == 10.0`) fails because nothing was accepted.
    # The fixture must advance the offset to stay inside the accepted range.
    second = _result(offset=37.79)
    session.on_recognized(second, _lyrics(), wall_time=10.0)
    # position() from the clock should reflect a real anchor history spanning
    # both calls, not a from-scratch single-anchor clock
    payload = session.to_payload(now=10.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["clock"]["anchor_wall"] == 10.0


def test_on_recognized_different_track_starts_a_fresh_clock():
    session = PlaybackSession()
    session.on_recognized(_result(title="Bonito"), _lyrics(), wall_time=0.0)
    session.on_recognized(_result(title="Other Song"), _lyrics(), wall_time=500.0)

    payload = session.to_payload(now=500.0)
    assert payload["track"]["title"] == "Other Song"
    assert payload["clock"]["anchor_wall"] == 500.0


def test_on_recognized_with_no_synced_lyrics_still_shows_track():
    session = PlaybackSession()
    unsynced = LyricsResult(synced_lines=(), plain_lyrics="letra sin sincronizar", instrumental=False)
    session.on_recognized(_result(), unsynced, wall_time=0.0)

    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["lyrics"] == []  # no karaoke, but the track/palette still show


def test_on_recognized_with_no_lyrics_result_at_all():
    session = PlaybackSession()
    session.on_recognized(_result(), None, wall_time=0.0)

    payload = session.to_payload(now=0.0)
    assert payload["lyrics"] == []


def test_on_unidentified_sets_state_without_clearing_nothing_to_clear():
    session = PlaybackSession()
    session.on_unidentified()
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.UNIDENTIFIED
    assert payload["track"] is None


def test_on_stopped_clears_track_and_returns_to_idle():
    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=0.0)
    session.on_stopped()

    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.IDLE
    assert payload["track"] is None
    assert payload["clock"] is None
    assert payload["lyrics"] == []


def test_on_track_gap_does_not_clear_the_current_track():
    session = PlaybackSession()
    session.on_recognized(_result(), _lyrics(), wall_time=0.0)
    session.on_track_gap()

    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["track"]["title"] == "Bonito"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/state/test_session.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.state.session'`

- [ ] **Step 3: Implement `session.py`**

```python
# vinylyrics/state/session.py
from __future__ import annotations

from enum import Enum

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.palette import FALLBACK_PALETTE, Palette, extract_palette
from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.state.clock import ClockConfig, PlaybackClock


class DisplayState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PLAYING = "PLAYING"
    UNIDENTIFIED = "UNIDENTIFIED"


def _same_track(a: "RecognitionResult | None", b: RecognitionResult) -> bool:
    return a is not None and a.title == b.title and a.artist == b.artist


class PlaybackSession:
    def __init__(self, clock_config: ClockConfig = ClockConfig()):
        self._clock_config = clock_config
        self._state = DisplayState.IDLE
        self._track: "RecognitionResult | None" = None
        self._lyrics: "LyricsResult | None" = None
        self._palette: Palette = FALLBACK_PALETTE
        self._clock: "PlaybackClock | None" = None

    def on_listening_started(self) -> None:
        self._state = DisplayState.LISTENING

    def on_recognized(self, result: RecognitionResult, lyrics: "LyricsResult | None", wall_time: float) -> None:
        if not _same_track(self._track, result) or self._clock is None:
            self._clock = PlaybackClock(self._clock_config)
            self._palette = extract_palette(result.cover_url)

        self._clock.add_anchor(wall_time=wall_time, position_sec=result.offset or 0.0, timeskew=result.timeskew or 0.0)
        self._track = result
        self._lyrics = lyrics
        self._state = DisplayState.PLAYING

    def on_unidentified(self) -> None:
        self._state = DisplayState.UNIDENTIFIED

    def on_track_gap(self) -> None:
        pass  # a signal, not a trigger — see spec §2; nothing to clear here

    def on_stopped(self) -> None:
        self._state = DisplayState.IDLE
        self._track = None
        self._lyrics = None
        self._palette = FALLBACK_PALETTE
        self._clock = None

    def to_payload(self, now: float) -> dict:
        track_payload = None
        if self._track is not None:
            track_payload = {
                "title": self._track.title,
                "artist": self._track.artist,
                "album": self._track.album,
                "cover_url": self._track.cover_url,
            }

        lyrics_payload = []
        if self._lyrics is not None and self._lyrics.has_synced:
            lyrics_payload = [{"ms": line.ms, "text": line.text} for line in self._lyrics.synced_lines]

        clock_payload = None
        if self._clock is not None and self._clock.is_anchored:
            clock_payload = {
                "anchor_wall": self._clock._anchor_wall,
                "anchor_ms": self._clock._anchor_position * 1000.0,
                "speed": self._clock.speed,
            }

        return {
            "state": self._state,
            "track": track_payload,
            "palette": {"bg": self._palette.bg, "fg": self._palette.fg, "dim": self._palette.dim},
            "lyrics": lyrics_payload,
            "clock": clock_payload,
        }
```

**Note on reaching into `PlaybackClock`'s "private" fields:** `to_payload`
reads `self._clock._anchor_wall`/`_anchor_position` directly rather than
adding new public properties to Phase 6's `PlaybackClock`. This is a
deliberate, minimal-footprint choice: `PlaybackClock.position(now)` already
gives the *interpolated* position, but the WebSocket contract (spec §6)
needs the raw anchor point itself (`anchor_wall`, `anchor_ms`) so the
*browser* can do its own interpolation — re-deriving that from `position()`
would be circular. If this reviews poorly, the fix is two one-line public
properties on `PlaybackClock` (`anchor_wall`, `anchor_position`); flagged
here for the task reviewer to weigh rather than decided unilaterally.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/state/test_session.py -v`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/state/session.py tests/state/test_session.py
git commit -m "feat: add playback session composing track, clock, lyrics, and palette into the websocket contract"
```

---

## Task 4: Orchestration engine (`vinylyrics/engine.py`)

**Files:**
- Create: `vinylyrics/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `AudioSource` (Phase 4's `audio/source.py`),
  `CircularAudioBuffer` (Phase 4's `audio/buffer.py`), `SilenceDetector`/
  `SilenceThresholds`/`AudioEvent`/`compute_rms_windows`/`calibrate_floor`
  (Phase 4's `audio/vad.py`), `CallCadencePolicy`/`CadenceConfig` (Phase
  5's `recognition/cadence.py`), `Recognizer` protocol + `recognize_with_cover_art`
  (Phase 5/Task 1), `LyricsService` (Phase 6's `lyrics/service.py`),
  `PlaybackSession` (Task 3).
- Produces:
  - `@dataclass(frozen=True) class EngineConfig`: `window_sec: float = 0.1`,
    `recognition_window_sec: float = 12.0`, `calibration_sec: float = 3.0`.
  - `class Engine`:
    - `__init__(self, source, recognizer, lyrics_service, session, on_change, thresholds=SilenceThresholds(), cadence_config=CadenceConfig(), config=EngineConfig(), now_fn=time.monotonic)`
    - `async def run(self) -> None` — the main loop; runs until cancelled.
    - `def debug_snapshot(self) -> dict` — last recognition result (or
      `None`), current speed estimate (or `None`), last RMS window in
      dBFS, and the clock's anchor history (spec §6: "el último
      reconocimiento, la estimación de velocidad, el RMS y el historial de
      anclas" — this is exactly that list, read from `session`).
  - `on_change: Callable[[], None]` is called every time the engine updates
    the session in a way that changes the broadcast payload (a new
    recognition, a state transition, a track gap/stop) — Task 6 (the
    server) passes a callback here that pushes `session.to_payload(now)`
    to every connected WebSocket.
  - `now_fn` exists purely for testability — the default is real wall-clock
    time (`time.monotonic`), and this task's own tests inject a fake,
    manually-advanced clock so cadence/timing behavior is deterministic
    without a single real `time.sleep`.

**Design note — audio reads must not block the event loop:**
`LineInSource.read()` (Phase 4) blocks on `sounddevice`'s
`InputStream.read()` until enough samples arrive — calling it directly
inside `async def run()` would freeze recognition calls, the WebSocket, and
`/health` for however long a read takes. `Engine.run()` wraps every
`source.read(...)` call in `await asyncio.to_thread(...)`, the same pattern
Phase 5's `find_cover_url_async` already established for this codebase's
one other blocking-call-inside-async-code case.

**Design note — recognition must not block the audio loop either:** a
Shazam call takes real network time (Phase 5's own manual tests measured
multi-second round-trips). `Engine.run()` fires recognition as a background
`asyncio.Task` via `asyncio.ensure_future(...)`, tracked through
`CallCadencePolicy`'s existing `mark_call_started()`/`in_flight`/
`mark_call_finished()` methods (already built exactly for this in Phase 5)
so the read loop keeps buffering audio and re-checking silence while a
recognition call is in flight, and never launches a second one concurrently
(spec §3: "nunca dos simultáneas").

**Verified during planning:** this task's design (event loop + background
task + `CallCadencePolicy` gating) follows the same async patterns already
proven in this codebase (`find_cover_url_async`'s `asyncio.to_thread`,
`ShazamIORecognizer`'s async retry loop) rather than a new pattern; the
test suite below exercises the actual wiring with fakes standing in for
real I/O, verified by running it as part of writing this plan.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine.py
import asyncio
from unittest import mock

import numpy as np
import pytest

from vinylyrics.engine import Engine, EngineConfig
from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine
from vinylyrics.recognition.base import RecognitionResult
from vinylyrics.recognition.cadence import CadenceConfig
from vinylyrics.state.session import DisplayState, PlaybackSession


class _FakeClock:
    """Manually-advanced now_fn for deterministic cadence tests."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class _FakeSource:
    """Yields a fixed sequence of chunks, raising StopAsyncIteration-like
    signal via a sentinel once exhausted so tests can await engine.run()
    for a bounded number of iterations."""

    def __init__(self, chunks: list[np.ndarray], sample_rate: int = 16000):
        self._chunks = list(chunks)
        self._sample_rate = sample_rate
        self.reads = 0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def read(self, seconds: float) -> np.ndarray:
        self.reads += 1
        if self._chunks:
            return self._chunks.pop(0)
        raise asyncio.CancelledError()  # test's cue to stop the loop


class _FakeRecognizer:
    def __init__(self, result: "RecognitionResult | None"):
        self._result = result
        self.calls = 0

    async def recognize(self, audio, sample_rate):
        self.calls += 1
        return self._result


class _FakeLyricsService:
    def __init__(self, result: "LyricsResult | None"):
        self._result = result

    def get_lyrics(self, artist, title, album, duration):
        return self._result


def _loud_chunk(sample_rate: int, seconds: float, amplitude: float = 0.3) -> np.ndarray:
    n = int(seconds * sample_rate)
    rng = np.random.default_rng(42)
    return (rng.standard_normal(n) * amplitude).astype(np.float32)


def _quiet_chunk(sample_rate: int, seconds: float, amplitude: float = 0.001) -> np.ndarray:
    # NOT all-zero: SilenceDetector.__init__ requires a finite calibration
    # floor, and rms_dbfs(all-zero) is exactly float("-inf") (verified —
    # calibrate_floor(np.zeros(...)) raises inside SilenceDetector's own
    # finiteness check). Low-amplitude noise gives a realistic, finite
    # "quiet surface noise" floor instead, matching spec §2's own point
    # that the calibration floor is never digital silence.
    n = int(seconds * sample_rate)
    rng = np.random.default_rng(7)
    return (rng.standard_normal(n) * amplitude).astype(np.float32)


@pytest.fixture(autouse=True)
def _no_real_network_enrichment():
    # Engine._recognize_and_update calls the REAL recognize_with_cover_art,
    # which — whenever a test's fake recognizer returns a non-None result —
    # goes on to call the REAL find_cover_url_async/find_track_duration_async
    # against MusicBrainz. Verified live during planning: without this,
    # several of this file's tests silently made real network calls (one
    # measured at 7+ seconds, occasionally flaky depending on network
    # conditions) despite this being part of the OFFLINE suite. These are
    # the same two functions Task 1's own enrich tests mock, for the same
    # reason — applied here too since the engine exercises the same code
    # path.
    with mock.patch(
        "vinylyrics.recognition.enrich.find_cover_url_async", new=mock.AsyncMock(return_value=None)
    ), mock.patch(
        "vinylyrics.recognition.enrich.find_track_duration_async", new=mock.AsyncMock(return_value=None)
    ):
        yield


def _run_engine_until_cancelled(engine: Engine) -> None:
    # run() is cancelled once the fake source's chunks are exhausted, but
    # any recognition it fired is a background task (asyncio.ensure_future,
    # never awaited by run() itself — by design, so the audio loop never
    # blocks on a network call). Verified live during planning: without
    # also awaiting that task here, run() being cancelled races ahead of
    # the (even though non-blocking) recognition coroutine ever getting a
    # chance to execute, and assertions on session state see stale data —
    # two of this file's tests failed on the first run for exactly this
    # reason before this helper awaited the pending task too.
    async def runner():
        with pytest.raises(asyncio.CancelledError):
            await engine.run()
        if engine._recognition_task is not None:
            await engine._recognition_task
    asyncio.run(runner())


def test_engine_transitions_to_listening_on_start():
    sr = 16000
    # first chunk is consumed by calibration, the rest by window reads —
    # all quiet, so no recognition should ever be triggered
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [_quiet_chunk(sr, 0.1)] * 3, sample_rate=sr)
    session = PlaybackSession()
    engine = Engine(
        source=source, recognizer=_FakeRecognizer(None), lyrics_service=_FakeLyricsService(None),
        session=session, on_change=lambda: None, now_fn=_FakeClock(),
    )
    _run_engine_until_cancelled(engine)
    assert session.to_payload(now=0.0)["state"] in (DisplayState.LISTENING, DisplayState.IDLE)


def test_engine_calls_recognizer_once_loud_audio_is_seen_and_updates_session():
    sr = 16000
    loud = _loud_chunk(sr, 0.1)
    # first chunk (calibration) is quiet, so the floor sits well below the
    # loud chunks that follow — otherwise the floor would equal the loud
    # level itself and the detector would misclassify loud audio as silence
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [loud] * 5, sample_rate=sr)
    result = RecognitionResult(
        title="Bonito", artist="Jarabe de Palo", album="Depende", cover_url=None,
        offset=10.0, timeskew=0.0, frequencyskew=0.0, isrc=None, duration=238.0,
    )
    recognizer = _FakeRecognizer(result)
    lyrics = LyricsResult(synced_lines=(LyricLine(ms=0, text="hola"),), plain_lyrics=None, instrumental=False)
    lyrics_service = _FakeLyricsService(lyrics)
    session = PlaybackSession()
    changes = []

    engine = Engine(
        source=source, recognizer=recognizer, lyrics_service=lyrics_service, session=session,
        on_change=lambda: changes.append(session.to_payload(now=0.0)["state"]),
        now_fn=_FakeClock(),
    )
    _run_engine_until_cancelled(engine)

    assert recognizer.calls >= 1
    payload = session.to_payload(now=0.0)
    assert payload["state"] == DisplayState.PLAYING
    assert payload["track"]["title"] == "Bonito"
    assert DisplayState.PLAYING in changes


def test_engine_respects_min_call_interval_between_recognitions():
    sr = 16000
    loud = _loud_chunk(sr, 0.1)
    # first chunk (calibration) is quiet; the rest are loud and
    # recognition-eligible if cadence allows it
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [loud] * 20, sample_rate=sr)
    result = RecognitionResult(
        title="Song", artist="Artist", album=None, cover_url=None,
        offset=0.0, timeskew=0.0, frequencyskew=0.0, isrc=None, duration=None,
    )
    recognizer = _FakeRecognizer(result)
    session = PlaybackSession()
    clock = _FakeClock()

    engine = Engine(
        source=source, recognizer=recognizer, lyrics_service=_FakeLyricsService(None), session=session,
        on_change=lambda: None, cadence_config=CadenceConfig(min_interval_sec=8.0), now_fn=clock,
    )

    async def drive():
        task = asyncio.ensure_future(engine.run())
        for _ in range(20):
            await asyncio.sleep(0)  # let queued callbacks/tasks progress
            clock.advance(0.1)  # matches window_sec, simulates real time passing
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(drive())
    # 20 iterations * 0.1s = 2.0s of simulated time — well under the 8s
    # minimum interval, so the recognizer must have been called at most once
    assert recognizer.calls <= 1


def test_debug_snapshot_reports_last_recognition_and_speed():
    sr = 16000
    result = RecognitionResult(
        title="Song", artist="Artist", album=None, cover_url=None,
        offset=5.0, timeskew=0.01, frequencyskew=0.0, isrc=None, duration=None,
    )
    source = _FakeSource([_quiet_chunk(sr, 3.0)] + [_loud_chunk(sr, 0.1)] * 3, sample_rate=sr)
    session = PlaybackSession()
    engine = Engine(
        source=source, recognizer=_FakeRecognizer(result), lyrics_service=_FakeLyricsService(None),
        session=session, on_change=lambda: None, now_fn=_FakeClock(),
    )
    _run_engine_until_cancelled(engine)

    snapshot = engine.debug_snapshot()
    assert snapshot["last_recognition"]["title"] == "Song"
    assert snapshot["speed"] == pytest.approx(1.01)
    assert "rms_dbfs" in snapshot
    assert isinstance(snapshot["anchor_history"], list)


class _EofSource:
    """Mimics FileSource's real end-of-stream behavior: returns real chunks,
    then an empty array forever once exhausted (never raises)."""

    def __init__(self, chunks: list[np.ndarray], sample_rate: int = 16000):
        self._chunks = list(chunks)
        self._sample_rate = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def read(self, seconds: float) -> np.ndarray:
        if self._chunks:
            return self._chunks.pop(0)
        return np.zeros(0, dtype=np.float32)


def test_engine_stops_cleanly_on_end_of_stream_instead_of_spinning():
    sr = 16000
    source = _EofSource([_quiet_chunk(sr, 3.0)] + [_quiet_chunk(sr, 0.1)] * 3, sample_rate=sr)
    session = PlaybackSession()
    engine = Engine(
        source=source, recognizer=_FakeRecognizer(None), lyrics_service=_FakeLyricsService(None),
        session=session, on_change=lambda: None, now_fn=_FakeClock(),
    )

    async def run_with_timeout():
        await asyncio.wait_for(engine.run(), timeout=2.0)

    # run() must return on its own (end of stream), not hang — verified
    # live that without an explicit empty-chunk check, this would spin
    # forever computing NaN rms_dbfs on empty arrays instead of returning
    # (see the Global Constraints note and the `run()` implementation below).
    asyncio.run(run_with_timeout())

    assert session.to_payload(now=0.0)["state"] == DisplayState.IDLE
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.engine'`

- [ ] **Step 3: Implement `engine.py`**

```python
# vinylyrics/engine.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np

from vinylyrics.audio.buffer import CircularAudioBuffer
from vinylyrics.audio.levels import rms_dbfs
from vinylyrics.audio.vad import AudioEvent, SilenceDetector, SilenceThresholds, calibrate_floor
from vinylyrics.lyrics.service import LyricsService
from vinylyrics.recognition.base import Recognizer
from vinylyrics.recognition.cadence import CadenceConfig, CallCadencePolicy
from vinylyrics.recognition.enrich import recognize_with_cover_art
from vinylyrics.state.session import PlaybackSession


class _AudioSource(Protocol):
    def read(self, seconds: float) -> np.ndarray: ...
    @property
    def sample_rate(self) -> int: ...


@dataclass(frozen=True)
class EngineConfig:
    window_sec: float = 0.1
    recognition_window_sec: float = 12.0
    calibration_sec: float = 3.0
    max_consecutive_failures: int = 3


class Engine:
    def __init__(
        self,
        source: _AudioSource,
        recognizer: Recognizer,
        lyrics_service: LyricsService,
        session: PlaybackSession,
        on_change: Callable[[], None],
        thresholds: SilenceThresholds = SilenceThresholds(),
        cadence_config: CadenceConfig = CadenceConfig(),
        config: EngineConfig = EngineConfig(),
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self._source = source
        self._recognizer = recognizer
        self._lyrics_service = lyrics_service
        self._session = session
        self._on_change = on_change
        self._thresholds = thresholds
        self._cadence = CallCadencePolicy(cadence_config)
        self._config = config
        self._now_fn = now_fn

        self._buffer = CircularAudioBuffer(source.sample_rate, max_seconds=20.0)
        self._detector: "SilenceDetector | None" = None
        self._consecutive_failures = 0
        self._last_rms_dbfs = float("-inf")
        self._last_recognition: "dict | None" = None
        self._recognition_task: "asyncio.Task | None" = None

    def debug_snapshot(self) -> dict:
        clock = self._session._clock
        return {
            "last_recognition": self._last_recognition,
            "speed": clock.speed if clock is not None and clock.is_anchored else None,
            "rms_dbfs": self._last_rms_dbfs,
            "anchor_history": list(clock._history) if clock is not None else [],
        }

    async def run(self) -> None:
        self._session.on_listening_started()
        self._on_change()

        calibration = await asyncio.to_thread(self._source.read, self._config.calibration_sec)
        if len(calibration) == 0:
            raise ValueError(
                "audio source returned no samples for calibration — the source is "
                "empty (e.g. a FileSource shorter than calibration_sec)"
            )
        floor = calibrate_floor(calibration)
        self._detector = SilenceDetector(floor, self._thresholds)

        while True:
            chunk = await asyncio.to_thread(self._source.read, self._config.window_sec)
            if len(chunk) == 0:
                # End of stream — only a finite source (FileSource past EOF)
                # can produce this; a live LineInSource read blocks until it
                # has samples and never returns empty. Verified live: without
                # this check, the loop spins forever computing rms_dbfs on
                # empty arrays (NaN, with a RuntimeWarning on every
                # iteration), pegging a CPU core and never registering
                # silence (NaN < threshold is always False), since the
                # SilenceDetector never sees a real STOPPED condition — this
                # is exactly what `--file dry.wav` (a finite ~90s recording)
                # would hit in Task 6's own manual verification step.
                self._session.on_stopped()
                self._on_change()
                return
            self._buffer.push(chunk)
            self._last_rms_dbfs = rms_dbfs(chunk)

            event = self._detector.process_window(self._last_rms_dbfs)
            if event == AudioEvent.TRACK_GAP:
                self._cadence.on_track_gap()
                self._session.on_track_gap()
                self._on_change()
            elif event == AudioEvent.STOPPED:
                self._session.on_stopped()
                self._consecutive_failures = 0
                self._on_change()

            now = self._now_fn()
            if self._cadence.should_call(now) and not self._detector.is_silent:
                self._cadence.mark_call_started(now)
                self._recognition_task = asyncio.ensure_future(self._recognize_and_update(now))

    async def _recognize_and_update(self, called_at: float) -> None:
        clip = self._buffer.read_last(self._config.recognition_window_sec)
        try:
            result = await recognize_with_cover_art(self._recognizer, clip, self._buffer.sample_rate)
        finally:
            self._cadence.mark_call_finished()

        if result is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._config.max_consecutive_failures:
                self._session.on_unidentified()
                self._on_change()
            return

        self._consecutive_failures = 0
        self._cadence.set_locked(True)
        self._last_recognition = {"title": result.title, "artist": result.artist}

        lyrics = None
        if result.duration is not None:
            lyrics = self._lyrics_service.get_lyrics(result.artist, result.title, result.album, result.duration)

        # anchor_wall marks when the recognized BUFFER STARTED, not when the
        # response arrived — spec §5's latency-subtraction requirement.
        anchor_wall = called_at - self._config.recognition_window_sec
        self._session.on_recognized(result, lyrics, wall_time=anchor_wall)
        self._on_change()
```

**Note on the `anchor_wall` computation (spec §5's latency-subtraction
requirement, flagged in Phase 6's `add_anchor` docstring):** the recognized
clip is the last `recognition_window_sec` (12s) of buffered audio, read at
the moment the call started (`called_at`). Its start therefore corresponds
to wall-clock time `called_at - recognition_window_sec`, which is what gets
passed as `add_anchor`'s `wall_time` — deliberately NOT `self._now_fn()`
evaluated after the (potentially multi-second) recognition call returns,
which would double-count both the buffer's own 12s window and the network
round-trip as if they were "in the future." This is the one line in this
whole plan implementing spec §5's "resta la latencia" requirement that
Phase 6 could only document, not build (it had no caller yet).

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_engine.py -v`
Expected: `5 passed`, each running in well under a second (a test in this
file taking noticeably longer than that means the `_no_real_network_enrichment`
autouse fixture isn't actually being applied and it's hitting the real
network — see the Global Constraints note about this).

- [ ] **Step 5: Run the full offline suite**

Run: `uv run pytest -v`
Expected: all tests pass, including every prior phase's.

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/engine.py tests/test_engine.py
git commit -m "feat: add orchestration engine wiring audio capture through to session state"
```

---

## Task 5: FastAPI server (`vinylyrics/server/app.py`)

**Files:**
- Modify: `pyproject.toml` (add `fastapi>=0.115`, `uvicorn>=0.30` to
  `dependencies`; add `httpx>=0.27` to the `dev` dependency group)
- Create: `vinylyrics/server/app.py`
- Test: `tests/server/test_app.py`

**Interfaces:**
- Consumes: `Engine` (Task 4, specifically its `debug_snapshot()` method
  and the fact that it calls `on_change` on every state transition),
  `PlaybackSession` (Task 3, specifically `to_payload(now)`).
- Produces:
  - `def create_app(session: PlaybackSession, engine: Engine, now_fn=time.monotonic) -> FastAPI`
    — the engine is passed in already constructed and wired with its
    `on_change` callback pointed at this app's broadcaster (Task 7's CLI
    does the actual wiring at startup; this function just builds routes
    around whatever it's given, so tests can pass a fake engine/session).
  - Routes: `GET /health` → `{"status": "ok"}`. `GET /debug` →
    `engine.debug_snapshot()`. `WS /ws` → accepts, sends the current
    `session.to_payload(now_fn())` immediately on connect (so a client that
    joins mid-song sees state right away, not just future changes), then
    stays open and receives future broadcasts.
  - A connected-clients registry + `def broadcast() -> None` used as the
    `on_change` callback the CLI (Task 7) wires into the `Engine`.

**Design note — testing a WebSocket without a live event loop:**
`fastapi.testclient.TestClient` (built on `httpx`, itself built on
`starlette`'s `TestClient`) supports `with client.websocket_connect("/ws") as ws: ws.receive_json()`
synchronously in tests, even though the app internally is async — this is
the standard, first-party way FastAPI apps are tested and needs no real
server process or `asyncio.run()` in the test file itself.

**A critical, verified-live finding: plain `uvicorn` cannot serve real
WebSocket connections at all.** `TestClient`'s websocket tests above pass
regardless, because Starlette's `TestClient` runs the ASGI app through its
own in-process transport — it never touches uvicorn's actual protocol
implementation. Running this app for real with bare `uvicorn` (no extras)
was verified live during planning to log `WARNING: Unsupported upgrade
request` / `WARNING: No supported WebSocket library detected` on every
connection attempt from a real browser, and the page never receives a
single message — the entire karaoke display (this whole project's reason
to exist) would silently fail while every automated test stays green. The
fix is `uvicorn[standard]` (pulls in `websockets`), not `uvicorn` — this is
exactly why Task 6's manual-browser-verification step matters: it is the
only step in this plan that would have caught this.

- [ ] **Step 1: Add the new dependencies**

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
    "lrclibapi>=0.3.1",
    "Pillow>=10.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]

[project.scripts]
vinylizer = "vinylyrics.vinylizer.cli:main"
vinylyrics-server = "vinylyrics.server.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
]
```

Run: `uv sync` — confirm it installs with no errors.

- [ ] **Step 2: Write the failing tests**

```python
# tests/server/test_app.py
from unittest import mock

from vinylyrics.server.app import create_app
from vinylyrics.state.session import DisplayState, PlaybackSession
from fastapi.testclient import TestClient


def _fake_engine(snapshot=None):
    engine = mock.MagicMock()
    engine.debug_snapshot.return_value = snapshot or {
        "last_recognition": None, "speed": None, "rms_dbfs": -60.0, "anchor_history": [],
    }
    return engine


def test_health_endpoint():
    session = PlaybackSession()
    app = create_app(session=session, engine=_fake_engine())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_debug_endpoint_reports_engine_snapshot():
    session = PlaybackSession()
    snapshot = {"last_recognition": {"title": "Bonito"}, "speed": 1.01, "rms_dbfs": -30.0, "anchor_history": []}
    app = create_app(session=session, engine=_fake_engine(snapshot))
    client = TestClient(app)

    response = client.get("/debug")

    assert response.status_code == 200
    assert response.json() == snapshot


def test_websocket_sends_current_state_immediately_on_connect():
    session = PlaybackSession()
    session.on_listening_started()
    app = create_app(session=session, engine=_fake_engine(), now_fn=lambda: 0.0)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        payload = ws.receive_json()

    assert payload["state"] == DisplayState.LISTENING.value


def test_websocket_broadcasts_on_session_change():
    from vinylyrics.recognition.base import RecognitionResult

    session = PlaybackSession()
    app = create_app(session=session, engine=_fake_engine(), now_fn=lambda: 0.0)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        initial = ws.receive_json()
        assert initial["state"] == DisplayState.IDLE.value

        result = RecognitionResult(
            title="Bonito", artist="Jarabe de Palo", album=None, cover_url=None,
            offset=0.0, timeskew=0.0, frequencyskew=0.0, isrc=None, duration=None,
        )
        session.on_recognized(result, None, wall_time=0.0)
        # `ws` (the WebSocketTestSession) runs the ASGI app on its own
        # background event loop via an anyio portal. Calling
        # `app.state.broadcast()` directly here — from the test's own
        # thread, with no running loop — was verified live during planning
        # to hang forever: `asyncio.ensure_future()` outside a running
        # loop implicitly creates a throwaway loop that never actually
        # runs, so the scheduled `send_json` never executes and
        # `ws.receive_json()` below blocks indefinitely waiting for a
        # message that never arrives. Routing the call through `ws.portal`
        # runs it on the SAME loop the websocket connection lives on —
        # exactly matching how `on_change` is really invoked in production
        # (always from inside the engine's own already-running coroutine,
        # on the app's one event loop, never cross-thread).
        ws.portal.call(app.state.broadcast)

        updated = ws.receive_json()
        assert updated["state"] == DisplayState.PLAYING.value
        assert updated["track"]["title"] == "Bonito"
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/server/test_app.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.server.app'`

- [ ] **Step 4: Implement `app.py`**

```python
# vinylyrics/server/app.py
from __future__ import annotations

import asyncio
import time
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from vinylyrics.engine import Engine
from vinylyrics.state.session import PlaybackSession


def create_app(session: PlaybackSession, engine: Engine, now_fn: Callable[[], float] = time.monotonic) -> FastAPI:
    app = FastAPI()
    clients: set[WebSocket] = set()

    def broadcast() -> None:
        payload = session.to_payload(now_fn())
        for ws in list(clients):
            task = asyncio.ensure_future(ws.send_json(payload))
            # send_json only fails INSIDE the scheduled task, never at
            # ensure_future() itself — verified live during planning that
            # a try/except wrapped around ensure_future can never observe
            # a send failure, making it dead code. A disconnected client's
            # own ws_endpoint handler already removes it from `clients`
            # via its `finally` block below; this callback only guards the
            # narrow race where a client drops between broadcasts before
            # that handler has run.
            task.add_done_callback(lambda t, ws=ws: clients.discard(ws) if t.exception() else None)

    app.state.broadcast = broadcast

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/debug")
    def debug():
        return engine.debug_snapshot()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            await websocket.send_json(session.to_payload(now_fn()))
            while True:
                await websocket.receive_text()  # keepalive; client sends nothing meaningful
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    return app
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/server/test_app.py -v`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/server/app.py tests/server/test_app.py
git commit -m "feat: add FastAPI server broadcasting session state over websocket"
```

---

## Task 6: Web frontend (`vinylyrics/web/index.html`)

**Files:**
- Create: `vinylyrics/web/index.html` (inline `<style>`/`<script>`, no
  build step, no separate CSS/JS files — matches spec §8's "un solo HTML +
  CSS + JS")
- Modify: `vinylyrics/server/app.py` (serve this file at `/`)
- Test: `tests/server/test_app.py` (add one route test)

**Interfaces:**
- Consumes: the exact WebSocket JSON contract from Task 3
  (`state`/`track`/`palette`/`lyrics`/`clock`).
- Produces: a static page served at `GET /` by the same FastAPI app.

**No automated test for the page's rendering itself** — this project's
spec (§9) lists LRC parsing, the silence detector, the clock, and palette
contrast as the things needing unit tests; the page is manually verified in
a browser instead, same as this task's own verification step below.

- [ ] **Step 1: Write `vinylyrics/web/index.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vinylyrics</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%; height: 100%; overflow: hidden;
    background: #1a2733; cursor: none;
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    transition: background-color 800ms ease;
  }
  #safe-area {
    position: absolute; inset: 8%;
    display: flex; flex-direction: column; justify-content: center; align-items: center;
    overflow: hidden;
  }
  #status-line {
    color: #f0ede8; font-weight: 600; font-size: clamp(1rem, 3vw, 2rem);
    opacity: 0.8; text-align: center;
  }
  #track-line {
    color: #f0ede8; font-weight: 600; font-size: clamp(1.2rem, 4vw, 2.5rem);
    text-align: center; margin-top: 0.5em;
  }
  #lyrics-viewport {
    width: 100%; overflow: hidden; text-align: center;
    height: 27vh; /* exactly 3 lines (.lyric-line is 9vh): one dim previous
                     line, the active line, and the next line — without an
                     explicit height here, overflow:hidden clips nothing
                     (verified live: a 40-line song rendered 8+ lines
                     simultaneously instead of the windowed karaoke view
                     spec §8 describes) since the container just grows to
                     fit all of #lyrics-track's content. */
  }
  #lyrics-track {
    display: flex; flex-direction: column; align-items: center;
    transform: translateY(0); will-change: transform;
    transition: transform 250ms cubic-bezier(0.4, 0, 0.2, 1);
  }
  .lyric-line {
    font-weight: 600; color: #f0ede8;
    height: 9vh; display: flex; align-items: center; justify-content: center;
    font-size: clamp(1rem, 5vw, 3rem);
    opacity: 0.15; transform: scale(0.75);
    transition: opacity 250ms ease, transform 250ms ease;
  }
  .lyric-line.active { opacity: 1; transform: scale(1); }
  .lyric-line.next { opacity: 0.45; transform: scale(0.75); }
</style>
</head>
<body>
<div id="safe-area">
  <div id="status-line" style="display:none"></div>
  <div id="track-line" style="display:none"></div>
  <div id="lyrics-viewport">
    <div id="lyrics-track"></div>
  </div>
</div>
<script>
const STATUS_TEXT = {
  IDLE: "esperando...",
  LISTENING: "escuchando...",
  UNIDENTIFIED: "no identificado",
};

let currentPayload = null;

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (event) => {
    currentPayload = JSON.parse(event.data);
    render();
  };
  ws.onclose = () => setTimeout(connect, 1000);
}

function render() {
  const payload = currentPayload;
  if (!payload) return;

  const statusEl = document.getElementById("status-line");
  const trackEl = document.getElementById("track-line");
  document.body.style.backgroundColor = payload.palette.bg;

  if (payload.state === "PLAYING" && payload.track) {
    statusEl.style.display = "none";
    trackEl.style.display = "block";
    trackEl.textContent = `${payload.track.title} — ${payload.track.artist}`;
    trackEl.style.color = payload.palette.fg;
  } else {
    trackEl.style.display = "none";
    statusEl.style.display = "block";
    statusEl.textContent = STATUS_TEXT[payload.state] || "";
    statusEl.style.color = payload.palette.fg;
  }

  renderLyrics(payload);
}

function currentLyricIndex(payload, nowMs) {
  if (!payload.clock || !payload.lyrics || payload.lyrics.length === 0) return -1;
  const elapsedSec = (nowMs / 1000) - payload.clock.anchor_wall;
  const positionMs = payload.clock.anchor_ms + elapsedSec * payload.clock.speed * 1000;
  let idx = -1;
  for (let i = 0; i < payload.lyrics.length; i++) {
    if (payload.lyrics[i].ms <= positionMs) idx = i;
    else break;
  }
  return idx;
}

let lastRenderedIndex = -2;
let lastRenderedTrackKey = null;

function renderLyrics(payload) {
  const track = document.getElementById("lyrics-track");
  if (!payload.lyrics || payload.lyrics.length === 0) {
    track.innerHTML = "";
    lastRenderedTrackKey = null;
    return;
  }
  // Rebuild whenever the TRACK changes, not just when the line count
  // changes — verified live: two different songs whose lyrics happened to
  // have the same number of lines left the OLD song's text on screen
  // forever (only positions/highlighting kept updating), since a
  // length-only check saw no reason to rebuild.
  const trackKey = payload.track ? `${payload.track.title}|${payload.track.artist}` : null;
  if (trackKey !== lastRenderedTrackKey) {
    track.innerHTML = "";
    for (const line of payload.lyrics) {
      const div = document.createElement("div");
      div.className = "lyric-line";
      div.textContent = line.text;
      div.style.color = payload.palette.fg;
      track.appendChild(div);
    }
    lastRenderedTrackKey = trackKey;
    lastRenderedIndex = -2;
  }

  const idx = currentLyricIndex(payload, Date.now());
  if (idx === lastRenderedIndex) return;
  lastRenderedIndex = idx;

  // Center the active line in the 3-line window (see #lyrics-viewport's
  // fixed height): shift up by (idx - 1) lines so the PREVIOUS line sits
  // in the top slot, active in the middle, next in the bottom slot.
  //
  // Uses offsetHeight, NOT getBoundingClientRect().height: the latter
  // reflects the CSS `transform: scale()` each .lyric-line carries
  // (0.75 for everything but the active line, which is scale(1)) — verified
  // live: measuring a scaled-down line's rendered height and using it as
  // the per-line spacing under-shifts every offset by the same 25%,
  // compounding with every line scrolled through (a 40-line test drifted
  // ~345px off by line 20 — the "active" line ended up rendered entirely
  // outside the visible window). offsetHeight is the LAYOUT box height,
  // unaffected by transform, so it stays the true 9vh spacing regardless
  // of which line is currently scaled up.
  const lineHeight = track.children[0] ? track.children[0].offsetHeight : 0;
  track.style.transform = `translateY(${-(idx - 1) * lineHeight}px)`;

  Array.from(track.children).forEach((el, i) => {
    el.classList.remove("active", "next");
    if (i === idx) {
      el.classList.add("active");
      el.style.color = payload.palette.fg;
    } else if (i === idx + 1) {
      el.classList.add("next");
      el.style.color = payload.palette.dim;
    } else {
      el.style.color = payload.palette.dim;
    }
  });
}

function tick() {
  if (currentPayload) render();
  requestAnimationFrame(tick);
}

connect();
requestAnimationFrame(tick);
</script>
</body>
</html>
```

- [ ] **Step 2: Serve it from FastAPI**

Modify `vinylyrics/server/app.py`: add near the top,
`from pathlib import Path` and `from fastapi.responses import FileResponse`,
and inside `create_app`, after the existing route definitions:

```python
    _web_dir = Path(__file__).resolve().parent.parent / "web"

    @app.get("/")
    def index():
        return FileResponse(_web_dir / "index.html")
```

- [ ] **Step 3: Add a route test**

Add to `tests/server/test_app.py`:

```python
def test_index_serves_the_web_page():
    session = PlaybackSession()
    app = create_app(session=session, engine=_fake_engine())
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "vinylyrics" in response.text
    assert response.headers["content-type"].startswith("text/html")
```

Run: `uv run pytest tests/server/test_app.py -v`
Expected: `5 passed`

- [ ] **Step 4: Manually verify the page in a browser**

This is the one deliverable in this plan that genuinely needs eyes on it,
not just an automated test — and this is not a formality. During planning,
manually driving this exact page in a real browser (by injecting test
payloads via the console and inspecting the live DOM, not just reading the
code) found and fixed three real bugs that no unit test would have caught,
because they only show up once real pixels are laid out:

1. **`#lyrics-viewport` had no explicit height.** Without one,
   `overflow: hidden` clips nothing — the container just grows to fit
   however many lines a song has. Verified live: a synthetic 40-line song
   rendered 8+ lines simultaneously on screen instead of the windowed
   "active + next + one dim previous" view spec §8 describes. Fixed by
   giving it a fixed `height: 27vh` (exactly 3 `.lyric-line`s).
2. **Switching tracks with a coincidentally-equal line count left the old
   lyrics on screen.** The rebuild check compared `track.children.length`
   to `payload.lyrics.length` — if two different songs happened to have the
   same number of synced lines, the DOM was never rebuilt and the OLD
   song's text stayed rendered forever (only the highlighted position kept
   moving). Fixed by keying the rebuild on the track's identity
   (`title|artist`) instead of line count.
3. **The per-line scroll offset was computed from a scaled element's
   `getBoundingClientRect().height`.** Every `.lyric-line` except the
   active one carries `transform: scale(0.75)`, which
   `getBoundingClientRect()` reflects (it reports the *painted*, scaled-down
   size) — using that as the "line height" for `translateY()` under-shifts
   every offset by 25%, and the error compounds with every line advanced.
   Verified live: on the same 40-line test, by line 20 this had drifted the
   "active" line roughly 345px outside the visible window entirely — the
   karaoke display would have looked broken for any song more than a few
   lines long. Fixed by using `offsetHeight` instead, which reflects the
   element's layout box and ignores `transform` entirely.

All three are already fixed in this task's own `index.html` above — this
step is about re-confirming the fix holds, not discovering it fresh. Start
the dev server (Task 7 must be done first for this step — if executing
tasks in order, come back to this step after Task 7):

```bash
uv run vinylyrics-server --file data/vinylizer_output/dry.wav --realtime
```

Open `http://localhost:8000/` in a browser (the built-in browser tool, if
available) and confirm: the background fills the whole viewport in a solid
dark color (no white flash), the status text is legible and centered
within an 8% margin, only about 3 lines of lyrics are ever visible at once
(not the whole song), switching tracks replaces the lyric text rather than
leaving stale lines behind, and lyric lines step (don't scroll
continuously) with a visible opacity/scale difference between the active
line and its neighbors — with the active line staying inside the visible
window even well into a long song (check somewhere past line 15-20, not
just the first few lines, since that's exactly where the drift bug above
would have reappeared if the `offsetHeight` fix regressed).

**A note on verifying this yourself, if you re-check it:** a live
WebSocket-connected page updates asynchronously — if you inject a test
payload via the console on a page that's ALSO connected to a real running
server, the real server's next broadcast can silently overwrite your test
payload out from under you, and a screenshot taken in the same tool round
as a payload change can catch the page mid-CSS-transition (250ms) and show
misleading transient values. Either check with `speed: 0` in the injected
`clock` payload (freezes the karaoke position deterministically, removing
real-wall-clock timing from the picture) and re-query the DOM in a
*separate* step after the change has settled, or just watch it run
against real, continuously-updating data for a few seconds instead of a
single frozen frame.

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/web/index.html vinylyrics/server/app.py tests/server/test_app.py
git commit -m "feat: add karaoke web page served at the app root"
```

---

## Task 7: CLI entry point (`vinylyrics/server/cli.py`)

**Files:**
- Create: `vinylyrics/server/cli.py`
- Test: `tests/server/test_cli.py`

**Interfaces:**
- Consumes: `FileSource`/`LineInSource`/`list_devices` (Phase 4's
  `audio/source.py`), `ShazamIORecognizer` + `DiskRecognitionCache` (Phase
  5), `LrcLibClient`/`LyricsCache`/`LyricsService` (Phase 6), `Engine`
  (Task 4), `create_app` (Task 5/6), `config.toml`'s `[dev]`/`[pi]`
  profiles (already present from Phase 1/4, read via stdlib `tomllib`).
- Produces: `def build_argparser() -> argparse.ArgumentParser`,
  `def main() -> int` — the actual command David runs. Registered as the
  `vinylyrics-server` script in `pyproject.toml` (Task 5's Step 1).

- [ ] **Step 1: Write the failing tests**

These test argument parsing and source selection only — starting a real
`uvicorn` server isn't something to assert on in a unit test (Task 6's
manual browser step is where the full run is actually exercised).

```python
# tests/server/test_cli.py
from pathlib import Path

import pytest

from vinylyrics.server.cli import build_argparser, resolve_source


def test_parser_requires_either_file_or_line_in_default():
    parser = build_argparser()
    args = parser.parse_args([])
    assert args.file is None
    assert args.device is None  # defaults to line-in with default device


def test_parser_accepts_file_with_realtime_flag():
    parser = build_argparser()
    args = parser.parse_args(["--file", "song.wav", "--realtime"])
    assert args.file == "song.wav"
    assert args.realtime is True


def test_parser_accepts_device_and_profile_and_port():
    parser = build_argparser()
    args = parser.parse_args(["--device", "3", "--profile", "pi", "--port", "9000"])
    assert args.device == 3
    assert args.profile == "pi"
    assert args.port == 9000


def test_resolve_source_returns_file_source_when_file_given(tmp_path: Path):
    import numpy as np
    import soundfile as sf

    wav_path = tmp_path / "test.wav"
    sf.write(wav_path, np.zeros(1600, dtype="float32"), 16000)

    parser = build_argparser()
    args = parser.parse_args(["--file", str(wav_path)])
    source = resolve_source(args, sample_rate=16000)

    assert source.sample_rate == 16000


def test_resolve_source_returns_line_in_source_by_default():
    parser = build_argparser()
    args = parser.parse_args([])
    source = resolve_source(args, sample_rate=16000)

    from vinylyrics.audio.source import LineInSource
    assert isinstance(source, LineInSource)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/server/test_cli.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.server.cli'`

- [ ] **Step 3: Implement `cli.py`**

```python
# vinylyrics/server/cli.py
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

import uvicorn

from vinylyrics.audio.source import FileSource, LineInSource
from vinylyrics.engine import Engine
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.lrclib import LrcLibClient
from vinylyrics.lyrics.service import LyricsService
from vinylyrics.recognition.cache import DiskRecognitionCache
from vinylyrics.recognition.shazam import ShazamIORecognizer
from vinylyrics.server.app import create_app
from vinylyrics.state.session import PlaybackSession

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.toml"


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Corre el servidor de vinylyrics en vivo.")
    parser.add_argument("--file", default=None, help="Usa un WAV como fuente en vez del micrófono (pruebas sin turntable)")
    parser.add_argument("--realtime", action="store_true", help="Con --file, respeta el reloj de pared en vez de ir a máxima velocidad")
    parser.add_argument("--device", type=int, default=None, help="Índice del dispositivo de entrada (ver scripts/list_audio_devices.py)")
    parser.add_argument("--profile", choices=["dev", "pi"], default="dev", help="Perfil de config.toml a usar")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0", help="No cambies esto a localhost — el proyector/móvil se conectan por red")
    return parser


def _load_profile(profile: str) -> dict:
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)
    return config[profile]


def resolve_source(args: argparse.Namespace, sample_rate: int):
    if args.file:
        return FileSource(Path(args.file), realtime=args.realtime, sample_rate=sample_rate)
    return LineInSource(device=args.device, sample_rate=sample_rate)


def main() -> int:
    args = build_argparser().parse_args()
    profile = _load_profile(args.profile)
    sample_rate = profile["sample_rate"]

    source = resolve_source(args, sample_rate)
    recognizer = ShazamIORecognizer(cache=DiskRecognitionCache(Path("shazam_cache")))
    lyrics_service = LyricsService(client=LrcLibClient(), cache=LyricsCache(Path("lyrics_cache.sqlite3")))
    session = PlaybackSession()

    engine = Engine(
        source=source, recognizer=recognizer, lyrics_service=lyrics_service,
        session=session, on_change=lambda: app.state.broadcast(),
    )
    app = create_app(session=session, engine=engine)

    @app.on_event("startup")
    async def _start_engine():
        import asyncio
        asyncio.ensure_future(engine.run())

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/server/test_cli.py -v`
Expected: `5 passed`

- [ ] **Step 5: Run the full offline suite**

Run: `uv run pytest -v`
Expected: all pass. Then go back and complete Task 6's Step 4 (manual
browser verification) now that `vinylyrics-server` exists.

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/server/cli.py tests/server/test_cli.py
git commit -m "feat: add vinylyrics-server CLI wiring source, engine, and app together"
```

---

## Task 8: README, justfile, and REUSE.md wrap-up

**Files:**
- Modify: `docs/REUSE.md` (add rows for `Pillow`, `fastapi`, `uvicorn`)
- Modify: `README.md` (document running the live server, including the
  exact phone-speaker + laptop-mic test David asked for)
- Create: `justfile`

**Interfaces:**
- Consumes: nothing new — this is documentation and a task runner around
  commands that already exist after Tasks 1–7.

- [ ] **Step 1: Update `docs/REUSE.md`**

Read the existing file first, then add three rows matching its format:

- **Pillow** — HPND (a permissive, BSD-style license). Actively maintained
  (unlike `colorthief`, the spec's other suggested option for this job,
  whose last PyPI release was in 2017 — confirmed during Phase 7 planning).
  Used for `Image.quantize()`-based dominant-color extraction from the
  cover art in `vinylyrics/palette.py`.
- **fastapi** — MIT. The server framework spec §6 names directly; provides
  the WebSocket endpoint, `/health`, and `/debug`.
- **uvicorn** — BSD-3-Clause. ASGI server that actually runs the FastAPI
  app.

- [ ] **Step 2: Update `README.md`**

Add a new section after the existing "Dispositivos de audio" section:

```markdown
## Correr el servidor en vivo

```bash
uv run vinylyrics-server
```

Por defecto escucha por el micrófono (`LineInSource`, dispositivo por
defecto del sistema) y sirve en `http://0.0.0.0:8000` — cualquier
dispositivo en la misma red (el proyector, un móvil, otro portátil) puede
abrir esa URL en su navegador y ver las letras.

**Probar sin tocadiscos:** pon música desde el altavoz de un móvil cerca
del micrófono del portátil, y abre la URL de arriba desde el navegador del
propio portátil o desde otro dispositivo en la misma WiFi.

Opciones:

- `--file RUTA.wav [--realtime]`: usa un WAV en vez del micrófono (útil
  para probar sin audio real; `--realtime` respeta el reloj de pared en vez
  de ir a máxima velocidad).
- `--device N`: índice del dispositivo de entrada — ver
  `uv run scripts/list_audio_devices.py`.
- `--profile dev|pi`: perfil de `config.toml` (por defecto `dev`).
- `--port N`: puerto HTTP (por defecto 8000).
```

- [ ] **Step 3: Create the `justfile`**

```just
# vinylyrics — recetas del proyecto

inspect carpeta:
    uv run vinylizer inspect {{carpeta}}

vinylize carpeta *args:
    uv run vinylizer build {{carpeta}} {{args}}

dev:
    uv run vinylyrics-server

test:
    uv run pytest -v

lint:
    uv run python -m py_compile $(find vinylyrics -name '*.py')

# eval y eval-full llegan en la Fase 8, junto al subcomando que envuelven —
# no se declaran aquí todavía para no apuntar a un comando que no existe.
```

- [ ] **Step 4: Commit**

```bash
git add docs/REUSE.md README.md justfile
git commit -m "docs: document the live server, add justfile, register Pillow/fastapi/uvicorn in REUSE.md"
```

---

## Self-Review Notes

- **Spec coverage:** §2's sliding-window loop and RMS/silence wiring →
  Task 4 (the pieces themselves were Phase 4's; this phase is what finally
  drives them). §3's call cadence, retries, `UNIDENTIFIED` after 3 failures
  → Task 4 (`CallCadencePolicy` was Phase 5's; wiring it live is here).
  §5's latency-subtraction (anchor wall-time = buffer start, not response
  arrival) → Task 4's `_recognize_and_update`, the one line Phase 6 could
  only document. §6's WebSocket JSON contract, `/health`, `/debug` → Tasks
  3 and 5. §7's palette (HSL clamp, WCAG 7:1, fallback) → Task 2. §8's
  interface (safe margins, step-advance karaoke, states, background fade,
  cursor hidden) → Task 6.
- **No placeholders:** every step has real, planning-verified code, except
  the two justfile recipes explicitly and visibly NOT added (`eval`,
  `eval-full`) — called out as a scope boundary, not a silent gap.
- **Type/interface consistency:** `RecognitionResult.duration` (Task 1) is
  read by `PlaybackSession.on_recognized` (Task 3) and
  `Engine._recognize_and_update` (Task 4) identically. `Palette` (Task 2)
  is constructed once by `PlaybackSession` and serialized unchanged by
  `to_payload` (Task 3). `Engine.debug_snapshot()` (Task 4)'s exact keys
  (`last_recognition`, `speed`, `rms_dbfs`, `anchor_history`) are what
  Task 5's `/debug` route returns verbatim, and what Task 5's own test
  asserts against.
- **A genuine open question, flagged rather than silently decided:**
  Task 3's `to_payload` reads `PlaybackClock`'s "private" `_anchor_wall`/
  `_anchor_position` fields directly instead of adding public properties to
  Phase 6's already-merged `clock.py`. This was a deliberate call to avoid
  touching a finished, reviewed phase's file for a two-line addition — but
  it is a real interface crossing that a task reviewer should weigh, not
  something this plan is asserting is definitely right.
- **Evaluation tooling out of scope, on purpose:** spec §9's `eval`/
  `eval-full` aggregate report across all 47 songs is Phase 8's job per the
  spec's own "Orden de trabajo," not this phase's — noted wherever it's
  relevant (Global Constraints, Task 8's justfile) rather than silently
  built or silently dropped.
- **Carried forward, finally claimed:** the `justfile` (spec §10) had been
  deferred seven plans in a row. This plan claims it (Task 8) rather than
  asking an eighth time, on the reasoning that "add a justfile with the
  recipes that exist today" is a decision small and reversible enough not
  to need David's sign-off first — unlike the deferred `eval`/`eval-full`
  recipes, which really do depend on a phase that hasn't happened yet.
- **This plan's code was not just designed, it was built and run end-to-end
  in a throwaway sandbox before being written up here** — every module
  across all 7 code tasks, plus the actual `vinylyrics-server` CLI entry
  point, was implemented, tested (176 tests total added on top of the
  pre-existing 136, all offline and passing in ~5s), and — for the parts a
  test suite can't see — driven live in a real browser against a real
  running server. That last step is what caught the bugs a green test
  suite couldn't: `uvicorn` needing its `[standard]` extra for WebSockets
  to work at all in production (every `TestClient`-based test passes
  either way, since it bypasses uvicorn's real protocol layer entirely);
  three separate frontend layout bugs (`#lyrics-viewport` needing an
  explicit height to actually clip anything, stale lyrics text surviving a
  track change when the old and new song had the same line count, and a
  `getBoundingClientRect()` vs `offsetHeight` mixup that silently drifted
  the "active" line off-screen the further into a song you got); an
  engine busy-loop on end-of-stream that would have hit the very first
  time anyone followed this plan's own manual-testing instructions with a
  finite WAV file; and a test-isolation gap where several of Task 4's
  "offline" engine tests were silently making real MusicBrainz calls. All
  of these are already fixed in the task text above — this note exists so
  whoever executes this plan understands the code they're transcribing has
  already been adversarially exercised once, not merely reviewed on paper.
