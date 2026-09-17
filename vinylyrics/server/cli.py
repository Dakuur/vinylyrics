# vinylyrics/server/cli.py
from __future__ import annotations

import argparse
import asyncio
import logging
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from vinylyrics.audio.source import FileSource, LineInSource
from vinylyrics.engine import Engine
from vinylyrics.lyrics.cache import LyricsCache
from vinylyrics.lyrics.lrclib import LrcLibClient
from vinylyrics.lyrics.service import LyricsService
from vinylyrics.recognition.cache import DiskRecognitionCache
from vinylyrics.recognition.shazam import ShazamIORecognizer
from vinylyrics.server.app import create_app
from vinylyrics.state.session import PlaybackSession

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.toml"

logger = logging.getLogger(__name__)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Corre el servidor de vinylyrics en vivo.")
    parser.add_argument("--file", default=None, help="Usa un WAV como fuente en vez del micrófono (pruebas sin turntable)")
    parser.add_argument("--realtime", action="store_true", help="Con --file, respeta el reloj de pared en vez de ir a máxima velocidad")
    parser.add_argument("--device", type=int, default=None, help="Índice del dispositivo de entrada (ver scripts/list_audio_devices.py)")
    parser.add_argument("--profile", choices=["dev", "pi"], default="dev", help="Perfil de config.toml a usar")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0", help="No cambies esto a localhost — el proyector/móvil se conectan por red")
    return parser


def _load_profile(profile: str) -> dict:
    with open(DEFAULT_CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)
    return config[profile]


def resolve_source(args: argparse.Namespace, sample_rate: int):
    if args.file:
        return FileSource(Path(args.file), realtime=args.realtime, sample_rate=sample_rate)
    return LineInSource(device=args.device, sample_rate=sample_rate)


def main() -> int:
    args = build_argparser().parse_args()
    profile = _load_profile(args.profile)
    sample_rate = profile["sample_rate"]

    source = resolve_source(args, sample_rate)
    recognizer = ShazamIORecognizer(cache=DiskRecognitionCache(Path("shazam_cache")))
    lyrics_service = LyricsService(client=LrcLibClient(), cache=LyricsCache(Path("lyrics_cache.sqlite3")))
    session = PlaybackSession()

    engine = Engine(
        source=source, recognizer=recognizer, lyrics_service=lyrics_service,
        session=session, on_change=lambda: app.state.broadcast(),
    )

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.ensure_future(engine.run())
        app.state.engine_task = task

        def _on_engine_done(t: "asyncio.Task") -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.error("engine.run() crashed", exc_info=exc)
                app.state.engine_error = exc

        task.add_done_callback(_on_engine_done)
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if hasattr(source, "close"):
                source.close()

    app = create_app(session=session, engine=engine, lifespan=lifespan)

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
