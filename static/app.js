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
const textButton = document.querySelector("#textMode");
const textInput = document.querySelector("#text");
const textForm = document.querySelector("#textForm");
const textFormInput = document.querySelector("#textInput");
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
  textButton.disabled = !connected;
  textInput.disabled = !connected;
  textFormInput.disabled = !connected;
}

function send(value) {
  if (state.socket?.readyState === WebSocket.OPEN) state.socket.send(JSON.stringify(value));
}

function parseAudioFrame(buffer) {
  const view = new DataView(buffer);
  if (view.byteLength < 77) return null;
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1));
  if (magic !== "AV" || view.getUint8(2) !== 1 || view.getUint8(3) !== 1) return null;
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
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws`);
  state.socket = socket;
  socket.binaryType = "arraybuffer";
  socket.onopen = () => socket.send(JSON.stringify({ type: "auth", protocol: 1, token, client: "browser" }));
  socket.onmessage = (message) => {
    if (message.data instanceof ArrayBuffer) {
      const frame = parseAudioFrame(message.data);
      if (frame && frame.responseId === state.responseId) audio.schedule(decodePcm(frame.payload), frame.sampleRate, frame.responseId, frame.mediaSequence);
      return;
    }
    handleEvent(JSON.parse(message.data));
  };
  socket.onerror = () => setStatus("connection error");
  socket.onclose = () => {
    state.connected = false;
    state.responseId = null;
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
    if (assistantState === "speaking") {
      audio.currentResponse = state.responseId;
      audio.nextStart = audio.context ? audio.context.currentTime + 0.03 : 0;
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
    audio.currentResponse = value.response_id;
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
    avatar.interrupt();
    setStatus("listening");
    addCaption("system", "Response interrupted.", true);
    return;
  }
  if (type === "error.recoverable") {
    hint.textContent = payload.code === "llm_unavailable" ? "Local LLM is unavailable; mock text response is active." : `Prototype warning: ${payload.code}`;
    return;
  }
  if (type === "pong") {
    metrics.textContent = `Connected for ${Math.round((performance.now() - state.startedAt) / 1000)}s`;
  }
}

async function startMicrophone(mode = "hands_free") {
  try {
    audio.onCapture = (pcm) => {
      if (state.socket?.readyState === WebSocket.OPEN && state.connected) state.socket.send(pcm);
    };
    audio.onPlayed = (responseId, mediaSequence) => send({ type: "playout.ack", response_id: responseId, media_sequence: mediaSequence });
    await audio.start();
    send({ type: "input.start", mode });
    setStatus("listening");
    hint.textContent = mode === "manual" ? "Push-to-talk is active." : "Microphone is live. Speak and pause.";
  } catch (error) {
    hint.textContent = `Microphone unavailable: ${error.message}`;
  }
}

connectButton.addEventListener("click", connect);
disconnectButton.addEventListener("click", () => state.socket?.close());
interruptButton.addEventListener("click", () => {
  send({ type: "response.cancel" });
  audio.clear();
  avatar.interrupt();
});
pttButton.addEventListener("pointerdown", () => {
  state.ptt = true;
  const requestId = crypto.randomUUID();
  state.pttRequestId = requestId;
  send({ type: "input.start", mode: "manual", request_id: requestId });
  void startMicrophone("manual");
});
pttButton.addEventListener("pointerup", () => {
  if (!state.ptt) return;
  state.ptt = false;
  send({ type: "input.end", request_id: state.pttRequestId || crypto.randomUUID() });
});
textButton.addEventListener("click", startMicrophone);
textForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = textFormInput.value.trim();
  if (!text) return;
  send({ type: "text.submit", text, request_id: crypto.randomUUID() });
  textFormInput.value = "";
});
document.querySelector("#clear").addEventListener("click", () => { captions.replaceChildren(); });

setControls(false);
