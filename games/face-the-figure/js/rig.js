// The balance. Art is pre-rendered in Blender (art/build_scale.py): one back layer and one front layer
// per beam angle. This module picks the frame, stands the two paper tickets in the pans from the
// exported pan coordinates, and plays authored motion scores. No physics, no CSS easing on the beam.

let A0 = -12, STEP = 1, N = 25;             // frame n is the beam at A0 + n * STEP degrees (read from scale.json)
let IMG_W = 900, IMG_H = 880, DW = 450, DH = 440;     // render px, and the same at 1x design px
const ZONE_W = 390, TICKET_W = 136;
const PLATE_W = 4, PLATE_H = 1.5;         // the room plate, in balance frames; it shares the frame's bottom edge and centre

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const ease = {
  linear: (p) => p,
  out: (p) => 1 - Math.pow(1 - p, 3),
  outQ: (p) => 1 - Math.pow(1 - p, 4),
  inOut: (p) => 0.5 - 0.5 * Math.cos(Math.PI * p),
  in: (p) => p * p,
};

// beam angle (degrees, positive = B side down) for a running value v against A. Log for sizes, linear for years.
export function tiltFor(kind, v, a) {
  const s = kind === "founded" ? (v - a) / 9 : Math.log(Math.max(v, 1e-9) / a);
  return 11.4 * Math.tanh(s / 0.5);
}

// A piecewise score: keys are [ms, value, ease-to-this-key]. Returns f(t).
// The rank for c correct calls on a chain of n links. The ladder follows the chain's length, which is 8 to 10 by the day:
// every call right is always the top rank, one miss the second, then 70, 50 and 30 per cent.
export const RANKS = ["Apprentice", "Junior clerk", "Senior clerk", "Chief cashier", "Auditor", "Comptroller"];
export function rankOf(c, n) {
  const cuts = [0, Math.ceil(n * 0.3), Math.ceil(n * 0.5), Math.min(Math.ceil(n * 0.7), n - 2), n - 1, n];
  return RANKS[cuts.filter((k) => c >= k).length - 1];
}

export function score(keys) {
  return (t) => {
    if (t <= keys[0][0]) return keys[0][1];
    for (let i = 1; i < keys.length; i++) {
      if (t <= keys[i][0]) { const [t0, v0] = keys[i - 1], [t1, v1, e] = keys[i]; return v0 + (v1 - v0) * (ease[e || "inOut"])((t - t0) / (t1 - t0)); }
    }
    return keys[keys.length - 1][1];
  };
}

export function createRig({ zone, back, front, plate, pa, pb, reduced }) {
  const bctx = back.getContext("2d"), fctx = front.getContext("2d");
  let meta = null, bImgs = [], fImgs = [], k = 1, shown = -1, theta = 0, raf = 0, ox = 0, oy = 0;
  const sway = { a: 0, b: 0 };

  async function load(base) {
    meta = await (await fetch(base + "scale.json")).json();
    A0 = meta.angles[0]; STEP = meta.step; N = meta.frames.length; IMG_W = meta.w; IMG_H = meta.h; DW = IMG_W / 2; DH = IMG_H / 2;
    const get = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
    const ext = meta.ext || "png";
    const names = Array.from({ length: meta.frames.length }, (_, n) => String(n).padStart(2, "0"));
    [bImgs, fImgs] = await Promise.all([Promise.all(names.map((n) => get(`${base}back_${n}.${ext}`))), Promise.all(names.map((n) => get(`${base}front_${n}.${ext}`)))]);
    for (const c of [back, front]) { c.width = IMG_W; c.height = IMG_H; }
  }

  function layout() {
    const zw = zone.clientWidth, zh = zone.clientHeight;
    k = Math.min(zw / ZONE_W, zh / DH, 1.15);
    const w = DW * k, h = DH * k;
    ox = (zw - w) / 2; oy = zh - h;                       // art stands on the bottom of the zone
    for (const c of [back, front]) { c.style.width = w + "px"; c.style.height = h + "px"; c.style.left = ox + "px"; c.style.top = oy + "px"; }
    if (plate) { plate.style.width = w * PLATE_W + "px"; plate.style.height = h * PLATE_H + "px"; plate.style.left = (zw - w * PLATE_W) / 2 + "px"; plate.style.top = zh - h * PLATE_H + "px"; }
    draw(theta, true);
  }

  // pan position at a continuous angle: linear blend of the two nearest exported frames
  function panAt(side, deg) {
    const f = clamp((deg - A0) / STEP, 0, N - 1), i = Math.floor(f), j = Math.min(N - 1, i + 1), u = f - i;
    const a = meta.frames[i][side], b = meta.frames[j][side];
    const m = (p, q) => p + (q - p) * u;
    return { x: m(a.base[0], b.base[0]), y: m(a.base[1], b.base[1]), rx: m(a.rim[0], b.rim[0]), ry: m(a.rim[1], b.rim[1]) };
  }

  function draw(deg, force) {
    theta = clamp(deg, A0, A0 + (N - 1) * STEP);
    if (!meta) return;
    const n = Math.round((theta - A0) / STEP);
    if (n !== shown || force) {
      shown = n;
      bctx.clearRect(0, 0, IMG_W, IMG_H); bctx.drawImage(bImgs[n], 0, 0);
      fctx.clearRect(0, 0, IMG_W, IMG_H); fctx.drawImage(fImgs[n], 0, 0);
    }
    for (const [el, side, sw] of [[pa, "l", sway.a], [pb, "r", sway.b]]) {
      const p = panAt(side, theta), x = ox + p.x * DW * k, y = oy + ((p.y + p.ry) / 2) * DH * k;   // the ticket stands half way down the bowl, behind its front wall
      el.style.transform = `translate(${(x - TICKET_W / 2).toFixed(2)}px, ${(y - el.offsetHeight).toFixed(2)}px) rotate(${sw.toFixed(2)}deg) scale(${k.toFixed(4)}, ${(k * (el._sq || 1)).toFixed(4)})`;
    }
  }

  // play a score f(t) -> degrees for `dur` ms; lag swings the tickets a little behind the beam
  function play(f, dur, onDone, onFrame) {
    cancelAnimationFrame(raf);
    if (reduced) { draw(f(dur), false); onDone?.(); return; }
    const t0 = performance.now(); let prev = f(0), sw = 0;
    const loop = (now) => {
      const t = Math.min(dur, now - t0), d = f(t);
      sw += (clamp(-(d - prev) * 5, -2.2, 2.2) - sw) * 0.35;   // tickets hang a beat behind the beam
      sway.a = sway.b = sw; prev = d;
      draw(d, false); onFrame?.(t);
      if (t < dur) raf = requestAnimationFrame(loop); else { sway.a = sway.b = 0; draw(f(dur), false); onDone?.(); }
    };
    raf = requestAnimationFrame(loop);
  }

  // ticket squash on contact: authored, 160 ms: 0.94, 1.03, 1.0 on the vertical axis
  function squash(el) {
    if (reduced) return;
    const keys = score([[0, 1], [55, 0.94, "out"], [110, 1.03, "inOut"], [170, 1, "inOut"]]);
    const t0 = performance.now();
    const loop = (now) => { const t = now - t0; el._sq = keys(t); draw(theta, false); if (t < 170) requestAnimationFrame(loop); else { el._sq = 1; draw(theta, false); } };
    requestAnimationFrame(loop);
  }

  return { load, layout, draw, play, squash, get theta() { return theta; }, get k() { return k; }, set(deg) { cancelAnimationFrame(raf); draw(deg, false); } };
}
