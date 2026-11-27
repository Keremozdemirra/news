// Synthesised sound, built on first use after a user gesture. Off until the player turns it on.
let ctx = null, master = null, enabled = false;

export function setEnabled(on) {
  enabled = on;
  if (on && !ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { enabled = false; return false; }
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.5;
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
function burst(freq, q, peak, dur, when = 0) {
  const t = ctx.currentTime + when, src = noise(dur + 0.01), f = ctx.createBiquadFilter(), g = ctx.createGain();
  f.type = "bandpass"; f.frequency.value = freq; f.Q.value = q;
  env(g, t, peak, 0.0015, dur);
  src.connect(f).connect(g).connect(master); src.start(t); src.stop(t + dur + 0.02);
}

// one flap of the drum: a dry paper-on-brass tick
export function flap() { if (enabled) burst(1800 + Math.random() * 900, 1.4, 1.1, 0.022); }
// a flap landing on its stop: a little lower and heavier
export function clack() { if (enabled) { burst(900 + Math.random() * 200, 2, 2.4, 0.04); burst(3200, 1, 0.7, 0.012, 0.004); } }
// typing a letter
export function key() { if (enabled) burst(2400 + Math.random() * 500, 1.1, 1.4, 0.03); }
export function buzz() {
  if (!enabled) return;
  const t = ctx.currentTime, o = ctx.createOscillator(), f = ctx.createBiquadFilter(), g = ctx.createGain();
  o.type = "sawtooth"; o.frequency.value = 104;
  f.type = "lowpass"; f.frequency.value = 380;
  env(g, t, 0.7, 0.005, 0.16);
  o.connect(f).connect(g).connect(master); o.start(t); o.stop(t + 0.22);
}
// struck brass bell, rising run for a win
export function bell(notes = 3) {
  if (!enabled) return;
  const base = 784, t0 = ctx.currentTime, ratios = [1, 1.26, 1.5, 2];
  for (let n = 0; n < Math.min(4, notes); n++) {
    for (const [mul, amp, dec] of [[1, 0.2, 1.4], [2.76, 0.07, 0.8], [5.4, 0.03, 0.4]]) {
      const o = ctx.createOscillator(), g = ctx.createGain(), at = t0 + n * 0.17;
      o.type = "sine"; o.frequency.value = base * ratios[n] * mul;
      env(g, at, amp, 0.004, dec);
      o.connect(g).connect(master); o.start(at); o.stop(at + dec + 0.05);
    }
  }
}
// board powering down on a miss
export function down() {
  if (!enabled) return;
  const t = ctx.currentTime, o = ctx.createOscillator(), g = ctx.createGain();
  o.type = "triangle"; o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(52, t + 0.4);
  env(g, t, 0.45, 0.01, 0.45);
  o.connect(g).connect(master); o.start(t); o.stop(t + 0.55);
}

// test hook: run any sound on an OfflineAudioContext to measure level and length (see art notes / CRITIQUE)
export function _testUse(c) { ctx = c; master = c.createGain(); master.gain.value = 0.5; master.connect(c.destination); enabled = true; }
export const _sounds = { flap, clack, key, buzz, bell, down };
