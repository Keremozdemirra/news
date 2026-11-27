// The Topfloor world: a dusk skyline built in SVG, five parallax planes plus sky, stars, moon, sun and cloud banks.
// Everything is drawn here from a fixed seed (no images). Windows light up with the score; the sky and
// building colours shift with altitude through CSS custom properties that the stylesheet tweens.

const NS = "http://www.w3.org/2000/svg";
export const FH = 20;        // floor height in world units
export const MAXF = 100;
const CW = 2000, CX = 1000;  // plane canvas width and its centre

function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function rngOf(seed) {
  let a = seed >>> 0;
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const pick = (r, arr) => arr[Math.floor(r() * arr.length)];
const lerp = (a, b, t) => a + (b - a) * t;

// altitude keyframes (0 = street level at dusk, 1 = helipad at night)
const KEYS = [
  { a: 0.0, sky: ["#3b5b7e", "#cb8a80", "#f6c680"], far: "#bb9892", mid: "#7c7284", near: "#4b5068", tower: "#2b4249", brass: "#b8924f", haze: "#f2bb8a", rim: 0.55, stars: 0.0, moon: 0.0, sun: 1, night: 0.0 },
  { a: 0.35, sky: ["#233a5e", "#8a6f7c", "#e1a678"], far: "#8d7f8c", mid: "#5b5f7a", near: "#363c57", tower: "#1f3340", brass: "#a98648", haze: "#cf9b82", rim: 0.4, stars: 0.35, moon: 0.2, sun: 0.65, night: 0.25 },
  { a: 0.7, sky: ["#111d37", "#34456c", "#a5806f"], far: "#566282", mid: "#3a4565", near: "#262e48", tower: "#172735", brass: "#957a42", haze: "#8f7480", rim: 0.2, stars: 0.85, moon: 0.8, sun: 0.15, night: 0.6 },
  { a: 1.0, sky: ["#070c17", "#111b33", "#4b4f69"], far: "#2b3552", mid: "#1d2740", near: "#131a2d", tower: "#0e1a26", brass: "#7f6a3e", haze: "#2c3350", rim: 0.0, stars: 1.0, moon: 1.0, sun: 0.0, night: 1.0 },
];
function mixHex(a, b, t) {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const A = p(a), B = p(b);
  return "#" + A.map((v, i) => Math.round(lerp(v, B[i], t)).toString(16).padStart(2, "0")).join("");
}
export function paletteAt(alt) {
  let i = 0;
  while (i < KEYS.length - 2 && alt > KEYS[i + 1].a) i++;
  const A = KEYS[i], B = KEYS[i + 1];
  const t = Math.min(1, Math.max(0, (alt - A.a) / (B.a - A.a)));
  const m = (k) => mixHex(A[k], B[k], t);
  const n = (k) => lerp(A[k], B[k], t);
  return {
    "--sky-top": mixHex(A.sky[0], B.sky[0], t), "--sky-mid": mixHex(A.sky[1], B.sky[1], t), "--sky-hor": mixHex(A.sky[2], B.sky[2], t),
    "--sky-haze": m("haze"),
    "--stars-a": n("stars").toFixed(3), "--moon-a": n("moon").toFixed(3), "--sun-a": n("sun").toFixed(3), "--night-a": n("night").toFixed(3),
  };
}

export function createWorld(container) {
  const planes = [];
  const lights = [];      // { rects: [layer elements], bias }
  const floorWins = [];   // floorWins[n] = [rect, ...]
  let skyEl;

  function makePlane(id, { k, lift, H, gpad, w = CW, vx = 0 }) {
    const d = document.createElement("div");
    d.className = "plane";
    d.dataset.id = id;
    const svg = el("svg", { viewBox: `${vx} 0 ${w} ${H}`, preserveAspectRatio: "xMidYMid meet" }, d);
    const defs = el("defs", {}, svg);
    container.appendChild(d);
    const p = { id, div: d, svg, defs, k, lift, H, gpad, w, vx, G: H - gpad };
    planes.push(p);
    return p;
  }

  // ---------------------------------------------------------------- sky, stars, moon, sun
  function buildSky() {
    skyEl = document.createElement("div");
    skyEl.className = "sky";
    container.appendChild(skyEl);

    const stars = makePlane("stars", { k: 0.03, lift: 0, H: 1000, gpad: 0 });
    stars.div.classList.add("stars-layer");
    const r = rngOf(7);
    const g = el("g", {}, stars.svg);
    for (let i = 0; i < 220; i++) {
      const big = r() < 0.08;
      const c = el("circle", { cx: r() * CW, cy: r() * 1000, r: big ? 1.7 : lerp(0.5, 1.2, r()), fill: pick(r, ["#fff6e0", "#dfe8ff", "#ffe9c8", "#ffffff"]), "fill-opacity": big ? 0.95 : lerp(0.25, 0.8, r()) }, g);
    }
    stars.top = () => -60;
    stars.special = true;

    const moon = makePlane("moon", { k: 0.05, lift: 0, H: 400, gpad: 0 });
    moon.div.classList.add("moon-layer");
    const mg = el("g", { transform: `translate(${CX + 150} 150)` }, moon.svg);
    const mdefs = moon.defs;
    const mgrad = el("radialGradient", { id: "moonG", cx: "0.38", cy: "0.34", r: "0.8" }, mdefs);
    el("stop", { offset: "0", "stop-color": "#fbf4dc" }, mgrad); el("stop", { offset: "0.7", "stop-color": "#e5dcc0" }, mgrad); el("stop", { offset: "1", "stop-color": "#b8b19c" }, mgrad);
    el("circle", { r: 34, fill: "url(#moonG)" }, mg);
    for (const [x, y, rr, o] of [[-9, -8, 6, 0.16], [10, 6, 9, 0.12], [-4, 14, 4.5, 0.14], [12, -14, 3.5, 0.12], [-17, 4, 3, 0.1]]) el("circle", { cx: x, cy: y, r: rr, fill: "#8d8672", "fill-opacity": o }, mg);
    // terminator shadow so it reads as a lit sphere, not a flat disc
    const clip = el("clipPath", { id: "moonClip" }, mdefs); el("circle", { r: 34 }, clip);
    el("circle", { cx: 20, cy: 6, r: 38, fill: "#0a1020", "fill-opacity": 0.38, "clip-path": "url(#moonClip)" }, mg);
    moon.special = true;

    const sun = makePlane("sun", { k: 0.1, lift: 0, H: 600, gpad: 0 });
    sun.div.classList.add("sun-layer");
    const sg = el("g", { transform: `translate(${CX - 175} 300)` }, sun.svg);
    // posterised glow in flat rings instead of a blurred blob
    for (const [rr, o, c] of [[210, 0.05, "#ffd08a"], [160, 0.08, "#ffc57a"], [118, 0.12, "#ffbb70"], [84, 0.2, "#ffd58f"], [58, 1, "#fff0c4"]]) el("circle", { r: rr, fill: c, "fill-opacity": o }, sg);
    sun.special = true;
  }

  // ---------------------------------------------------------------- skylines
  // window layers: lit patterns cumulative with score; one shared tile set per plane
  function windowSet(p, rng, { cw, ch, cols, rows, density, layers, tones }) {
    const ww = cw * 0.52, wh = ch * 0.56;
    const defs = p.defs;
    const dk = el("pattern", { id: `${p.id}-dk`, width: cw, height: ch, y: p.G % ch, patternUnits: "userSpaceOnUse" }, defs);
    el("rect", { x: (cw - ww) / 2, y: (ch - wh) / 2, width: ww, height: wh, fill: "#05080f", "fill-opacity": 0.28 }, dk);
    const L = [];
    for (let i = 0; i < layers; i++) {
      const pat = el("pattern", { id: `${p.id}-L${i}`, width: cw * cols, height: ch * rows, y: p.G % ch, patternUnits: "userSpaceOnUse" }, defs);
      const used = new Set();
      const n = Math.round(cols * rows * density);
      let guard = 0;
      while (used.size < n && guard++ < 999) {
        const c = Math.floor(rng() * cols), r = Math.floor(rng() * rows), key = c + "," + r;
        if (used.has(key)) continue;
        used.add(key);
        el("rect", { x: c * cw + (cw - ww) / 2, y: r * ch + (ch - wh) / 2, width: ww, height: wh, fill: pick(rng, tones) }, pat);
      }
      L.push(`url(#${p.id}-L${i})`);
    }
    return { cw, ch, dk: `url(#${p.id}-dk)`, L };
  }

  function addLights(g, ws, x, y, w, h, bias) {
    if (w < ws.cw * 3 || h < ws.ch * 2) return;
    const ix = x + ws.cw, iw = w - ws.cw * 2, iy = y + ws.ch * 0.5, ih = h - ws.ch * 1.5;
    if (iw <= 0 || ih <= 0) return;
    el("rect", { x: ix, y: iy, width: iw, height: ih, fill: ws.dk }, g);
    const rects = ws.L.map((f) => { const r = el("rect", { x: ix, y: iy, width: iw, height: ih, fill: f, class: "lit" }, g); r.style.transitionDelay = `${Math.floor(Math.random() * 700)}ms`; return r; });
    lights.push({ rects, bias });
  }

  function skyline(p, seed, o) {
    const r = rngOf(seed);
    const G = p.G;
    const ws = windowSet(p, r, o.win);
    const grad = el("linearGradient", { id: `${p.id}-g`, gradientUnits: "userSpaceOnUse", x1: 0, y1: G - o.hMax, x2: 0, y2: G }, p.defs);
    el("stop", { offset: "0", style: `stop-color:color-mix(in srgb, var(--c-${o.col}) ${o.topMix}%, var(--haze))` }, grad);
    el("stop", { offset: "1", style: `stop-color:color-mix(in srgb, var(--c-${o.col}) ${o.botMix}%, var(--haze))` }, grad);
    const g = el("g", {}, p.svg);
    const fill = `url(#${p.id}-g)`;
    const rimW = o.rim;
    let x = -80;
    let guard = 0;
    while (x < CW + 80 && guard++ < 200) {
      let w = Math.round(lerp(o.wMin, o.wMax, r()) / o.win.cw) * o.win.cw;
      if (o.avoid && x + w > o.avoid[0] && x < o.avoid[1]) { x = o.avoid[1] + lerp(10, 40, r()); continue; }
      // taller towards the middle of the canvas, like a downtown core
      const centre = 1 - Math.min(1, Math.abs(x - CX) / (CW / 2));
      let h = lerp(o.hMin, o.hMax, Math.pow(r(), 1.3) * (0.45 + 0.7 * centre));
      h = Math.max(o.hMin, Math.round(h / o.win.ch) * o.win.ch);
      const kind = r() < o.deco ? "deco" : r() < 0.55 ? "slab" : "block";
      const bias = (r() - 0.5) * 0.4;
      const tiers = [];
      if (kind === "deco") {
        const h0 = Math.round(h * 0.6 / o.win.ch) * o.win.ch, h1 = Math.round(h * 0.22 / o.win.ch) * o.win.ch, h2 = Math.round(h * 0.12 / o.win.ch) * o.win.ch;
        const w1 = Math.max(o.win.cw * 3, Math.round(w * 0.74 / o.win.cw) * o.win.cw), w2 = Math.max(o.win.cw * 3, Math.round(w * 0.46 / o.win.cw) * o.win.cw);
        tiers.push({ x, y: G - h0, w, h: h0 }, { x: x + Math.round((w - w1) / 2 / o.win.cw) * o.win.cw, y: G - h0 - h1, w: w1, h: h1 + 1 }, { x: x + Math.round((w - w2) / 2 / o.win.cw) * o.win.cw, y: G - h0 - h1 - h2, w: w2, h: h2 + 1 });
      } else if (kind === "slab") {
        tiers.push({ x, y: G - h, w, h });
        const bw = Math.max(o.win.cw * 3, Math.round(w * 0.5 / o.win.cw) * o.win.cw);
        tiers.push({ x: x + Math.round((w - bw) / 2 / o.win.cw) * o.win.cw, y: G - h - o.win.ch * 2, w: bw, h: o.win.ch * 2 + 1 });
      } else {
        const hh = Math.round(h * 0.55 / o.win.ch) * o.win.ch;
        tiers.push({ x, y: G - hh, w, h: hh });
      }
      for (const t of tiers) {
        el("rect", { x: t.x, y: t.y, width: t.w, height: t.h, fill }, g);
        el("rect", { x: t.x, y: t.y, width: rimW, height: t.h, fill: "#ffc88a", style: "fill-opacity:var(--rim-a)" }, g);
        el("rect", { x: t.x, y: t.y, width: t.w, height: Math.max(1.4, rimW * 0.7), fill: "#ffe3b0", style: "fill-opacity:calc(var(--rim-a) * 0.55)" }, g);
        if (o.fluting && t.w > 36) {
          let fx = t.x + t.w / 4;
          while (fx < t.x + t.w - 6) { el("rect", { x: fx, y: t.y + 3, width: 1.4, height: t.h - 3, fill: "#000", "fill-opacity": 0.1 }, g); fx += t.w / 4; }
        }
        if (o.windows) addLights(g, ws, t.x, t.y, t.w, t.h, bias);
      }
      const top = tiers[tiers.length - 1];
      if (kind === "deco") {
        // spire: tapered needle, with a beacon on the tallest ones
        const sh = lerp(30, 70, r()) * (o.spire || 1), cx = top.x + top.w / 2;
        el("polygon", { points: `${cx - top.w * 0.16},${top.y} ${cx + top.w * 0.16},${top.y} ${cx + 1.4},${top.y - sh} ${cx - 1.4},${top.y - sh}`, fill }, g);
        el("rect", { x: cx - 0.8, y: top.y - sh - 18 * (o.spire || 1), width: 1.6, height: 18 * (o.spire || 1), fill }, g);
        if (h > o.hMax * 0.62 && r() < 0.8) {
          const b = el("circle", { cx, cy: top.y - sh - 18 * (o.spire || 1), r: o.beaconR, fill: "#ff5a3c", class: "beacon" }, g);
          b.style.animationDelay = `${(r() * 2).toFixed(2)}s`;
        }
      } else if (kind === "block" && o.tanks && r() < 0.6) {
        const tx = top.x + top.w * 0.3, tw = Math.min(30, top.w * 0.3);
        el("rect", { x: tx, y: top.y - 30, width: tw, height: 30, fill }, g);
        el("polygon", { points: `${tx - 3},${top.y - 30} ${tx + tw + 3},${top.y - 30} ${tx + tw / 2},${top.y - 44}`, fill }, g);
        for (const lx of [tx + 4, tx + tw - 5]) el("rect", { x: lx, y: top.y - 8, width: 1.6, height: 8, fill }, g);
      } else if (kind === "slab") {
        el("rect", { x: top.x + top.w / 2 - 0.9, y: top.y - 26, width: 1.8, height: 26, fill }, g);
      }
      x += w + lerp(o.gapMin, o.gapMax, r());
    }
    // ground mist so each plane sinks into the haze behind it
    const mist = el("linearGradient", { id: `${p.id}-m`, x1: 0, y1: 0, x2: 0, y2: 1 }, p.defs);
    el("stop", { offset: "0", style: "stop-color:var(--haze);stop-opacity:0" }, mist);
    el("stop", { offset: "1", style: `stop-color:var(--haze);stop-opacity:${o.mist}` }, mist);
    el("rect", { x: 0, y: G - o.mistH, width: CW, height: o.mistH + 4, fill: `url(#${p.id}-m)` }, p.svg);
    if (o.plaza) {
      const pg = el("linearGradient", { id: `${p.id}-pg`, gradientUnits: "userSpaceOnUse", x1: 0, y1: G, x2: 0, y2: G + p.gpad }, p.defs);
      el("stop", { offset: "0", style: "stop-color:color-mix(in srgb, var(--c-near) 55%, var(--haze))" }, pg);
      el("stop", { offset: "0.35", style: "stop-color:color-mix(in srgb, var(--c-near) 80%, var(--haze))" }, pg);
      el("stop", { offset: "1", style: "stop-color:color-mix(in srgb, var(--c-near) 90%, #000)" }, pg);
      el("rect", { x: 0, y: G, width: CW, height: p.gpad + 4, fill: `url(#${p.id}-pg)` }, p.svg);
      // window light spilling onto the wet plaza
      for (let i = 0; i < 90; i++) {
        const t = r(), y = G + 5 + t * t * p.gpad * 0.85, wd = lerp(14, 90, r()) * (0.6 + t);
        el("rect", { x: r() * CW, y, width: wd, height: 1 + t * 1.6, fill: pick(r, ["#ffd58a", "#ffc068", "#ffe7b6"]), "fill-opacity": lerp(0.04, 0.2, r()) * (1 - t * 0.6) }, p.svg);
      }
    } else el("rect", { x: 0, y: G, width: CW, height: p.gpad + 4, style: `fill:color-mix(in srgb, var(--c-${o.col}) 55%, var(--haze))` }, p.svg);
  }

  // ---------------------------------------------------------------- the tower
  function buildTower() {
    const H = 2560, gpad = 140;
    const p = makePlane("tower", { k: 1, lift: 0, H, gpad, w: 900, vx: CX - 450 });
    const G = p.G, defs = p.defs;
    const yF = (n) => G - n * FH;   // baseline of floor n
    const SEG = [{ a: 3, b: 70, w: 218 }, { a: 70, b: 84, w: 196 }, { a: 84, b: 93, w: 176 }, { a: 93, b: 98, w: 160 }, { a: 98, b: 100, w: 148 }];
    const SHAFT = 128, SH = SHAFT / 2;
    const r = rngOf(31);

    // gradients
    const body = el("linearGradient", { id: "tw-body", gradientUnits: "userSpaceOnUse", x1: 0, y1: yF(100), x2: 0, y2: G }, defs);
    el("stop", { offset: "0", style: "stop-color:color-mix(in srgb, var(--c-tower) 70%, var(--sky-mid))" }, body);
    el("stop", { offset: "0.6", style: "stop-color:var(--c-tower)" }, body);
    el("stop", { offset: "1", style: "stop-color:color-mix(in srgb, var(--c-tower) 80%, var(--haze))" }, body);
    const light = el("linearGradient", { id: "tw-light", x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
    el("stop", { offset: "0", style: "stop-color:#ffc487;stop-opacity:calc(var(--rim-a) * 0.7)" }, light);
    el("stop", { offset: "0.16", style: "stop-color:#ffc487;stop-opacity:calc(var(--rim-a) * 0.14)" }, light);
    el("stop", { offset: "0.5", style: "stop-color:#000;stop-opacity:0" }, light);
    el("stop", { offset: "1", style: "stop-color:#02050a;stop-opacity:0.42" }, light);
    const shaftG = el("linearGradient", { id: "tw-shaft", x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
    el("stop", { offset: "0", "stop-color": "#04080b" }, shaftG); el("stop", { offset: "0.5", "stop-color": "#0d171c" }, shaftG); el("stop", { offset: "1", "stop-color": "#04080b" }, shaftG);
    const brassG = el("linearGradient", { id: "tw-brass", x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
    el("stop", { offset: "0", style: "stop-color:color-mix(in srgb, var(--c-brass) 70%, #fff)" }, brassG); el("stop", { offset: "0.5", style: "stop-color:var(--c-brass)" }, brassG); el("stop", { offset: "1", style: "stop-color:color-mix(in srgb, var(--c-brass) 60%, #000)" }, brassG);

    // silhouette clip for lighting overlays
    [["#fff0c0", "#f0b45e"], ["#ffd88a", "#e8963c"], ["#fffadb", "#f5cf8a"]].forEach(([a, b], i) => {
      const lg = el("linearGradient", { id: `tw-lit${i}`, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
      el("stop", { offset: "0", "stop-color": a }, lg); el("stop", { offset: "1", "stop-color": b }, lg);
    });
    const clip = el("clipPath", { id: "tw-clip" }, defs);
    for (const s of SEG) el("rect", { x: CX - s.w / 2, y: yF(s.b), width: s.w, height: (s.b - s.a) * FH + 1 }, clip);
    el("rect", { x: CX - 135, y: yF(3.6), width: 270, height: 3.6 * FH }, clip);

    const g = el("g", {}, p.svg);

    // plaza line (the ground itself is painted by the near skyline plane)
    el("rect", { x: 0, y: G, width: CW, height: 3, style: "fill:color-mix(in srgb, var(--haze) 70%, #fff);fill-opacity:0.35" }, g);

    // body segments
    for (const s of SEG) el("rect", { x: CX - s.w / 2, y: yF(s.b), width: s.w, height: (s.b - s.a) * FH + 1, fill: "url(#tw-body)" }, g);
    // shaft recess
    el("rect", { x: CX - SH, y: yF(100), width: SHAFT, height: 97 * FH, fill: "url(#tw-shaft)" }, g);

    // windows
    for (let n = 0; n < 100; n++) floorWins[n] = [];
    for (const s of SEG) {
      const ww = s.w / 2 - SH;                 // wing width
      const cnt = ww >= 60 ? 3 : ww >= 40 ? 2 : ww >= 20 ? 1 : 0;
      const winW = cnt === 2 ? 14 : 12;
      const gap = cnt > 1 ? (ww - 10 - cnt * winW) / (cnt - 1) : 0;
      for (let n = s.a; n < s.b; n++) {
        for (const side of [-1, 1]) {
          for (let i = 0; i < cnt; i++) {
            const x0 = side < 0 ? CX - s.w / 2 + 5 + i * (winW + gap) : CX + SH + 5 + i * (winW + gap);
            const x = cnt === 1 ? (side < 0 ? CX - s.w / 2 + (ww - winW) / 2 : CX + SH + (ww - winW) / 2) : x0;
            const wy = yF(n + 1) + 3.5;
            el("rect", { x, y: wy, width: winW, height: FH - 7, class: "fl-win" }, g);
            const rr = el("rect", { x, y: wy, width: winW, height: FH - 7, class: "fl-lit", fill: `url(#tw-lit${r() < 0.3 ? 1 : r() < 0.35 ? 2 : 0})`, "data-r": r().toFixed(3) }, g);
            floorWins[n].push(rr);
          }
        }
      }
    }
    // spandrels and piers
    let d = "";
    for (const s of SEG) for (let n = s.a; n <= s.b; n++) d += `M${CX - s.w / 2} ${yF(n)}h${s.w}`;
    el("path", { d, stroke: "#000", "stroke-opacity": 0.3, "stroke-width": 1, fill: "none" }, g);
    for (const s of SEG) {
      const xs = [CX - s.w / 2, CX - SH, CX + SH, CX + s.w / 2 - 2.4];
      for (const x of xs) el("rect", { x, y: yF(s.b), width: 2.4, height: (s.b - s.a) * FH, fill: "url(#tw-brass)", "fill-opacity": 0.9 }, g);
    }
    // shaft rails, floor ticks, counterweight cables
    for (const x of [CX - SH + 6, CX + SH - 9]) el("rect", { x, y: yF(100), width: 3, height: 97 * FH, fill: "url(#tw-brass)" }, g);
    let t = "";
    for (let n = 3; n < 100; n++) t += `M${CX - SH + 9} ${yF(n)}h7M${CX + SH - 16} ${yF(n)}h7`;
    el("path", { d: t, stroke: "#c7a25e", "stroke-opacity": 0.5, "stroke-width": 1.2, fill: "none" }, g);
    el("rect", { x: CX - SH + 24, y: yF(100), width: 1.2, height: 97 * FH, fill: "#c7a25e", "fill-opacity": 0.18 }, g);
    el("rect", { x: CX + SH - 25, y: yF(100), width: 1.2, height: 97 * FH, fill: "#c7a25e", "fill-opacity": 0.18 }, g);

    // belt cornices with engraved floor numbers every ten floors
    for (let n = 10; n <= 90; n += 10) {
      const s = SEG.find((q) => n >= q.a && n < q.b) || SEG[SEG.length - 1];
      const bw = s.w + 8;
      el("rect", { x: CX - bw / 2, y: yF(n) - 3, width: bw, height: 6, fill: "url(#tw-brass)" }, g);
      el("rect", { x: CX - bw / 2, y: yF(n) + 3, width: bw, height: 2, fill: "#000", "fill-opacity": 0.35 }, g);
      const tx = el("text", { x: CX - s.w / 2 + 8, y: yF(n) - 7, style: "font:400 13px Limelight,serif;fill:var(--c-brass);letter-spacing:.04em" }, g);
      tx.textContent = String(n);
    }
    // setback shoulders: stepped brass chevrons
    for (const s of SEG.slice(1)) {
      const y = yF(s.a);
      el("polygon", { points: `${CX - s.w / 2 - 14},${y + 6} ${CX + s.w / 2 + 14},${y + 6} ${CX + s.w / 2 + 2},${y - 3} ${CX - s.w / 2 - 2},${y - 3}`, fill: "url(#tw-brass)" }, g);
    }
    // podium and lobby
    const py = yF(3.6);
    el("rect", { x: CX - 135, y: py, width: 270, height: 3.6 * FH, style: "fill:color-mix(in srgb, var(--c-tower) 85%, var(--haze))" }, g);
    el("rect", { x: CX - 135, y: py, width: 270, height: 5, fill: "url(#tw-brass)" }, g);
    const lobbyG = el("linearGradient", { id: "tw-lobby", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
    el("stop", { offset: "0", "stop-color": "#ffe3a8" }, lobbyG); el("stop", { offset: "1", "stop-color": "#e9b361" }, lobbyG);
    const arch = (cx, w, h) => `M${cx - w / 2} ${G}V${G - h + w / 2}A${w / 2} ${w / 2} 0 0 1 ${cx + w / 2} ${G - h + w / 2}V${G}Z`;
    el("path", { d: arch(CX, SHAFT - 14, 3.2 * FH), fill: "url(#tw-lobby)" }, g);
    for (const sx of [-98, 98]) el("path", { d: arch(CX + sx, 46, 2.5 * FH), fill: "url(#tw-lobby)", "fill-opacity": 0.92 }, g);
    for (const sx of [-98, 98]) for (const ox of [-8, 8]) el("rect", { x: CX + sx + ox - 1, y: G - 2.5 * FH + 24, width: 2, height: 2.5 * FH - 24, fill: "#6b4a1a", "fill-opacity": 0.55 }, g);
    for (const x of [CX - 130, CX - 66, CX + 66, CX + 124]) el("rect", { x, y: py + 5, width: 6, height: 3.6 * FH - 5, fill: "url(#tw-brass)" }, g);
    // canopy sign
    el("rect", { x: CX - 60, y: py + 9, width: 120, height: 17, fill: "#0a1114", stroke: "var(--c-brass)", style: "stroke:var(--c-brass)", "stroke-width": 1 }, g);
    const sign = el("text", { x: CX, y: py + 22, "text-anchor": "middle", style: "font:400 11px Limelight,serif;fill:#ecd49c;letter-spacing:.2em" }, g);
    sign.textContent = "BOARDREAD";
    // steps
    for (let i = 0; i < 3; i++) el("rect", { x: CX - 70 - i * 6, y: G - 1 + i * 3, width: 140 + i * 12, height: 3, fill: "#fff", "fill-opacity": 0.08 - i * 0.02 }, g);
    // street lamps
    for (const lx of [CX - 215, CX - 175, CX + 175, CX + 215]) {
      el("rect", { x: lx - 1, y: G - 46, width: 2, height: 46, fill: "#05080c" }, g);
      el("circle", { cx: lx, cy: G - 48, r: 4, fill: "#ffd58a" }, g);
      el("circle", { cx: lx, cy: G - 48, r: 9, fill: "#ffd58a", "fill-opacity": 0.14 }, g);
    }

    // light and glass overlays, clipped to the silhouette
    const ov = el("g", { "clip-path": "url(#tw-clip)" }, g);
    el("rect", { x: CX - 160, y: yF(100), width: 320, height: 100 * FH, fill: "url(#tw-light)" }, ov);
    for (const [x, w, o] of [[CX - 118, 18, 0.05], [CX - 70, 7, 0.04], [CX + 24, 26, 0.045], [CX + 80, 9, 0.035]]) {
      el("polygon", { points: `${x},${yF(100)} ${x + w},${yF(100)} ${x + w - 60},${G} ${x - 60},${G}`, fill: "#fff", "fill-opacity": o }, ov);
    }

    // crown: brass fins, then the helipad hovering above the shaft
    const cy = yF(100);
    for (const [dx, hh] of [[-58, 34], [-36, 52], [-14, 70], [14, 70], [36, 52], [58, 34]]) el("polygon", { points: `${CX + dx - 5},${cy} ${CX + dx + 5},${cy} ${CX + dx + 2.4},${cy - hh} ${CX + dx - 2.4},${cy - hh}`, fill: "url(#tw-brass)" }, g);
    el("rect", { x: CX - 70, y: cy - 5, width: 140, height: 6, fill: "url(#tw-brass)" }, g);
    // struts and platform at floor 108
    const pady = yF(108);
    for (const dx of [-70, 70]) el("polygon", { points: `${CX + dx - 3},${cy - 70} ${CX + dx + 3},${cy - 70} ${CX + dx * 0.78 + 3},${pady + 6} ${CX + dx * 0.78 - 3},${pady + 6}`, fill: "url(#tw-brass)", "fill-opacity": 0.85 }, g);
    el("ellipse", { cx: CX, cy: pady + 7, rx: 96, ry: 12, style: "fill:color-mix(in srgb, var(--c-tower) 50%, #000)" }, g);
    el("rect", { x: CX - 96, y: pady, width: 192, height: 7, style: "fill:color-mix(in srgb, var(--c-tower) 60%, #000)" }, g);
    el("ellipse", { cx: CX, cy: pady, rx: 96, ry: 12, style: "fill:color-mix(in srgb, var(--c-tower) 40%, #30383b)" }, g);
    el("ellipse", { cx: CX, cy: pady, rx: 70, ry: 8.4, fill: "none", stroke: "#f6ecd0", "stroke-opacity": 0.8, "stroke-width": 2 }, g);
    const hh = el("text", { x: CX, y: pady, "text-anchor": "middle", transform: `translate(0 ${pady + 0}) scale(1 .3) translate(0 ${-pady})`, style: "font:400 54px Limelight,serif;fill:#f6ecd0;fill-opacity:.9", "dominant-baseline": "central" }, g);
    hh.textContent = "H";
    for (let i = 0; i < 14; i++) {
      const a = (i / 14) * Math.PI * 2;
      el("circle", { cx: CX + Math.cos(a) * 96, cy: pady + Math.sin(a) * 12, r: 1.8, fill: "#ffd58a" }, g);
    }
    el("rect", { x: CX - 1.6, y: pady - 150, width: 3.2, height: 150, fill: "url(#tw-brass)" }, g);
    el("rect", { x: CX - 9, y: pady - 80, width: 18, height: 2, fill: "url(#tw-brass)" }, g);
    el("circle", { cx: CX, cy: pady - 152, r: 4, fill: "#ff5a3c", class: "beacon" }, g);
    return p;
  }

  function buildCarpet() {
    const p = makePlane("carpet", { k: 0.22, lift: 30, H: 340, gpad: 20 });
    const r = rngOf(11);
    const pat = el("pattern", { id: "cp-dots", width: 56, height: 22, patternUnits: "userSpaceOnUse" }, p.defs);
    for (let i = 0; i < 9; i++) el("rect", { x: Math.floor(r() * 54), y: Math.floor(r() * 20), width: 2.2, height: 1.6, fill: pick(r, ["#ffd58a", "#ffc068", "#fff0c0", "#ffb35c"]), "fill-opacity": lerp(0.5, 1, r()) }, pat);
    const mk = el("linearGradient", { id: "cp-fade", x1: 0, y1: 0, x2: 0, y2: 1 }, p.defs);
    el("stop", { offset: "0", "stop-color": "#000" }, mk); el("stop", { offset: "0.45", "stop-color": "#fff" }, mk); el("stop", { offset: "1", "stop-color": "#fff" }, mk);
    const mask = el("mask", { id: "cp-mask" }, p.defs);
    el("rect", { x: 0, y: 0, width: CW, height: 340, fill: "url(#cp-fade)" }, mask);
    el("rect", { x: 0, y: 40, width: CW, height: 300, fill: "url(#cp-dots)", mask: "url(#cp-mask)" }, p.svg);
    // street grid
    let d = "";
    for (let i = 0; i < 24; i++) d += `M${i * 100 + (i % 3) * 11} 330L${CX + (i * 100 - CX) * 0.35} 120`;
    el("path", { d, stroke: "#ffd58a", "stroke-opacity": 0.07, "stroke-width": 1, fill: "none", mask: "url(#cp-mask)" }, p.svg);
    el("rect", { x: 0, y: 330, width: CW, height: 40, style: "fill:color-mix(in srgb, var(--c-far) 55%, var(--haze))" }, p.svg);
  }

  function buildClouds() {
    const r = rngOf(19);
    for (const fl of [34, 71]) {
      const H = 300, yc = fl * FH * 1.3 + 90;
      const p = makePlane("clouds" + fl, { k: 1.3, lift: yc - H / 2, H, gpad: 0 });
      const f = el("filter", { id: "cloudf" + fl, x: "-10%", y: "-60%", width: "120%", height: "220%" }, p.defs);
      el("feTurbulence", { type: "fractalNoise", baseFrequency: "0.006 0.018", numOctaves: 3, seed: 8 + fl, result: "n" }, f);
      el("feDisplacementMap", { in: "SourceGraphic", in2: "n", scale: 50, result: "d" }, f);
      el("feGaussianBlur", { in: "d", stdDeviation: 5 }, f);
      const g = el("g", { filter: `url(#cloudf${fl})` }, p.svg);
      for (let i = 0; i < 16; i++) {
        const cx = r() * CW, w = lerp(280, 600, r()), h = lerp(26, 56, r()), dy = (r() - 0.5) * 50, y = H / 2;
        el("ellipse", { cx, cy: y + dy, rx: w / 2, ry: h / 2, style: "fill:color-mix(in srgb, var(--haze) 55%, #fff);fill-opacity:.42" }, g);
        el("ellipse", { cx: cx + w * 0.06, cy: y + dy - h * 0.22, rx: w * 0.36, ry: h * 0.3, style: "fill:color-mix(in srgb, var(--haze) 25%, #fff);fill-opacity:.4" }, g);
      }
    }
  }

  // ---------------------------------------------------------------- layout and motion
  let s = 1, groundY = 400, curFloor = 0;

  function layout(scale, ground, vh, vw = 1000) {
    s = scale; groundY = ground;
    skyEl.style.top = `${-300 * s}px`;
    const hor = (ground - 96 * s) + 300 * s;
    skyEl.style.height = `${hor + 1400 * s}px`;
    skyEl.style.background = `linear-gradient(to bottom, var(--sky-top) 0px, var(--sky-top) ${hor * 0.1}px, var(--sky-mid) ${hor * 0.58}px, var(--sky-hor) ${hor * 0.9}px, var(--sky-haze) ${hor}px, var(--sky-haze) 100%)`;
    for (const p of planes) {
      // paint only as much width as the screen can show; huge layers get dropped by some compositors
      const vis = Math.min(p.w, vw / s + 260), w = vis * s, h = p.H * s;
      p.svg.setAttribute("viewBox", `${p.vx + (p.w - vis) / 2} 0 ${vis} ${p.H}`);
      p.svg.setAttribute("width", w); p.svg.setAttribute("height", h);
      p.div.style.marginLeft = `${-w / 2}px`;
      p.div.style.width = `${w}px`; p.div.style.height = `${h}px`;
      let top;
      if (p.id === "stars") top = -60 * s;
      else if (p.id === "moon") top = 0;
      else if (p.id === "sun") top = ground - 96 * s - 300 * s;
      else top = ground - p.lift * s - p.G * s;
      p.div.style.top = `${top}px`;
    }
    setFloor(curFloor, true);
  }

  function setFloor(f, instant) {
    curFloor = f;
    if (instant) for (const p of planes) p.div.style.transitionDuration = "0ms", skyEl.style.transitionDuration = "0ms";
    else for (const p of planes) p.div.style.transitionDuration = "", skyEl.style.transitionDuration = "";
    for (const p of planes) p.div.style.transform = `translate3d(0, ${f * FH * p.k * s}px, 0)`;
    skyEl.style.transform = `translate3d(0, ${f * FH * 0.06 * s}px, 0)`;
  }

  // lights: window layers by score progress (0..1), tower floors by floor
  function setProgress(prog) {
    for (const l of lights) {
      const v = prog + l.bias;
      l.rects.forEach((r, i) => r.classList.toggle("on", v >= i * 0.19 - 0.02 + (i === 0 ? -0.2 : 0)));
    }
  }
  let litTo = -1;
  function setLitFloors(f) {
    const top = Math.min(99, Math.floor(f) + 2);
    const dir = top >= litTo ? 1 : -1;
    for (let n = 0; n <= 99; n++) {
      const on = n <= top;
      for (const w of floorWins[n]) {
        const want = on && parseFloat(w.dataset.r) < 0.86;
        if (w.classList.contains("on") !== want) {
          w.style.transitionDelay = `${Math.max(0, (n - Math.max(litTo, 0)) * 36 * dir)}ms`;
          w.classList.toggle("on", want);
        }
      }
    }
    litTo = top;
  }

  buildSky();
  const far = makePlane("far", { k: 0.16, lift: 74, H: 1180, gpad: 420 });
  skyline(far, 101, { col: "far", wMin: 26, wMax: 58, hMin: 90, hMax: 470, deco: 0.55, gapMin: -6, gapMax: 12, rim: 1.4, topMix: 92, botMix: 70, mist: 0.6, mistH: 150, spire: 0.8, beaconR: 1.6, windows: true, win: { cw: 5, ch: 7, cols: 10, rows: 12, density: 0.1, layers: 5, tones: ["#ffd58a", "#ffe1a8", "#ffc068"] } });
  buildCarpet();
  const mid = makePlane("mid", { k: 0.38, lift: 38, H: 1400, gpad: 420 });
  skyline(mid, 202, { col: "mid", wMin: 44, wMax: 90, hMin: 160, hMax: 640, deco: 0.5, gapMin: -10, gapMax: 22, rim: 2, topMix: 94, botMix: 68, mist: 0.5, mistH: 200, spire: 1, beaconR: 2.2, tanks: true, windows: true, win: { cw: 8, ch: 11, cols: 8, rows: 9, density: 0.12, layers: 5, tones: ["#ffd58a", "#ffe1a8", "#ffc068", "#ffb35c"] } });
  const near = makePlane("near", { k: 0.64, lift: 14, H: 1660, gpad: 420 });
  skyline(near, 303, { col: "near", wMin: 64, wMax: 130, hMin: 260, hMax: 920, deco: 0.42, gapMin: 2, gapMax: 30, rim: 3, topMix: 96, botMix: 76, mist: 0.55, mistH: 160, spire: 1.4, beaconR: 3, tanks: true, fluting: true, plaza: true, avoid: [CX - 190, CX + 190], windows: true, win: { cw: 10, ch: 14, cols: 8, rows: 8, density: 0.13, layers: 5, tones: ["#ffd88f", "#ffe7b6", "#ffc468", "#ffaa55"] } });
  const tower = buildTower();
  buildClouds();

  return { layout, setFloor, setProgress, setLitFloors, planes };
}
