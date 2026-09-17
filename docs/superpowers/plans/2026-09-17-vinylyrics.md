# vinylyrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a system that listens to a turntable's line-out, identifies the
playing track, and projects a solid-color background (derived from the cover
art) with karaoke-style synced lyrics.

**Architecture:** An abstract `AudioSource` (line-in on the Pi, WAV file for
dev/eval) feeds a circular buffer; a sliding-window recognizer (Shazam via
`shazamio`) anchors a linear playback clock; a lyrics module (LRCLIB) maps that
clock to karaoke lines; FastAPI pushes clock+state over a WebSocket to a
plain HTML/CSS/JS frontend that interpolates locally at 60fps. A separate
offline CLI (`vinylizer`) synthesizes vinyl-degraded test WAVs with ground
truth, used for evaluation instead of real turntable hardware (none is
available yet).

**Tech Stack:** Python 3.11+ / `uv`, `shazamio` (+`shazamio-core`), `lrclibapi`,
`musicbrainzngs`, `mutagen`, `soundfile`, `sounddevice`, `scipy`/`numpy`,
`pedalboard`, `colorthief`, `Pillow`, FastAPI + `uvicorn[standard]`, plain
HTML/CSS/JS (no build step), `pytest`.

**Spec:** [docs/SPEC.md](../../SPEC.md) — verbatim spec from David, plus a
"Decisiones tomadas..." section at the end recording the reuse-research
conclusions this plan is built on. Read both together.

## Global Constraints

- Python 3.11+, managed with `uv`. No other package manager.
- `sounddevice` must import cleanly on a machine with zero audio devices
  (lazy device selection everywhere — never touch a device at import time).
- No API keys in the core path (shazamio, LRCLIB, MusicBrainz/Cover Art Archive
  need none). Never invent a key, never commit one. Any optional keyed service
  (Discogs, AudD, ACRCloud, Last.fm, Spotify) requires asking David first.
- All config via environment variables: `.env.example` versioned with every
  variable documented and empty/placeholder-commented, `.env` gitignored.
- Never fabricate missing ID3 metadata. A track missing artist or title is
  reported and excluded by default, never guessed.
- Vinylizer speed changes are resampling, never pitch-preserving time-stretch.
- Lyrics text is never committed (`.gitignore`) — copyrighted, community data.
- License: **GPLv3** (not MIT — see docs/SPEC.md "Decisiones tomadas"). Every
  new file's header/README must reflect GPLv3, not MIT.
- Network-touching tests are marked `@pytest.mark.network`; `pytest -m "not network"`
  (the default local run) must pass with zero network access.
- Reuse audit: every third-party dependency and every idea borrowed from a
  reference repo (Spindle, eyeliner, now-playing, real-time-lyrics,
  vinyl-player) is recorded in `docs/REUSE.md` as it's introduced, not
  batched at the end.

---

## Roadmap (spec §"Orden de trabajo")

This plan only breaks **Phase 1** into bite-sized tasks. Each later phase gets
its own plan doc, written after the phase before it is reviewed and merged —
per David's explicit "no lo hagas todo de golpe."

1. **Reuse research** — done (see docs/SPEC.md "Decisiones tomadas" and the
   chat conclusions). No code.
2. **Phase 1 (this plan): scaffold + `inspect`.** `vinylyrics/vinylizer/library.py`
   scans the 47 mp3s in `/home/dakur/Downloads/songs` with `mutagen`, reports
   title/artist/album/duration/missing-tags as a table, excludes tracks
   missing artist or title by default. Ships as `vinylizer inspect <dir>`.
3. **Phase 2: vinylizer `build`.** `vinylyrics/vinylizer/{speed,noise,build}.py`
   — wow/flutter LFO resampling (ported from vinyl-player's algorithm),
   constant speed offset, pink-noise surface + Poisson clicks, rumble, 12kHz
   shelf (via `pedalboard.LowShelfFilter`/custom biquad — TBD which, decided
   in that plan), lead-in/gap/lead-out structure, `.truth.json` writer, TOML
   params. `--dry`, `--tracks N` (default 6, seeded), `--all`.
4. **Phase 3: audio sources + silence detector.** `vinylyrics/audio/source.py`
   (`AudioSource` protocol, `LineInSource`, `FileSource`), `vinylyrics/audio/vad.py`
   (RMS windows, hysteresis silence detector calibrated against the lead-in
   noise floor, `TRACK_GAP`/`STOPPED` events). Unit tests with synthetic
   signals — no hardware or files needed.
5. **Phase 4: recognition.** `vinylyrics/recognition/{base,shazam,cache}.py` —
   `Recognizer` protocol, `ShazamIORecognizer` wrapping `shazamio`, call
   cadence policy (≥8s / immediately after `TRACK_GAP` / 45s resync once
   locked), backoff + 3-failure→`UNIDENTIFIED`, disk cache keyed by audio-hash,
   MusicBrainz+Cover Art Archive cover art lookup with Shazam-art fallback.
   Tested first against one loose audio fragment, per spec, before wiring into
   the sliding window.
6. **Phase 5: clock + lyrics.** `vinylyrics/state/clock.py` (linear
   anchor/speed model, regression over ≥2 anchors, [0.97,1.03] clamp, >3s
   jump rejection, <400ms soft absorption), `vinylyrics/lyrics/{lrclib,parser,cache}.py`
   (`lrclibapi` client + hand-written LRC→`(ms,text)` parser, SQLite cache).
7. **Phase 6: server + interface.** FastAPI app, WebSocket state push (clock,
   not current line), `/health`, `/debug`; single `web/index.html` +
   `web/app.js` + `web/style.css` implementing the karaoke transform/opacity
   rules, palette module (`vinylyrics/state/palette.py`, HSL clamp + WCAG
   7:1 iterative darkening).
8. **Phase 7: evaluation.** `eval` (one side, fast mode, vs `.truth.json`) and
   `eval-full` (all 47 tracks, all sides) commands producing the stdout table
   + JSON report described in the spec.

---

## Phase 1 — Tasks

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `vinylyrics/__init__.py`
- Create: `vinylyrics/vinylizer/__init__.py`
- Create: `vinylyrics/audio/__init__.py`
- Create: `vinylyrics/recognition/__init__.py`
- Create: `vinylyrics/lyrics/__init__.py`
- Create: `vinylyrics/state/__init__.py`
- Create: `vinylyrics/server/__init__.py`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.toml`

**Interfaces:**
- Produces: an installable `vinylyrics` package (editable install via `uv`),
  a `vinylizer` console-script entry point (wired to `vinylyrics.vinylizer.cli:main`,
  implemented in Task 3), a `pytest` command that runs offline by default.

- [ ] **Step 1: Check `uv` is available, install it if not**

Run: `uv --version`

If missing:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Expected: prints a version like `uv 0.x.y` (confirmed absent on this machine
during research — will need the install step).

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "vinylyrics"
version = "0.1.0"
description = "Listens to a turntable, identifies the track, and projects synced karaoke lyrics."
readme = "README.md"
license = { text = "GPL-3.0-or-later" }
requires-python = ">=3.11"
dependencies = [
    "mutagen>=1.48",
    "python-dotenv>=1.0",
]

[project.scripts]
vinylizer = "vinylyrics.vinylizer.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["vinylyrics"]

[tool.pytest.ini_options]
markers = [
    "network: tests that need internet access (excluded by default)",
]
addopts = "-m 'not network'"
```

- [ ] **Step 3: Create the package skeleton**

```bash
mkdir -p vinylyrics/vinylizer vinylyrics/audio vinylyrics/recognition vinylyrics/lyrics vinylyrics/state vinylyrics/server web scripts tests
touch vinylyrics/__init__.py vinylyrics/vinylizer/__init__.py vinylyrics/audio/__init__.py vinylyrics/recognition/__init__.py vinylyrics/lyrics/__init__.py vinylyrics/state/__init__.py vinylyrics/server/__init__.py tests/__init__.py
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# Secrets
.env

# Generated / large media — never commit audio or lyrics
data/
*.mp3
*.wav
*.lrc
lyrics_cache.sqlite3
shazam_cache/

# Editors
.idea/
.vscode/
```

- [ ] **Step 5: Write `.env.example`**

```dotenv
# vinylyrics environment variables
# Copy to .env and fill in only if you enable an optional integration.
# The core pipeline (shazamio, LRCLIB, MusicBrainz, Cover Art Archive)
# needs NO API key — only a descriptive User-Agent, set below.

# Sent as the User-Agent header to LRCLIB and MusicBrainz/Cover Art Archive.
VINYLYRICS_USER_AGENT="vinylyrics/0.1 (+https://github.com/Dakuur/vinylyrics)"

# Optional integrations — DO NOT set these without asking David first,
# and without explaining what they add over the free/keyless path.
# DISCOGS_TOKEN=
# AUDD_API_TOKEN=
# ACRCLOUD_ACCESS_KEY=
# ACRCLOUD_ACCESS_SECRET=
# LASTFM_API_KEY=
# SPOTIFY_CLIENT_ID=
# SPOTIFY_CLIENT_SECRET=
```

- [ ] **Step 6: Write a minimal `config.toml`**

```toml
[dev]
sample_rate = 16000
buffer_seconds = 20.0

[pi]
sample_rate = 16000
buffer_seconds = 20.0
```

(Only the fields Phase 1 needs — silence/recognition/clock parameters are
added by the plans that introduce them, to keep each phase's diff scoped to
what it actually uses.)

- [ ] **Step 7: Sync and verify the environment**

Run:
```bash
uv sync
uv run pytest --collect-only
```
Expected: `uv sync` creates `.venv/` and installs `mutagen`, `python-dotenv`,
`pytest` with no errors; `pytest --collect-only` reports "no tests ran" (no
test files yet) without import errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml vinylyrics tests .gitignore .env.example config.toml
git commit -m "chore: scaffold vinylyrics package with uv"
```

---

### Task 2: ID3 metadata scanner (`vinylizer/library.py`)

**Files:**
- Create: `vinylyrics/vinylizer/library.py`
- Test: `tests/vinylizer/test_library.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure `mutagen` + `pathlib`).
- Produces:
  - `@dataclasses.dataclass(frozen=True) class TrackMeta`: fields
    `path: Path`, `title: str | None`, `artist: str | None`,
    `album: str | None`, `duration_seconds: float | None`,
    `missing_fields: tuple[str, ...]`, `usable: bool` (property-like, computed
    in `__post_init__`... actually plain field set by the builder — see step 3).
  - `def scan_library(directory: Path) -> list[TrackMeta]` — Phase 3
    (`inspect` CLI) and later the vinylizer `build` command both import this.

- [ ] **Step 1: Write the failing test for a fully-tagged file**

```python
# tests/vinylizer/test_library.py
import subprocess
from pathlib import Path

import pytest
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

from vinylyrics.vinylizer.library import scan_library


def _make_silent_mp3(path: Path, seconds: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(seconds),
            "-codec:a", "libmp3lame", "-qscale:a", "9",
            str(path),
        ],
        check=True,
    )


def _tag(path: Path, **tags: str) -> None:
    try:
        audio = EasyID3(path)
    except Exception:
        audio = MP3(path)
        audio.add_tags()
        audio.save()
        audio = EasyID3(path)
    for key, value in tags.items():
        audio[key] = value
    audio.save()


def test_scan_library_reports_full_metadata(tmp_path: Path) -> None:
    mp3_path = tmp_path / "song.mp3"
    _make_silent_mp3(mp3_path, seconds=2.0)
    _tag(mp3_path, title="Test Song", artist="Test Artist", album="Test Album")

    tracks = scan_library(tmp_path)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.path == mp3_path
    assert track.title == "Test Song"
    assert track.artist == "Test Artist"
    assert track.album == "Test Album"
    assert track.duration_seconds == pytest.approx(2.0, abs=0.2)
    assert track.missing_fields == ()
    assert track.usable is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/vinylizer/test_library.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.vinylizer.library'`

- [ ] **Step 3: Implement `scan_library`**

```python
# vinylyrics/vinylizer/library.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3

AUDIO_SUFFIXES = {".mp3"}
REQUIRED_FIELDS = ("title", "artist")


@dataclass(frozen=True)
class TrackMeta:
    path: Path
    title: str | None
    artist: str | None
    album: str | None
    duration_seconds: float | None
    missing_fields: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not any(f in self.missing_fields for f in REQUIRED_FIELDS)


def _read_tag(tags: EasyID3 | None, key: str) -> str | None:
    if tags is None or key not in tags:
        return None
    values = tags[key]
    return str(values[0]) if values else None


def _load_one(path: Path) -> TrackMeta:
    try:
        tags = EasyID3(path)
    except Exception:
        tags = None

    title = _read_tag(tags, "title")
    artist = _read_tag(tags, "artist")
    album = _read_tag(tags, "album")

    audio = MutagenFile(path)
    duration = audio.info.length if audio is not None else None

    missing = tuple(
        field
        for field, value in (("title", title), ("artist", artist), ("album", album))
        if not value
    )

    return TrackMeta(
        path=path,
        title=title,
        artist=artist,
        album=album,
        duration_seconds=duration,
        missing_fields=missing,
    )


def scan_library(directory: Path) -> list[TrackMeta]:
    paths = sorted(p for p in Path(directory).iterdir() if p.suffix.lower() in AUDIO_SUFFIXES)
    return [_load_one(p) for p in paths]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/vinylizer/test_library.py -v`
Expected: `1 passed`

- [ ] **Step 5: Write the failing test for missing-tag detection**

```python
def test_scan_library_flags_missing_artist_as_unusable(tmp_path: Path) -> None:
    mp3_path = tmp_path / "untagged.mp3"
    _make_silent_mp3(mp3_path, seconds=1.0)
    _tag(mp3_path, title="Only Title")

    tracks = scan_library(tmp_path)

    assert len(tracks) == 1
    assert tracks[0].missing_fields == ("artist",)
    assert tracks[0].usable is False


def test_scan_library_sorts_by_filename(tmp_path: Path) -> None:
    for name in ("b.mp3", "a.mp3"):
        p = tmp_path / name
        _make_silent_mp3(p, seconds=0.5)
        _tag(p, title=name, artist="Someone")

    tracks = scan_library(tmp_path)

    assert [t.path.name for t in tracks] == ["a.mp3", "b.mp3"]
```

- [ ] **Step 6: Run to verify both fail for the right reason, then pass**

Run: `uv run pytest tests/vinylizer/test_library.py -v`
Expected first (before adding, they should already pass since Step 3's
implementation already handles both cases) — if they pass immediately, that's
fine, it means Step 3 already covers them; if `test_scan_library_sorts_by_filename`
fails, fix `scan_library` to sort with `sorted(...)` (already present above).
Expected final: `4 passed`.

- [ ] **Step 7: Commit**

```bash
git add vinylyrics/vinylizer/library.py tests/vinylizer/test_library.py tests/vinylizer/__init__.py
git commit -m "feat: scan mp3 library metadata with mutagen"
```

---

### Task 3: `inspect` CLI subcommand

**Files:**
- Create: `vinylyrics/vinylizer/cli.py`
- Test: `tests/vinylizer/test_cli.py`

**Interfaces:**
- Consumes: `scan_library(directory: Path) -> list[TrackMeta]` and `TrackMeta`
  from Task 2 (`vinylyrics.vinylizer.library`).
- Produces: `def main(argv: list[str] | None = None) -> int`, the
  `vinylizer` console-script entry point (already wired in `pyproject.toml`
  Task 1). `vinylizer inspect <directory>` prints a table to stdout and
  returns exit code 0 always (it reports problems, it doesn't fail the run).

- [ ] **Step 1: Write the failing test**

```python
# tests/vinylizer/test_cli.py
from pathlib import Path

from vinylyrics.vinylizer.cli import main


def _make_and_tag(tmp_path: Path, name: str, **tags: str) -> Path:
    import subprocess
    p = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
         "-codec:a", "libmp3lame", "-qscale:a", "9", str(p)],
        check=True,
    )
    if tags:
        from mutagen.mp3 import MP3
        from mutagen.easyid3 import EasyID3
        audio = MP3(p)
        audio.add_tags()
        audio.save()
        easy = EasyID3(p)
        for k, v in tags.items():
            easy[k] = v
        easy.save()
    return p


def test_inspect_reports_full_and_missing_tracks(tmp_path: Path, capsys) -> None:
    _make_and_tag(tmp_path, "good.mp3", title="Good Song", artist="Artist", album="Album")
    _make_and_tag(tmp_path, "bad.mp3")  # no tags at all

    exit_code = main(["inspect", str(tmp_path)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "good.mp3" in out
    assert "Good Song" in out
    assert "bad.mp3" in out
    assert "excluid" in out.lower()  # summary mentions exclusion
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/vinylizer/test_cli.py -v`
Expected: `ModuleNotFoundError: No module named 'vinylyrics.vinylizer.cli'`

- [ ] **Step 3: Implement the CLI**

```python
# vinylyrics/vinylizer/cli.py
from __future__ import annotations

import argparse
from pathlib import Path

from vinylyrics.vinylizer.library import TrackMeta, scan_library


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def _print_table(tracks: list[TrackMeta]) -> None:
    columns = ("Archivo", "Título", "Artista", "Álbum", "Duración", "Faltan")
    rows = [
        (
            t.path.name,
            t.title or "-",
            t.artist or "-",
            t.album or "-",
            _format_duration(t.duration_seconds),
            ",".join(t.missing_fields) or "-",
        )
        for t in tracks
    ]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(columns)]
    def fmt_row(row: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(w) for cell, w in zip(row, widths))
    print(fmt_row(columns))
    print(fmt_row(tuple("-" * w for w in widths)))
    for row in rows:
        print(fmt_row(row))


def _cmd_inspect(args: argparse.Namespace) -> int:
    tracks = scan_library(Path(args.directory))
    _print_table(tracks)

    excluded = [t for t in tracks if not t.usable]
    print()
    print(f"Total: {len(tracks)} pistas, {len(excluded)} excluidas por metadatos incompletos.")
    for t in excluded:
        print(f"  - {t.path.name}: faltan {', '.join(t.missing_fields)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vinylizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Muestra el estado de los metadatos ID3 de una carpeta")
    inspect_parser.add_argument("directory", help="Carpeta con archivos .mp3")
    inspect_parser.set_defaults(func=_cmd_inspect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/vinylizer/test_cli.py -v`
Expected: `1 passed`

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass (Task 2's 4 tests + Task 3's 1 test).

- [ ] **Step 6: Commit**

```bash
git add vinylyrics/vinylizer/cli.py tests/vinylizer/test_cli.py
git commit -m "feat: add vinylizer inspect CLI subcommand"
```

---

### Task 4: Ubuntu setup script + README stub

**Files:**
- Create: `scripts/setup-ubuntu.sh`
- Modify: `README.md`

**Interfaces:**
- Produces: a script David runs himself (it needs `sudo`, so this task writes
  it but does not execute it) that installs the system packages every later
  phase's Python deps need (`sounddevice` → portaudio, `soundfile` → libsndfile,
  `shazamio`'s pydub path → ffmpeg).

- [ ] **Step 1: Write the setup script**

```bash
# scripts/setup-ubuntu.sh
#!/usr/bin/env bash
set -euo pipefail

echo "Installing vinylyrics system dependencies (Ubuntu/Debian)..."
sudo apt-get update
sudo apt-get install -y ffmpeg libsndfile1 portaudio19-dev python3-dev

echo "Done. Install uv separately if needed:"
echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/setup-ubuntu.sh`

- [ ] **Step 3: Verify it's syntactically valid without running the sudo parts**

Run: `bash -n scripts/setup-ubuntu.sh`
Expected: no output, exit code 0 (syntax check only — do NOT run the script
itself, it needs sudo and this task doesn't have standing permission to modify
system packages).

- [ ] **Step 4: Write the README stub**

```markdown
# vinylyrics

Escucha lo que suena en un tocadiscos, identifica la canción, y proyecta un
fondo de color con letras sincronizadas en modo karaoke.

## Estado

En desarrollo. Ver [docs/SPEC.md](docs/SPEC.md) para la especificación completa
y [docs/superpowers/plans/](docs/superpowers/plans/) para los planes de cada fase.

## Setup (Ubuntu)

\`\`\`bash
./scripts/setup-ubuntu.sh
curl -LsSf https://astral.sh/uv/install.sh | sh   # si no tienes uv
uv sync
\`\`\`

## Uso

\`\`\`bash
uv run vinylizer inspect /ruta/a/tus/mp3
\`\`\`

## Licencia

GPLv3 — ver [LICENSE](LICENSE). (Elegida por la dependencia `pedalboard`, que
liga JUCE 6; ver [docs/REUSE.md](docs/REUSE.md).)
```

- [ ] **Step 5: Add the LICENSE file**

Run:
```bash
curl -sL https://www.gnu.org/licenses/gpl-3.0.txt -o LICENSE
```
Expected: `LICENSE` starts with `GNU GENERAL PUBLIC LICENSE` / `Version 3, 29 June 2007`.
If offline, fetch it manually from https://www.gnu.org/licenses/gpl-3.0.txt —
this step needs network once; it is not part of the pytest suite.

- [ ] **Step 6: Commit**

```bash
git add scripts/setup-ubuntu.sh README.md LICENSE
git commit -m "docs: add Ubuntu setup script, README stub, and GPLv3 license"
```

---

## Self-Review Notes

- Spec coverage for this phase: §1 "Subcomando inspect" — Task 2 + Task 3 cover
  table output, missing-tag detection, and default exclusion. §Entorno's system
  deps — Task 4. §10 `.gitignore`/`.env.example`/`config.toml`/license — Task 1
  and Task 4 (including the actual `LICENSE` file, added in Step 5 above after
  the initial self-review caught it missing). Everything else in the spec
  belongs to later phases (see Roadmap).
- No placeholders: every step above has runnable code, not a description.
- Type consistency: `TrackMeta` (Task 2) is imported unchanged into `cli.py`
  (Task 3) — `usable`, `missing_fields`, `path`, `title`, `artist`, `album`,
  `duration_seconds` are the only fields either file touches.
