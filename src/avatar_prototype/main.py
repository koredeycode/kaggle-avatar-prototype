from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .models import ConversationEngine
from .session import SessionCoordinator

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def _token_matches(value: str | None, expected: str) -> bool:
    return bool(value) and secrets.compare_digest(value.removeprefix("Bearer ").strip(), expected)


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or Settings.from_env()
    engine = ConversationEngine(selected)
    active_session: SessionCoordinator | None = None
    session_lock = asyncio.Lock()

    app = FastAPI(
        title="Kaggle Avatar Prototype",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = selected
    app.state.active_session = None

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="static client is missing")
        return FileResponse(index_path)

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {
            "ok": True,
            "mode": selected.model_mode,
            "public": selected.public_mode,
            "active_session": app.state.active_session is not None,
        }

    @app.get("/api/profile")
    async def profile() -> dict[str, object]:
        return {
            "model_profile": "keyless-local-v1",
            "model_mode": selected.model_mode,
            "tts_mode": selected.tts_mode,
            "vad_mode": selected.vad_mode,
            "barge_in": True,
            "push_to_talk": True,
            "avatar": "procedural-2d",
        }

    @app.post("/api/session")
    async def create_session(authorization: str | None = Header(default=None)) -> dict[str, object]:
        nonlocal active_session
        if not _token_matches(authorization, selected.runtime_token):
            raise HTTPException(status_code=401, detail="invalid runtime token")
        async with session_lock:
            if active_session is not None and not active_session.closed:
                raise HTTPException(status_code=409, detail="prototype session is busy")
        return {"session_id": "pending", "websocket_path": "/ws", "protocol": 1}

    @app.get("/metrics")
    async def metrics(request: Request) -> JSONResponse:
        if selected.public_mode or request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
            return JSONResponse(status_code=404, content={"detail": "not found"})
        session = app.state.active_session
        return JSONResponse(
            content={
                "ok": True,
                "active_session": session is not None,
                "metrics": session.metrics.snapshot() if session is not None else {},
            }
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        nonlocal active_session
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host")
        if selected.public_mode and origin and host and urlparse(origin).netloc != host:
            await websocket.close(code=1008, reason="origin not allowed")
            return
        await websocket.accept()
        session: SessionCoordinator | None = None
        try:
            first = await websocket.receive_json()
            token = str(first.get("token", ""))
            if not secrets.compare_digest(token, selected.runtime_token):
                await websocket.close(code=1008, reason="invalid runtime token")
                return
            if first.get("protocol") != 1:
                await websocket.close(code=1008, reason="unsupported protocol")
                return
            async with session_lock:
                if active_session is not None and not active_session.closed:
                    await websocket.close(code=4001, reason="prototype session is busy")
                    return
                session = SessionCoordinator(
                    selected,
                    engine,
                    lambda value: websocket.send_json(value),
                    lambda value: websocket.send_bytes(value),
                )
                active_session = session
                app.state.active_session = session
            await session.emit("ready", {
                "model_profile": "keyless-local-v1",
                "input": {"capture_sample_rate": 48000, "wire_format": "pcm_s16le", "channels": 1},
                "output": {"sample_rate": 24000, "wire_format": "pcm_s16le", "channels": 1},
                "capabilities": {
                    "partial_transcripts": True,
                    "barge_in": True,
                    "push_to_talk": True,
                    "viseme_events": True,
                },
            })
            await session.emit("metrics.snapshot", session.metrics.snapshot())
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    binary = message["bytes"]
                    if len(binary) > 65_535:
                        await websocket.close(code=1009, reason="audio frame too large")
                        return
                    await session.handle_audio(binary)
                elif message.get("text") is not None:
                    text_value = message["text"]
                    if len(text_value) > 65_535:
                        await websocket.close(code=1009, reason="message too large")
                        return
                    value = json.loads(text_value)
                    if isinstance(value, dict):
                        await session.handle_message(value)
        except WebSocketDisconnect:
            pass
        except (ValueError, TypeError, json.JSONDecodeError):
            with contextlib.suppress(Exception):
                await websocket.close(code=1003, reason="invalid message")
        finally:
            if session is not None:
                await session.close("websocket_closed")
                async with session_lock:
                    if active_session is session:
                        active_session = None
                        app.state.active_session = None

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = app.state.settings
    print(f"Prototype runtime token: {settings.runtime_token}")
    uvicorn.run(app, host=settings.app_host, port=settings.app_port, reload=False)


if __name__ == "__main__":
    run()
