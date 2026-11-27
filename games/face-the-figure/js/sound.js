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

function env(g, t, peak, attack, decay) {
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(peak, t + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
}
function tone(type, f0, f1, t, peak, attack, decay, dest = master) {
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = type; o.frequency.setValueAtTime(f0, t);
  if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(f1, t + attack + decay);
  env(g, t, peak, attack, decay);
  o.connect(g).connect(dest); o.start(t); o.stop(t + attack + decay + 0.05);
}

// ratchet tick while the sealed figure counts up; pitch climbs with progress (0..1)
export function tick(p = 0) {
  if (!enabled) return;
  tone("square", 700 + p * 900, 500 + p * 700, ctx.currentTime, 0.035, 0.002, 0.03);
}

// brass bell: more notes the longer the streak
export function ding(streak = 1) {
  if (!enabled) return;
  const base = 880, notes = [[0, base]];
  if (streak >= 2) notes.push([0.12, base * 1.26]);
  if (streak >= 4) notes.push([0.24, base * 1.5]);
  if (streak >= 7) notes.push([0.36, base * 2]);
  const t0 = ctx.currentTime;
  for (const [dt, f] of notes)
    for (const [mul, amp, dec] of [[1, 0.2, 1.3], [2.76, 0.07, 0.7], [5.4, 0.03, 0.35]]) tone("sine", f * mul, f * mul, t0 + dt, amp, 0.004, dec);
}

// wrong call: a low wooden thud and a short sag
export function thud() {
  if (!enabled) return;
  const t = ctx.currentTime;
  tone("triangle", 150, 52, t, 0.6, 0.005, 0.24);
  tone("sawtooth", 140, 90, t + 0.02, 0.08, 0.01, 0.2);
}

// beam settling on its stop
export function clack() {
  if (!enabled) return;
  const t = ctx.currentTime;
  tone("triangle", 320, 120, t, 0.28, 0.002, 0.07);
}

export function press() {
  if (!enabled) return;
  tone("sine", 480, 320, ctx.currentTime, 0.12, 0.003, 0.06);
}
