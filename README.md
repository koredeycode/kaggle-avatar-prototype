# Kaggle Avatar Prototype

A temporary, single-user conversational avatar prototype for local model experiments in a Kaggle notebook.

## What runs

- FastAPI static client and WebSocket endpoint.
- Procedural 2D browser avatar.
- Mock mode that works without model downloads and returns captions plus a valid PCM tone.
- Optional local Ollama text generation.
- Optional Kokoro TTS adapter with a tone fallback.
- Interfaces and configuration boundaries for sherpa-ONNX, Silero VAD, and Smart Turn.
- Local transcript, metrics, and run-manifest hooks.
- Dependency-free counters, p50/p95 timing summaries, recent spans, and browser latency diagnostics.
- No third-party AI API key is required for mock mode.

The local quick start defaults to `mock` mode. The Kaggle notebook also defaults to `MODEL_PROFILE=mock`, so it does not download or start optional model runtimes. Set `MODEL_PROFILE=local` only when you want the optional Ollama, sherpa, and Kokoro bootstrap; failures fall back to the mock profile. Smart Turn and Silero are not auto-enabled until their runtime contracts are qualified.

## Local quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
export RUNTIME_TOKEN="choose-a-long-local-token"
export MODEL_MODE=mock
uvicorn avatar_prototype.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, enter the token, and connect. Text mode works immediately. Microphone mode requires a secure browser context; `localhost` is accepted by modern browsers.

The mock path returns a tone rather than speech. It is for validating the browser, WebSocket, turn, cancellation, and renderer mechanics.

## Optional Ollama mode

Start Ollama on loopback and set:

```bash
export MODEL_MODE=local
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:8b
export OLLAMA_CONTEXT=4096
export OLLAMA_PREDICT=160
export TTS_MODE=mock
```

The application never exposes Ollama publicly. If Ollama is unavailable, the response remains visibly in a recoverable mock/error state rather than switching models silently.

## Optional Kokoro mode

Install a compatible Kokoro runtime in an isolated environment, make its voice/model assets available, and set:

```bash
export TTS_MODE=kokoro
export KOKORO_VOICE=af_heart
```

Kokoro is phrase-oriented and may not provide provider-grade timestamps. The prototype uses clause-duration and simple viseme cues until a timestamped adapter is configured.

## API

- `GET /healthz` returns minimal readiness.
- `GET /api/profile` returns prototype capabilities.
- `POST /api/session` validates `Authorization: Bearer <token>`.
- `WS /ws` accepts a first JSON authentication message.
- `GET /metrics` is available only to loopback clients and is disabled in public mode.

The WebSocket protocol and binary audio framing are documented in the plan file:
`/home/yusufakoredey/projects/kaggle-hosted-avatar-prototype-plan.md`.

## Observability

The session records audio/VAD/ASR, LLM, TTS, first-audio, total-response, cancellation, and WebSocket event timings. The browser displays the latest p50 values, and the authenticated WebSocket can request a `metrics.snapshot`. Loopback operators can inspect `GET /metrics` when public mode is disabled.

See `docs/observability.md`. Metrics contain no raw audio, full prompts, tokens, or secrets.

## Tests and checks

```bash
pytest -q
python -m compileall src
ruff check .
ruff format --check .
mypy src
```

The static client is plain HTML, CSS, and ES modules. It has no Node build requirement. If a JavaScript linter is added, keep it outside the Kaggle runtime.

## Kaggle use

The notebook launcher is in `kaggle/00_kaggle_prototype.ipynb`. It clones the GitHub repository into `/kaggle/working/kaggle-avatar-prototype` using `GITHUB_REPO` and `GITHUB_REF`; the clone URL must not contain an embedded token. Public repositories need no GitHub credential. For a private repository, set `GITHUB_PRIVATE=true` and attach a Kaggle Secret named `GITHUB_TOKEN`; the temporary askpass flow does not persist the token. The browser path requires Cloudflare Quick Tunnel:

- It exposes only the FastAPI loopback port.
- It uses a locally generated runtime token.
- It is public and temporary, not production hosting.
- It has no SLA.
- It must be stopped before the notebook session ends.
- The cleanup cell is manual by default; running all cells does not immediately tear down the demo.

Set `CLOUDFLARED_URL` and `CLOUDFLARED_SHA256` when a pinned Cloudflare binary is required. Do not attach cloud credentials to the keyless notebook. Do not expose Ollama, Jupyter, or model dashboards.

## Project layout

```text
src/avatar_prototype/  FastAPI, protocol, audio, session, model adapters
static/                 Browser client and procedural 2D avatar
scripts/                Preflight and smoke-test utilities
kaggle/                 Notebook launcher
tests/                  Protocol and session tests
```

## Current limitations

- Default mock mode is not speech quality.
- Voice ASR, Silero, Smart Turn, and full Kokoro integration require pinned model/runtime assets and a qualification notebook.
- The prototype is single-session and in-memory.
- Browser refresh closes the WebSocket; it does not stop notebook processes. Use the cleanup cell for process teardown.
- Kaggle GPU availability, quota, model downloads, and tunnel uptime are not guaranteed.
- A secure production deployment still needs proper credentials, TLS, durable storage, observability, and WebRTC/TURN or another production transport.
