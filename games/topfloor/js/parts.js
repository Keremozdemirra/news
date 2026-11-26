// The brass floor-indicator dial and the glass lift car, drawn as SVG.
const NS = "http://www.w3.org/2000/svg";
function el(name, attrs = {}, parent) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
const stops = (g, list) => list.forEach(([o, c]) => el("stop", { offset: o, "stop-color": c }, g));
const pt = (r, a) => [120 + r * Math.sin((a * Math.PI) / 180), 120 - r * Math.cos((a * Math.PI) / 180)];
export const angleFor = (floor) => -110 + 2.2 * floor;
export const BANDS = [[0, 20, "--t0"], [20, 45, "--t1"], [45, 72, "--t2"], [72, 92, "--t3"], [92, 100, "--t4"]];

export function buildDial(svg) {
  const defs = el("defs", {}, svg);
  const ring = el("linearGradient", { id: "d-ring", x1: 0.1, y1: 0, x2: 0.9, y2: 1 }, defs);
  stops(ring, [[0, "#fbe9b8"], [0.3, "#c9a45f"], [0.55, "#8d6d30"], [0.8, "#d4b06a"], [1, "#6f5224"]]);
  const ring2 = el("linearGradient", { id: "d-ring2", x1: 0.9, y1: 1, x2: 0.1, y2: 0 }, defs);
  stops(ring2, [[0, "#e7cc8a"], [0.5, "#7a5a26"], [1, "#d9b671"]]);
  const face = el("radialGradient", { id: "d-face", cx: 0.42, cy: 0.3, r: 0.85 }, defs);
  stops(face, [[0, "#1c2e34"], [0.6, "#0e1a1e"], [1, "#070d10"]]);
  const needle = el("linearGradient", { id: "d-needle", x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
  stops(needle, [[0, "#fff1c4"], [0.5, "#d9b468"], [1, "#8d6b2c"]]);
  const hub = el("radialGradient", { id: "d-hub", cx: 0.35, cy: 0.3, r: 0.8 }, defs);
  stops(hub, [[0, "#fff4d0"], [0.5, "#c9a45f"], [1, "#6b4e1e"]]);
  const clip = el("clipPath", { id: "d-clip" }, defs); el("circle", { cx: 120, cy: 120, r: 103 }, clip);

  el("circle", { cx: 120, cy: 123, r: 119, fill: "#000", "fill-opacity": 0.45 }, svg);
  el("circle", { cx: 120, cy: 120, r: 118, fill: "url(#d-ring)" }, svg);
  el("circle", { cx: 120, cy: 120, r: 108, fill: "url(#d-ring2)" }, svg);
  el("circle", { cx: 120, cy: 120, r: 105, fill: "#05090b" }, svg);
  el("circle", { cx: 120, cy: 120, r: 103, fill: "url(#d-face)" }, svg);

  // tier bands
  for (const [a, b, v] of BANDS) {
    const [x1, y1] = pt(91, angleFor(a) + 0.8), [x2, y2] = pt(91, angleFor(b) - 0.8);
    const large = (angleFor(b) - angleFor(a)) > 180 ? 1 : 0;
    el("path", { d: `M${x1} ${y1}A91 91 0 ${large} 1 ${x2} ${y2}`, fill: "none", style: `stroke:var(${v})`, "stroke-width": 5, "stroke-opacity": 0.9, "stroke-linecap": "butt" }, svg);
  }
  // ticks
  let minor = "", major = "";
  for (let f = 0; f <= 100; f += 2) {
    const big = f % 10 === 0;
    const [x1, y1] = pt(big ? 77 : 82, angleFor(f)), [x2, y2] = pt(86, angleFor(f));
    (big ? (major += `M${x1} ${y1}L${x2} ${y2}`) : (minor += `M${x1} ${y1}L${x2} ${y2}`));
  }
  el("path", { d: minor, stroke: "#c9a45f", "stroke-opacity": 0.55, "stroke-width": 1, fill: "none" }, svg);
  el("path", { d: major, stroke: "#ecd49c", "stroke-width": 2, fill: "none", "stroke-linecap": "round" }, svg);
  for (let f = 0; f <= 100; f += 20) {
    const [x, y] = pt(61, angleFor(f));
    const t = el("text", { x, y, "text-anchor": "middle", "dominant-baseline": "central", style: "font:400 16px Limelight,serif;fill:#f2e9d3" }, svg);
    t.textContent = String(f);
  }
  // maker's mark
  const m = el("text", { x: 120, y: 44, "text-anchor": "middle", style: "font:400 7.4px Limelight,serif;letter-spacing:.34em;fill:#c7a25e;fill-opacity:.85" }, svg);
  m.textContent = "BOARDREAD";
  el("path", { d: "M104 52h32M110 56h20", stroke: "#c7a25e", "stroke-opacity": 0.5, "stroke-width": 1, fill: "none" }, svg);

  // needle
  const n = el("g", { class: "needle", id: "needle" }, svg);
  n.style.transform = `rotate(${angleFor(0)}deg)`;
  el("path", { d: "M121.8 33L125.6 120L120 146L114.4 120L118.2 33Z", fill: "#000", "fill-opacity": 0.4, transform: "translate(2.5 4)" }, n);
  el("path", { d: "M120 28L123.6 120L120 142L116.4 120Z", fill: "url(#d-needle)" }, n);
  el("path", { d: "M120 36V118", stroke: "#fff7dc", "stroke-opacity": 0.55, "stroke-width": 0.8 }, n);
  el("circle", { cx: 120, cy: 144, r: 5.5, fill: "url(#d-hub)" }, n);
  el("circle", { cx: 120, cy: 120, r: 10.5, fill: "#2a1d08" }, svg);
  el("circle", { cx: 120, cy: 120, r: 9, fill: "url(#d-hub)" }, svg);
  el("path", { d: "M115.5 118.5h9", stroke: "#4b3510", "stroke-width": 1.6, "stroke-linecap": "round" }, svg);

  // crystal glare and bezel catch-light
  el("path", { d: "M32 96A92 92 0 0 1 120 28 120 120 0 0 0 32 96Z", fill: "#fff", "fill-opacity": 0.07, "clip-path": "url(#d-clip)" }, svg);
  const [a1, b1] = pt(113.5, -142), [a2, b2] = pt(113.5, -52);
  el("path", { d: `M${a1} ${b1}A113.5 113.5 0 0 1 ${a2} ${b2}`, fill: "none", stroke: "#fff6d8", "stroke-opacity": 0.65, "stroke-width": 1.4, "stroke-linecap": "round" }, svg);
  return n;
}

export function buildCar(svg) {
  const defs = el("defs", {}, svg);
  const brass = el("linearGradient", { id: "c-brass", x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
  stops(brass, [[0, "#f5dfa6"], [0.25, "#c9a45f"], [0.6, "#8d6d30"], [1, "#d3ae66"]]);
  const brassV = el("linearGradient", { id: "c-brassv", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
  stops(brassV, [[0, "#f1d896"], [0.5, "#b08c47"], [1, "#6a4d1f"]]);
  const room = el("linearGradient", { id: "c-room", x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
  stops(room, [[0, "#fff0c4"], [0.35, "#ffdc96"], [1, "#d89d4c"]]);
  const glass = el("linearGradient", { id: "c-glass", x1: 0, y1: 0, x2: 1, y2: 1 }, defs);
  stops(glass, [[0, "#d6ecf0"], [0.5, "#a4c9d2"], [1, "#7fa8b4"]]);
  const clip = el("clipPath", { id: "c-open" }, defs); el("rect", { x: 16, y: 30, width: 80, height: 98 }, clip);

  el("rect", { x: 55.2, y: -80, width: 1.6, height: 84, fill: "#6d5a35" }, svg);          // cable
  el("rect", { x: 53, y: -80, width: 6, height: 1, fill: "#000", "fill-opacity": 0 }, svg);
  // roof: stepped Deco cap
  el("rect", { x: 44, y: 0, width: 24, height: 7, fill: "url(#c-brass)" }, svg);
  el("rect", { x: 24, y: 6, width: 64, height: 9, fill: "url(#c-brass)" }, svg);
  el("rect", { x: 4, y: 14, width: 104, height: 10, fill: "url(#c-brass)" }, svg);
  el("rect", { x: 4, y: 22, width: 104, height: 2, fill: "#000", "fill-opacity": 0.35 }, svg);
  el("circle", { cx: 56, cy: 19, r: 3.4, fill: "#6b3b17", class: "alarm", id: "alarm" }, svg);
  // frame
  el("rect", { x: 8, y: 24, width: 96, height: 112, fill: "url(#c-brassv)" }, svg);
  el("rect", { x: 13, y: 28, width: 86, height: 104, fill: "#1b1408" }, svg);
  // interior
  el("rect", { x: 16, y: 30, width: 80, height: 98, fill: "url(#c-room)" }, svg);
  const inn = el("g", { "clip-path": "url(#c-open)" }, svg);
  for (let x = 24; x < 96; x += 12) el("rect", { x, y: 30, width: 1, height: 98, fill: "#8a5a1c", "fill-opacity": 0.18 }, inn);
  el("rect", { x: 20, y: 33, width: 72, height: 4, fill: "#fffbe8" }, inn);                // ceiling lamp
  el("rect", { x: 16, y: 88, width: 80, height: 3, fill: "url(#c-brass)" }, inn);         // handrail
  el("rect", { x: 16, y: 91, width: 80, height: 2, fill: "#000", "fill-opacity": 0.2 }, inn);
  el("rect", { x: 16, y: 116, width: 80, height: 12, fill: "#8a5a1c", "fill-opacity": 0.35 }, inn);
  el("rect", { x: 46, y: 50, width: 20, height: 24, fill: "#8a5a1c", "fill-opacity": 0.16 }, inn);
  el("circle", { cx: 56, cy: 62, r: 6, fill: "#fff6d8", "fill-opacity": 0.6 }, inn);
  // doors
  const doors = el("g", { "clip-path": "url(#c-open)" }, svg);
  const mk = (x, id, edgeX) => {
    const g = el("g", { id }, doors);
    el("rect", { x, y: 30, width: 40, height: 98, fill: "url(#c-glass)", "fill-opacity": 0.5 }, g);
    el("polygon", { points: `${x + 6},30 ${x + 16},30 ${x + 4},128 ${x - 6},128`, fill: "#fff", "fill-opacity": 0.2 }, g);
    el("rect", { x, y: 30, width: 40, height: 98, fill: "none", stroke: "#c9a45f", "stroke-width": 1.6 }, g);
    el("rect", { x: x + 18, y: 30, width: 4, height: 98, fill: "url(#c-brass)" }, g);
    el("rect", { x: edgeX, y: 30, width: 3.4, height: 98, fill: "url(#c-brassv)" }, g);
    return g;
  };
  mk(16, "door-l", 52.6); mk(56, "door-r", 56);
  el("rect", { x: 16, y: 128, width: 80, height: 8, fill: "url(#c-brass)" }, svg);        // sill
  el("rect", { x: 4, y: 136, width: 104, height: 12, fill: "url(#c-brassv)" }, svg);       // platform
  el("rect", { x: 4, y: 146, width: 104, height: 2, fill: "#000", "fill-opacity": 0.4 }, svg);
  // rivets
  for (const [x, y] of [[11, 40], [101, 40], [11, 120], [101, 120]]) el("circle", { cx: x, cy: y, r: 1.4, fill: "#fff3c8", "fill-opacity": 0.8 }, svg);
  return { l: svg.querySelector("#door-l"), r: svg.querySelector("#door-r"), alarm: svg.querySelector("#alarm") };
}
