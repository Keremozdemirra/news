// The floor indicator and the lift car. Both are rendered objects (art/build_art.py); this module lays the flat
// print over the dial face (ticks, numerals, tier bands: print is flat) and plays the authored motion.
const NS = "http://www.w3.org/2000/svg";
function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
const pt = (r, a) => [120 + r * Math.sin((a * Math.PI) / 180), 120 - r * Math.cos((a * Math.PI) / 180)];
export const angleFor = (floor) => -110 + 2.2 * floor;
export const BANDS = [[0, 20, "--t0"], [20, 45, "--t1"], [45, 72, "--t2"], [72, 92, "--t3"], [92, 100, "--t4"]];
export const DOOR_FRAMES = 13;

const EASE = { linear: (p) => p, out: (p) => 1 - Math.pow(1 - p, 3), in: (p) => p * p, inOut: (p) => 0.5 - 0.5 * Math.cos(Math.PI * p), lift: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2) };
// A piecewise score: keys are [ms, value, ease-to-this-key]. Returns f(t).
export function score(keys) {
  return (t) => {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      if (t <= keys[i][0]) { const [t0, v0] = keys[i - 1], [t1, v1, e] = keys[i]; return v0 + (v1 - v0) * EASE[e || "inOut"]((t - t0) / (t1 - t0)); }
    }
    return keys[keys.length - 1][1];
  };
}
export function play(f, dur, apply, done) {
  const t0 = performance.now(); let raf = 0;
  const loop = (now) => { const t = Math.min(dur, now - t0); apply(f(t), t); if (t < dur) raf = requestAnimationFrame(loop); else done?.(); };
  raf = requestAnimationFrame(loop);
  return () => cancelAnimationFrame(raf);
}

// ---- the print on the dial face
export function buildDial(svg, needleEl) {
  for (const [a, b, v] of BANDS) {
    const [x1, y1] = pt(84, angleFor(a) + 0.9), [x2, y2] = pt(84, angleFor(b) - 0.9);
    el("path", { d: `M${x1} ${y1}A84 84 0 0 1 ${x2} ${y2}`, fill: "none", style: `stroke:var(${v})`, "stroke-width": 5, "stroke-linecap": "butt" }, svg);
  }
  let minor = "", major = "";
  for (let f = 0; f <= 100; f += 2) {
    const big = f % 10 === 0;
    const [x1, y1] = pt(big ? 68 : 73, angleFor(f)), [x2, y2] = pt(78, angleFor(f));
    (big ? (major += `M${x1} ${y1}L${x2} ${y2}`) : (minor += `M${x1} ${y1}L${x2} ${y2}`));
  }
  el("path", { d: minor, stroke: "#c7a25e", "stroke-width": 1, fill: "none" }, svg);
  el("path", { d: major, stroke: "#f2e9d3", "stroke-width": 2.2, fill: "none" }, svg);
  for (let f = 0; f <= 100; f += 20) {
    const [x, y] = pt(55, angleFor(f));
    const t = el("text", { x, y, "text-anchor": "middle", "dominant-baseline": "central", style: "font:400 14.5px Limelight,serif;fill:#f2e9d3" }, svg);
    t.textContent = String(f);
  }
  const lab = el("text", { x: 120, y: 152, "text-anchor": "middle", style: "font:600 7.6px Jost,sans-serif;letter-spacing:.34em;fill:#c7a25e" }, svg);
  lab.textContent = "FLOOR";

  // The needle is its own rendered sprite. It never tweens on a CSS curve: every move is a score.
  let angle = angleFor(0), stop = null;
  const set = (deg) => { angle = deg; needleEl.style.transform = `rotate(${deg.toFixed(2)}deg)`; };
  set(angle);
  return {
    set(floor) { stop?.(); set(angleFor(floor)); },
    // climb: a dip back against the stop (anticipation), the run, an overshoot past the mark, one swing back, rest
    to(floor, ms, reduced) {
      stop?.();
      const a0 = angle, a1 = angleFor(floor), d = a1 - a0;
      if (reduced || !d) { set(a1); return; }
      const sg = Math.sign(d), over = Math.min(9, 2.5 + Math.abs(d) * 0.07);
      const f = score([[0, a0], [140, a0 - sg * 2.2, "out"], [ms, a1 + sg * over, "lift"], [ms + 170, a1 - sg * over * 0.38, "inOut"], [ms + 320, a1 + sg * over * 0.14, "inOut"], [ms + 450, a1, "inOut"]]);
      stop = play(f, ms + 450, set);
    },
  };
}

// ---- the car: one strip of door positions, stepped. No leaf is ever tweened.
export function buildCar(art, alarm) {
  let frame = 0, timers = [], goal = 0;
  const show = (n) => { frame = Math.max(0, Math.min(DOOR_FRAMES - 1, Math.round(n))); art.style.backgroundPositionX = `${(frame / (DOOR_FRAMES - 1)) * 100}%`; };
  show(0);
  return {
    alarm,
    get frame() { return frame; },
    // open is 0 (shut) to 1 (open). With ms, the leaves run there on held frames: quick out of the stop, slow into it.
    doors(open, ms = 0, onContact) {
      const target = Math.round(open * (DOOR_FRAMES - 1));
      if (!ms && timers.length && goal === target) return;            // already on the way there
      timers.forEach(clearTimeout); timers = []; goal = target;
      if (!ms || target === frame) { show(target); if (ms) onContact?.(); return; }
      const from = frame, n = Math.abs(target - from), dir = Math.sign(target - from);
      for (let i = 1; i <= n; i++) timers.push(setTimeout(() => { show(from + dir * i); if (i === n) { timers = []; onContact?.(); } }, ms * Math.pow(i / n, 1.8)));
    },
  };
}
