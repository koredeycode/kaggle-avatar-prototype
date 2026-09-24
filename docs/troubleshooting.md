# Troubleshooting

- The page loads but the token is rejected: restart the app and use the token printed by the same process.
- The browser cannot access the microphone: use HTTPS or localhost, grant permission, and avoid a suspended page.
- The app exits at import: install the project dependencies in the Kaggle environment and run `python -m compileall src`.
- Ollama is unavailable: keep `MODEL_MODE=mock`; the browser/protocol path still works.
- Kokoro is unavailable: leave `TTS_MODE=mock`; the response becomes a valid tone rather than speech.
- A tunnel URL is stale: stop the old tunnel, remove the URL file, and start a new one.
- The notebook is idle: export artifacts and do not rely on a heartbeat to keep Kaggle alive.
- A port is occupied: inspect the process registry and stop only the owned process.
