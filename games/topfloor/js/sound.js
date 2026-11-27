// Synthesised sound, built on first use after a user gesture. Off until the player turns it on.
let ctx = null, master = null, enabled = false;

export function setEnabled(on) {
  enabled = on;
  if (on && !ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { enabled = false; return false; }
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.55;
    master.connect(ctx.destination);
  }
  if (on && ctx.state === "suspended") ctx.resume();
  return enabled;
}
export const isOn = () => enabled;

function noise(dur) {
  const n = Math.max(1, Math.floor(ctx.sampleRate * dur));
  const buf = ctx.createBuffer(1, n, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = buf;
  return src;
}
function env(g, t, peak, attack, decay) {
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
}

// short key click
export function click() {
  if (!enabled) return;
  const t = ctx.currentTime, src = noise(0.03), f = ctx.createBiquadFilter(), g = ctx.createGain();
  f.type = "bandpass"; f.frequency.value = 2400 + Math.random() * 600; f.Q.value = 1.1;
  env(g, t, 0.28, 0.002, 0.03);
  src.connect(f).connect(g).connect(master);
  src.start(t); src.stop(t + 0.04);
}

// lift arrival chime: a struck bell, more notes for higher tiers
export function ding(tier = 0) {
  if (!enabled) return;
  const base = 988; // B5
  const notes = [[0, base]];
  if (tier >= 2) notes.push([0.16, base * 1.26]);
  if (tier >= 3) notes.push([0.32, base * 1.5]);
  if (tier >= 4) notes.push([0.48, base * 2]);
  const t0 = ctx.currentTime;
  for (const [dt, f] of notes) {
    for (const [mul, amp, dec] of [[1, 0.2, 1.5], [2.76, 0.07, 0.8], [5.4, 0.03, 0.4]]) {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = f * mul;
      env(g, t0 + dt, amp, 0.004, dec);
      o.connect(g).connect(master);
      o.start(t0 + dt); o.stop(t0 + dt + dec + 0.05);
    }
  }
}

// rubber stamp slam
export function stamp() {
  if (!enabled) return;
  const t = ctx.currentTime;
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = "sine"; o.frequency.setValueAtTime(130, t); o.frequency.exponentialRampToValueAtTime(48, t + 0.14);
  env(g, t, 0.7, 0.004, 0.18);
  o.connect(g).connect(master); o.start(t); o.stop(t + 0.25);
  const src = noise(0.08), f = ctx.createBiquadFilter(), ng = ctx.createGain();
  f.type = "lowpass"; f.frequency.value = 1400;
  env(ng, t, 0.3, 0.002, 0.07);
  src.connect(f).connect(ng).connect(master); src.start(t); src.stop(t + 0.1);
}

// doors meeting
export function thunk() {
  if (!enabled) return;
  const t = ctx.currentTime;
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = "triangle"; o.frequency.setValueAtTime(95, t); o.frequency.exponentialRampToValueAtTime(40, t + 0.2);
  env(g, t, 0.6, 0.005, 0.26);
  o.connect(g).connect(master); o.start(t); o.stop(t + 0.35);
}

export function buzz() {
  if (!enabled) return;
  const t = ctx.currentTime, o = ctx.createOscillator(), f = ctx.createBiquadFilter(), g = ctx.createGain();
  o.type = "sawtooth"; o.frequency.value = 110;
  f.type = "lowpass"; f.frequency.value = 420;
  env(g, t, 0.22, 0.005, 0.16);
  o.connect(f).connect(g).connect(master); o.start(t); o.stop(t + 0.22);
}

// soft tick while the lift passes floors
export function pass(i = 0) {
  if (!enabled) return;
  const t = ctx.currentTime, o = ctx.createOscillator(), g = ctx.createGain();
  o.type = "sine"; o.frequency.value = 520 + i * 18;
  env(g, t, 0.05, 0.003, 0.05);
  o.connect(g).connect(master); o.start(t); o.stop(t + 0.08);
}
