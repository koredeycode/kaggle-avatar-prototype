from __future__ import annotations

import math
import struct
from collections.abc import Iterable

import numpy as np


def pcm16_to_float(data: bytes) -> np.ndarray:
    if len(data) % 2:
        data = data[:-1]
    if not data:
        return np.empty(0, dtype=np.float32)
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    target_length = max(1, int(round(samples.size * target_rate / source_rate)))
    source_positions = np.linspace(0.0, samples.size - 1, num=samples.size, dtype=np.float64)
    target_positions = np.linspace(0.0, samples.size - 1, num=target_length, dtype=np.float64)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)


def split_clauses(text: str, max_words: int = 14) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    clauses: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(current) >= max_words or word.endswith((".", "!", "?", ",", ";", ":")):
            clauses.append(" ".join(current))
            current = []
    if current:
        clauses.append(" ".join(current))
    return clauses


def tone_pcm(
    duration_ms: int,
    sample_rate: int,
    frequency: float = 220.0,
    amplitude: float = 0.08,
) -> bytes:
    sample_count = max(1, int(sample_rate * duration_ms / 1000))
    time = np.arange(sample_count, dtype=np.float32) / sample_rate
    envelope = np.minimum(1.0, time * 20.0) * np.minimum(1.0, np.maximum(0.0, (duration_ms / 1000.0) - time) * 20.0)
    signal = amplitude * envelope * np.sin(2.0 * math.pi * frequency * time)
    return float_to_pcm16(signal)


def iter_pcm_chunks(data: bytes, chunk_bytes: int = 4096) -> Iterable[bytes]:
    for start in range(0, len(data), chunk_bytes):
        yield data[start : start + chunk_bytes]


def pcm_duration_ms(data: bytes, sample_rate: int, channels: int = 1) -> int:
    bytes_per_sample = 2 * channels
    samples = len(data) // max(1, bytes_per_sample)
    return int(samples * 1000 / max(1, sample_rate * channels))


def wav_header(sample_rate: int, channels: int, data_bytes: int) -> bytes:
    bits = 16
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_bytes,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_bytes,
    )
