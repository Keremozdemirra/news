// The balance. Art is pre-rendered in Blender (art/build_scale.py layers): seven sprites at level beam.
// This module turns the beam, shifts the pans, stands the two paper tickets in them from the exported pan
// coordinates, and plays authored motion scores. No physics, no CSS easing on the beam.

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
  let meta = null, k = 1, theta = 0, raf = 0, ox = 0, oy = 0;
  const sway = { a: 0, b: 0 };
  const L = {};          // layer name -> <img>

  // Seven sprites rendered at level beam (art/build_scale.py layers): the stand with the balance's shadow, the beam, the
  // head and reading plate that cover its middle and its needle tip, and each pan as a back and a front half. The beam only turns about its pin and the pans only shift, so a frame is three
  // transforms on images the compositor already holds. No frame is decoded or painted while the beam moves.
  async function load(base) {
    meta = await (await fetch(base + "scale.json")).json();
    A0 = meta.angles[0]; STEP = meta.step; N = meta.frames.length; IMG_W = meta.w; IMG_H = meta.h; DW = IMG_W / 2; DH = IMG_H / 2;
    const place = (name, host) => new Promise((res, rej) => {
      const b = meta.layers[name], i = new Image();
      i.alt = ""; i.decoding = "async"; i.draggable = false; i.className = "sprite";
      i.style.cssText = `left:${(100 * b.x / IMG_W).toFixed(4)}%;top:${(100 * b.y / IMG_H).toFixed(4)}%;width:${(100 * b.w / IMG_W).toFixed(4)}%;height:${(100 * b.h / IMG_H).toFixed(4)}%`;
      i.onload = () => res(); i.onerror = rej; i.src = `${base}${name}.webp`;
      host.appendChild(i); L[name] = i;
    });
    back.textContent = ""; front.textContent = "";
    await Promise.all([...["stand", "beam", "top", "pan_l_back", "pan_r_back"].map((n) => place(n, back)), ...["pan_l_front", "pan_r_front"].map((n) => place(n, front))]);
    const b = meta.layers.beam;
    L.beam.style.transformOrigin = `${(100 * (meta.pivot[0] * IMG_W - b.x) / b.w).toFixed(3)}% ${(100 * (meta.pivot[1] * IMG_H - b.y) / b.h).toFixed(3)}%`;
  }

  // a ticket's height is read when it can change (layout, new text), never inside a frame
  const measure = () => { for (const el of [pa, pb]) el._h = el.offsetHeight; };
  if (typeof ResizeObserver !== "undefined") { const ro = new ResizeObserver(() => { measure(); if (meta && !raf) draw(theta); }); ro.observe(pa); ro.observe(pb); }

  function layout() {
    const zw = zone.clientWidth, zh = zone.clientHeight;
    k = Math.min(zw / ZONE_W, zh / DH, 1.15);
    const w = DW * k, h = DH * k;
    ox = (zw - w) / 2; oy = zh - h;                       // art stands on the bottom of the zone
    for (const c of [back, front]) { c.style.width = w + "px"; c.style.height = h + "px"; c.style.left = ox + "px"; c.style.top = oy + "px"; }
    if (plate) { plate.style.width = w * PLATE_W + "px"; plate.style.height = h * PLATE_H + "px"; plate.style.left = (zw - w * PLATE_W) / 2 + "px"; plate.style.top = zh - h * PLATE_H + "px"; }
    measure();
    draw(theta);
  }

  // pan position at a continuous angle: linear blend of the two nearest exported positions
  function panAt(side, deg) {
    const f = clamp((deg - A0) / STEP, 0, N - 1), i = Math.floor(f), j = Math.min(N - 1, i + 1), u = f - i;
    const a = meta.frames[i][side], b = meta.frames[j][side];
    const m = (p, q) => p + (q - p) * u;
    return { x: m(a.base[0], b.base[0]), y: m(a.base[1], b.base[1]), rx: m(a.rim[0], b.rim[0]), ry: m(a.rim[1], b.rim[1]) };
  }

  function draw(deg) {
    theta = clamp(deg, A0, A0 + (N - 1) * STEP);
    if (!meta) return;
    const w = DW * k, h = DH * k;
    L.beam.style.transform = `rotate(${theta.toFixed(3)}deg)`;
    for (const [el, side, sw] of [[pa, "l", sway.a], [pb, "r", sway.b]]) {
      const p = panAt(side, theta), p0 = panAt(side, 0);
      const t = `translate3d(${((p.x - p0.x) * w).toFixed(2)}px, ${((p.y - p0.y) * h).toFixed(2)}px, 0)`;
      L[`pan_${side}_back`].style.transform = t; L[`pan_${side}_front`].style.transform = t;
      const x = ox + p.x * w, y = oy + ((p.y + p.ry) / 2) * h;   // the ticket stands half way down the bowl, behind its front wall
      el.style.transform = `translate3d(${(x - TICKET_W / 2).toFixed(2)}px, ${(y - (el._h || 0)).toFixed(2)}px, 0) rotate(${sw.toFixed(2)}deg) scale(${k.toFixed(4)}, ${(k * (el._sq || 1)).toFixed(4)})`;
    }
  }

  // play a score f(t) -> degrees for `dur` ms; lag swings the tickets a little behind the beam
  function play(f, dur, onDone, onFrame) {
    cancelAnimationFrame(raf);
    if (reduced) { draw(f(dur)); onDone?.(); return; }
    const t0 = performance.now(); let prev = f(0), sw = 0;
    const loop = (now) => {
      const t = Math.min(dur, now - t0), d = f(t);
      sw += (clamp(-(d - prev) * 5, -2.2, 2.2) - sw) * 0.35;   // tickets hang a beat behind the beam
      sway.a = sway.b = sw; prev = d;
      draw(d); onFrame?.(t);
      if (t < dur) raf = requestAnimationFrame(loop); else { raf = 0; sway.a = sway.b = 0; draw(f(dur)); onDone?.(); }
    };
    raf = requestAnimationFrame(loop);
  }

  // ticket squash on contact: authored, 160 ms: 0.94, 1.03, 1.0 on the vertical axis
  function squash(el) {
    if (reduced) return;
    const keys = score([[0, 1], [55, 0.94, "out"], [110, 1.03, "inOut"], [170, 1, "inOut"]]);
    const t0 = performance.now();
    const loop = (now) => { const t = now - t0; el._sq = keys(t); draw(theta); if (t < 170) requestAnimationFrame(loop); else { el._sq = 1; draw(theta); } };
    requestAnimationFrame(loop);
  }

  return { load, layout, draw, play, squash, get theta() { return theta; }, get k() { return k; }, set(deg) { cancelAnimationFrame(raf); raf = 0; draw(deg); } };
}
