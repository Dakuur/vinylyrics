# Reuso de terceros

Este proyecto sigue la regla de no reinventar la rueda: antes de escribir
código propio para un problema ya resuelto, se busca una librería mantenida
que lo cubra. Este documento registra cada dependencia de terceros según se
introduce — no se rellena al final — junto con por qué se eligió y bajo qué
licencia se distribuye.

## Licencia del proyecto

**vinylyrics se distribuye bajo GPLv3**, no bajo la licencia MIT que suele ser
la opción por defecto en proyectos Python.

El motivo es una dependencia de una fase posterior: `pedalboard` (de Spotify),
usada para los efectos de audio del vinylizer. `pedalboard` enlaza
estáticamente con JUCE 6, que solo es libre bajo GPL a menos que se pague la
licencia comercial de Steinberg/JUCE. Al integrar `pedalboard` de verdad (no
como opción descartable), todo el repositorio hereda esa obligación y pasa a
GPLv3. Esta decisión se tomó explícitamente durante la investigación de reuso
de la Fase 1 y está documentada en [docs/SPEC.md](SPEC.md#decisiones-tomadas-durante-la-investigación-de-reuso-2026-09-17).

## Dependencias de PyPI

Estas son las dependencias que la Fase 1 introdujo realmente en
`pyproject.toml`. Ninguna otra librería mencionada en `docs/SPEC.md` (como
`shazamio`, `lrclibapi`, `musicbrainzngs`, `colorthief`, `sounddevice` o
`scipy`) forma parte del proyecto todavía; se añadirán a esta misma tabla
cuando la fase correspondiente las incorpore.

La Fase 2 (el vinylizer) añadió `numpy`, `pedalboard` y `soundfile` a esa
misma tabla.

| Paquete | Versión mínima | Licencia | Por qué |
|---|---|---|---|
| [`mutagen`](https://pypi.org/project/mutagen/) | ≥1.48 | GPL-2.0-or-later | Lee y escribe etiquetas ID3 de los mp3. La especificación lo nombra directamente como la librería estándar en Python para esto, y el subcomando `inspect` depende de él para leer título, artista, álbum y duración. |
| [`python-dotenv`](https://pypi.org/project/python-dotenv/) | ≥1.0 | BSD-3-Clause | Carga variables de entorno desde un `.env` no versionado, siguiendo la regla de la especificación de no hardcodear claves ni credenciales en el código. |
| [`pytest`](https://pypi.org/project/pytest/) | ≥8.0 (grupo `dev`) | MIT | Framework de tests del proyecto (marcador `network` para excluir por defecto las pruebas que requieren red). |
| [`hatchling`](https://pypi.org/project/hatchling/) | — (`build-system.requires`) | MIT | Backend de build del paquete `vinylyrics`, declarado en `pyproject.toml`. No se importa en tiempo de ejecución. |
| [`numpy`](https://pypi.org/project/numpy/) | ≥1.26 | BSD-3-Clause | Matemática DSP del vinylizer: generación de LFOs, integración temporal acumulada para el remuestreo a velocidad variable, ruido rosa basado en FFT, y planificación de clics mediante un proceso de Poisson. |
| [`pedalboard`](https://pypi.org/project/pedalboard/) (Spotify) | ≥0.9 | GPLv3 (ver la justificación de licencia de este proyecto, ya registrada más arriba en este documento) | Usada para `HighShelfFilter` (el rolloff a 12kHz del vinylizer), `HighpassFilter` (dar forma a los clics) y `LowpassFilter` (dar forma al rumble) — efectos de audio sobre JUCE, exactamente el reuso que pedía la especificación original en vez de biquads hechos a mano. |
| [`soundfile`](https://pypi.org/project/soundfile/) | ≥0.13 | BSD-3-Clause | Lee los mp3 de origen directamente (confirmado durante la planificación de la Fase 2: el libsndfile 1.2.2 empaquetado decodifica MP3 de forma nativa, sin necesidad de un paso con ffmpeg/pydub para esta ruta) y escribe el WAV de salida. |

Las licencias se han verificado contra los metadatos publicados en PyPI de
cada paquete (`License-Expression` en su `METADATA`), no solo copiadas de
memoria.

### Nota sobre `mutagen` y GPLv3

`mutagen` es GPL-2.0-or-later. Al ser "or later", es compatible con un
proyecto GPLv3: no impone una licencia más restrictiva que la ya elegida por
`pedalboard`. No cambia nada respecto a la decisión de licencia de la sección
anterior, pero se anota aquí porque es la primera dependencia con licencia
copyleft que entra en el repo.

## Código propio

Todo lo demás en `vinylyrics/vinylizer/` (el escaneo de la carpeta de mp3, el
formateo de la tabla de `inspect` y la CLI en sí) es código propio del
proyecto, escrito para esta fase.

## Repos de referencia

Ningún repo de referencia de la sección "Reuso" de `docs/SPEC.md` se ha
incorporado como submódulo ni se ha copiado código de ellos en esta fase.
