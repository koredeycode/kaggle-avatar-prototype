from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class TurnDetectorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SmartTurnConfig:
    model_path: str
    sample_rate: int = 16000
    threshold: float = 0.5
    max_input_seconds: int = 8


class SmartTurn:
    def __init__(self, config: SmartTurnConfig) -> None:
        self.config = config
        self.session: Any | None = None

    @classmethod
    def from_env(cls) -> SmartTurn | None:
        path = os.getenv("SMART_TURN_MODEL", "")
        if not path:
            return None
        return cls(
            SmartTurnConfig(
                model_path=path,
                threshold=float(os.getenv("SMART_TURN_THRESHOLD", "0.5")),
            )
        )

    def load(self) -> None:
        if self.session is not None:
            return
        if not Path(self.config.model_path).exists():
            raise TurnDetectorUnavailable("Smart Turn model file is missing")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise TurnDetectorUnavailable("onnxruntime is not installed") from exc
        self.session = ort.InferenceSession(
            self.config.model_path,
            providers=["CPUExecutionProvider"],
        )

    def is_complete(self, pcm16: bytes) -> bool:
        self.load()
        if self.session is None:
            raise TurnDetectorUnavailable("Smart Turn session is unavailable")
        import numpy as np

        samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        if samples.size == 0 or samples.size / self.config.sample_rate > self.config.max_input_seconds:
            return False
        input_name = self.session.get_inputs()[0].name
        result = self.session.run(None, {input_name: samples[None, :]})
        values = result[0].reshape(-1)
        if values.size == 0:
            return False
        return bool(float(values[-1]) >= self.config.threshold)
