# vinylyrics/server/app.py
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from vinylyrics.engine import Engine
from vinylyrics.state.session import PlaybackSession

logger = logging.getLogger(__name__)


def create_app(
    session: PlaybackSession,
    engine: Engine,
    now_fn: Callable[[], float] = time.time,
    lifespan=None,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    clients: set[WebSocket] = set()

    def broadcast() -> None:
        payload = session.to_payload(now_fn())
        for ws in list(clients):
            task = asyncio.ensure_future(ws.send_json(payload))
            # send_json only fails INSIDE the scheduled task, never at
            # ensure_future() itself — verified live during planning that
            # a try/except wrapped around ensure_future can never observe
            # a send failure, making it dead code. A disconnected client's
            # own ws_endpoint handler already removes it from `clients`
            # via its `finally` block below; this callback only guards the
            # narrow race where a client drops between broadcasts before
            # that handler has run.
            task.add_done_callback(
                lambda t, ws=ws: clients.discard(ws) if not t.cancelled() and t.exception() else None
            )

    app.state.broadcast = broadcast

    _web_dir = Path(__file__).resolve().parent.parent / "web"

    @app.get("/")
    def index():
        return FileResponse(_web_dir / "index.html")

    @app.get("/health")
    def health():
        engine_error = getattr(app.state, "engine_error", None)
        if engine_error is not None:
            return {"status": "degraded", "error": str(engine_error)}
        return {"status": "ok"}

    @app.get("/debug")
    def debug():
        return engine.debug_snapshot()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            await websocket.send_json(session.to_payload(now_fn()))
            while True:
                await websocket.receive_text()  # keepalive; client sends nothing meaningful
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    return app
