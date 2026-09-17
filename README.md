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

## Licencia

GPLv3 — ver [LICENSE](LICENSE). (Elegida por la dependencia `pedalboard`, que
liga JUCE 6; ver [docs/REUSE.md](docs/REUSE.md).)
