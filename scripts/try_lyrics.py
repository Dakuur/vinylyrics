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
