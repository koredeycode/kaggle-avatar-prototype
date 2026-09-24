#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os

import httpx
import websockets


async def run(url: str, token: str) -> int:
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        response = await client.get(f"{url}/healthz")
        response.raise_for_status()
        health = response.json()
        print(json.dumps({"health": health}, indent=2))
    ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    async with websockets.connect(ws_url) as socket:
        await socket.send(json.dumps({"type": "auth", "protocol": 1, "token": token}))
        ready = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if ready.get("type") != "ready":
            raise RuntimeError(f"unexpected first event: {ready}")
        await socket.send(json.dumps({"type": "text.submit", "text": "hello avatar", "request_id": "smoke-1"}))
        saw_response = False
        saw_audio_metadata = False
        saw_audio_frame = False
        saw_generation_complete = False
        saw_response_complete = False
        for _ in range(128):
            message = await asyncio.wait_for(socket.recv(), timeout=10)
            if isinstance(message, bytes):
                if len(message) < 77 or message[:2] != b"AV" or message[2] != 1 or message[3] != 1:
                    raise RuntimeError("invalid assistant audio frame")
                payload_length = int.from_bytes(message[73:77], "big")
                if len(message) != 77 + payload_length:
                    raise RuntimeError("truncated assistant audio frame")
                saw_audio_frame = True
                continue
            value = json.loads(message)
            event_type = value.get("type")
            if event_type == "assistant.text.delta":
                saw_response = True
            elif event_type == "assistant.audio":
                saw_audio_metadata = True
            elif event_type == "assistant.generation_complete":
                saw_generation_complete = True
            elif event_type == "response.completed":
                saw_response_complete = True
            if saw_response and saw_audio_metadata and saw_audio_frame and saw_generation_complete and saw_response_complete:
                break
        if not all((saw_response, saw_audio_metadata, saw_audio_frame, saw_generation_complete, saw_response_complete)):
            raise RuntimeError("incomplete assistant response")
        print(json.dumps({"smoke": "ok", "session_id": ready.get("session_id")}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.getenv("RUNTIME_TOKEN", ""))
    args = parser.parse_args()
    if not args.token:
        parser.error("--token or RUNTIME_TOKEN is required")
    return asyncio.run(run(args.url, args.token))


if __name__ == "__main__":
    raise SystemExit(main())
