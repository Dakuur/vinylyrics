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
