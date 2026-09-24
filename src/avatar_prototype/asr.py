from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class ASRUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StreamingASRConfig:
    encoder: str
    decoder: str
    joiner: str
    tokens: str
    sample_rate: int = 16000
    feature_dim: int = 80
    num_threads: int = 1


class SherpaStreamingASR:
    def __init__(self, config: StreamingASRConfig) -> None:
        self.config = config
        self.recognizer: Any | None = None
        self.stream: Any | None = None

    @classmethod
    def from_env(cls) -> SherpaStreamingASR | None:
        names = {
            "encoder": os.getenv("SHERPA_ENCODER", ""),
            "decoder": os.getenv("SHERPA_DECODER", ""),
            "joiner": os.getenv("SHERPA_JOINER", ""),
            "tokens": os.getenv("SHERPA_TOKENS", ""),
        }
        if not all(names.values()):
            return None
        config = StreamingASRConfig(
            encoder=names["encoder"],
            decoder=names["decoder"],
            joiner=names["joiner"],
            tokens=names["tokens"],
            sample_rate=int(os.getenv("SHERPA_SAMPLE_RATE", "16000")),
            feature_dim=int(os.getenv("SHERPA_FEATURE_DIM", "80")),
            num_threads=int(os.getenv("SHERPA_NUM_THREADS", "1")),
        )
        return cls(config)

    def load(self) -> None:
        if self.recognizer is not None:
            return
        try:
            from sherpa_onnx import OnlineRecognizer
        except ImportError as exc:
            raise ASRUnavailable("sherpa-onnx is not installed") from exc
        required = [self.config.encoder, self.config.decoder, self.config.joiner, self.config.tokens]
        if not all(os.path.exists(path) for path in required):
            raise ASRUnavailable("one or more sherpa model files are missing")
        self.recognizer = OnlineRecognizer.from_transducer(
            tokens=self.config.tokens,
            encoder=self.config.encoder,
            decoder=self.config.decoder,
            joiner=self.config.joiner,
            num_threads=self.config.num_threads,
            sample_rate=self.config.sample_rate,
            feature_dim=self.config.feature_dim,
        )
        self.reset()

    def reset(self) -> None:
        if self.recognizer is None:
            return
        self.stream = self.recognizer.create_stream()

    def transcribe_pcm16(self, data: bytes) -> str:
        self.load()
        if self.stream is None or self.recognizer is None:
            return ""
        import numpy as np

        samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
        self.stream.accept_waveform(self.config.sample_rate, samples)
        while self.recognizer.is_ready(self.stream):
            self.recognizer.decode_stream(self.stream)
        return str(self.recognizer.get_result(self.stream))
