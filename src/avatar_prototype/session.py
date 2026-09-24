from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .audio import float_to_pcm16, pcm16_to_float, resample_linear, rms
from .config import Settings
from .models import ConversationEngine
from .protocol import event
from .telemetry import MetricsRegistry
from .turn import SmartTurn, TurnDetectorUnavailable
from .vad import SileroVAD, VADUnavailable

EmitJson = Callable[[dict[str, object]], Awaitable[None]]
EmitAudio = Callable[[bytes], Awaitable[None]]


@dataclass
class AssistantSegment:
    segment_id: str
    response_id: str
    text: str
    state: str = "generated"
    media_sequences: list[int] = field(default_factory=list)
    last_acknowledged_sequence: int = -1


class SessionCoordinator:
    def __init__(
        self,
        settings: Settings,
        engine: ConversationEngine,
        send_json: EmitJson,
        send_audio: EmitAudio,
        *,
        session_id: str | None = None,
        session_epoch: int = 1,
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.vad = SileroVAD() if settings.vad_mode == "silero" else None
        self.smart_turn = SmartTurn.from_env() if settings.smart_turn_mode == "smart" else None
        self.metrics = MetricsRegistry()
        self.send_json = send_json
        self.send_audio = send_audio
        self.session_id = session_id or str(uuid.uuid4())
        self.session_epoch = session_epoch
        self.created_at = time.time()
        self.last_activity = self.created_at
        self.audio_buffer = bytearray()
        self.speech_active = False
        self.last_voice_at = 0.0
        self.voice_commit_task: asyncio.Task[None] | None = None
        self.active_turn_id: str | None = None
        self.active_response_id: str | None = None
        self.active_user_text = ""
        self.active_assistant_text = ""
        self.response_started_at: float | None = None
        self.first_audio_recorded = False
        self.response_task: asyncio.Task[None] | None = None
        self.cancelled_responses: set[str] = set()
        self.segments: list[AssistantSegment] = []
        self.transcript: list[dict[str, str]] = []
        self.input_mode = "hands_free"
        self.last_playback_ack = -1
        self.closed = False

    @property
    def busy(self) -> bool:
        return self.active_response_task_running or (
            self.voice_commit_task is not None and not self.voice_commit_task.done()
        )

    @property
    def active_response_task_running(self) -> bool:
        return self.response_task is not None and not self.response_task.done()

    async def emit(
        self,
        event_type: str,
        payload: dict[str, object] | None = None,
        *,
        turn_id: str | None = None,
        response_id: str | None = None,
    ) -> None:
        await self.send_json(
            event(
                event_type,
                self.session_id,
                self.session_epoch,
                payload,
                turn_id=turn_id,
                response_id=response_id,
            )
        )

    async def _engine_event(self, value: dict[str, object]) -> None:
        event_type = str(value.get("type", "engine.event"))
        payload = value.get("payload")
        turn_id_value = value.get("turn_id")
        response_id_value = value.get("response_id")
        turn_id = str(turn_id_value) if turn_id_value else None
        response_id = str(response_id_value) if response_id_value else None
        if event_type == "profile.stage" and isinstance(payload, dict):
            stage = str(payload.get("stage", "unknown"))
            state = str(payload.get("state", "event"))
            self.metrics.increment(f"profile.{stage}.{state}")
            duration = payload.get("duration_ms")
            if isinstance(duration, (int, float)):
                self.metrics.observe(f"profile.{stage}", float(duration))
        if event_type == "assistant.audio":
            if not self.first_audio_recorded and self.response_started_at is not None:
                self.metrics.observe("speech_end_to_first_audio", (time.monotonic() - self.response_started_at) * 1000.0)
                self.first_audio_recorded = True
            await self.emit(
                "assistant.state",
                {"state": "speaking"},
                turn_id=turn_id,
                response_id=response_id,
            )
        await self.send_json(
            event(
                event_type,
                self.session_id,
                self.session_epoch,
                payload if isinstance(payload, dict) else None,
                turn_id=turn_id,
                response_id=response_id,
            )
        )

    async def handle_audio(self, data: bytes) -> None:
        if self.closed or not data:
            return
        self.last_activity = time.time()
        self.metrics.increment("audio.frames")
        self.metrics.observe("audio.frame_bytes", len(data))
        vad_started = time.monotonic()
        if len(self.audio_buffer) + len(data) > self.settings.max_audio_buffer_bytes:
            self.metrics.increment("audio.buffer_overflow")
            await self.cancel_active_response("audio_buffer_limit")
            self.audio_buffer.clear()
            return
        self.audio_buffer.extend(data)
        if self.vad is not None:
            vad_samples = resample_linear(pcm16_to_float(data), 48_000, 16_000)
            vad_audio = float_to_pcm16(vad_samples)
            try:
                level = await asyncio.to_thread(self.vad.is_speech, vad_audio, 16000)
            except VADUnavailable:
                await self.emit("error.recoverable", {"code": "vad_unavailable", "recoverable": True})
                self.audio_buffer.clear()
                return
        else:
            level = rms(pcm16_to_float(data))
        self.metrics.observe("vad.frame", (time.monotonic() - vad_started) * 1000.0)
        now = time.monotonic()
        if level >= self.settings.speech_rms_threshold:
            if not self.speech_active:
                self.speech_active = True
                await self.emit(
                    "speech.started",
                    {"source": "local_energy_mock" if self.settings.vad_mode == "mock" else "vad"},
                )
            self.last_voice_at = now
        elif self.speech_active and self.input_mode == "hands_free":
            if (now - self.last_voice_at) * 1000 >= self.settings.silence_ms:
                if self.voice_commit_task is None or self.voice_commit_task.done():
                    self.voice_commit_task = asyncio.create_task(self._commit_voice_turn())

    async def handle_message(self, message: dict[str, Any]) -> None:
        if self.closed:
            return
        self.last_activity = time.time()
        message_type = str(message.get("type", ""))
        self.metrics.increment(f"message.{message_type or 'unknown'}")
        if message_type == "input.start":
            self.input_mode = str(message.get("mode", "hands_free"))
            self.speech_active = False
            self.last_voice_at = time.monotonic()
        elif message_type == "input.end":
            await self._commit_voice_turn(request_id=str(message.get("request_id", "")))
        elif message_type == "input.cancel":
            self.audio_buffer.clear()
            self.speech_active = False
            task = self.voice_commit_task
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self.voice_commit_task = None
            await self.emit("input.cancelled", {"request_id": message.get("request_id")})
        elif message_type == "text.submit":
            text = str(message.get("text", "")).strip()
            if text:
                await self._commit_text_turn(text, str(message.get("request_id", "")))
        elif message_type in {"response.cancel", "response.stop"}:
            await self.cancel_active_response("client_request")
        elif message_type == "playout.ack":
            sequence = int(message.get("media_sequence", -1))
            self.last_playback_ack = max(self.last_playback_ack, sequence)
            for segment in self.segments:
                if segment.response_id == self.active_response_id:
                    segment.last_acknowledged_sequence = max(segment.last_acknowledged_sequence, sequence)
        elif message_type == "input.local_hint":
            if self.active_response_task_running:
                await self.emit(
                    "interrupt.candidate",
                    {"source": "browser", "level": message.get("level", 0.0)},
                    response_id=self.active_response_id,
                )
        elif message_type == "metrics.request":
            await self.emit("metrics.snapshot", self.metrics.snapshot())
        elif message_type == "ping":
            await self.emit("pong", {"client_time": message.get("client_time")})
        elif message_type == "close":
            await self.close("client_close")

    async def _commit_voice_turn(self, request_id: str = "") -> None:
        if self.closed or not self.audio_buffer:
            return
        turn_started = time.monotonic()
        audio = bytes(self.audio_buffer)
        if self.smart_turn is not None:
            smart_started = time.monotonic()
            samples = resample_linear(pcm16_to_float(audio), 48_000, 16_000)
            smart_audio = float_to_pcm16(samples)
            try:
                complete = await asyncio.to_thread(self.smart_turn.is_complete, smart_audio)
                self.metrics.observe("turn.smart", (time.monotonic() - smart_started) * 1000.0)
            except TurnDetectorUnavailable:
                await self.emit("error.recoverable", {"code": "turn_detector_unavailable", "recoverable": True})
                return
            if not complete:
                self.speech_active = True
                return
        self.audio_buffer.clear()
        self.speech_active = False
        asr_started = time.monotonic()
        text = await self.engine.transcribe_voice(audio)
        self.metrics.observe("asr.voice_turn", (time.monotonic() - asr_started) * 1000.0)
        if not text:
            return
        self.metrics.observe("turn.commit", (time.monotonic() - turn_started) * 1000.0)
        await self._commit_text_turn(text, request_id, source="voice")

    async def _commit_text_turn(
        self,
        text: str,
        request_id: str,
        *,
        source: str = "text",
    ) -> None:
        if self.active_response_task_running:
            await self.cancel_active_response("new_user_turn")
        turn_started = time.monotonic()
        turn_id = str(uuid.uuid4())
        response_id = str(uuid.uuid4())
        self.active_turn_id = turn_id
        self.active_response_id = response_id
        self.active_user_text = text
        self.active_assistant_text = ""
        self.response_started_at = turn_started
        self.first_audio_recorded = False
        self.cancelled_responses.discard(response_id)
        self.transcript.append({"role": "user", "text": text, "turn_id": turn_id})
        self.segments.append(AssistantSegment(segment_id=str(uuid.uuid4()), response_id=response_id, text=""))
        await self.emit("stt.final", {"text": text, "source": source, "request_id": request_id}, turn_id=turn_id)
        await self.emit("turn.committed", {"source": source, "request_id": request_id}, turn_id=turn_id)
        await self.emit("assistant.state", {"state": "thinking"}, turn_id=turn_id, response_id=response_id)

        async def run() -> None:
            try:
                assistant_text = await self.engine.stream_response(
                    text,
                    turn_id,
                    response_id,
                    self.session_epoch,
                    self._engine_event,
                    self.send_audio,
                    lambda: response_id in self.cancelled_responses,
                )
                self.active_assistant_text = assistant_text
                if self.response_started_at is not None:
                    self.metrics.observe("response.total", (time.monotonic() - self.response_started_at) * 1000.0)
                self.metrics.increment("response.completed")
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.emit(
                    "error.recoverable",
                    {"code": "response_failed", "recoverable": True},
                    turn_id=turn_id,
                    response_id=response_id,
                )
            if response_id not in self.cancelled_responses:
                self.transcript.append({"role": "assistant", "text": self.active_assistant_text, "turn_id": turn_id})
                await self.emit(
                    "response.completed",
                    {"text": self.active_assistant_text, "history": "conservative"},
                    turn_id=turn_id,
                    response_id=response_id,
                )
                await self.emit("metrics.snapshot", self.metrics.snapshot())

        self.response_task = asyncio.create_task(run())

    async def cancel_active_response(self, reason: str) -> None:
        response_id = self.active_response_id
        task = self.response_task
        if response_id is None:
            return
        self.cancelled_responses.add(response_id)
        self.metrics.increment("response.cancelled")
        if self.response_started_at is not None:
            self.metrics.observe("response.cancel_latency", (time.monotonic() - self.response_started_at) * 1000.0)
        self.active_assistant_text = ""
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for segment in self.segments:
            if segment.response_id == response_id and segment.state == "generated":
                segment.state = "cancelled"
        await self.emit("response.cancelled", {"reason": reason, "history": "conservative"}, response_id=response_id)
        self.active_response_id = None
        self.response_started_at = None
        self.response_task = None

    async def close(self, reason: str) -> None:
        if self.closed:
            return
        await self.cancel_active_response(reason)
        if self.voice_commit_task is not None and not self.voice_commit_task.done():
            self.voice_commit_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.voice_commit_task
        self.closed = True
        self.audio_buffer.clear()
        self.transcript.clear()
        self.segments.clear()
