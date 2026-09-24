from __future__ import annotations

import asyncio

import pytest

from avatar_prototype.audio import pcm16_to_float, rms, split_clauses
from avatar_prototype.config import Settings
from avatar_prototype.models import ConversationEngine
from avatar_prototype.protocol import AudioFrame, pack_audio_frame, unpack_audio_frame
from avatar_prototype.session import SessionCoordinator
from avatar_prototype.telemetry import MetricsRegistry


def test_split_clauses() -> None:
    clauses = split_clauses("one two three. four five", max_words=3)
    assert clauses == ["one two three.", "four five"]


def test_audio_frame_round_trip() -> None:
    frame = AudioFrame(
        session_epoch=2,
        response_id="11111111-1111-1111-1111-111111111111",
        turn_id="22222222-2222-2222-2222-222222222222",
        segment_id="33333333-3333-3333-3333-333333333333",
        media_sequence=4,
        sample_rate=24000,
        channels=1,
        payload=b"\x01\x02\x03\x04",
        final=True,
    )
    parsed = unpack_audio_frame(pack_audio_frame(frame))
    assert parsed == frame


def test_pcm_helpers() -> None:
    samples = pcm16_to_float(b"\x00\x00\x00\x00")
    assert samples.tolist() == [0.0, 0.0]
    assert rms(samples) == 0.0


def test_metrics_snapshot() -> None:
    metrics = MetricsRegistry()
    metrics.increment("audio.frames")
    metrics.observe("response.total", 120.0)
    metrics.observe("response.total", 80.0)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["audio.frames"] == 1
    assert snapshot["timings"]["response.total"]["count"] == 2
    assert snapshot["timings"]["response.total"]["p50_ms"] == 100.0


@pytest.mark.asyncio
async def test_session_text_turn() -> None:
    events: list[dict[str, object]] = []
    audio: list[bytes] = []

    async def send_json(value: dict[str, object]) -> None:
        events.append(value)

    async def send_audio(value: bytes) -> None:
        audio.append(value)

    settings = Settings(runtime_token="test", model_mode="mock")
    session = SessionCoordinator(
        settings,
        ConversationEngine(settings),
        send_json,
        send_audio,
        session_id="session",
    )
    await session.handle_message({"type": "text.submit", "text": "hello", "request_id": "1"})
    await asyncio.sleep(0.05)
    assert any(item.get("type") == "assistant.text.delta" for item in events)
    assert audio
    await session.close("test")


@pytest.mark.asyncio
async def test_session_mock_voice_turn() -> None:
    events: list[dict[str, object]] = []
    audio: list[bytes] = []

    async def send_json(value: dict[str, object]) -> None:
        events.append(value)

    async def send_audio(value: bytes) -> None:
        audio.append(value)

    settings = Settings(runtime_token="test", model_mode="mock", vad_mode="mock")
    session = SessionCoordinator(
        settings,
        ConversationEngine(settings),
        send_json,
        send_audio,
        session_id="voice-session",
    )
    await session.handle_message({"type": "input.start", "mode": "manual", "sample_rate": 48000})
    await session.handle_audio(b"\x00\x00")
    await session.handle_message({"type": "input.end", "request_id": "voice-1"})
    await asyncio.sleep(0.05)
    assert any(item.get("type") == "stt.final" for item in events)
    assert any(item.get("type") == "assistant.text.delta" for item in events)
    assert audio
    await session.close("test")
