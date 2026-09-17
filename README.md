# vinylyrics

Escucha lo que suena en un tocadiscos, identifica la canción, y proyecta un
fondo de color con letras sincronizadas en modo karaoke.

## Estado

En desarrollo. Ver [docs/SPEC.md](docs/SPEC.md) para la especificación completa
y [docs/superpowers/plans/](docs/superpowers/plans/) para los planes de cada fase.

## Setup (Ubuntu)

```bash
./scripts/setup-ubuntu.sh
curl -LsSf https://astral.sh/uv/install.sh | sh   # si no tienes uv
uv sync
```

## Uso

```bash
uv run vinylizer inspect /ruta/a/tus/mp3
```

```bash
uv run vinylizer build /ruta/a/tus/mp3 --tracks 6 --seed 42
```

Genera un WAV que simula una cara de vinilo, junto a su `.truth.json` con los
datos reales usados (pistas, offsets de velocidad, ruido). Opciones:

- `--tracks N`: pistas por cara (por defecto 6).
- `--all`: reparte todas las pistas usables en varias caras en vez de una sola.
- `--dry`: genera ~90s de prueba (3 fragmentos de 30s) para revisar rápido.
- `--seed S`: semilla para reproducibilidad.
- `--output-dir DIR`: carpeta de salida (por defecto `data/vinylizer_output`).
- `--params PATH`: ruta a un TOML de parámetros alternativo.

### Dispositivos de audio (para más adelante)

Cuando haya una tarjeta USB conectada:

```bash
uv run scripts/list_audio_devices.py
```

Necesita `portaudio` instalado (`./scripts/setup-ubuntu.sh`).

## Licencia

GPLv3 — ver [LICENSE](LICENSE). (Elegida por la dependencia `pedalboard`, que
liga JUCE 6; ver [docs/REUSE.md](docs/REUSE.md).)
