class AvatarRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d");
    this.phase = 0;
    this.mouth = 0;
    this.targetMouth = 0;
    this.blink = 0;
    this.nextBlink = 1800;
    this.lastFrame = performance.now();
    this.speaking = false;
    this.interrupted = false;
    requestAnimationFrame((time) => this.render(time));
  }

  setSpeaking(value) {
    this.speaking = value;
    this.targetMouth = value ? 0.75 : 0.08;
  }

  setMouth(value) {
    this.targetMouth = Math.max(0.04, Math.min(1, value));
  }

  interrupt() {
    this.interrupted = true;
    this.speaking = false;
    this.targetMouth = 0.05;
  }

  reset() {
    this.interrupted = false;
    this.speaking = false;
    this.targetMouth = 0.05;
  }

  render(time) {
    const delta = Math.min(50, time - this.lastFrame);
    this.lastFrame = time;
    this.phase += delta * (this.speaking ? 0.012 : 0.004);
    this.mouth += (this.targetMouth - this.mouth) * Math.min(1, delta / 100);
    if (time > this.nextBlink) {
      this.blink = 1;
      this.nextBlink = time + 1800 + Math.random() * 2600;
    }
    this.blink *= 0.86;
    const ctx = this.context;
    const width = this.canvas.width;
    const height = this.canvas.height;
    const centerX = width / 2;
    const bob = Math.sin(this.phase) * (this.speaking ? 5 : 2);
    const headY = height * 0.43 + bob;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(255,255,255,.035)";
    for (let i = 0; i < 8; i += 1) {
      ctx.beginPath();
      ctx.arc(width * (0.15 + i * 0.1), height * 0.18, 40 + i * 8, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = "#1b264e";
    ctx.beginPath();
    ctx.ellipse(centerX, headY, width * 0.23, height * 0.27, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#f0b38a";
    ctx.beginPath();
    ctx.ellipse(centerX, headY + 12, width * 0.17, height * 0.21, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#20264b";
    ctx.beginPath();
    ctx.ellipse(centerX, headY - height * 0.12, width * 0.19, height * 0.11, 0, Math.PI, Math.PI * 2);
    ctx.fill();
    const eyeY = headY - 5;
    const eyeHeight = 5 + this.blink * 4;
    ctx.fillStyle = "#20213b";
    ctx.beginPath();
    ctx.ellipse(centerX - width * 0.07, eyeY, 9, eyeHeight, 0, 0, Math.PI * 2);
    ctx.ellipse(centerX + width * 0.07, eyeY, 9, eyeHeight, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#573d62";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(centerX - width * 0.1, headY - 25);
    ctx.lineTo(centerX - width * 0.035, headY - 30);
    ctx.moveTo(centerX + width * 0.035, headY - 30);
    ctx.lineTo(centerX + width * 0.1, headY - 25);
    ctx.stroke();
    const mouthY = headY + 48;
    const mouthWidth = 30 + this.mouth * 24;
    const mouthHeight = 3 + this.mouth * 22;
    ctx.fillStyle = "#713c59";
    ctx.beginPath();
    ctx.ellipse(centerX, mouthY, mouthWidth, mouthHeight, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff0e2";
    ctx.globalAlpha = 0.75;
    ctx.fillRect(centerX - mouthWidth * 0.5, mouthY - mouthHeight * 0.1, mouthWidth, 3);
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#4c68ba";
    ctx.beginPath();
    ctx.ellipse(centerX, height * 0.82, width * 0.25, height * 0.18, 0, 0, Math.PI * 2);
    ctx.fill();
    if (this.interrupted) {
      ctx.fillStyle = "rgba(255,255,255,.7)";
      ctx.font = "18px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("interrupted", centerX, height * 0.94);
    }
    requestAnimationFrame((next) => this.render(next));
  }
}
