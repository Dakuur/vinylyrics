from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from vinylyrics.vinylizer.build import build_side, partition_tracks, select_tracks, write_side
from vinylyrics.vinylizer.library import TrackMeta, scan_library
from vinylyrics.vinylizer.params import load_params


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


def _cmd_build(args: argparse.Namespace) -> int:
    if args.all and args.dry:
        print("--all y --dry no se pueden combinar.")
        return 1

    tracks = scan_library(Path(args.directory))
    rng = np.random.default_rng(args.seed)
    params = load_params(Path(args.params) if args.params else None)
    output_dir = Path(args.output_dir)

    if args.dry:
        selected = select_tracks(tracks, 3, rng)
        audio, truth = build_side(selected, params, rng, max_track_seconds=30.0)
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = output_dir / "dry.wav"
        json_path = output_dir / "dry.truth.json"
        import soundfile as sf
        sf.write(wav_path, audio, truth["sample_rate"])
        json_path.write_text(json.dumps(truth, indent=2, ensure_ascii=False))
        print(f"Generado {wav_path} ({truth['duration_sec']:.1f}s, {len(selected)} pistas)")
        return 0

    if args.all:
        groups = partition_tracks(tracks, args.tracks, rng)
        for i, group in enumerate(groups, start=1):
            audio, truth = build_side(group, params, rng)
            wav_path, _ = write_side(audio, truth, output_dir, i)
            print(f"Generado {wav_path} ({truth['duration_sec']:.1f}s, {len(group)} pistas)")
        return 0

    selected = select_tracks(tracks, args.tracks, rng)
    audio, truth = build_side(selected, params, rng)
    wav_path, _ = write_side(audio, truth, output_dir, 1)
    print(f"Generado {wav_path} ({truth['duration_sec']:.1f}s, {len(selected)} pistas)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vinylizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Muestra el estado de los metadatos ID3 de una carpeta")
    inspect_parser.add_argument("directory", help="Carpeta con archivos .mp3")
    inspect_parser.set_defaults(func=_cmd_inspect)

    build_parser = subparsers.add_parser("build", help="Genera un WAV que simula una cara de vinilo")
    build_parser.add_argument("directory", help="Carpeta con archivos .mp3")
    build_parser.add_argument("--tracks", type=int, default=6, help="Pistas por cara (por defecto 6)")
    build_parser.add_argument("--all", action="store_true", help="Reparte todas las pistas usables en varias caras")
    build_parser.add_argument("--dry", action="store_true", help="Genera ~90s de prueba (3 fragmentos de 30s)")
    build_parser.add_argument("--seed", type=int, default=None, help="Semilla para reproducibilidad")
    build_parser.add_argument("--output-dir", default="data/vinylizer_output", help="Carpeta de salida")
    build_parser.add_argument("--params", default=None, help="Ruta a un TOML de parámetros alternativo")
    build_parser.set_defaults(func=_cmd_build)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
