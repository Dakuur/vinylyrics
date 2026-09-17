# vinylyrics Phase 6 Implementation Plan — Clock + Lyrics

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two data/logic subsystems the future server needs to
show something on screen: a `PlaybackClock` that turns Shazam anchors into
a smooth, never-jumping song position, and a lyrics pipeline (LRCLIB fetch
with a closest-duration fallback, a hand-written LRC parser since no
library on PyPI actually parses to `(ms, text)`, and a SQLite cache).

**Architecture:** `vinylyrics/lyrics/parser.py` turns raw LRC text into
`LyricLine(ms, text)` entries — verified against real LRCLIB content, not
just synthetic fixtures. `vinylyrics/lyrics/lrclib.py` wraps `lrclibapi`:
`/get` first (exact match), falling back to `/search` and picking the
result whose duration is closest to the recognized track's, when `/get`
404s (confirmed this happens routinely with real data, not a rare case).
`vinylyrics/lyrics/cache.py` is a SQLite cache keyed by
artist+title+duration. `vinylyrics/lyrics/service.py` composes client+cache
the same way Phase 5's `enrich.py` composed recognition+cover-art.
`vinylyrics/state/clock.py`'s `PlaybackClock` holds one linear
speed/anchor model, updated by `add_anchor()` calls: a brand-new song seeds
speed from Shazam's `timeskew`; two or more anchors trigger a linear
regression over recent anchors (`numpy.polyfit`) for a better speed
estimate; anchors implying a jump of more than 3s are rejected outright
(probable false match); accepted anchors never cause a position
discontinuity — the correction is spread smoothly over the next few
seconds via a decaying offset term, verified by direct execution to be
continuous at the anchor boundary down to floating-point precision.

**Tech Stack:** `lrclibapi` (new — chosen over `lrcup` per Phase 1's
research: neither library parses LRC to `(ms, text)`, but `lrclibapi`'s
typed exceptions, `NotFoundError` specifically, fit this task's
get-then-search-fallback flow better), `numpy` (already a dependency —
`polyfit` for the clock's linear regression), stdlib `sqlite3`/`re`/`json`
(no new dependency for the cache or parser).

**Spec:** [docs/SPEC.md](../../SPEC.md) §4 "Letras" and §5 "Reloj de
reproducción".

## Global Constraints

(Phases 1/2/4/5's constraints all still apply. This phase adds:)

- **No API keys.** LRCLIB needs none — only a descriptive User-Agent
  (confirmed during Phase 1's research; unchanged). Use the same
  `VINYLYRICS_USER_AGENT` value already in `.env.example`
  (`"vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)"`) — this time
  as one combined string, matching `LrcLibAPI(user_agent=...)`'s single
  parameter (unlike Phase 5's MusicBrainz client, which wanted three
  separate fields — LRCLIB's client takes the whole string directly, no
  hardcoded duplication needed here).
- **Never commit lyrics text.** `lyrics_cache.sqlite3` is already in
  `.gitignore` from Phase 1 — this phase is the first to actually create
  that file; don't remove the gitignore entry, and don't add a new cache
  filename that isn't covered by it.
- **`/get` 404ing is the normal case, not an edge case.** Verified live
  during planning: even with a real, correctly-spelled artist/title/album
  from a real Shazam response, `/get` 404'd (album name or duration didn't
  match LRCLIB's stored metadata exactly) and `/search` — picking the
  closest-duration result — is what actually found the lyrics. Every
  `LrcLibClient` test in this plan exercises the fallback path for this
  reason; don't treat a `/get` 404 as something to special-case or log as
  unusual.
- **No pitch-preserving anything, and no position jump, ever.** The clock
  mirrors the vinylizer's own "no time-stretch" rule the other direction —
  `PlaybackClock` must never assign `position()` a value that jumps
  discontinuously when a new anchor is accepted, matching spec §5's "un
  salto brusco en las letras se ve fatal." Verified by direct measurement
  (position just before vs. just after an anchor update differs by <1
  microsecond-equivalent, not the multi-hundred-millisecond correction
  being absorbed).
- **A rejected anchor changes nothing.** If `add_anchor()` returns `False`
  (implied jump > 3s), the clock's speed/anchor/history are left exactly as
  they were — the caller is expected to just keep using the existing model
  and try again with the next recognition anchor.
- **Ambiguity resolved during planning, flagged for correction:** spec §5
  says "si el error es menor de 400 ms, absórbelo ajustando velocidad
  durante los siguientes segundos," and separately caps rejection at
  anchors implying a jump of more than 3s — leaving the 400ms–3s band
  formally unspecified. This plan applies the same smooth-absorption
  mechanism uniformly across that whole accepted range (0 to 3s), reading
  "no saltes al corregir" as the general rule and "400ms" as the
  spec-writer's mental model of the *typical* case size, not a second
  distinct threshold with different handling above it. If this isn't what
  was intended, it's a one-parameter change once real data (Phase 7's live
  runs) shows it's wrong — flag it explicitly rather than silently picking
  an interpretation.
- **Roadmap correction from Phase 5's plan:** Phase 5 said the sliding-window
  orchestration loop (wiring `AudioSource`+`CircularAudioBuffer`+
  `SilenceDetector`+`CallCadencePolicy`+`Recognizer`+`PlaybackClock`+lyrics
  together into one running loop) belonged with this phase, "since the
  clock is what actually needs continuous anchors." On reflection, that's
  wrong: an orchestration engine with nothing to observe its output is
  hard to build *or verify* in isolation — you'd be staring at an in-memory
  object with no way to see it work. It belongs with Phase 7 (spec's own
  step 7, "Servidor + interfaz"), where the FastAPI server and the web page
  give the engine something real to feed and a way to actually watch it
  work end-to-end. This phase builds `PlaybackClock` and the lyrics
  pipeline as fully unit-tested, standalone modules — no consumer yet,
  same as Phase 5's `CallCadencePolicy`.
- Every module in this plan was hand-verified by actually running it
  before the plan was written: the LRC parser against real LRCLIB content
  for a real song (68 lines, correct millisecond values, correct handling
  of a trailing empty interlude line); the LRCLIB client's full
  get-404-then-search-closest-duration path against the real API; the
  clock's continuity-at-anchor-boundary, bad-anchor rejection, and
  multi-anchor regression convergence, all with real numbers, not just
  designed on paper.

---

## Roadmap Context

This is the next phase after Phase 5 (recognition, merged). Per the spec's
"Orden de trabajo," it's step 6: "Reloj + letras." Wiring these into an
actual running pipeline (spec §2's sliding-window loop, spec §6's server)
is Phase 7's job — see the Global Constraints correction above for why that
roadmap decision changed from what Phase 5's plan said.

Carried forward for the **seventh** time: spec §10's `justfile`/`Makefile`
still has no owning phase. Per Phase 5's own plan text ("that's the point
to stop deferring and ask directly"), this plan does not claim it either —
David should be asked directly whether to claim it now or keep deferring,
rather than this sentence appearing an eighth time in Phase 7's plan.

---

## Task 1: Lyrics data types and LRC parser (`lyrics/parser.py`, `lyrics/base.py`)

**Files:**
- Create: `vinylyrics/lyrics/parser.py`
- Create: `vinylyrics/lyrics/base.py`
- Test: `tests/lyrics/test_parser.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) class LyricLine`: `ms: int`, `text: str`.
  - `def parse_lrc(text: str) -> list[LyricLine]`.
  - `@dataclass(frozen=True) class LyricsResult`: `synced_lines: tuple[LyricLine, ...]`,
    `plain_lyrics: str | None`, `instrumental: bool`, with a `has_synced`
    property (`len(synced_lines) > 0`).
  - Task 3 (`lrclib.py`) calls `parse_lrc` and constructs `LyricsResult`.
    Task 2 (`cache.py`) serializes/deserializes `LyricsResult` and
    `LyricLine` for SQLite storage.

**Verified during planning:** ran `parse_lrc` against a real LRCLIB
response for "Bonito" by Jarabe de Palo (fetched live) — correctly parsed
68 lines with accented Spanish text intact, correct millisecond values
(e.g. `[00:10.97]` → `10970`), and correctly kept the trailing empty
interlude line (`[03:38.97]` with no text) as a line with `text=""` rather
than dropping it. Also verified against synthetic edge cases: metadata
tags (`[ar:]`, `[ti:]`, `[al:]`, `[length:]`) are correctly skipped (they
don't match the timestamp regex), a line with two timestamps
(`[00:20.00][00:45.50]text`) correctly produces two separate `LyricLine`
entries with the same text, and both 2-digit (`.34`) and 3-digit (`.123`)
fractional-second precision parse correctly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lyrics/test_parser.py
from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine, parse_lrc


def test_parse_lrc_skips_metadata_tags():
    text = "[ar:Jarabe de Palo]\n[ti:Bonito]\n[00:12.34]Primera linea\n"
    lines = parse_lrc(text)
    assert lines == [LyricLine(ms=12340, text="Primera linea")]


def test_parse_lrc_expands_multiple_timestamps_on_one_line():
    text = "[00:20.00][00:45.50]Estribillo repetido\n"
    lines = parse_lrc(text)
    assert lines == [
        LyricLine(ms=20000, text="Estribillo repetido"),
        LyricLine(ms=45500, text="Estribillo repetido"),
    ]


def test_parse_lrc_keeps_empty_interlude_lines():
    text = "[00:30.00]\n[00:35.00]Texto\n"
    lines = parse_lrc(text)
    assert lines == [
        LyricLine(ms=30000, text=""),
        LyricLine(ms=35000, text="Texto"),
    ]


def test_parse_lrc_handles_two_and_three_digit_fractions():
    text = "[00:12.34]Dos digitos\n[00:35.123]Tres digitos\n"
    lines = parse_lrc(text)
    assert lines[0].ms == 12340
    assert lines[1].ms == 35123


def test_parse_lrc_sorts_by_timestamp_regardless_of_source_order():
    text = "[00:45.50]Estribillo\n[00:20.00]Primera\n"
    lines = parse_lrc(text)
    assert [l.ms for l in lines] == [20000, 45500]


def test_parse_lrc_against_real_lrclib_content():
    # A real synced-lyrics excerpt fetched from LRCLIB for "Bonito" by
    # Jarabe de Palo during planning, trimmed to the first few lines plus
    # the real trailing empty interlude line.
    text = (
        "[00:10.97] Bonito, todo me parece bonito\n"
        "[00:18.97] Bonita mañana, bonito lugar\n"
        "[00:23.15] Bonita la cama, que bien se ve el mar\n"
        "[03:38.97] \n"
    )
    lines = parse_lrc(text)
    assert lines[0] == LyricLine(ms=10970, text="Bonito, todo me parece bonito")
    assert lines[1] == LyricLine(ms=18970, text="Bonita mañana, bonito lugar")
    assert lines[2] == LyricLine(ms=23150, text="Bonita la cama, que bien se ve el mar")
    assert lines[3] == LyricLine(ms=218970, text="")


def test_lyrics_result_has_synced_reflects_line_count():
    with_lines = LyricsResult(synced_lines=(LyricLine(ms=0, text="hi"),), plain_lyrics=None, instrumental=False)
    without_lines = LyricsResult(synced_lines=(), plain_lyrics="plain text only", instrumental=False)
    assert with_lines.has_synced is True
    assert without_lines.has_synced is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/lyrics/test_parser.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.lyrics'` (this is
the first file in a new package — create `vinylyrics/lyrics/__init__.py`
and `tests/lyrics/__init__.py` as empty files too, in this step)

- [ ] **Step 3: Implement `parser.py`**

```python
# vinylyrics/lyrics/parser.py
from __future__ import annotations

import re
from dataclasses import dataclass

_TIMESTAMP_RE = re.compile(r"\[(\d{2,}):(\d{2})[.:](\d{2,3})\]")


@dataclass(frozen=True)
class LyricLine:
    ms: int
    text: str


def _timestamp_to_ms(minutes: str, seconds: str, fraction: str) -> int:
    frac_digits = len(fraction)
    frac_value = int(fraction) * (10 ** (3 - frac_digits)) if frac_digits <= 3 else int(fraction[:3])
    return int(minutes) * 60_000 + int(seconds) * 1_000 + frac_value


def parse_lrc(text: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        timestamps = list(_TIMESTAMP_RE.finditer(raw_line))
        if not timestamps:
            continue  # metadata tag like [ar:...] or a stray non-lyric line
        lyric_text = _TIMESTAMP_RE.sub("", raw_line).strip()
        for m in timestamps:
            ms = _timestamp_to_ms(m.group(1), m.group(2), m.group(3))
            lines.append(LyricLine(ms=ms, text=lyric_text))
    lines.sort(key=lambda l: l.ms)
    return lines
```

- [ ] **Step 4: Implement `base.py`**

```python
# vinylyrics/lyrics/base.py
from __future__ import annotations

from dataclasses import dataclass

from vinylyrics.lyrics.parser import LyricLine


@dataclass(frozen=True)
class LyricsResult:
    synced_lines: "tuple[LyricLine, ...]"
    plain_lyrics: "str | None"
    instrumental: bool

    @property
    def has_synced(self) -> bool:
        return len(self.synced_lines) > 0
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/lyrics/test_parser.py -v`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/lyrics/__init__.py vinylyrics/lyrics/parser.py vinylyrics/lyrics/base.py tests/lyrics/__init__.py tests/lyrics/test_parser.py
git commit -m "feat: add LRC parser and lyrics data types"
```

---

## Task 2: SQLite lyrics cache (`lyrics/cache.py`)

**Files:**
- Create: `vinylyrics/lyrics/cache.py`
- Test: `tests/lyrics/test_cache.py`

**Interfaces:**
- Consumes: `LyricLine` (Task 1's `parser.py`), `LyricsResult` (Task 1's `base.py`).
- Produces: `class LyricsCache`: `__init__(self, db_path: Path)`,
  `def get(self, artist: str, title: str, duration: float) -> LyricsResult | None`,
  `def set(self, artist: str, title: str, duration: float, result: LyricsResult) -> None`.
  Task 4 (`service.py`) checks this cache before calling Task 3's client,
  and populates it after a successful fetch.

**Verified during planning:** ran the exact SQLite schema and round-trip
(insert then select, plus a genuine cache-miss on a different duration)
directly — works with stdlib `sqlite3`, no new dependency.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lyrics/test_cache.py
from pathlib import Path

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.parser import LyricLine


def test_cache_returns_none_on_miss(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    assert cache.get("Jarabe de Palo", "Bonito", 238.0) is None


def test_cache_roundtrip_with_synced_lines(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(
        synced_lines=(LyricLine(ms=1000, text="hola"), LyricLine(ms=2000, text="mundo")),
        plain_lyrics=None,
        instrumental=False,
    )
    cache.set("Jarabe de Palo", "Bonito", 238.0, result)

    fetched = cache.get("Jarabe de Palo", "Bonito", 238.0)
    assert fetched == result


def test_cache_roundtrip_with_plain_lyrics_only(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(synced_lines=(), plain_lyrics="letra sin sincronizar", instrumental=False)
    cache.set("Artist", "Title", 200.0, result)

    fetched = cache.get("Artist", "Title", 200.0)
    assert fetched == result


def test_cache_roundtrip_instrumental(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(synced_lines=(), plain_lyrics=None, instrumental=True)
    cache.set("Artist", "Instrumental Track", 180.0, result)

    fetched = cache.get("Artist", "Instrumental Track", 180.0)
    assert fetched.instrumental is True


def test_cache_key_rounds_duration_to_nearest_second(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    result = LyricsResult(synced_lines=(), plain_lyrics="x", instrumental=False)
    cache.set("Artist", "Title", 200.4, result)

    assert cache.get("Artist", "Title", 200.0) == result
    assert cache.get("Artist", "Title", 200.49) == result


def test_cache_creates_db_file_if_missing(tmp_path: Path):
    db_path = tmp_path / "nested" / "lyrics.sqlite3"
    assert not db_path.exists()
    LyricsCache(db_path)
    assert db_path.exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/lyrics/test_cache.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.lyrics.cache'`

- [ ] **Step 3: Implement `cache.py`**

```python
# vinylyrics/lyrics/cache.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import LyricLine


class LyricsCache:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lyrics_cache (
                artist TEXT NOT NULL,
                title TEXT NOT NULL,
                duration INTEGER NOT NULL,
                synced_lines_json TEXT NOT NULL,
                plain_lyrics TEXT,
                instrumental INTEGER NOT NULL,
                PRIMARY KEY (artist, title, duration)
            )
            """
        )
        self._conn.commit()

    def get(self, artist: str, title: str, duration: float) -> "LyricsResult | None":
        row = self._conn.execute(
            "SELECT synced_lines_json, plain_lyrics, instrumental FROM lyrics_cache "
            "WHERE artist = ? AND title = ? AND duration = ?",
            (artist, title, round(duration)),
        ).fetchone()
        if row is None:
            return None
        synced_lines_json, plain_lyrics, instrumental = row
        lines = tuple(LyricLine(ms=item["ms"], text=item["text"]) for item in json.loads(synced_lines_json))
        return LyricsResult(synced_lines=lines, plain_lyrics=plain_lyrics, instrumental=bool(instrumental))

    def set(self, artist: str, title: str, duration: float, result: "LyricsResult") -> None:
        synced_lines_json = json.dumps([{"ms": l.ms, "text": l.text} for l in result.synced_lines])
        self._conn.execute(
            "INSERT OR REPLACE INTO lyrics_cache VALUES (?, ?, ?, ?, ?, ?)",
            (artist, title, round(duration), synced_lines_json, result.plain_lyrics, int(result.instrumental)),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/lyrics/test_cache.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/lyrics/cache.py tests/lyrics/test_cache.py
git commit -m "feat: add SQLite lyrics cache keyed by artist+title+duration"
```

---

## Task 3: LRCLIB client with closest-duration fallback (`lyrics/lrclib.py`)

**Files:**
- Modify: `pyproject.toml` (add `lrclibapi>=0.3.1` to `dependencies`)
- Create: `vinylyrics/lyrics/lrclib.py`
- Test: `tests/lyrics/test_lrclib.py`
- Test: `tests/lyrics/test_lrclib_network.py`

**Interfaces:**
- Consumes: `LyricsResult` (Task 1's `base.py`), `parse_lrc` (Task 1's `parser.py`).
- Produces: `class LrcLibClient`: `__init__(self, user_agent: str = DEFAULT_USER_AGENT, api=None)`,
  `def fetch(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None"`.
  The `api` parameter exists so tests can inject a fake object instead of
  touching the real network — same pattern as Phase 5's `ShazamIORecognizer(client=...)`.
  Task 4 (`service.py`) calls `fetch()` on a cache miss.

**Verified during planning:** ran this exact client against the real
LRCLIB API for "Bonito" by Jarabe de Palo with a deliberately wrong album
name and duration (simulating what Shazam's metadata will realistically
look like) — `/get` 404'd exactly as expected, `/search` returned 20
candidates with durations 226/238/252/254s, and picking the
closest-to-`238` one returned real, correctly-parseable synced lyrics (68
lines). This confirms the fallback path isn't just a defensive nicety —
it's the path that actually finds lyrics in realistic conditions.

- [ ] **Step 1: Add the `lrclibapi` dependency**

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
]
```

Run: `uv sync` — confirm it installs with no errors.

- [ ] **Step 2: Write the failing offline tests**

```python
# tests/lyrics/test_lrclib.py
from dataclasses import dataclass, field
from unittest import mock

from vinylyrics.lyrics.lrclib import LrcLibClient
from lrclib.exceptions import NotFoundError


def _not_found_error() -> NotFoundError:
    # NotFoundError.__init__ reads .status_code/.reason/.url/.text/.headers
    # off its argument (expects a real requests.Response) — a MagicMock
    # satisfies that without needing a real HTTP response object.
    return NotFoundError(mock.MagicMock())


@dataclass
class _FakeLyricsItem:
    synced_lyrics: "str | None" = None
    plain_lyrics: "str | None" = None
    duration: "float | None" = None
    instrumental: bool = False


class _FakeApi:
    def __init__(self, get_result=None, get_raises=None, search_results=None, search_raises=None):
        self._get_result = get_result
        self._get_raises = get_raises
        self._search_results = search_results or []
        self._search_raises = search_raises
        self.get_calls = 0
        self.search_calls = 0

    def get_lyrics(self, track_name, artist_name, album_name, duration):
        self.get_calls += 1
        if self._get_raises is not None:
            raise self._get_raises
        return self._get_result

    def search_lyrics(self, track_name, artist_name):
        self.search_calls += 1
        if self._search_raises is not None:
            raise self._search_raises
        return self._search_results


def test_fetch_uses_get_result_when_found():
    api = _FakeApi(get_result=_FakeLyricsItem(synced_lyrics="[00:01.00]hola\n", plain_lyrics=None, instrumental=False))
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result.has_synced
    assert result.synced_lines[0].text == "hola"
    assert api.search_calls == 0  # /get succeeded, /search never tried


def test_fetch_falls_back_to_search_on_not_found():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[
            _FakeLyricsItem(synced_lyrics="[00:01.00]lejos\n", duration=100.0),
            _FakeLyricsItem(synced_lyrics="[00:01.00]cerca\n", duration=201.0),
        ],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert api.get_calls == 1
    assert api.search_calls == 1
    assert result.synced_lines[0].text == "cerca"  # duration 201 is closer to 200 than 100


def test_fetch_returns_none_when_search_finds_nothing_useful():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[_FakeLyricsItem(synced_lyrics=None, plain_lyrics=None, instrumental=False, duration=200.0)],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result is None


def test_fetch_returns_none_when_search_itself_fails():
    api = _FakeApi(get_raises=_not_found_error(), search_raises=ConnectionError("boom"))
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result is None


def test_fetch_prefers_instrumental_candidate_over_nothing():
    api = _FakeApi(
        get_raises=_not_found_error(),
        search_results=[_FakeLyricsItem(instrumental=True, duration=200.0)],
    )
    client = LrcLibClient(api=api)

    result = client.fetch("Artist", "Title", "Album", 200.0)

    assert result is not None
    assert result.instrumental is True
    assert result.has_synced is False
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/lyrics/test_lrclib.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.lyrics.lrclib'`

- [ ] **Step 4: Implement `lrclib.py`**

```python
# vinylyrics/lyrics/lrclib.py
from __future__ import annotations

from lrclib import LrcLibAPI
from lrclib.exceptions import NotFoundError

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.parser import parse_lrc

DEFAULT_USER_AGENT = "vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)"


def _to_lyrics_result(item) -> LyricsResult:
    synced = getattr(item, "synced_lyrics", None)
    lines = tuple(parse_lrc(synced)) if synced else ()
    return LyricsResult(
        synced_lines=lines,
        plain_lyrics=getattr(item, "plain_lyrics", None),
        instrumental=bool(getattr(item, "instrumental", False)),
    )


class LrcLibClient:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, api=None):
        self._api = api if api is not None else LrcLibAPI(user_agent=user_agent)

    def fetch(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None":
        try:
            item = self._api.get_lyrics(
                track_name=title, artist_name=artist, album_name=album or "", duration=int(round(duration))
            )
            return _to_lyrics_result(item)
        except NotFoundError:
            pass
        except Exception:
            return None

        try:
            results = self._api.search_lyrics(track_name=title, artist_name=artist)
        except Exception:
            return None

        candidates = [
            r for r in results
            if getattr(r, "synced_lyrics", None) or getattr(r, "plain_lyrics", None) or getattr(r, "instrumental", False)
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda r: abs((getattr(r, "duration", None) or 0) - duration))
        return _to_lyrics_result(best)
```

- [ ] **Step 5: Run to verify the offline tests pass**

Run: `uv run pytest tests/lyrics/test_lrclib.py -v`
Expected: `5 passed`

- [ ] **Step 6: Write and run the network test**

```python
# tests/lyrics/test_lrclib_network.py
import pytest

from vinylyrics.lyrics.lrclib import LrcLibClient


@pytest.mark.network
def test_fetch_finds_real_lyrics_via_search_fallback():
    client = LrcLibClient()
    # Deliberately wrong album/duration, matching what Shazam's real metadata
    # will realistically look like — this exercises the /get-404-then-/search
    # path, which is the one that actually works in practice (verified during
    # planning: /get 404s here every time, /search finds it).
    result = client.fetch("Jarabe de Palo", "Bonito", "Depende", 238.0)

    assert result is not None
    assert result.has_synced
    assert any("bonito" in line.text.lower() for line in result.synced_lines)
```

Run: `uv run pytest tests/lyrics/test_lrclib_network.py -v -m network`
Expected: `1 passed` (needs internet access)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock vinylyrics/lyrics/lrclib.py tests/lyrics/test_lrclib.py tests/lyrics/test_lrclib_network.py
git commit -m "feat: add LRCLIB client with closest-duration search fallback"
```

---

## Task 4: Lyrics service composing client + cache (`lyrics/service.py`)

**Files:**
- Create: `vinylyrics/lyrics/service.py`
- Test: `tests/lyrics/test_service.py`

**Interfaces:**
- Consumes: `LrcLibClient` (Task 3), `LyricsCache` (Task 2), `LyricsResult` (Task 1).
- Produces: `class LyricsService`: `__init__(self, client: LrcLibClient, cache: LyricsCache)`,
  `def get_lyrics(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None"`.
  A later phase's orchestration engine (Phase 7) calls this once per
  newly-identified track — mirrors Phase 5's `recognize_with_cover_art`
  composition pattern exactly (check cache, fetch on miss, store on hit).

- [ ] **Step 1: Write the failing tests**

```python
# tests/lyrics/test_service.py
from pathlib import Path
from unittest import mock

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.parser import LyricLine
from vinylyrics.lyrics.service import LyricsService


def test_service_returns_cached_result_without_calling_client(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    cached_result = LyricsResult(synced_lines=(LyricLine(ms=0, text="cached"),), plain_lyrics=None, instrumental=False)
    cache.set("Artist", "Title", 200.0, cached_result)

    fake_client = mock.MagicMock()
    service = LyricsService(client=fake_client, cache=cache)

    result = service.get_lyrics("Artist", "Title", "Album", 200.0)

    assert result == cached_result
    fake_client.fetch.assert_not_called()


def test_service_fetches_and_caches_on_miss(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    fetched_result = LyricsResult(synced_lines=(LyricLine(ms=0, text="fresh"),), plain_lyrics=None, instrumental=False)
    fake_client = mock.MagicMock()
    fake_client.fetch.return_value = fetched_result
    service = LyricsService(client=fake_client, cache=cache)

    result = service.get_lyrics("Artist", "Title", "Album", 200.0)

    assert result == fetched_result
    fake_client.fetch.assert_called_once_with("Artist", "Title", "Album", 200.0)
    assert cache.get("Artist", "Title", 200.0) == fetched_result


def test_service_does_not_cache_a_failed_fetch(tmp_path: Path):
    cache = LyricsCache(tmp_path / "lyrics.sqlite3")
    fake_client = mock.MagicMock()
    fake_client.fetch.return_value = None
    service = LyricsService(client=fake_client, cache=cache)

    result = service.get_lyrics("Artist", "Title", "Album", 200.0)

    assert result is None
    assert cache.get("Artist", "Title", 200.0) is None
    assert fake_client.fetch.call_count == 1

    # a second call should retry the client, not be stuck with a cached failure
    service.get_lyrics("Artist", "Title", "Album", 200.0)
    assert fake_client.fetch.call_count == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/lyrics/test_service.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.lyrics.service'`

- [ ] **Step 3: Implement `service.py`**

```python
# vinylyrics/lyrics/service.py
from __future__ import annotations

from vinylyrics.lyrics.base import LyricsResult
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.lrclib import LrcLibClient


class LyricsService:
    def __init__(self, client: LrcLibClient, cache: LyricsCache):
        self._client = client
        self._cache = cache

    def get_lyrics(self, artist: str, title: str, album: "str | None", duration: float) -> "LyricsResult | None":
        cached = self._cache.get(artist, title, duration)
        if cached is not None:
            return cached

        result = self._client.fetch(artist, title, album, duration)
        if result is not None:
            self._cache.set(artist, title, duration, result)
        return result
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/lyrics/test_service.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add vinylyrics/lyrics/service.py tests/lyrics/test_service.py
git commit -m "feat: add lyrics service composing LRCLIB client and cache"
```

---

## Task 5: Playback clock (`state/clock.py`)

**Files:**
- Create: `vinylyrics/state/clock.py`
- Test: `tests/state/test_clock.py`

**Interfaces:**
- Consumes: nothing (pure `numpy`, no dependency on Tasks 1-4).
- Produces:
  - `@dataclass(frozen=True) class ClockConfig`: `min_speed: float = 0.97`,
    `max_speed: float = 1.03`, `reject_threshold_sec: float = 3.0`,
    `absorb_window_sec: float = 4.0`, `max_history: int = 8`.
  - `class PlaybackClock`: `__init__(self, config: ClockConfig = ClockConfig())`,
    `@property is_anchored -> bool`, `@property speed -> float`,
    `def position(self, now: float) -> float | None`,
    `def add_anchor(self, wall_time: float, position_sec: float, timeskew: float = 0.0) -> bool`
    (returns `True` if accepted, `False` if rejected as a probable false match).
  - A later phase's orchestration engine constructs one `PlaybackClock` per
    identified song (a NEW song means a NEW `PlaybackClock` instance — this
    class has no concept of "which song," that's the caller's job, same
    boundary as `CallCadencePolicy` not knowing about audio) and calls
    `add_anchor()` once per successful recognition, `position(time.monotonic())`
    at render/broadcast time.

**Design note — why `position()` never jumps:** when `add_anchor()` accepts
a new anchor with a nonzero prediction error, it doesn't snap `position()`
to the anchor's exact value going forward. Instead, it records the error
and subtracts a linearly-decaying fraction of it from every `position()`
call for the next `absorb_window_sec` — at the instant of acceptance, that
subtracted fraction is 100% of the error, which exactly cancels out the
jump (verified: continuous to within floating-point precision); by the end
of the window, the fraction is 0% and the position matches the new anchor
model exactly. Note the ambiguity called out in Global Constraints:
"absorb" is applied for any accepted anchor (up to the 3s rejection
threshold), not only the <400ms case spec §5 explicitly names.

**Verified during planning:** ran this exact implementation with real
numbers: a single anchor's `speed` seeds correctly from `timeskew`
(`1.0 + 0.005` → `1.005`, and `position()` extrapolates correctly from
there); a second anchor implying a 0.3s error produces `position()` values
that are continuous across the anchor boundary (difference on the order of
1e-6, i.e. floating-point noise, not the 0.3s correction) and fully
converges to the new model after exactly `absorb_window_sec`; an anchor
implying a 40s jump is correctly rejected (`add_anchor` returns `False`,
`speed` unchanged); five anchors sampled from a track with a true constant
speed of `1.008` converge the regression to `1.008` almost exactly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/state/test_clock.py
import pytest

from vinylyrics.state.clock import ClockConfig, PlaybackClock


def test_clock_starts_unanchored():
    clock = PlaybackClock()
    assert clock.is_anchored is False
    assert clock.position(0.0) is None


def test_first_anchor_seeds_speed_from_timeskew():
    clock = PlaybackClock()
    clock.add_anchor(wall_time=100.0, position_sec=30.0, timeskew=0.005)
    assert clock.speed == pytest.approx(1.005)
    assert clock.position(105.0) == pytest.approx(30.0 + 5.0 * 1.005)


def test_accepted_anchor_never_causes_a_position_jump():
    clock = PlaybackClock()
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.0)

    just_before = clock.position(10.0 - 1e-6)
    accepted = clock.add_anchor(wall_time=10.0, position_sec=10.3, timeskew=0.0)
    just_after = clock.position(10.0)

    assert accepted is True
    assert just_after == pytest.approx(just_before, abs=1e-4)


def test_accepted_anchor_fully_absorbed_after_the_window():
    config = ClockConfig(absorb_window_sec=4.0)
    clock = PlaybackClock(config)
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.0)
    clock.add_anchor(wall_time=10.0, position_sec=10.3, timeskew=0.0)

    at_window_end = clock.position(10.0 + config.absorb_window_sec)
    expected = 10.3 + clock.speed * config.absorb_window_sec
    assert at_window_end == pytest.approx(expected, abs=1e-6)


def test_anchor_implying_large_jump_is_rejected():
    clock = PlaybackClock()
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.0)

    accepted = clock.add_anchor(wall_time=10.0, position_sec=50.0, timeskew=0.0)

    assert accepted is False
    assert clock.speed == pytest.approx(1.0)


def test_speed_converges_via_regression_over_multiple_anchors():
    clock = PlaybackClock()
    true_speed = 1.008
    for t in (0.0, 10.0, 20.0, 30.0, 40.0):
        clock.add_anchor(wall_time=t, position_sec=true_speed * t, timeskew=0.0)

    assert clock.speed == pytest.approx(true_speed, abs=1e-6)


def test_speed_is_clamped_to_configured_range():
    config = ClockConfig(min_speed=0.97, max_speed=1.03)
    clock = PlaybackClock(config)
    clock.add_anchor(wall_time=0.0, position_sec=0.0, timeskew=0.5)  # absurd timeskew
    assert clock.speed == pytest.approx(1.03)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/state/test_clock.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.state.clock'` —
create `vinylyrics/state/__init__.py` and `tests/state/__init__.py` as
empty files if they don't already exist (check first — Phase 1's plan
created `vinylyrics/state/__init__.py` as an empty placeholder already).

- [ ] **Step 3: Implement `clock.py`**

```python
# vinylyrics/state/clock.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class ClockConfig:
    min_speed: float = 0.97
    max_speed: float = 1.03
    reject_threshold_sec: float = 3.0
    absorb_window_sec: float = 4.0
    max_history: int = 8


class PlaybackClock:
    def __init__(self, config: ClockConfig = ClockConfig()):
        self._config = config
        self._speed = 1.0
        self._anchor_wall: "float | None" = None
        self._anchor_position: "float | None" = None
        self._history: list[tuple[float, float]] = []
        self._correction_start: "float | None" = None
        self._correction_error = 0.0

    @property
    def is_anchored(self) -> bool:
        return self._anchor_wall is not None

    @property
    def speed(self) -> float:
        return self._speed

    def position(self, now: float) -> "float | None":
        if not self.is_anchored:
            return None
        base = self._speed * (now - self._anchor_wall) + self._anchor_position
        if self._correction_start is not None:
            elapsed = now - self._correction_start
            if elapsed < self._config.absorb_window_sec:
                remaining_fraction = 1.0 - elapsed / self._config.absorb_window_sec
                base -= self._correction_error * remaining_fraction
        return base

    def add_anchor(self, wall_time: float, position_sec: float, timeskew: float = 0.0) -> bool:
        cfg = self._config

        if not self.is_anchored:
            self._speed = _clamp(1.0 + timeskew, cfg.min_speed, cfg.max_speed)
            self._anchor_wall = wall_time
            self._anchor_position = position_sec
            self._history = [(wall_time, position_sec)]
            self._correction_start = None
            return True

        predicted = self.position(wall_time)
        error = position_sec - predicted
        if abs(error) > cfg.reject_threshold_sec:
            return False

        self._history.append((wall_time, position_sec))
        if len(self._history) > cfg.max_history:
            self._history = self._history[-cfg.max_history :]

        if len(self._history) >= 2:
            times = np.array([t for t, _ in self._history])
            positions = np.array([p for _, p in self._history])
            slope, _intercept = np.polyfit(times, positions, 1)
            self._speed = _clamp(float(slope), cfg.min_speed, cfg.max_speed)

        self._correction_start = wall_time
        self._correction_error = error
        self._anchor_wall = wall_time
        self._anchor_position = position_sec
        return True
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/state/test_clock.py -v`
Expected: `7 passed`

- [ ] **Step 5: Run the full offline suite**

Run: `uv run pytest -v`
Expected: all tests pass — Phases 1/2/4/5's 104, plus this phase's Task 1
(7) + Task 2 (6) + Task 3 (5 offline) + Task 4 (3) + Task 5 (7) = 132
total offline. The 4 network tests (3 from Phase 5, 1 new from this
phase's Task 3) are excluded by default and run separately with `-m network`.

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/state/clock.py tests/state/test_clock.py
git commit -m "feat: add playback clock with linear regression and smooth correction"
```

---

## Task 6: Reuse docs and a real smoke test

**Files:**
- Modify: `docs/REUSE.md` (add `lrclibapi`)
- Create: `scripts/try_lyrics.py`

**Interfaces:**
- Consumes: `LrcLibClient` (Task 3), `LyricsCache` (Task 2), `LyricsService`
  (Task 4).
- Produces: a standalone script demonstrating the full fetch→cache→parse
  pipeline against real LRCLIB data, following the same precedent as
  `scripts/try_recognize.py` (Phase 5) and `scripts/list_audio_devices.py`
  (Phase 4) — a manual tool for David to try against real songs before any
  orchestration engine exists to call this automatically.

- [ ] **Step 1: Update `docs/REUSE.md`**

Read the existing file first (it has rows for `mutagen`, `python-dotenv`,
`pytest`, `hatchling`, `numpy`, `pedalboard`, `soundfile`, `shazamio`,
`musicbrainzngs`, `requests`). Add one more row matching its format:
- **lrclibapi** — MIT. LRCLIB API client (`/get` then `/search` fallback).
  Chosen over the alternative `lrcup` during Phase 1's research: neither
  library parses LRC text into `(ms, text)` pairs, but `lrclibapi`'s typed
  exceptions (`NotFoundError` specifically) fit this project's
  get-then-search-fallback flow more directly — the LRC parsing itself is
  hand-written (`vinylyrics/lyrics/parser.py`), verified against real
  LRCLIB content during Phase 6 planning.

- [ ] **Step 2: Write `scripts/try_lyrics.py`**

```python
#!/usr/bin/env python3
"""Prueba manual: busca letras sincronizadas en LRCLIB para una canción,
las cachea en SQLite, y las imprime.

No hay todavía un motor que llame a esto automáticamente (eso es la Fase 7)
- este script es solo para probar el pipeline de letras contra datos reales,
igual que scripts/try_recognize.py probó el reconocimiento antes de que
existiera el módulo real.

Uso:
    uv run scripts/try_lyrics.py "Jarabe de Palo" "Bonito" --album Depende --duration 238
    uv run scripts/try_lyrics.py "Jarabe de Palo" "Bonito" --duration 238  # sin álbum
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.lrclib import LrcLibClient
from vinylyrics.lyrics.service import LyricsService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("artist")
    parser.add_argument("title")
    parser.add_argument("--album", default=None)
    parser.add_argument("--duration", type=float, required=True, help="Duración en segundos")
    args = parser.parse_args()

    cache = LyricsCache(Path("lyrics_cache.sqlite3"))
    service = LyricsService(client=LrcLibClient(), cache=cache)

    start = time.monotonic()
    result = service.get_lyrics(args.artist, args.title, args.album, args.duration)
    elapsed = time.monotonic() - start

    print(f"Tiempo: {elapsed:.2f}s")

    if result is None:
        print("No se encontraron letras.")
        return 1

    if result.instrumental:
        print("Pista instrumental — sin letra, solo color y título.")
        return 0

    if not result.has_synced:
        print("Solo letra sin sincronizar — solo color y título, sin karaoke.")
        print(result.plain_lyrics or "(sin texto)")
        return 0

    print(f"{len(result.synced_lines)} líneas sincronizadas:")
    for line in result.synced_lines[:10]:
        minutes, seconds = divmod(line.ms // 1000, 60)
        print(f"  [{minutes:02d}:{seconds:02d}] {line.text}")
    if len(result.synced_lines) > 10:
        print(f"  ... y {len(result.synced_lines) - 10} más")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the smoke test twice to demonstrate the cache**

```bash
rm -f lyrics_cache.sqlite3
uv run scripts/try_lyrics.py "Jarabe de Palo" "Bonito" --album Depende --duration 238
uv run scripts/try_lyrics.py "Jarabe de Palo" "Bonito" --album Depende --duration 238
```

Expected: the first run takes a real network round-trip (both the `/get`
404 and the `/search` fallback — likely under 1s combined, but real
network latency); the second run should be visibly faster since it's
served from `lyrics_cache.sqlite3` (already gitignored from Phase 1)
without any network call. Report both elapsed times in your report — same
pattern as Phase 5's cache-demo step, and note if this phase avoids that
phase's masking problem (nothing else in this pipeline does an uncached
network call the way Phase 5's cover-art lookup did, so the speedup should
actually be visible this time).

- [ ] **Step 4: Commit**

```bash
git add docs/REUSE.md scripts/try_lyrics.py
git commit -m "feat: add lyrics smoke-test script and document lrclibapi"
```

(`lyrics_cache.sqlite3` itself is already gitignored — do not add it.)

---

## Self-Review Notes

- **Spec coverage:** §4's `/get` then `/search`-by-closest-duration →
  Task 3. LRC parsing to `(ms, text)`, multiple timestamps, empty
  interlude lines, `[ar:]`/`[ti:]` metadata skipped → Task 1. Unsynced-only
  or instrumental → shown via `has_synced`/`instrumental` on
  `LyricsResult`, consumed by a later phase's frontend (not built here).
  SQLite cache by artist+title+duration, never committing lyrics → Task 2
  + the pre-existing `.gitignore` entry. User-Agent → Task 3.
  §5's anchor model, timeskew-seeded speed, regression over ≥2 anchors,
  [0.97,1.03] clamp, >3s rejection, no-jump absorption → Task 5.
- **No placeholders:** every step has real, planning-verified code.
- **Type/interface consistency:** `LyricsResult`/`LyricLine` (Task 1) are
  constructed identically by `lrclib.py`'s `_to_lyrics_result` (Task 3) and
  serialized/deserialized unchanged by `cache.py` (Task 2); `service.py`
  (Task 4) passes them through without modification. `LrcLibClient`/
  `LyricsCache` (Tasks 2-3) are consumed by `LyricsService` (Task 4) via
  constructor injection, mirroring Phase 5's `ShazamIORecognizer(client=...)`
  pattern exactly. `PlaybackClock` (Task 5) has no dependency on any other
  task in this phase — verified independent, matching `CallCadencePolicy`'s
  precedent from Phase 5.
- **Roadmap correction made explicit, not silently changed:** Phase 5's
  plan said the orchestration loop belonged here; this plan's Global
  Constraints section explains why that's revised to Phase 7, so anyone
  reading both plans in sequence sees the correction rather than being
  confused by a dropped commitment.
- **Ambiguity flagged, not silently resolved:** the 400ms-vs-3s absorption
  band (spec §5) has one interpretation implemented and clearly marked as
  a judgment call in Global Constraints, the same way Phase 4 flagged its
  TRACK_GAP duration-range interpretation.
- **Carried forward again (now the eighth time it will need to NOT be
  written again):** spec §10's `justfile`/`Makefile`. Phase 7's plan should
  either claim it or ask David directly — the "keep deferring" option is
  spent.
