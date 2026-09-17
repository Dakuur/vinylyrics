# tests/server/test_app.py
from unittest import mock

from vinylyrics.server.app import create_app
from vinylyrics.state.session import DisplayState, PlaybackSession
from fastapi.testclient import TestClient


def _fake_engine(snapshot=None):
    engine = mock.MagicMock()
    engine.debug_snapshot.return_value = snapshot or {
        "last_recognition": None, "speed": None, "rms_dbfs": -60.0, "anchor_history": [],
    }
    return engine


def test_health_endpoint():
    session = PlaybackSession()
    app = create_app(session=session, engine=_fake_engine())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_debug_endpoint_reports_engine_snapshot():
    session = PlaybackSession()
    snapshot = {"last_recognition": {"title": "Bonito"}, "speed": 1.01, "rms_dbfs": -30.0, "anchor_history": []}
    app = create_app(session=session, engine=_fake_engine(snapshot))
    client = TestClient(app)

    response = client.get("/debug")

    assert response.status_code == 200
    assert response.json() == snapshot


def test_websocket_sends_current_state_immediately_on_connect():
    session = PlaybackSession()
    session.on_listening_started()
    app = create_app(session=session, engine=_fake_engine(), now_fn=lambda: 0.0)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        payload = ws.receive_json()

    assert payload["state"] == DisplayState.LISTENING.value


def test_websocket_broadcasts_on_session_change():
    from vinylyrics.recognition.base import RecognitionResult

    session = PlaybackSession()
    app = create_app(session=session, engine=_fake_engine(), now_fn=lambda: 0.0)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        initial = ws.receive_json()
        assert initial["state"] == DisplayState.IDLE.value

        result = RecognitionResult(
            title="Bonito", artist="Jarabe de Palo", album=None, cover_url=None,
            offset=0.0, timeskew=0.0, frequencyskew=0.0, isrc=None, duration=None,
        )
        session.on_recognized(result, None, wall_time=0.0)
        # `ws` (the WebSocketTestSession) runs the ASGI app on its own
        # background event loop via an anyio portal. Calling
        # `app.state.broadcast()` directly here — from the test's own
        # thread, with no running loop — was verified live during planning
        # to hang forever: `asyncio.ensure_future()` outside a running
        # loop implicitly creates a throwaway loop that never actually
        # runs, so the scheduled `send_json` never executes and
        # `ws.receive_json()` below blocks indefinitely waiting for a
        # message that never arrives. Routing the call through `ws.portal`
        # runs it on the SAME loop the websocket connection lives on —
        # exactly matching how `on_change` is really invoked in production
        # (always from inside the engine's own already-running coroutine,
        # on the app's one event loop, never cross-thread).
        ws.portal.call(app.state.broadcast)

        updated = ws.receive_json()
        assert updated["state"] == DisplayState.PLAYING.value
        assert updated["track"]["title"] == "Bonito"


def test_index_serves_the_web_page():
    session = PlaybackSession()
    app = create_app(session=session, engine=_fake_engine())
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "vinylyrics" in response.text
    assert response.headers["content-type"].startswith("text/html")
