# vinylyrics/server/app.py
from __future__ import annotations

import asyncio
import time
from typing import Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from vinylyrics.engine import Engine
from vinylyrics.state.session import PlaybackSession


def create_app(session: PlaybackSession, engine: Engine, now_fn: Callable[[], float] = time.monotonic) -> FastAPI:
    app = FastAPI()
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
            task.add_done_callback(lambda t, ws=ws: clients.discard(ws) if t.exception() else None)

    app.state.broadcast = broadcast

    @app.get("/health")
    def health():
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
