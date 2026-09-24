from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from .asr import SherpaStreamingASR
from .audio import (
    float_to_pcm16,
    iter_pcm_chunks,
    pcm16_to_float,
    pcm_duration_ms,
    resample_linear,
    split_clauses,
    tone_pcm,
)
from .config import Settings

EmitJson = Callable[[dict[str, object]], Awaitable[None]]
EmitAudio = Callable[[bytes], Awaitable[None]]
Cancelled = Callable[[], bool]


class ModelError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        import httpx

        payload = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": True,
            "think": False,
            "options": {
                "temperature": 0.4,
                "num_ctx": self.settings.ollama_context,
                "num_predict": self.settings.ollama_predict,
            },
        }
        timeout = httpx.Timeout(30.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream("POST", f"{self.settings.ollama_url}/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise ModelError(f"Ollama returned HTTP {response.status_code}: {body[:200]!r}")
                async for line in response.aiter_lines():
                    if not line or line.startswith("event:"):
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = value.get("message", {}).get("content", "")
                    if content:
                        yield str(content)


class MockTTS:
    async def synthesize(self, text: str) -> bytes:
        duration = min(1800, max(280, len(text) * 42))
        await asyncio.sleep(0)
        return tone_pcm(duration, 24_000)

    @property
    def sample_rate(self) -> int:
        return 24_000


class KokoroTTS:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pipeline: Any | None = None
        self._sample_rate = 24_000

    def load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from kokoro import KPipeline

            self._pipeline = KPipeline(lang_code="a")
            self._sample_rate = int(getattr(self._pipeline, "sampling_rate", 24_000))
        except Exception as exc:
            self._pipeline = None
            raise ModelError("Kokoro is unavailable") from exc

    def synthesize_sync(self, text: str) -> bytes:
        try:
            self.load()
            assert self._pipeline is not None
            chunks: list[np.ndarray] = []
            for _, _, audio in self._pipeline(text, voice=self.settings.kokoro_voice):
                chunks.append(np.asarray(audio, dtype=np.float32))
            if not chunks:
                return b""
            return float_to_pcm16(np.concatenate(chunks))
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(f"Kokoro synthesis failed: {exc}") from exc

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self.synthesize_sync, text)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate


@dataclass(frozen=True)
class ResponseChunk:
    text: str
    audio: bytes
    sample_rate: int
    segment_id: str
    media_start_sample: int


class ConversationEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ollama = OllamaClient(settings)
        self.asr = SherpaStreamingASR.from_env()
        self.mock_tts = MockTTS()
        self.kokoro_tts = KokoroTTS(settings)

    async def transcribe_voice(self, audio: bytes, sample_rate: int = 48_000) -> str:
        if self.settings.model_mode == "mock" or self.asr is None:
            return "Voice input received"
        try:
            normalized = float_to_pcm16(
                resample_linear(pcm16_to_float(audio), sample_rate, self.asr.config.sample_rate)
            )
            try:
                text = await asyncio.to_thread(self.asr.transcribe_pcm16, normalized)
            finally:
                self.asr.reset()
            return text or "Voice input received"
        except asyncio.CancelledError:
            raise
        except Exception:
            return "Voice input received; local ASR is unavailable."

    async def _response_text(self, user_text: str) -> str:
        if self.settings.model_mode == "mock":
            return f"I heard you say: {user_text}"
        messages = [
            {
                "role": "system",
                "content": "You are a concise spoken conversation partner. Answer in one or two short sentences.",
            },
            {"role": "user", "content": user_text},
        ]
        pieces: list[str] = []
        try:
            async for delta in self.ollama.stream(messages):
                pieces.append(delta)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ModelError(f"local LLM unavailable: {exc}") from exc
        text = "".join(pieces).strip()
        if not text:
            raise ModelError("local LLM returned no text")
        return text

    async def stream_response(
        self,
        user_text: str,
        turn_id: str,
        response_id: str,
        session_epoch: int,
        emit_json: EmitJson,
        emit_audio: EmitAudio,
        is_cancelled: Cancelled,
    ) -> str:
        llm_started = time.monotonic()
        await emit_json(
            {
                "type": "profile.stage",
                "turn_id": turn_id,
                "response_id": response_id,
                "payload": {"stage": "llm", "state": "start"},
            }
        )
        try:
            response_text = await self._response_text(user_text)
        except ModelError:
            response_text = "The local language model is unavailable, so I cannot answer in voice yet."
            await emit_json(
                {
                    "type": "profile.stage",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "payload": {
                        "stage": "llm",
                        "state": "error",
                        "duration_ms": round((time.monotonic() - llm_started) * 1000.0, 3),
                    },
                }
            )
            await emit_json(
                {
                    "type": "error.recoverable",
                    "response_id": response_id,
                    "payload": {"code": "llm_unavailable", "recoverable": True},
                }
            )
        else:
            await emit_json(
                {
                    "type": "profile.stage",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "payload": {
                        "stage": "llm",
                        "state": "complete",
                        "duration_ms": round((time.monotonic() - llm_started) * 1000.0, 3),
                    },
                }
            )
        await emit_json(
            {
                "type": "assistant.text.delta",
                "turn_id": turn_id,
                "response_id": response_id,
                "payload": {"text": response_text},
            }
        )
        media_sequence = 0
        media_start_sample = 0
        for clause in split_clauses(response_text):
            if is_cancelled():
                return response_text
            tts_started = time.monotonic()
            await emit_json(
                {
                    "type": "profile.stage",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "payload": {"stage": "tts", "state": "start"},
                }
            )
            try:
                if self.settings.tts_mode == "kokoro":
                    audio = await self.kokoro_tts.synthesize(clause)
                    sample_rate = self.kokoro_tts.sample_rate
                else:
                    audio = await self.mock_tts.synthesize(clause)
                    sample_rate = self.mock_tts.sample_rate
            except asyncio.CancelledError:
                raise
            except Exception:
                audio = await self.mock_tts.synthesize(clause)
                sample_rate = self.mock_tts.sample_rate
                await emit_json(
                    {
                        "type": "error.recoverable",
                        "response_id": response_id,
                        "payload": {"code": "tts_fallback", "recoverable": True},
                    }
                )
            await emit_json(
                {
                    "type": "profile.stage",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "payload": {
                        "stage": "tts",
                        "state": "complete",
                        "duration_ms": round((time.monotonic() - tts_started) * 1000.0, 3),
                    },
                }
            )
            if not audio:
                continue
            segment_id = str(uuid.uuid4())
            duration_ms = pcm_duration_ms(audio, sample_rate)
            await emit_json(
                {
                    "type": "assistant.audio",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "payload": {
                        "segment_id": segment_id,
                        "media_sequence": media_sequence,
                        "media_start_sample": media_start_sample,
                        "sample_rate": sample_rate,
                        "channels": 1,
                        "duration_ms": duration_ms,
                    },
                }
            )
            total_samples = len(audio) // 2
            await emit_json(
                {
                    "type": "avatar.cues",
                    "turn_id": turn_id,
                    "response_id": response_id,
                    "payload": {
                        "segment_id": segment_id,
                        "media_sequence": media_sequence,
                        "sample_rate": sample_rate,
                        "start_sample": media_start_sample,
                        "duration_samples": total_samples,
                        "viseme": "AA",
                        "weight": 0.72,
                    },
                }
            )
            chunks = list(iter_pcm_chunks(audio))
            for index, chunk in enumerate(chunks):
                if is_cancelled():
                    return response_text
                await emit_audio(
                    self._frame_bytes(
                        session_epoch=session_epoch,
                        turn_id=turn_id,
                        response_id=response_id,
                        segment_id=segment_id,
                        media_sequence=media_sequence,
                        sample_rate=sample_rate,
                        payload=chunk,
                        final=index == len(chunks) - 1,
                    )
                )
                media_sequence += 1
            media_start_sample += total_samples
        await emit_json(
            {
                "type": "assistant.generation_complete",
                "turn_id": turn_id,
                "response_id": response_id,
                "payload": {"media_sequences": media_sequence},
            }
        )
        return response_text

    @staticmethod
    def _frame_bytes(
        *,
        session_epoch: int,
        turn_id: str,
        response_id: str,
        segment_id: str,
        media_sequence: int,
        sample_rate: int,
        payload: bytes,
        final: bool,
    ) -> bytes:
        from .protocol import AudioFrame, pack_audio_frame

        return pack_audio_frame(
            AudioFrame(
                session_epoch=session_epoch,
                response_id=uuid.UUID(response_id),
                turn_id=uuid.UUID(turn_id),
                segment_id=uuid.UUID(segment_id),
                media_sequence=media_sequence,
                sample_rate=sample_rate,
                channels=1,
                payload=payload,
                final=final,
            )
        )
