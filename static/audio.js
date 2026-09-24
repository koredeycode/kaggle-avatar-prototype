class AvatarAudio {
  constructor(onLevel) {
    this.onLevel = onLevel;
    this.context = null;
    this.stream = null;
    this.source = null;
    this.processor = null;
    this.worklet = null;
    this.scheduled = new Set();
    this.nextStart = 0;
    this.currentResponse = null;
    this.onCapture = () => {};
    this.onPlayed = () => {};
  }

  async ensureOutput() {
    if (!this.context || this.context.state === "closed") this.context = new AudioContext();
    if (this.context.state === "suspended") await this.context.resume();
  }

  async start() {
    if (this.stream) return;
    await this.ensureOutput();
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    try {
      await this.context.audioWorklet.addModule("/static/audio-worklet.js");
      this.worklet = new AudioWorkletNode(this.context, "pcm-capture");
      this.worklet.port.onmessage = (event) => this.handleCapture(event.data);
    } catch (error) {
      this.processor = this.context.createScriptProcessor(4096, 1, 1);
      this.processor.onaudioprocess = (event) => this.handleCapture(event.inputBuffer.getChannelData(0));
    }
    this.source = this.context.createMediaStreamSource(this.stream);
    this.silent = this.context.createGain();
    this.silent.gain.value = 0;
    if (this.worklet) {
      this.source.connect(this.worklet);
      this.worklet.connect(this.silent);
      this.silent.connect(this.context.destination);
    }
    if (this.processor) {
      this.source.connect(this.processor);
      this.processor.connect(this.silent);
      this.silent.connect(this.context.destination);
    }
  }

  handleCapture(samples) {
    let sum = 0;
    for (const sample of samples) sum += sample * sample;
    this.onLevel(Math.sqrt(sum / Math.max(1, samples.length)));
    const pcm = new ArrayBuffer(samples.length * 2);
    const view = new DataView(pcm);
    for (let i = 0; i < samples.length; i += 1) {
      const value = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(i * 2, value < 0 ? value * 32768 : value * 32767, true);
    }
    this.onCapture(pcm);
  }

  beginResponse(responseId) {
    this.nextStart = Math.max(this.nextStart, this.context ? this.context.currentTime + 0.03 : 0.03);
    this.currentResponse = responseId;
  }

  schedule(samples, sampleRate, responseId, mediaSequence) {
    if (!this.context || this.currentResponse !== responseId) return;
    if (this.context.state === "suspended") void this.context.resume();
    const buffer = this.context.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    const startAt = Math.max(this.context.currentTime + 0.01, this.nextStart);
    this.nextStart = startAt + buffer.duration;
    source.start(startAt);
    this.scheduled.add(source);
    source.onended = () => {
      this.scheduled.delete(source);
      this.onPlayed(responseId, mediaSequence);
    };
  }

  clear() {
    for (const source of this.scheduled) {
      try { source.stop(); } catch (error) { void error; }
    }
    this.scheduled.clear();
    this.nextStart = 0;
    this.currentResponse = null;
  }

  stopCapture() {
    this.source?.disconnect();
    this.processor?.disconnect();
    this.worklet?.disconnect();
    this.silent?.disconnect();
    for (const track of this.stream?.getTracks() || []) track.stop();
    this.stream = null;
    this.source = null;
    this.processor = null;
    this.worklet = null;
    this.silent = null;
  }

  stop() {
    this.clear();
    this.stopCapture();
  }
}

export { AvatarAudio };
