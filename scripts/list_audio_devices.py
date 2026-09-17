#!/usr/bin/env python3
"""Lista los dispositivos de audio que ve sounddevice (para elegir --device
más adelante, cuando haya una tarjeta USB conectada).

Necesita portaudio instalado (scripts/setup-ubuntu.sh). Si ves
"OSError: PortAudio library not found", ejecuta ese script primero.
"""
from __future__ import annotations

from vinylyrics.audio.source import list_devices


def main() -> int:
    devices = list_devices()
    if not devices:
        print("No se detectó ningún dispositivo de audio.")
        return 0

    for i, device in enumerate(devices):
        name = device.get("name", "?")
        max_in = device.get("max_input_channels", 0)
        max_out = device.get("max_output_channels", 0)
        print(f"[{i}] {name}  (entradas: {max_in}, salidas: {max_out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
