import { createWorld, paletteAt, MAXF } from "./world.js";
import { buildDial, buildCar, score, play } from "./parts.js";
import * as snd from "./sound.js";

const $ = (id) => document.getElementById(id);
const app = $("app"), card = $("card");
const params = new URLSearchParams(location.search);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const STORE = "topfloor:v1";
const BARS = ["▁", "▃", "▅", "▇", "█"];
const BANDS = [["Lobby", 0, 19], ["Mezzanine", 20, 44], ["Corner Office", 45, 71], ["Penthouse", 72, 91], ["Helipad", 92, 100]];
const bandOf = (f) => BANDS.findIndex(([, a, b]) => f >= a && f <= b);

// ---- matching (mirrors norm() in build_data.py)
const MAP = { "ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "ı": "i", "þ": "th", "ð": "d", "ß": "ss" };
const SUFFIX = /\s(inc|incorporated|ltd|limited|plc|llc|corp|corporation|co|company|ag|sa|se|nv|spa|gmbh|group|holdings|holding|ab|oyj|asa|bv)$/;
function norm(s) {
  s = s.toLowerCase().replace(/[øđłæœıþðß]/g, (c) => MAP[c]);
  s = s.normalize("NFKD").replace(/\p{M}/gu, "").replace(/&/g, " and ").replace(/[^\p{L}\p{N}]+/gu, " ").replace(/\s+/g, " ").trim();
  return s.replace(/^the /, "");
}

// ---- storage
const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (o) => { try { localStorage.setItem(STORE, JSON.stringify(o)); } catch { /* private mode */ } };

// ---- state
let data, world, needle, doors, S = 1;
let idx = 0, total = 0, floor = 0, phase = "loading", answers = [], maps = [];
let deadline = 0, leftMs = 0, raf = 0, SECS = 25, arrived = true, autoTimer = 0;
const stats = load();

// ---- layout
function fit() {
  const vv = window.visualViewport;
  const w = vv ? vv.width : innerWidth, h = vv ? vv.height : innerHeight;
  S = Math.max(0.62, Math.min(1.3, Math.min(w / 390, h / 844)));
  app.style.setProperty("--vh", h + "px");
  app.style.setProperty("--s", S.toFixed(4));
  // The gauge and the car stand as low as the open card allows, so the street meets the card and the sky gets the room.
  const sat = parseFloat(getComputedStyle(app).getPropertyValue("--sat")) || 0;
  const natural = sat + (44 + 232 + 156) * S, cardTop = card.getBoundingClientRect().top;
  const drop = Math.max(0, Math.min(h * 0.3, cardTop - 14 * S - natural));
  app.style.setProperty("--drop", drop.toFixed(1) + "px");
  world.layout(S, natural + drop - 8 * S, h, w);
}

// ---- odometer
const wheelH = () => parseFloat(getComputedStyle($("w-o").parentElement).getPropertyValue("--wh")) || 30;
function buildOdometer() {
  const fillStrip = (id, reps, maxDigit = 9) => { const s = $(id); for (let r = 0; r < reps; r++) for (let d = 0; d <= maxDigit; d++) { const sp = document.createElement("span"); sp.textContent = d; s.appendChild(sp); } };
  fillStrip("w-h", 1, 1); fillStrip("w-t", 2); fillStrip("w-o", 11);
}
function setOdometer(f) {
  const tr = (id, v) => { $(id).style.transform = `translateY(calc(var(--wh) * ${-v}))`; };
  tr("w-o", f); tr("w-t", Math.floor(f / 10) + Math.max(0, (f % 10) - 9)); tr("w-h", f >= 100 ? 1 : 0);
}

// ---- motion helpers
function setLiftMs(ms) { app.style.setProperty("--lift-ms", REDUCED ? "1ms" : ms + "ms"); }
function applyPalette(alt) { const p = paletteAt(alt); for (const k in p) app.style.setProperty(k, p[k]); }

function ascendTo(f, done) {
  const delta = Math.abs(f - floor);
  const ms = REDUCED ? 1 : Math.round(Math.min(2300, 1150 + delta * 60));
  setLiftMs(ms);
  floor = f;
  needle.to(f, ms, REDUCED);
  carScore([[0, 0], [130, 3, "out"], [300, -2, "inOut"], [520, 0, "inOut"]], 520);          // the car sinks on its cable, then is taken up
  setOdometer(f);
  world.setFloor(f, false);
  applyPalette(f / MAXF);
  world.setProgress(total / 700);
  world.setLitFloors(f);
  if (snd.isOn() && !REDUCED) { const n = Math.max(4, Math.round(delta / 2)); for (let i = 0; i < n; i++) setTimeout(() => snd.pass(i), (ms / n) * i * 0.85 + 80); }
  setTimeout(done, ms + 120);
}

// ---- the car's own movement inside the frame: authored offsets in px, never a CSS curve
let carStop = null;
function carScore(keys, dur, axis = "Y") {
  carStop?.();
  if (REDUCED) return;
  const el = $("car");
  carStop = play(score(keys), dur, (v) => { el.style.transform = `translate${axis}(${(v * S).toFixed(2)}px)`; }, () => { el.style.transform = ""; });
}

// ---- doors
function setDoors(open, ms = 0, onContact) { doors.doors(open, REDUCED ? 0 : ms, onContact); }

// ---- screens
function show(name) {
  card.dataset.screen = name;
  card.querySelectorAll(".screen").forEach((s) => { s.hidden = s.dataset.s !== name; });
  card.scrollTop = 0;
  app.dataset.phase = name;
  if (world) requestAnimationFrame(fit);
}
function pipsRender() {
  $("pips").innerHTML = "";
  for (let i = 0; i < data.prompts.length; i++) {
    const li = document.createElement("li");
    const a = answers[i];
    if (a) { li.className = a.tier >= 0 ? "done" : "miss"; if (a.tier >= 0) li.style.setProperty("--tc", `var(--t${a.tier})`); }
    else if (i === idx && (phase === "prompt" || phase === "result")) li.className = "now";
    li.setAttribute("aria-label", `Question ${i + 1}`);
    $("pips").appendChild(li);
  }
}
const noun = (t) => t.replace(/^Name an? /, "").replace(/^./, (c) => c.toUpperCase());
const pad = (n) => String(n).padStart(2, "0");
let toastT = 0;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2200); }

// ---- prompt phase
function startPrompt(i) {
  idx = i; phase = "prompt"; arrived = true;
  const p = data.prompts[i];
  show("prompt");
  $("q-count").textContent = `Question ${i + 1} of ${data.prompts.length}`;
  $("q-text").textContent = p.text;
  $("ans").value = ""; $("ride").classList.remove("ready");
  $("q-note").textContent = `${p.n} valid answers on file. Rare ones count more.`; $("q-note").classList.remove("bad");
  $("q-time").textContent = `0:${pad(SECS)}`; $("q-time").classList.remove("hot");
  doors.alarm.classList.remove("hot");
  pipsRender();
  setDoors(1, REDUCED ? 0 : 520);
  leftMs = SECS * 1000;
  deadline = performance.now() + leftMs + (REDUCED ? 0 : 520);
  cancelAnimationFrame(raf); raf = requestAnimationFrame(tick);
  $("ans").focus({ preventScroll: true });
}
function tick(now) {
  if (phase !== "prompt") return;
  leftMs = Math.max(0, deadline - now);
  const left = Math.min(SECS * 1000, leftMs) / 1000;
  const open = REDUCED ? Math.ceil(left) / SECS : left / SECS;
  setDoors(open);
  $("q-time").textContent = `0:${pad(Math.ceil(left))}`;
  const hot = left <= 6;
  $("q-time").classList.toggle("hot", hot);
  doors.alarm.classList.toggle("hot", hot);
  if (leftMs <= 0) return timeout();
  raf = requestAnimationFrame(tick);
}
document.addEventListener("visibilitychange", () => {
  if (phase !== "prompt") return;
  if (document.hidden) { cancelAnimationFrame(raf); leftMs = Math.max(0, deadline - performance.now()); }
  else { deadline = performance.now() + leftMs; raf = requestAnimationFrame(tick); }
});

function find(i, raw) {
  const m = maps[i], k = norm(raw);
  if (!k) return null;
  const hit = m.get(k) ?? m.get(k.replace(SUFFIX, ""));
  return hit === undefined ? null : hit;
}
function submit() {
  if (phase !== "prompt") return;
  const raw = $("ans").value.trim();
  const note = $("q-note");
  if (!raw) { nope("Type an answer first."); return; }
  const hit = find(idx, raw);
  if (hit === null) { nope(`Not on file for this prompt. Try another.`); return; }
  success(hit);
}
function nope(msg) {
  const slot = $("slot");
  slot.classList.remove("nope"); void slot.offsetWidth; slot.classList.add("nope");
  $("q-note").textContent = msg; $("q-note").classList.add("bad");
  snd.buzz();
  $("ans").select();
}

function resultCommon() {
  cancelAnimationFrame(raf);
  phase = "result";
  show("result");
  $("next").hidden = true;
  $("r-extra").hidden = true;
}
function success(entryIdx) {
  const p = data.prompts[idx], e = p.entries[entryIdx];
  const tier = e[2], pts = data.tiers[tier].pts;
  resultCommon();
  answers[idx] = { label: e[0], tier, pts, rank: entryIdx, n: p.entries.length };
  total += pts;
  const st = $("stamp");
  st.style.setProperty("--c", `var(--t${tier})`);
  $("st-tier").textContent = data.tiers[tier].name; $("st-pts").textContent = `+${pts}`;
  st.classList.remove("slam"); void st.offsetWidth; st.classList.add("slam");
  $("r-answer").textContent = e[0];
  const share = entryIdx / p.entries.length;
  $("r-rare").textContent = share < 0.03 ? `One of the best known of ${p.entries.length} answers on file.` : `Rarer than ${Math.round(share * 100)}% of the ${p.entries.length} answers on file.`;
  if (e[4]) { $("r-extra").hidden = false; $("r-extra").textContent = `In today’s Boardread: “${e[4]}”`; }
  snd.stamp();
  pipsRender();
  arrived = false;
  const F = Math.min(MAXF, Math.round(total / 7));
  setTimeout(() => { setDoors(0, 300, () => carScore([[0, 0], [40, 1.5, "out"], [120, 0, "inOut"]], 120, "X")); }, 120);
  setTimeout(() => { snd.thunk(); }, REDUCED ? 0 : 420);
  setTimeout(() => {
    ascendTo(F, () => {
      arrived = true;
      snd.ding(tier);
      carScore([[0, 0], [90, -4, "out"], [210, 2.5, "inOut"], [330, -1, "inOut"], [430, 0, "inOut"]], 430);   // arrival: over the sill, back, rest
      revealNext();
    });
  }, REDUCED ? 0 : 520);
}
function timeout() {
  const p = data.prompts[idx];
  resultCommon();
  answers[idx] = { label: null, tier: -1, pts: 0 };
  const st = $("stamp");
  st.style.setProperty("--c", "var(--muted)");
  $("st-tier").textContent = "Doors closed"; $("st-pts").textContent = "+0";
  st.classList.remove("slam"); void st.offsetWidth; st.classList.add("slam");
  $("r-answer").textContent = "The lift left without you.";
  $("r-rare").textContent = `Familiar answers: ${p.easy.join(", ")}.`;
  $("r-extra").hidden = false; $("r-extra").textContent = `Rarest on file: ${p.rare[0]}.`;
  setDoors(0, REDUCED ? 0 : 200);
  doors.alarm.classList.remove("hot");
  setTimeout(snd.thunk, 180);
  pipsRender();
  revealNext();
}
function revealNext() {
  const last = idx === data.prompts.length - 1;
  $("next").firstChild.textContent = last ? "See your floor" : "Next floor";
  $("next").hidden = false;
  $("next").focus({ preventScroll: true });
}
function next() {
  if (phase !== "result" || $("next").hidden) return;
  if (idx + 1 < data.prompts.length) startPrompt(idx + 1);
  else finish();
}

// ---- end
function finish() {
  phase = "end";
  const F = Math.min(MAXF, Math.round(total / 7));
  const rec = { floor: F, total, ans: answers.map((a) => [a.label, a.tier, a.pts]) };
  if (!stats.days) stats.days = {};
  if (!stats.days[data.date] || params.has("fresh")) {
    stats.played = (stats.played || 0) + 1;
    stats.sum = (stats.sum || 0) + F;
    stats.best = Math.max(stats.best || 0, F);
    const y = new Date(Date.parse(data.date + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
    stats.streak = stats.last === y ? (stats.streak || 0) + 1 : 1;
    stats.last = data.date;
    stats.days[data.date] = rec;
    save(stats);
  }
  renderEnd(rec);
}
function mini(rec) {
  const svg = $("mini"); svg.innerHTML = "";
  const NS = "http://www.w3.org/2000/svg";
  const el = (n, a, p = svg) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); p.appendChild(e); return e; };
  const base = 346, fh = 3.1, X = 60;
  const y = (f) => base - f * fh;
  const SEG = [[0, 70, 64], [70, 84, 54], [84, 93, 46], [93, 98, 38], [98, 100, 30]];
  const defs = el("defs", {});
  const lit = el("pattern", { id: "m-lit", width: 6, height: fh * 2, patternUnits: "userSpaceOnUse", y: base % (fh * 2) }, defs);
  el("rect", { x: 1.6, y: 0.7, width: 2.8, height: fh * 2 - 1.8, fill: "#ffd58a" }, lit);
  const dim = el("pattern", { id: "m-dim", width: 6, height: fh * 2, patternUnits: "userSpaceOnUse", y: base % (fh * 2) }, defs);
  el("rect", { x: 1.6, y: 0.7, width: 2.8, height: fh * 2 - 1.8, fill: "#4c6670", "fill-opacity": 0.55 }, dim);
  const clip = el("clipPath", { id: "m-clip" }, defs);
  for (const [a, b, w] of SEG) el("rect", { x: X - w / 2, y: y(b), width: w, height: (b - a) * fh + 1 }, clip);
  const bodyG = el("linearGradient", { id: "m-body", x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
  el("stop", { offset: "0", "stop-color": "#2d4650" }, bodyG); el("stop", { offset: "1", "stop-color": "#14222a" }, bodyG);
  el("ellipse", { cx: X, cy: base + 2, rx: 56, ry: 4, fill: "#000", "fill-opacity": 0.35 });
  for (const [a, b, w] of SEG) el("rect", { x: X - w / 2, y: y(b), width: w, height: (b - a) * fh + 1, fill: "url(#m-body)" });
  const g = el("g", { "clip-path": "url(#m-clip)" });
  el("rect", { x: 0, y: 0, width: 120, height: base, fill: "url(#m-dim)" }, g);
  el("rect", { x: 0, y: y(rec.floor), width: 120, height: base - y(rec.floor), fill: "url(#m-lit)" }, g);
  el("rect", { x: X - 30, y: y(100) - 4, width: 60, height: 4, fill: "#c7a25e" }, svg);
  el("rect", { x: X - 1, y: y(100) - 26, width: 2, height: 22, fill: "#c7a25e" }, svg);
  el("circle", { cx: X, cy: y(100) - 28, r: 2.2, fill: "#ff6a4a" }, svg);
  for (let n = 10; n < 100; n += 10) { const s = SEG.find(([a, b]) => n >= a && n < b); el("rect", { x: X - s[2] / 2 - 2, y: y(n) - 0.7, width: s[2] + 4, height: 1.4, fill: "#c7a25e", "fill-opacity": 0.6 }); }
  // your floor
  const fy = y(rec.floor);
  el("rect", { x: X - 40, y: fy - 0.9, width: 80, height: 1.8, fill: "#ecd49c" });
  const flag = el("text", { x: X - 44, y: fy + 4, "text-anchor": "end", style: "font:400 13px Limelight,serif;fill:#ecd49c" }); flag.textContent = String(rec.floor);
  // answers, cumulative
  let acc = 0; const marks = [];
  rec.ans.forEach((a, i) => { acc += a[2]; marks.push({ i, tier: a[1], y: y(Math.min(100, acc / 7)), ty: 0 }); });
  const sorted = [...marks].sort((a, b) => b.y - a.y); // lowest first
  let prev = Infinity;
  for (const m of sorted) { m.ty = Math.min(m.y, prev - 14); prev = m.ty; }
  for (const m of marks) {
    const c = m.tier < 0 ? "#6b7a7c" : `var(--t${m.tier})`;
    el("path", { d: `M${X + 36} ${m.y}L${X + 46} ${m.ty}`, stroke: c, "stroke-width": 1, fill: "none", "stroke-opacity": 0.8 });
    el("circle", { cx: X + 36, cy: m.y, r: 1.8, style: `fill:${c}` });
    el("circle", { cx: X + 52, cy: m.ty, r: 7.4, style: `fill:${c}` });
    const t = el("text", { x: X + 52, y: m.ty, "text-anchor": "middle", "dominant-baseline": "central", style: "font:600 10px Jost,sans-serif;fill:#0b1218" }); t.textContent = String(m.i + 1);
  }
}
function renderEnd(rec) {
  show("end");
  const F = rec.floor, b = bandOf(F);
  $("e-issue").textContent = `Topfloor No. ${data.no} · ${new Date(data.date + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}`;
  $("e-floor").textContent = `Floor ${F}`;
  $("e-tier").textContent = BANDS[b][0];
  $("e-tier").style.setProperty("--tier-c", `var(--t${b})`);
  const best = rec.ans.map((a, i) => ({ a, i })).filter((x) => x.a[1] >= 0).sort((x, y) => y.a[1] - x.a[1])[0];
  $("e-line").textContent = best ? `Best answer: ${best.a[0]}, ${data.tiers[best.a[1]].name}, +${best.a[2]}.` : "No answers landed. The building is still there tomorrow.";
  // list
  const ol = $("e-list"); ol.innerHTML = "";
  rec.ans.forEach((a, i) => {
    const p = data.prompts[i], li = document.createElement("li");
    li.style.setProperty("--tc", a[1] >= 0 ? `var(--t${a[1]})` : "#7c8a8b");
    const mk = (cls, txt) => { const s = document.createElement("span"); s.className = cls; s.textContent = txt; return s; };
    li.append(mk("n", String(i + 1)), mk("a", a[0] || "No answer"), mk("p", a[1] >= 0 ? `+${a[2]}` : "0"));
    const sub = document.createElement("span"); sub.className = "sub";
    sub.append(`${noun(p.text)} · `);
    if (a[1] >= 0) { const em = document.createElement("em"); em.textContent = data.tiers[a[1]].name; sub.append(em, " · "); }
    sub.append(`rarest on file: ${p.rare[0]}`);
    li.append(sub); ol.appendChild(li);
  });
  mini(rec);
  // stats
  const played = stats.played || 1;
  const sd = $("stats"); sd.innerHTML = "";
  for (const [k, v] of [["Played", played], ["Streak", stats.streak || 1], ["Best", stats.best ?? F], ["Average", Math.round((stats.sum ?? F) / played)]]) {
    const d = document.createElement("div"); const dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = k; dd.textContent = v; d.append(dt, dd); sd.appendChild(d);
  }
  // share
  $("share-text").textContent = shareText(rec);
  $("credit").textContent = data.credit;
  // dial and world for restored games
  if (floor !== F) { total = rec.total; floor = F; setLiftMs(1); applyPalette(F / MAXF); world.setFloor(F, true); world.setProgress(total / 700); world.setLitFloors(F); setOdometer(F); needle.set(F); }
  setDoors(0);
  answers = rec.ans.map((a) => ({ label: a[0], tier: a[1], pts: a[2] }));
  pipsRender();
  clearInterval(cdT); cdT = setInterval(countdown, 1000); countdown();
  requestAnimationFrame(() => $("e-floor").focus({ preventScroll: true }));
}
const shareText = (rec) => `Topfloor No. ${data.no}\nFloor ${rec.floor} of 100\n${rec.ans.map((a) => (a[1] >= 0 ? BARS[a[1]] : "·")).join("")}\nboardread.news/play/topfloor`;
let cdT = 0;
function countdown() {
  const now = new Date(), nx = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
  const s = Math.max(0, Math.floor((nx - now.getTime()) / 1000));
  $("countdown").textContent = `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}
async function share() {
  const text = $("share-text").textContent;
  try {
    if (navigator.share && matchMedia("(pointer: coarse)").matches) { await navigator.share({ text }); return; }
    await navigator.clipboard.writeText(text);
    toast("Copied. Paste it anywhere.");
  } catch {
    const r = document.createRange(); r.selectNodeContents($("share-text")); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    toast("Select and copy the text.");
  }
}

// ---- boot
async function boot() {
  try {
    const res = await fetch("assets/data/today.json", { cache: "no-cache" });
    data = await res.json();
  } catch (e) {
    $("card").innerHTML = '<p class="lede">Today’s building did not load. Reload to try again.</p>';
    app.dataset.phase = "intro"; return;
  }
  if (params.get("t")) SECS = Math.max(3, +params.get("t"));
  else SECS = data.seconds || 25;
  maps = data.prompts.map((p) => { const m = new Map(); p.entries.forEach((e, i) => e[3].forEach((k) => { if (!m.has(k)) m.set(k, i); })); return m; });

  world = createWorld($("world"));
  needle = buildDial($("dial-svg"), $("needle"));
  doors = buildCar($("car-art"), $("alarm"));
  buildOdometer();
  setDoors(0);
  applyPalette(0);
  world.setProgress(0); world.setLitFloors(0);
  setOdometer(0);
  fit();
  addEventListener("resize", fit);
  window.visualViewport?.addEventListener("resize", fit);
  document.fonts?.ready.then(fit);

  const d = new Date(data.date + "T12:00:00Z");
  $("issue").textContent = `No. ${data.no} · ${d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}`;
  if (stats.streak && stats.last) $("intro-fine").textContent = `Streak ${stats.streak}. Best floor ${stats.best}. Same building for everyone each UTC day.`;

  // sound toggle
  const sb = $("sound");
  const setSound = (on) => { const v = snd.setEnabled(on); sb.setAttribute("aria-pressed", v); sb.setAttribute("aria-label", v ? "Sound on" : "Sound off"); try { localStorage.setItem("topfloor:sound", v ? "1" : "0"); } catch { /* ignore */ } };
  sb.addEventListener("click", () => { setSound(!snd.isOn()); if (snd.isOn()) snd.ding(1); });

  // wiring
  $("start").addEventListener("click", () => { if (localStorage.getItem("topfloor:sound") === "1" && !snd.isOn()) setSound(true); startPrompt(0); });
  $("form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  $("ride").addEventListener("mousedown", (e) => e.preventDefault());
  $("ride").addEventListener("pointerdown", () => $("ride").classList.add("press"));
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) $("ride").addEventListener(ev, () => $("ride").classList.remove("press"));
  $("ans").addEventListener("input", () => {
    const slot = $("slot"); slot.classList.remove("tick", "nope"); void slot.offsetWidth; slot.classList.add("tick");
    $("ride").classList.toggle("ready", $("ans").value.trim().length > 0);
    if ($("q-note").classList.contains("bad")) { $("q-note").classList.remove("bad"); $("q-note").textContent = `${data.prompts[idx].n} valid answers on file. Rare ones count more.`; }
    snd.click();
  });
  $("next").addEventListener("click", next);
  $("share").addEventListener("click", share);
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && phase === "result" && !e.repeat) { e.preventDefault(); next(); } });

  const saved = stats.days?.[data.date];
  if (saved && !params.has("fresh")) { total = saved.total; phase = "end"; app.dataset.phase = "end"; renderEnd(saved); }
  else { phase = "intro"; show("intro"); pipsRender(); }
  requestAnimationFrame(() => requestAnimationFrame(() => { app.dataset.phase = card.dataset.screen; }));
  if (localStorage.getItem("topfloor:sound") === "1") $("sound").title = "Sound is on after your first tap";
  window.__tf = { get state() { return { idx, total, floor, phase, answers }; }, data, next, submit };
}
boot();
