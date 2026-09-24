#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os

import httpx
import websockets


async def run(url: str, token: str) -> int:
    async with httpx.AsyncClient(timeout=10.0) as client:
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
        for _ in range(8):
            value = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
            if value.get("type") == "assistant.text.delta":
                saw_response = True
                break
        if not saw_response:
            raise RuntimeError("no assistant response observed")
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
