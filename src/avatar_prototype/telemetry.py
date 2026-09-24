from __future__ import annotations

import statistics
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    span_id: str
    name: str
    started_at: float
    fields: dict[str, Any] = field(default_factory=dict)


class MetricsRegistry:
    def __init__(self, max_spans: int = 200, max_samples: int = 500) -> None:
        self._lock = threading.RLock()
        self.counters: dict[str, int] = defaultdict(int)
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.gauges: dict[str, float] = {}
        self.recent_spans: deque[dict[str, Any]] = deque(maxlen=max_spans)
        self.max_samples = max_samples

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[name] += amount

    def observe(self, name: str, value_ms: float) -> None:
        with self._lock:
            values = self.timings[name]
            values.append(float(value_ms))
            if len(values) > self.max_samples:
                del values[: len(values) - self.max_samples]

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self.gauges[name] = float(value)

    def start_span(self, name: str, **fields: Any) -> Span:
        return Span(str(uuid.uuid4()), name, time.monotonic(), dict(fields))

    def finish_span(self, span: Span, status: str = "ok", **fields: Any) -> float:
        duration_ms = (time.monotonic() - span.started_at) * 1000.0
        with self._lock:
            self.observe(span.name, duration_ms)
            self.recent_spans.append(
                {
                    "span_id": span.span_id,
                    "name": span.name,
                    "duration_ms": round(duration_ms, 3),
                    "status": status,
                    "at": time.time(),
                    "fields": {**span.fields, **fields},
                }
            )
        return duration_ms

    def record_event(self, name: str, **fields: Any) -> None:
        self.increment(f"event.{name}")
        with self._lock:
            self.recent_spans.append(
                {
                    "span_id": str(uuid.uuid4()),
                    "name": name,
                    "duration_ms": None,
                    "status": "event",
                    "at": time.time(),
                    "fields": dict(fields),
                }
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            timing_summary: dict[str, dict[str, float | int]] = {}
            for name, values in self.timings.items():
                if not values:
                    continue
                ordered = sorted(values)
                index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
                timing_summary[name] = {
                    "count": len(ordered),
                    "min_ms": round(ordered[0], 3),
                    "p50_ms": round(statistics.median(ordered), 3),
                    "p95_ms": round(ordered[index], 3),
                    "max_ms": round(ordered[-1], 3),
                    "avg_ms": round(statistics.fmean(ordered), 3),
                }
            return {
                "counters": dict(self.counters),
                "timings": timing_summary,
                "gauges": dict(self.gauges),
                "recent_spans": list(self.recent_spans),
                "captured_at": time.time(),
            }
