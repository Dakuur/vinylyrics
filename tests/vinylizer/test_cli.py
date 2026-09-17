import json
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
        if audio.tags is None:
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
    assert "bad.mp3: faltan title, artist" in out  # actually excluded, not just mentioned


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
