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
