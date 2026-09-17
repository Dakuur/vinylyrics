#!/usr/bin/env python3
"""Prueba manual: reconoce un fragmento de audio con el módulo real de la
Fase 5 (ShazamIORecognizer + caché en disco + portada vía MusicBrainz/Cover
Art Archive) y mide cuánto tarda.

Uso:
    uv run scripts/try_recognize.py "/home/dakur/Downloads/songs/Bonito.mp3"
    uv run scripts/try_recognize.py data/vinylizer_smoke/dry.wav --offset 5 --duration 12
"""
from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from vinylyrics.recognition.cache import DiskRecognitionCache
from vinylyrics.recognition.enrich import recognize_with_cover_art
from vinylyrics.recognition.shazam import ShazamIORecognizer


def extract_clip(path: Path, offset: float, duration: float) -> tuple[np.ndarray, int]:
    info = sf.info(path)
    sr = info.samplerate
    audio, _ = sf.read(
        path, dtype="float32", always_2d=True,
        start=int(offset * sr), frames=int(duration * sr),
    )
    if len(audio) == 0:
        raise ValueError(f"El offset {offset}s está más allá del final de {path.name} ({info.duration:.1f}s)")
    return audio.mean(axis=1).astype(np.float32), sr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_file", help="Ruta a un .mp3 o .wav")
    parser.add_argument("--offset", type=float, default=30.0, help="Segundo de inicio del fragmento (por defecto 30s)")
    parser.add_argument("--duration", type=float, default=12.0, help="Duración del fragmento en segundos (por defecto 12s, como la ventana deslizante de la Fase 4)")
    args = parser.parse_args()

    path = Path(args.audio_file)
    print(f"Extrayendo {args.duration}s desde el segundo {args.offset} de {path.name}...")
    clip, sr = extract_clip(path, args.offset, args.duration)

    print("Enviando a Shazam...")
    cache = DiskRecognitionCache(Path("shazam_cache"))
    recognizer = ShazamIORecognizer(cache=cache)

    start = time.monotonic()
    result = asyncio.run(recognize_with_cover_art(recognizer, clip, sr))
    elapsed = time.monotonic() - start

    print(f"\nTiempo de reconocimiento: {elapsed:.2f}s")

    if result is None:
        print("No identificado. Prueba con otro --offset (evita intros silenciosas o habladas).")
        return 1

    print(f"Título:  {result.title}")
    print(f"Artista: {result.artist}")
    print(f"Álbum:   {result.album or '-'}")
    print(f"Portada: {result.cover_url or '-'}")
    print(f"offset={result.offset}  timeskew={result.timeskew}  frequencyskew={result.frequencyskew}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
