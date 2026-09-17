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
    assert "excluid" in out.lower()  # summary mentions exclusion
