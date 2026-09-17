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
        for field, value in (("title", title), ("artist", artist))
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
