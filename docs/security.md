# Security notes

- Bind FastAPI to `127.0.0.1`.
- Never expose Ollama, Jupyter, or model worker ports.
- Keep docs and OpenAPI disabled.
- Keep metrics loopback-only and return 404 in public mode.
- Use a generated runtime token for any temporary browser tunnel.
- Do not place the token in a URL or logs.
- Validate WebSocket origin/host in public mode.
- Bound JSON, binary, audio-buffer, and session lifetimes.
- The tunnel is an intermediary and is not an E2EE boundary.
- Browser refresh closes the socket, not notebook processes; use the cleanup cell.
- Do not attach provider or cloud credentials to the keyless notebook.
