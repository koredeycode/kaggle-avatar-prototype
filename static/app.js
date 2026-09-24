import { AvatarRenderer } from "/static/avatar.js";
import { AvatarAudio } from "/static/audio.js";

const state = {
  socket: null,
  sessionId: null,
  epoch: 1,
  connected: false,
  responseId: null,
  turnId: null,
  ptt: false,
  pttReady: false,
  captureMode: null,
  connectionGeneration: 0,
  pingTimer: null,
  startedAt: performance.now(),
};

const avatar = new AvatarRenderer(document.querySelector("#avatar"));
const audio = new AvatarAudio((level) => {
  if (state.connected && level > 0.035) send({ type: "input.local_hint", level });
});

const tokenInput = document.querySelector("#token");
const connectButton = document.querySelector("#connect");
const disconnectButton = document.querySelector("#disconnect");
const interruptButton = document.querySelector("#interrupt");
const pttButton = document.querySelector("#ptt");
const handsFreeButton = document.querySelector("#handsFree");
const textButton = document.querySelector("#textMode");
const textInput = document.querySelector("#text");
const textForm = document.querySelector("#textForm");
const textFormInput = document.querySelector("#textInput");
const textFormSubmit = textForm.querySelector('button[type="submit"]');
const captions = document.querySelector("#captions");
const status = document.querySelector("#status");
const metrics = document.querySelector("#metrics");
const hint = document.querySelector("#hint");

function setStatus(value) {
  status.textContent = value;
}

function addCaption(role, text, system = false) {
  if (!text) return;
  const item = document.createElement("div");
  item.className = `caption ${system ? "system" : role}`;
  item.textContent = `${role === "user" ? "You" : "Avatar"}: ${text}`;
  captions.appendChild(item);
  captions.scrollTop = captions.scrollHeight;
}

function setControls(connected) {
  connectButton.disabled = connected;
  disconnectButton.disabled = !connected;
  interruptButton.disabled = !connected;
  pttButton.disabled = !connected;
  handsFreeButton.disabled = !connected;
  textButton.disabled = !connected;
  textInput.disabled = !connected;
  textFormInput.disabled = !connected;
  textFormSubmit.disabled = !connected;
}

function send(value) {
  if (state.socket?.readyState === WebSocket.OPEN) state.socket.send(JSON.stringify(value));
}

function parseAudioFrame(buffer) {
  const view = new DataView(buffer);
  if (view.byteLength < 77) return null;
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1));
  const version = view.getUint8(2);
  const messageType = view.getUint8(3);
  const flags = view.getUint32(4, false);
  if (magic !== "AV" || version !== 1 || messageType !== 1 || (flags & ~1) !== 0) return null;
  const payloadLength = view.getUint32(73, false);
  if (view.byteLength !== 77 + payloadLength) return null;
  const responseId = uuidFromBytes(new Uint8Array(buffer, 12, 16));
  const turnId = uuidFromBytes(new Uint8Array(buffer, 28, 16));
  const segmentId = uuidFromBytes(new Uint8Array(buffer, 44, 16));
  return {
    responseId,
    turnId,
    segmentId,
    sessionEpoch: view.getUint32(8),
    mediaSequence: Number(view.getBigUint64(60)),
    sampleRate: view.getUint32(68),
    channels: view.getUint8(72),
    payload: new Uint8Array(buffer, 77, view.byteLength - 77),
  };
}

function uuidFromBytes(bytes) {
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function decodePcm(bytes) {
  const samples = new Float32Array(bytes.length / 2);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let i = 0; i < samples.length; i += 1) samples[i] = view.getInt16(i * 2, true) / 32768;
  return samples;
}

async function connect() {
  const token = tokenInput.value.trim();
  if (!token) {
    hint.textContent = "Enter the runtime token printed by the notebook.";
    return;
  }
  connectButton.disabled = true;
  try {
    await audio.ensureOutput();
  } catch (error) {
    hint.textContent = `Audio output unavailable: ${error.message}`;
  }
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws`);
  const generation = ++state.connectionGeneration;
  state.socket = socket;
  socket.binaryType = "arraybuffer";
  socket.onopen = () => {
    if (state.socket !== socket || generation !== state.connectionGeneration) return;
    socket.send(JSON.stringify({ type: "auth", protocol: 1, token, client: "browser" }));
  };
  socket.onmessage = (message) => {
    if (state.socket !== socket || generation !== state.connectionGeneration) return;
    if (message.data instanceof ArrayBuffer) {
      const frame = parseAudioFrame(message.data);
      if (frame && frame.sessionEpoch === state.epoch && frame.responseId === state.responseId) {
        audio.schedule(decodePcm(frame.payload), frame.sampleRate, frame.responseId, frame.mediaSequence);
      }
      return;
    }
    handleEvent(JSON.parse(message.data));
  };
  socket.onerror = () => {
    if (state.socket === socket && generation === state.connectionGeneration) setStatus("connection error");
  };
  socket.onclose = () => {
    if (state.socket !== socket || generation !== state.connectionGeneration) return;
    state.connected = false;
    state.connectionGeneration += 1;
    state.captureMode = null;
    state.ptt = false;
    state.pttReady = false;
    state.responseId = null;
    if (state.pingTimer) clearInterval(state.pingTimer);
    state.pingTimer = null;
    handsFreeButton.textContent = "Start hands-free";
    audio.stop();
    avatar.reset();
    setStatus("offline");
    setControls(false);
  };
}

function renderMetrics(snapshot) {
  const timings = snapshot?.timings || {};
  const firstAudio = timings.speech_end_to_first_audio?.p50_ms;
  const total = timings["response.total"]?.p50_ms;
  const turn = timings['turn.commit']?.p50_ms;
  const counters = snapshot?.counters || {};
  const turns = (counters["response.completed"] || 0) + (counters["response.cancelled"] || 0);
  const parts = [
    `turns ${turns}`,
    turn == null ? null : `commit ${Math.round(turn)}ms`,
    firstAudio == null ? null : `first audio ${Math.round(firstAudio)}ms`,
    total == null ? null : `response ${Math.round(total)}ms`,
  ].filter(Boolean);
  metrics.textContent = parts.join(" · ");
}

function handleEvent(value) {
  const type = value.type;
  const payload = value.payload || {};
  if (type !== "ready" && value.session_epoch !== state.epoch) return;
  if (type === "metrics.snapshot") {
    renderMetrics(payload);
    return;
  }
  if (type === "profile.stage") {
    const duration = payload.duration_ms == null ? "" : ` ${Math.round(payload.duration_ms)}ms`;
    metrics.textContent = `${payload.stage} ${payload.state}${duration}`;
    return;
  }
  if (type === "ready") {
    state.connected = true;
    state.sessionId = value.session_id;
    state.epoch = value.session_epoch;
    setStatus("ready");
    setControls(true);
    if (state.pingTimer) clearInterval(state.pingTimer);
    state.pingTimer = setInterval(() => send({ type: "ping", client_time: Date.now() }), 15000);
    addCaption("system", "Connected. Use headphones for the first microphone test.", true);
    return;
  }
  if (type === "speech.started") {
    setStatus("listening");
    return;
  }
  if (type === "stt.final") {
    addCaption("user", payload.text);
    setStatus("thinking");
    return;
  }
  if (type === "turn.committed") {
    state.turnId = value.turn_id;
    state.responseId = null;
    setStatus("thinking");
    return;
  }
  if (type === "assistant.state") {
    const assistantState = payload.state;
    if (value.response_id) state.responseId = value.response_id;
    setStatus(assistantState);
    avatar.setSpeaking(assistantState === "speaking");
    if (assistantState === "speaking" && state.responseId && audio.currentResponse !== state.responseId) {
      audio.beginResponse(state.responseId);
    }
    return;
  }
  if (type === "assistant.text.delta") {
    if (!state.responseId) state.responseId = value.response_id;
    const existing = [...captions].reverse().find((item) => item.dataset.response === value.response_id);
    if (existing) existing.textContent = `Avatar: ${payload.text}`;
    else {
      const item = document.createElement("div");
      item.className = "caption assistant";
      item.dataset.response = value.response_id;
      item.textContent = `Avatar: ${payload.text}`;
      captions.appendChild(item);
    }
    return;
  }
  if (type === "assistant.audio") {
    state.responseId = value.response_id;
    if (audio.currentResponse !== value.response_id) audio.beginResponse(value.response_id);
    return;
  }
  if (type === "avatar.cues") {
    avatar.setMouth(payload.weight || 0.4);
    return;
  }
  if (type === "response.completed") {
    avatar.setSpeaking(false);
    setStatus("listening");
    return;
  }
  if (type === "response.cancelled") {
    audio.clear();
    state.responseId = null;
    avatar.interrupt();
    setStatus("listening");
    addCaption("system", "Response interrupted.", true);
    return;
  }
  if (type === "error.recoverable") {
    if (payload.code === "llm_unavailable") {
      hint.textContent = "Local LLM is unavailable; mock text response is active.";
    } else if (payload.code === "vad_unavailable") {
      hint.textContent = "Silero VAD is unavailable; energy-based fallback is active.";
    } else if (payload.code === "asr_unavailable") {
      hint.textContent = "Local ASR is unavailable; using the fallback transcript.";
    } else if (payload.code === "turn_detector_unavailable") {
      hint.textContent = "Turn detection is unavailable; using the manual fallback.";
    } else if (payload.code === "tts_fallback") {
      hint.textContent = "Local TTS is unavailable; using the mock audio fallback.";
    } else {
      hint.textContent = `Prototype warning: ${payload.code}`;
    }
    return;
  }
  if (type === "pong") {
    metrics.textContent = `Connected for ${Math.round((performance.now() - state.startedAt) / 1000)}s`;
  }
}

async function startMicrophone(mode = "hands_free", requestId = "") {
  const connectionGeneration = state.connectionGeneration;
  try {
    audio.onCapture = (pcm) => {
      const active = state.captureMode === "hands_free" || (state.captureMode === "manual" && state.ptt);
      if (active && state.socket?.readyState === WebSocket.OPEN && state.connected) state.socket.send(pcm);
    };
    audio.onPlayed = (responseId, mediaSequence) => send({ type: "playout.ack", response_id: responseId, media_sequence: mediaSequence });
    await audio.ensureOutput();
    state.captureMode = mode;
    const message = {
      type: "input.start",
      mode,
      sample_rate: audio.context?.sampleRate || 48000,
    };
    if (requestId) message.request_id = requestId;
    send(message);
    if (mode === "manual") state.pttReady = true;
    await audio.start();
    if (!state.connected || connectionGeneration !== state.connectionGeneration) {
      send({ type: "input.cancel", request_id: requestId });
      state.captureMode = null;
      state.pttReady = false;
      audio.stopCapture();
      return;
    }
    if (mode === "manual" && !state.ptt) {
      send({ type: "input.cancel", request_id: requestId });
      state.captureMode = null;
      state.pttReady = false;
      audio.stopCapture();
      return;
    }
    setStatus("listening");
    hint.textContent = mode === "manual" ? "Push-to-talk is active." : "Microphone is live. Speak and pause.";
  } catch (error) {
    send({ type: "input.cancel", request_id: requestId });
    state.captureMode = null;
    state.pttReady = false;
    audio.stopCapture();
    hint.textContent = `Microphone unavailable: ${error.message}`;
  }
}

function finishPtt() {
  if (!state.ptt && !state.pttReady) return;
  state.ptt = false;
  if (state.pttReady) {
    send({ type: "input.end", request_id: state.pttRequestId || crypto.randomUUID() });
    state.pttReady = false;
    state.captureMode = null;
    audio.stopCapture();
  }
}

connectButton.addEventListener("click", connect);
disconnectButton.addEventListener("click", () => state.socket?.close());
interruptButton.addEventListener("click", () => {
  send({ type: "response.cancel" });
  audio.clear();
  avatar.interrupt();
});
pttButton.addEventListener("pointerdown", (event) => {
  if (!state.connected || state.captureMode === "hands_free") return;
  state.ptt = true;
  const requestId = crypto.randomUUID();
  state.pttRequestId = requestId;
  try { event.currentTarget.setPointerCapture(event.pointerId); } catch (error) { void error; }
  void startMicrophone("manual", requestId);
});
pttButton.addEventListener("pointerup", finishPtt);
pttButton.addEventListener("pointercancel", finishPtt);
pttButton.addEventListener("lostpointercapture", finishPtt);
handsFreeButton.addEventListener("click", async () => {
  if (!state.connected) return;
  if (state.captureMode === "hands_free") {
    send({ type: "input.end" });
    state.captureMode = null;
    audio.stopCapture();
    handsFreeButton.textContent = "Start hands-free";
    setStatus("ready");
    return;
  }
  await startMicrophone("hands_free");
  if (state.captureMode === "hands_free") handsFreeButton.textContent = "Stop hands-free";
});
function submitText(value) {
  const text = value.trim();
  if (!text) return;
  send({ type: "text.submit", text, request_id: crypto.randomUUID() });
}
textButton.addEventListener("click", () => textInput.focus());
textInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  submitText(textInput.value);
  textInput.value = "";
});
textForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitText(textFormInput.value);
  textFormInput.value = "";
});
document.querySelector("#clear").addEventListener("click", () => { captions.replaceChildren(); });

setControls(false);
