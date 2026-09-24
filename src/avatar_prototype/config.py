from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    runtime_token: str = ""
    model_mode: str = "mock"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_context: int = 4096
    ollama_predict: int = 160
    kokoro_voice: str = "af_heart"
    public_mode: bool = False
    vad_mode: str = "mock"
    smart_turn_mode: str = "manual"
    tts_mode: str = "mock"
    silence_ms: int = 900
    speech_rms_threshold: float = 0.015
    max_audio_buffer_bytes: int = 4_000_000

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            app_host=os.getenv("APP_HOST", "127.0.0.1"),
            app_port=int(os.getenv("APP_PORT", "8000")),
            runtime_token=os.getenv("RUNTIME_TOKEN") or secrets.token_urlsafe(32),
            model_mode=os.getenv("MODEL_MODE", "mock").lower(),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
            ollama_context=int(os.getenv("OLLAMA_CONTEXT", "4096")),
            ollama_predict=int(os.getenv("OLLAMA_PREDICT", "160")),
            kokoro_voice=os.getenv("KOKORO_VOICE", "af_heart"),
            public_mode=os.getenv("PUBLIC_MODE", "false").lower() in {"1", "true", "yes"},
            vad_mode=os.getenv("VAD_MODE", "mock").lower(),
            smart_turn_mode=os.getenv("SMART_TURN_MODE", "manual").lower(),
            tts_mode=os.getenv("TTS_MODE", "mock").lower(),
            silence_ms=int(os.getenv("SILENCE_MS", "900")),
            speech_rms_threshold=float(os.getenv("SPEECH_RMS_THRESHOLD", "0.015")),
            max_audio_buffer_bytes=int(os.getenv("MAX_AUDIO_BUFFER_BYTES", "4000000")),
        )
