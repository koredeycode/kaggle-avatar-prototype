from __future__ import annotations

from typing import Any


class VADUnavailable(RuntimeError):
    pass


class SileroVAD:
    def __init__(self) -> None:
        self.model: Any | None = None

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            from silero_vad import load_silero_vad
            self.model = load_silero_vad()
        except Exception as exc:
            raise VADUnavailable("Silero VAD is unavailable") from exc

    def is_speech(self, pcm16: bytes, sample_rate: int = 16000) -> float:
        try:
            self.load()
            if self.model is None:
                raise VADUnavailable("Silero model is unavailable")
            import numpy as np

            samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
            if samples.size == 0:
                return 0.0
            try:
                import torch

                probability = self.model(torch_tensor=torch.from_numpy(samples), sample_rate=sample_rate)
            except TypeError:
                probability = self.model(samples, sample_rate)
            if hasattr(probability, "item"):
                return float(probability.item())
            return float(probability)
        except VADUnavailable:
            raise
        except Exception as exc:
            raise VADUnavailable("Silero VAD inference failed") from exc
