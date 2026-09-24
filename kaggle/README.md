# Kaggle notebook

The notebook clones the GitHub repository into `/kaggle/working/kaggle-avatar-prototype`. Set `GITHUB_REPO` to the repository URL and optionally set `GITHUB_REF` to the branch before running `00_kaggle_prototype.ipynb` top to bottom. The clone URL must not contain an embedded token.

For a public repository, no GitHub credential is needed. For a private repository, set `GITHUB_PRIVATE=true` and attach a Kaggle Secret named `GITHUB_TOKEN`; the notebook uses a temporary `GIT_ASKPASS` helper and never writes the token into the URL, repository config, notebook output, or source file.

The notebook defaults to the reliable `mock` profile and does not download optional models:

- Connects the browser to a local FastAPI/WebSocket server.
- Verifies a text response and PCM audio frame with `scripts/smoke_test.py`.
- Keeps the microphone path available through PTT and hands-free controls.
- Uses `MODEL_PROFILE=local` only when you explicitly want the optional Ollama, sherpa, and Kokoro bootstrap.
- Keeps Smart Turn and Silero disabled until their model contracts are qualified.

No AI provider key is required. Cloudflare Quick Tunnel is started for the browser path.

The Quick Tunnel is public, temporary, and not production hosting. It exposes only FastAPI, not Ollama or model workers, and must be stopped before ending the session. The final cleanup cell defines `cleanup()` but leaves `CLEANUP_ON_RUN_ALL = False`, so running all cells leaves the demo available; call `cleanup()` manually when finished. The tunnel installer accepts `CLOUDFLARED_URL` and optional `CLOUDFLARED_SHA256` for a pinned binary.

For a local model profile, add pinned model assets and set `MODEL_MODE=local`, `TTS_MODE=kokoro`, and the relevant model paths in a separate qualification notebook. Do not attach GitHub, named Cloudflare, R2, or AI provider secrets to the keyless notebook.
