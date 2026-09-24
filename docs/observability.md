# Observability and profiling

The prototype uses a dependency-free in-memory telemetry registry so it works before external monitoring services are configured.

## Measured stages

- Audio frame count and byte size.
- VAD processing latency.
- Smart Turn decision latency when enabled.
- Voice-turn ASR latency.
- LLM stage latency from `profile.stage` events.
- TTS stage latency and fallback events.
- Speech-end/turn-commit to first assistant audio.
- Total response duration.
- Cancellation latency and response counts.
- Client WebSocket ping/pong and diagnostic events.

## Access

- The browser receives `metrics.snapshot` after ready, response completion, and explicit `metrics.request` messages.
- `GET /metrics` exposes the active session snapshot only to loopback clients when public mode is disabled.
- Public mode hides the HTTP metrics route; browser diagnostics use the authenticated WebSocket.
- The UI’s metrics line shows p50 values for commit, first audio, and total response latency.

## Data safety

The registry stores counters, timings, gauges, and short recent-span metadata. It does not store raw audio, full prompts, GitHub credentials, runtime tokens, or unrestricted transcript text. Add an external exporter only after defining retention and redaction.

## Profiling interpretation

Use distributions, not one run. Cold model loading, tunnel latency, TTS fallback, and browser scheduling are separate cohorts. A `profile.stage` event with `state=error` is not equivalent to a successful latency sample.
