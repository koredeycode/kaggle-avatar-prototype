from __future__ import annotations

import struct
import time
import uuid
from dataclasses import dataclass

MAGIC = b"AV"
VERSION = 1
TYPE_AUDIO = 1
FLAG_FINAL = 1
HEADER = struct.Struct("!2sBBII16s16s16sQIBI")


@dataclass(frozen=True)
class AudioFrame:
    session_epoch: int
    response_id: uuid.UUID
    turn_id: uuid.UUID
    segment_id: uuid.UUID
    media_sequence: int
    sample_rate: int
    channels: int
    payload: bytes
    final: bool = False


def uuid_bytes(value: str | uuid.UUID) -> bytes:
    return uuid.UUID(str(value)).bytes


def pack_audio_frame(frame: AudioFrame) -> bytes:
    if len(frame.payload) > 65_535:
        raise ValueError("audio payload is too large")
    flags = FLAG_FINAL if frame.final else 0
    header = HEADER.pack(
        MAGIC,
        VERSION,
        TYPE_AUDIO,
        flags,
        frame.session_epoch,
        uuid_bytes(frame.response_id),
        uuid_bytes(frame.turn_id),
        uuid_bytes(frame.segment_id),
        frame.media_sequence,
        frame.sample_rate,
        frame.channels,
        len(frame.payload),
    )
    return header + frame.payload


def unpack_audio_frame(data: bytes) -> AudioFrame:
    if len(data) < HEADER.size:
        raise ValueError("audio frame is shorter than its header")
    (
        magic,
        version,
        message_type,
        flags,
        session_epoch,
        response_bytes,
        turn_bytes,
        segment_bytes,
        media_sequence,
        sample_rate,
        channels,
        payload_length,
    ) = HEADER.unpack(data[: HEADER.size])
    if magic != MAGIC or version != VERSION or message_type != TYPE_AUDIO:
        raise ValueError("invalid audio frame header")
    payload = data[HEADER.size : HEADER.size + payload_length]
    if len(payload) != payload_length:
        raise ValueError("audio frame payload is truncated")
    return AudioFrame(
        session_epoch=session_epoch,
        response_id=uuid.UUID(bytes=response_bytes),
        turn_id=uuid.UUID(bytes=turn_bytes),
        segment_id=uuid.UUID(bytes=segment_bytes),
        media_sequence=media_sequence,
        sample_rate=sample_rate,
        channels=channels,
        payload=payload,
        final=bool(flags & FLAG_FINAL),
    )


def event(
    event_type: str,
    session_id: str,
    session_epoch: int,
    payload: dict[str, object] | None = None,
    *,
    turn_id: str | None = None,
    response_id: str | None = None,
    sequence: int | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "type": event_type,
        "protocol": 1,
        "session_id": session_id,
        "session_epoch": session_epoch,
        "sent_at": time.time(),
    }
    if turn_id is not None:
        value["turn_id"] = turn_id
    if response_id is not None:
        value["response_id"] = response_id
    if sequence is not None:
        value["sequence"] = sequence
    if payload is not None:
        value["payload"] = payload
    return value
