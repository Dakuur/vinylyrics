# vinylyrics — especificación

> Documento fuente proporcionado por David el 2026-09-17. Se conserva verbatim
> como referencia para todos los planes de implementación derivados de él.

Sistema que escucha lo que suena en un tocadiscos, identifica la canción, y
proyecta en la pared un fondo de color sólido derivado de la portada con las
letras en modo karaoke.

## Reuso: no reinventes la rueda

Regla general: prefiero integrar código existente y mantenido antes que escribir
el mío. Antes de implementar cualquier bloque, busca si ya existe.

**Paquetes de PyPI que ya cubren partes del problema** — verifica que siguen
mantenidos y úsalos si encajan:

- `shazamio` — cliente de la API de Shazam (no oficial). El reconocimiento entero.
- `lrcup` o `lrclibapi` — cliente de LRCLIB. Evalúa los dos y quédate con el que
  tenga mejor parseo de LRC; si uno ya parsea a `(ms, texto)` con casos raros
  resueltos, no escribas tu propio parser.
- `musicbrainzngs` — búsqueda de releases para sacar el MBID.
- `pedalboard` (Spotify) — efectos de audio sobre JUCE. Cubre filtros, saturación
  y compresión del vinylizer sin escribir DSP a mano. Wow y flutter no vienen
  hechos, eso sí lo tendrás que implementar.
- `colorthief` o `Pillow` con k-means — color dominante de la portada.
- `mutagen` — lectura de etiquetas ID3.
- `soundfile` / `librosa` — I/O y remuestreo.

**Repos de referencia.** Léelos si puedes y aprovecha sus decisiones, pero son
aplicaciones completas, no librerías: no los metas como dependencia.

- `github.com/LuKresXD/Spindle` — misma cadena de señal; captura con ventana
  deslizante (pasos de 2 s, ventanas solapadas de 10 s).
- `github.com/lanebecker/eyeliner` — backend de reconocimiento intercambiable.
- `github.com/schuettc/now-playing` — portadas vía MusicBrainz + Cover Art
  Archive; su `docs/EDGE-CASES.md` documenta casos raros (samples, ediciones
  múltiples, prensados) que conviene conocer.
- `github.com/reteps/real-time-lyrics` — letras sincronizadas en tiempo real.
- `github.com/reagan-pius/vinyl-player` — DSP de vinilo en AudioWorklet: wow y
  flutter como remuestreo fraccional de tasa variable (ring buffer + puntero de
  lectura modulado por dos LFOs sumados), clics con planificación Poisson sobre
  un banco de impulsos. Es JS, pero el algoritmo es directamente portable a numpy
  y es exactamente lo que necesita el vinylizer.

**Submódulos git:** permitidos, pero solo si encuentras un repo que sea de verdad
una librería reutilizable y no esté en PyPI. Si crees que uno lo merece,
**pregúntame antes de añadirlo** y justifica por qué no vale una dependencia
normal. Por defecto, asume que no hace falta ninguno.

Al final, un `docs/REUSE.md` listando qué es código de terceros, qué es mío y por
qué. Lo quiero para la web del proyecto.

## Claves y credenciales

**Pregúntame cualquier clave que necesites antes de usarla. No inventes valores,
no crees cuentas, no metas placeholders en el código y no hagas commit de nada.**
Todo por variables de entorno con un `.env.example` versionado y `.env` ignorado.

Hasta donde sé, el camino principal no necesita ninguna clave: shazamio no lleva
autenticación, LRCLIB tampoco, y MusicBrainz / Cover Art Archive solo piden un
User-Agent identificativo. Si al investigar ves que algo de esto ha cambiado,
dímelo.

Servicios opcionales que sí llevan clave — **no los integres sin preguntarme
primero, y explícame qué aportan antes de que yo la genere**: Discogs (token de
usuario), AudD, ACRCloud, Last.fm, Spotify. Ninguno es necesario para el núcleo.

## Entorno

- Desarrollo y pruebas en **Ubuntu**, en mi portátil, sin hardware de audio.
- Python 3.11+, gestionado con `uv`.
- Dependencias de sistema en un `scripts/setup-ubuntu.sh` y en el README:
  `sudo apt install -y ffmpeg libsndfile1 portaudio19-dev python3-dev`
- `sounddevice` se instala aunque no haya tarjeta: el código debe importar sin
  fallar en una máquina sin dispositivos de entrada. Selección de fuente perezosa.
- Destino final: Raspberry Pi 5 con Raspberry Pi OS. No despliego todavía, pero
  no uses nada que no funcione en ARM64 (comprueba que hay wheels de `pedalboard`
  para aarch64; si no, el vinylizer solo corre en el portátil, y eso vale).

## Hardware objetivo (producción, más adelante)

- Raspberry Pi 5 (4 GB).
- Tarjeta USB con entrada de línea (tipo Behringer UCA202).
- Señal de línea del tocadiscos partida con cable RCA en Y: una rama a los
  altavoces, otra a la tarjeta USB.
- Proyector barato de 30 € por micro-HDMI. **Resolución nativa baja** (asume
  800x480 como peor caso, configurable), poco brillo, enfoque pobre en los bordes.
  Esto condiciona toda la interfaz.

## Arquitectura

Paquete `vinylyrics/`. Frontend en HTML + CSS + JS a mano, sin build step.

Pieza central: **la fuente de audio es una interfaz abstracta**.

```python
class AudioSource(Protocol):
    def read(self, seconds: float) -> np.ndarray: ...   # float32 mono, 16 kHz
    @property
    def sample_rate(self) -> int: ...
```

- `LineInSource` — `sounddevice`, tarjeta USB. No puedo probarla todavía; escríbela
  con índice de dispositivo configurable y un `--list-devices`.
- `FileSource` — lee un WAV. `realtime=True` respeta el reloj de pared (prueba
  realista), `realtime=False` va a máxima velocidad (iteración y evaluación).

Módulos: `vinylizer/`, `audio/`, `recognition/`, `lyrics/`, `state/`, `server/`,
`web/`.

## 1. Vinylizer

Herramienta offline, CLI aparte del runtime.

**Entrada: `/home/dakur/Downloads/songs`, 47 mp3.**

Subcomando `inspect`: recorre la carpeta y saca una tabla con título, artista,
álbum, duración y etiquetas ID3 que falten. Necesito ver el estado real de los
metadatos antes de nada, porque son la verdad de referencia de toda la
evaluación. Si a un archivo le faltan artista o título, avísame y exclúyelo por
defecto en vez de inventar nada.

Subcomando `build`: produce un WAV que simula una cara de vinilo.

- **Caras cortas por defecto.** 47 canciones seguidas son casi 3 horas, inútil
  para iterar. `--tracks 6` por defecto, muestra aleatoria con semilla fijable.
  `--all` reparte las 47 en varias caras de 6 (`cara_01.wav`, …) para la
  evaluación grande. `--dry` genera 90 s con 3 fragmentos de 30 s.
- **Velocidad constante desviada:** ±0.8 % aleatorio, distinto por archivo.
- **Wow:** LFO senoidal 0.5–2 Hz, ±0.3 %. **Flutter:** LFO 6–10 Hz, ±0.05 %.
  Súmalos, como hace vinyl-player.
- Velocidad variable por remuestreo con interpolación sobre un índice de tiempo
  acumulado. Cambia tono y duración a la vez: eso es lo que hace un plato. **No
  uses time-stretch que preserve el tono.**
- **Ruido de superficie:** ruido rosa a ~-38 dBFS. **Clics:** impulsos cortos
  filtrados con planificación Poisson, densidad configurable.
- **Rumble:** ruido filtrado en graves, opcional.
- **Respuesta en frecuencia:** shelf suave atenuando por encima de 12 kHz.
- **Estructura:** 3 s de lead-in (solo ruido), pistas separadas por 2.0 s de
  silencio **con ruido de superficie** (no silencio digital), 5 s de lead-out.
- `.truth.json` por cara: orden real, offsets de inicio y fin de cada pista en el
  WAV, factor de velocidad aplicado, metadatos del ID3.

Parámetros en TOML, semilla fijable, reproducible. Sin saltos de aguja.

## 2. Audio y detección de estado

- Buffer circular de 20 s.
- **Ventana deslizante:** intento de reconocimiento cada 2 s sobre los últimos
  12 s. Identifica en 10-15 s en vez de esperar al silencio.
- RMS en ventanas de 100 ms. Detector de silencio **con histéresis**: umbrales de
  entrada y salida distintos y duración mínima. El ruido de superficie hace que el
  hueco entre cortes no sea silencio real: calibra contra el nivel de fondo medido
  en el lead-in, no contra un valor absoluto.
- Eventos: `TRACK_GAP` (1-3 s de silencio) y `STOPPED` (>10 s, aguja levantada).
  `TRACK_GAP` es una señal más, no el disparador principal.

## 3. Reconocimiento

- Interfaz `Recognizer`, implementación `ShazamIORecognizer`. API no oficial:
  deja hueco para AudD o ACRCloud sin tocar el resto (pero no los integres sin
  preguntarme).
- Política de llamadas: nunca dos simultáneas; nueva petición si han pasado ≥8 s,
  o inmediatamente tras `TRACK_GAP`. Con la canción ya identificada y el reloj
  estable, baja a una cada 45 s como resincronización.
- Extrae título, artista, álbum, URL de portada y **`matches[0].offset`,
  `timeskew` y `frequencyskew`**. Son la base de la sincronización.
- Reintentos con backoff. Tras 3 fallos seguidos, `UNIDENTIFIED`.
- **Caché en disco de las respuestas, indexada por hash del fragmento de audio.**
  Voy a repetir la evaluación muchas veces y no quiero martillear la API; si
  empiezan a llegar respuestas vacías es rate limiting, no un bug.
- **Portada:** la de Shazam suele ser pequeña y a veces del single. Busca el
  release en MusicBrainz y pide la portada a Cover Art Archive, con la de Shazam
  como respaldo. Mejor imagen, mejor paleta.

## 4. Letras

- LRCLIB vía `lrcup` o `lrclibapi`. `/api/get` con track, artist, album y
  duration; si falla, `/api/search` eligiendo la duración más cercana.
- Letra a `(ms, texto)`. Casos: varias marcas de tiempo para una línea, líneas
  vacías (interludios), metadatos `[ar:]`, `[ti:]`. Si la librería elegida ya
  cubre esto, úsala tal cual.
- Solo letra sin sincronizar, o pista instrumental: guárdala, pero muestra solo
  color y título, sin karaoke.
- Caché en SQLite por artista+título+duración. User-Agent identificativo: es una
  API comunitaria y gratuita.
- **No commitees letras al repo**, es material con copyright. Al `.gitignore`.

## 5. Reloj de reproducción

La parte delicada. Mapeo lineal:

```
posicion_cancion(t) = velocidad * (t - t_ancla) + offset_ancla
```

- Cada reconocimiento da un ancla `(t_ancla, offset_ancla)`. Resta la latencia: el
  `offset` corresponde al **inicio** del buffer enviado, no a cuando llega la
  respuesta.
- `velocidad` arranca en el `timeskew` de Shazam, o 1.0. Con dos o más anclas de
  la misma canción, regresión lineal. La ventana deslizante da anclas cada pocos
  segundos, así que converge rápido.
- Limita `velocidad` a [0.97, 1.03] y descarta anclas que impliquen un salto de
  más de 3 s respecto a la predicción (probable match erróneo).
- **No saltes al corregir:** si el error es menor de 400 ms, absórbelo ajustando
  `velocidad` durante los siguientes segundos. Un salto brusco en las letras se ve
  fatal.

## 6. Servidor

FastAPI. WebSocket que emite el estado completo cuando cambia:

```json
{
  "state": "PLAYING",
  "track": {"title": "...", "artist": "...", "album": "...", "cover_url": "..."},
  "palette": {"bg": "#1a2e3d", "fg": "#f0ede8", "dim": "#8a99a5"},
  "lyrics": [{"ms": 27930, "text": "..."}],
  "clock": {"anchor_wall": 1758100000.0, "anchor_ms": 27930, "speed": 1.004}
}
```

**Manda el reloj, no la línea actual.** El navegador interpola a 60 fps con
`performance.now()`. Si el servidor empujara la línea activa, cualquier hipo de
red se vería en pantalla.

`/health` y un endpoint de debug con el último reconocimiento, la estimación de
velocidad, el RMS y el historial de anclas. Me hará falta para ajustar umbrales.

## 7. Paleta

Color dominante de la portada, y luego **fuérzalo a ser proyectable**:

- A HSL: luminosidad 0.12–0.20, saturación máxima 0.5. Un fondo claro en un
  proyector barato es una mancha de luz.
- Texto blanco roto. Verifica contraste WCAG y oscurece el fondo iterativamente
  hasta pasar de 7:1.
- Fallback a gris azulado oscuro si no hay portada.

## 8. Interfaz

Objetivo: legible en un proyector de 800x480 mal enfocado.

- Fondo de color sólido a pantalla completa. Sin gradientes ni imágenes de fondo.
  La portada no se muestra de momento: solo alimenta la paleta.
- Área segura: 8 % de margen por lado.
- Sans-serif, peso 600+, nunca light. Línea actual a ~9 % de la altura del
  viewport, en `clamp()`.
- **Karaoke:**
  - Actual: opacidad 1, tamaño completo. Siguiente: 0.45 y tamaño 0.75. Una o dos
    anteriores: 0.15.
  - **Avance verso a verso, no continuo.** Al llegar la marca de tiempo de la
    siguiente línea, el contenedor se traslada exactamente la altura de la línea
    saliente, con transición de 250 ms `cubic-bezier(0.4, 0, 0.2, 1)`. Entre
    versos la pantalla está quieta y luego salta un escalón.
  - `transform: translateY()`, nunca `top` ni `scrollTop`. `will-change`.
  - Hueco > 8 s entre líneas: título y artista centrados.
- Estados: `IDLE`, `LISTENING`, `PLAYING`, `UNIDENTIFIED`.
- Fundido del fondo en 800 ms entre canciones.
- Cursor oculto, pantalla completa.

Un solo HTML + CSS + JS, abrible tal cual en el navegador de Ubuntu y en Chromium
kiosko en la Pi sin cambios.

## 9. Pruebas

- Unitarias: parser de LRC (o la integración con la librería elegida), detector de
  silencio con señales sintéticas, reloj (deriva, corrección suave, rechazo de
  anclas absurdas), contraste de la paleta.
- Integración: pasa una cara en modo rápido y compara con su `.truth.json`. Tabla
  con pistas identificadas correctamente, tiempo hasta la primera identificación,
  falsos cambios de pista y error medio de sincronización en ms.
- `eval-full`: las 47 canciones en todas las caras, resultados agregados. Este
  informe va en la web: legible por stdout y también en JSON.
- Red: `@pytest.mark.network`. El resto de la suite corre offline.

## 10. Repo

- `README.md`: diagrama de ambos setups (físico y de simulación), hardware con
  precios, cómo correr la simulación, resultados de la evaluación, y una nota de
  que ningún proyecto existente combina vinilo con letras sincronizadas.
- `docs/REUSE.md` con la atribución de terceros.
- `.gitignore`: `data/`, `*.mp3`, `*.wav`, caché de letras, `.env`.
- `justfile` o `Makefile`: `inspect`, `vinylize`, `dev`, `eval`, `eval-full`,
  `test`, `lint`.
- `config.toml` con perfiles `dev` y `pi`.
- MIT. Nota de que shazamio es una API no oficial y LRCLIB es comunitaria.
- Respeta las licencias de lo que reutilices; si algo es GPL y lo integras de
  verdad, avísame porque cambia la licencia del proyecto.

## Orden de trabajo

No lo hagas todo de golpe. Propón el plan, y luego:

1. Investigación de reuso: qué paquetes cubren qué, cuáles están mantenidos, qué
   tengo que escribir yo. Enséñame la conclusión antes de instalar nada.
2. `inspect` sobre las 47 canciones. Quiero ver el estado de los metadatos.
3. Vinylizer + verdad de referencia. Quiero escuchar un WAV y validarlo.
4. Fuentes de audio + detector de silencio, con pruebas.
5. Reconocimiento, contra un fragmento suelto primero.
6. Reloj + letras.
7. Servidor + interfaz.
8. Evaluación.

Después de cada paso, para y enséñame lo que hay.

## Decisiones tomadas durante la investigación de reuso (2026-09-17)

- **Licencia del proyecto: GPLv3, no MIT.** `pedalboard` resultó ser GPLv3 (por
  JUCE 6, libre solo bajo GPL salvo licencia comercial de Steinberg/Juce). David
  confirmó por chat que el proyecto es personal, no comercial, y que prefiere lo
  que dé mejor resultado antes que la pureza de licencia — así que se usa
  `pedalboard` y todo el repo pasa a GPLv3 en vez de MIT.
- `librosa` queda descartado: no aporta nada que `soundfile` + `scipy.signal` no
  cubran ya para este proyecto (I/O y resampling de tasa fija), pesa mucho más
  (numba, scikit-learn, joblib) y su versión 1.0.0 en PyPI exige Python ≥3.12,
  lo que entra en conflicto con el suelo de 3.11 fijado aquí.
- Ni `lrcup` ni `lrclibapi` parsean el LRC a `(ms, texto)`: ambos exponen
  `syncedLyrics` como el bloque de texto crudo. Se usará `lrclibapi` como
  cliente HTTP (excepciones tipadas — `NotFoundError`, `RateLimitError`,
  `ServerError` — encajan mejor con la política de reintentos/backoff pedida) y
  se escribirá un parser LRC propio y probado (Fase 6).
