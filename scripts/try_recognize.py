#!/usr/bin/env python3
"""Prueba manual: reconoce un fragmento de audio con Shazam y mide cuánto tarda.

No es el módulo de reconocimiento definitivo (eso es la Fase 5, con caché,
reintentos y política de llamadas) - esto es solo para probar rápido qué tal
funciona shazamio contra tus propias canciones o contra un WAV del vinylizer.

Uso:
    uv run scripts/try_recognize.py "/home/dakur/Downloads/songs/Bonito.mp3"
    uv run scripts/try_recognize.py data/vinylizer_smoke/dry.wav --offset 5 --duration 12
"""
from __future__ import annotations

import argparse
import asyncio
import io
import time
from pathlib import Path

import soundfile as sf
from shazamio import Shazam


def extract_clip(path: Path, offset: float, duration: float) -> bytes:
    info = sf.info(path)
    sr = info.samplerate
    audio, _ = sf.read(
        path, dtype="float32", always_2d=True,
        start=int(offset * sr), frames=int(duration * sr),
    )
    if len(audio) == 0:
        raise ValueError(f"El offset {offset}s está más allá del final de {path.name} ({info.duration:.1f}s)")
    buffer = io.BytesIO()
    sf.write(buffer, audio, sr, format="WAV")
    return buffer.getvalue()


async def recognize(data: bytes) -> tuple[dict, float]:
    shazam = Shazam()
    start = time.monotonic()
    result = await shazam.recognize(data)
    elapsed = time.monotonic() - start
    return result, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio_file", help="Ruta a un .mp3 o .wav")
    parser.add_argument("--offset", type=float, default=30.0, help="Segundo de inicio del fragmento (por defecto 30s)")
    parser.add_argument("--duration", type=float, default=12.0, help="Duración del fragmento en segundos (por defecto 12s, como la ventana deslizante de la Fase 4)")
    args = parser.parse_args()

    path = Path(args.audio_file)
    print(f"Extrayendo {args.duration}s desde el segundo {args.offset} de {path.name}...")
    clip = extract_clip(path, args.offset, args.duration)

    print("Enviando a Shazam...")
    result, elapsed = asyncio.run(recognize(clip))

    print(f"\nTiempo de reconocimiento: {elapsed:.2f}s")

    track = result.get("track")
    if not track:
        print("No identificado. Prueba con otro --offset (evita intros silenciosas o habladas).")
        return 1

    print(f"Título:  {track.get('title')}")
    print(f"Artista: {track.get('subtitle')}")

    matches = result.get("matches", [])
    if matches:
        m = matches[0]
        print(f"offset={m.get('offset')}  timeskew={m.get('timeskew')}  frequencyskew={m.get('frequencyskew')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
