import { comeBack, topArticle, said, contrast } from "./again.js";
import * as snd from "./sound.js";
import * as T from "./tower.js";
import { spring } from "./spring.js";

// Topfloor. Seven prompts on a clock; the rarer the answer, the more floors it is worth. The page is type on paper:
// a floor number, a five-band scale, the question and a list of what was answered. One thing moves per answer: the
// floor counts up and the mark slides along the scale. The clock is one compositor animation, not a frame loop.
const $ = (id) => document.getElementById(id);
const app = $("app"), card = $("card");
const params = new URLSearchParams(location.search);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const STORE = "topfloor:v1";
const MAXF = 100;
const EASE = "cubic-bezier(0.23, 1, 0.32, 1)";
const BARS = ["▁", "▃", "▅", "▇", "█"];
const BANDS = [["Lobby", 0, 19], ["Mezzanine", 20, 44], ["Corner Office", 45, 71], ["Penthouse", 72, 91], ["Helipad", 92, 100]];
const bandOf = (f) => BANDS.findIndex(([, a, b]) => f >= a && f <= b);
const GRACE = 1500;   // the prompt is read before the clock runs
let SECS = 25;

// ---- storage
const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (o) => { try { localStorage.setItem(STORE, JSON.stringify(o)); } catch { /* private mode */ } };

// ---- state
let data;
let idx = 0, total = 0, floor = 0, phase = "loading", answers = [];
const stats = load();

// ---- the answer lists, in a worker (js/lists.worker.js). info[i] = { n, rareTier } once a set of prompts is in.
let lists = null, askId = 0, info = [], ready = Promise.resolve();
const waiting = new Map();
function ask(msg) {
  return new Promise((res, rej) => { const id = ++askId; waiting.set(id, [res, rej]); lists.postMessage({ ...msg, id }); });
}
function loadLists(prompts) {
  if (!lists) {
    lists = new Worker(new URL("./lists.worker.js", import.meta.url), { type: "module" });
    lists.onmessage = ({ data: m }) => { const w = waiting.get(m.id); if (!w) return; waiting.delete(m.id); m.error ? w[1](new Error(m.error)) : w[0](m); };
    lists.onerror = () => { for (const [, rej] of waiting.values()) rej(new Error("lists worker")); waiting.clear(); };
  }
  const slim = prompts.map((p) => ({ list: p.list, entries: p.entries, generic: p.generic, rare: p.rare }));
  ready = ask({ t: "load", prompts: slim, rules: data.match, base: location.href }).then((m) => { info = m.info; });
  return ready;
}

const noun = (t) => t.replace(/^Name an? /, "").replace(/^./, (c) => c.toUpperCase());
const pad = (n) => String(n).padStart(2, "0");
// Wikidata writes some names (currencies above all) in lower case; on the page they are names.
const nice = (s) => (s && s === s.toLowerCase() ? s.replace(/^\p{L}/u, (c) => c.toUpperCase()) : s);
const mk = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
// the example of what scores high: a real entry with its own tier, never a claim about "the rarest"
function rareLine(p) {
  const t = info[data.prompts.indexOf(p)]?.rareTier;
  return `${t != null ? data.tiers[t].name : "Rare"} answer: ${nice(p.rare[0])}`;
}
let toastT = 0;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2200); }

// ---- the building. It is drawn once (js/tower.js) and only ever moved: the car keeps its place in the window and
// the tower slides past it on a spring. A second copy with lit windows shows through a mask that ends at the car, so
// the floors light as they are passed without a pixel being repainted. The floor counter rolls with the same value.
const CAR_AT = () => (matchMedia("(min-width: 900px)").matches ? 0.56 : 0.7);      // where the car rides in the window, from the top
let K = 1, ride = null, labels = [];
function buildTower() {
  $("strip").innerHTML = T.build(false);
  $("strip-lit").innerHTML = T.build(true);
  const odo = $("floor"); odo.textContent = "";
  for (let c = 0; c < 3; c++) { const col = mk("span", "col"), reel = mk("span", "reel"); for (let d = 0; d <= 10; d++) reel.appendChild(mk("span", "", String(d % 10))); col.appendChild(reel); odo.appendChild(col); }
  ride = spring(0, paint);
}
const tyOf = (f) => $("tower").clientHeight * CAR_AT() - (T.yTop(f) + T.U) * K;        // strip offset that puts floor f under the car
const floorAt = (ty) => 100 - (($("tower").clientHeight * CAR_AT() - ty) / K - T.U - T.TOP) / T.U;
let shownInt = -1;
function paint(ty) {
  const y = ty.toFixed(2), h = $("tower").clientHeight * CAR_AT();
  $("strip").style.transform = `translate3d(0, ${y}px, 0)`;
  $("strip-lit").style.transform = `translate3d(0, ${(ty - h).toFixed(2)}px, 0)`;
  odometer(Math.max(0, Math.min(MAXF, floorAt(ty))));
}
// a mechanical counter: the ones reel turns with the lift, each higher reel turns while the one below it passes nine
function odometer(v) {
  const cols = $("floor").children, ones = v % 10, tensRaw = Math.floor(v / 10) % 10, tens = tensRaw + Math.max(0, ones - 9), hund = Math.floor(v / 100) + (tensRaw === 9 ? Math.max(0, ones - 9) : 0);
  [hund, tens, ones].forEach((d, i) => { cols[i].firstChild.style.transform = `translate3d(0, ${(-d * 100 / 11).toFixed(3)}%, 0)`; });
  cols[0].classList.toggle("off", v < 99.5); cols[1].classList.toggle("off", v < 9.5);
  const n = Math.round(v);
  if (n !== shownInt) { if (shownInt >= 0 && ride && Math.abs(v - floor) > 0.5) snd.pass(n); shownInt = n; }
}
// the answers stand beside the floor the lift had reached with them, in their tier's colour, and the windows the
// lift passed on that answer are lit in it
const FILL = ["var(--out)", "var(--near)", "var(--near)", "var(--ok)", "var(--top)"];
let painted = [];
function labelFloors(fresh, windowsOnly) {
  const svg = $("strip").firstChild, lit = $("strip-lit").firstChild;
  const at = new Map(), want = []; let sum = 0, prev = 0;
  answers.forEach((a) => {
    if (!a || a.tier < 0) return;
    sum += a.pts; const f = Math.min(MAXF, Math.round(sum / 7));
    for (let n = prev; n < f; n++) want[n] = FILL[a.tier];
    prev = Math.max(prev, f);
    const had = at.get(f); at.set(f, { text: had ? `${had.text}, ${a.label}` : a.label, tier: Math.max(a.tier, had ? had.tier : 0) });
  });
  for (let n = 0; n < MAXF; n++) if (painted[n] !== want[n]) { for (const r of lit.querySelectorAll(".f" + n)) r.style.fill = want[n] || ""; painted[n] = want[n]; }
  if (windowsOnly) return;            // before a ride: the windows it is about to uncover take their colour first
  labels.forEach((l) => l.remove()); labels = [];
  for (const [f, { text, tier }] of at) {
    const hw = T.BANDS.find(([a, b]) => f >= a && f <= b)[2], y = T.yTop(f) + T.U;
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g"); g.setAttribute("class", "ans t" + tier);
    g.innerHTML = `<path d="M${T.AXIS + hw} ${y}H${T.AXIS + hw + 14}" stroke-width="1.5"/><text x="${T.AXIS + hw + 19}" y="${y + 4.5}"></text>`;
    g.lastChild.textContent = text.length > 22 ? text.slice(0, 21) + "…" : text;
    svg.appendChild(g); labels.push(g);
    if (fresh === f && !REDUCED) g.animate([{ opacity: 0, transform: "translateX(-6px)" }, { opacity: 1, transform: "none" }], { duration: 220, easing: EASE });
  }
}
function setFloor(f, animate, top) {
  floor = f;
  $("band").textContent = BANDS[bandOf(f)][0]; $("floor-sr").textContent = f;
  if (!animate || REDUCED) { ride.set(tyOf(f)); labelFloors(); return; }
  labelFloors(null, true);
  ride.to(tyOf(f), () => {
    labelFloors(f);
    // an answer as rare as they come: the building takes a second, smaller swing
    if (top) ride.kick(-150 * K);
  });
}
function screen(name) {
  app.dataset.phase = name;
  $("intro").hidden = name !== "intro"; $("end").hidden = name !== "end"; $("game").hidden = name === "end";
  if (name === "prompt" || name === "result") { card.dataset.screen = name; card.querySelectorAll(".screen").forEach((s) => { s.hidden = s.dataset.s !== name; }); }
}
// ---- the clock: the fuse is one animation the compositor runs; the page only rewrites the seconds
let fuseAnim = null, secT = 0, endT = 0, deadline = 0, leftMs = 0;
function clockStop() { clearInterval(secT); clearTimeout(endT); fuseAnim?.cancel(); fuseAnim = null; }
function clockRun(ms) {
  clearInterval(secT); clearTimeout(endT);
  leftMs = ms; deadline = performance.now() + ms;
  const run = Math.min(ms, SECS * 1000), wait = ms - run;
  fuseAnim?.cancel();
  if (!REDUCED) fuseAnim = $("fuse").animate([{ transform: `scaleX(${(run / (SECS * 1000)).toFixed(4)})` }, { transform: "scaleX(0)" }], { duration: run, delay: wait, easing: "linear", fill: "both" });
  const paint = () => { const s = Math.ceil(Math.min(SECS * 1000, Math.max(0, deadline - performance.now())) / 1000); $("q-time").textContent = `0:${pad(s)}`; $("q-time").classList.toggle("hot", s <= 5); };
  paint(); secT = setInterval(paint, 200);
  endT = setTimeout(onClock, ms);
}
function onClock() {
  if (phase !== "prompt") return;
  clockStop();
  // time is up on what is in the box: a valid answer typed in time is not thrown away for a missing Enter
  phase = "checking";
  find(idx, $("ans").value).then((hit) => (hit ? success(hit) : timeout()), () => timeout());
}
document.addEventListener("visibilitychange", () => {
  if (phase !== "prompt") return;
  if (document.hidden) { leftMs = Math.max(0, deadline - performance.now()); clearInterval(secT); clearTimeout(endT); fuseAnim?.pause(); }
  else clockRun(leftMs);
});

// ---- prompt
let promptAt = 0;
function startPrompt(i) {
  idx = i; phase = "prompt"; promptAt = performance.now();
  const p = data.prompts[i];
  screen("prompt");
  $("q-count").textContent = `Question ${i + 1} of ${data.prompts.length}`;
  $("q-text").textContent = p.text;
  $("ans").value = ""; $("ride").classList.remove("ready");
  $("q-note").textContent = `${(info[i]?.n ?? p.n).toLocaleString("en-US")} answers on file.`; $("q-note").classList.remove("bad");
  if (!REDUCED && i > 0) card.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 200, easing: EASE });
  clockRun(SECS * 1000 + GRACE);
  $("ans").focus({ preventScroll: true });
}
// the entry a typed answer means ({ rank, label, tier, extra }) or null; answered by the worker
async function find(i, raw) {
  return raw.trim() ? (await ask({ t: "find", i, raw })).hit : null;
}
let asking = false;
async function submit() {
  if (phase !== "prompt" || asking || performance.now() - promptAt < 400) return;     // a held Enter from the last card is not an answer
  const raw = $("ans").value.trim(), at = idx;
  if (!raw) { nope("Type an answer first."); return; }
  asking = true;
  let hit = null;
  try { hit = await find(at, raw); } catch { /* the worker died: the answer is treated as unknown */ } finally { asking = false; }
  if (phase !== "prompt" || idx !== at) return;                 // the clock ran out while the list was being read
  if (!hit) { missed(raw); nope("Not on file. Try another."); return; }
  success(hit);
}
// An answer we did not know stays on this device only (nothing is sent anywhere): the last 200, for the day's
// end screen and for anyone who wants to tell us what the lists are missing.
function missed(raw) {
  try {
    const log = JSON.parse(localStorage.getItem("topfloor:misses") || "[]");
    log.push({ d: data.date, p: data.prompts[idx].id, g: raw.slice(0, 80) });
    localStorage.setItem("topfloor:misses", JSON.stringify(log.slice(-200)));
  } catch { /* private mode */ }
}
function nope(msg) {
  if (!REDUCED) $("form").animate([{ transform: "translateX(0)" }, { transform: "translateX(-5px)" }, { transform: "translateX(5px)" }, { transform: "translateX(-3px)" }, { transform: "translateX(0)" }], { duration: 220, easing: "linear" });
  $("q-note").textContent = msg; $("q-note").classList.add("bad");
  $("form").classList.add("bad"); clearTimeout(nope.t); nope.t = setTimeout(() => $("form").classList.remove("bad"), 700);
  snd.buzz();
  $("ans").select();
}

// ---- result
function result(tierName, pts, tier) {
  clockStop();
  phase = "result";
  screen("result");
  $("r-extra").hidden = true;
  $("st-tier").textContent = tierName; $("st-pts").textContent = `+${pts}`;
  card.className = "q " + (tier >= 0 ? "t" + tier : "tx");
  [...$("lamps").children].forEach((l, i) => { l.className = i <= tier ? "on" : ""; l.style.setProperty("--i", i); });
  const last = idx === data.prompts.length - 1;
  $("next-label").textContent = last ? "See your floor" : "Next";
  nextAt = performance.now() + 350;
  if (!REDUCED) card.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 200, easing: EASE });
  $("next").focus({ preventScroll: true });
}
function success(hit) {
  const N = info[idx].n;
  const tier = hit.tier, pts = data.tiers[tier].pts;
  answers[idx] = { label: nice(hit.label), tier, pts, rank: hit.rank, n: N };
  total += pts;
  progress(false);
  result(data.tiers[tier].name, pts, tier);
  $("r-answer").textContent = nice(hit.label);
  // what the tier means in words; a percentile would mislead, because most of any list is names few people know
  const n = N.toLocaleString("en-US");
  $("r-rare").textContent = ["One of the best known answers.", "A familiar name.", "Past most people’s first thought.", "Few people would name it.", "As rare as answers get."][hit.rank / N < 0.03 ? 0 : Math.max(1, tier)];
  if (hit.extra) { $("r-extra").hidden = false; $("r-extra").textContent = `In today’s Boardread: “${hit.extra}”`; }
  snd.ding(tier);
  setFloor(Math.min(MAXF, Math.round(total / 7)), true, tier === 4);
}
function timeout() {
  const p = data.prompts[idx];
  answers[idx] = { label: null, tier: -1, pts: 0 };
  progress(false);
  result("Time", 0, -1);
  $("r-answer").textContent = "No answer";
  $("r-rare").textContent = `Familiar answers: ${p.easy.map(nice).join(", ")}.`;
  $("r-extra").hidden = false; $("r-extra").textContent = `${rareLine(p)}.`;
  snd.thunk();
}
let nextAt = 0;
function next() {
  if (phase !== "result" || performance.now() < nextAt) return;
  nextAt = performance.now() + 350;
  if (idx + 1 < data.prompts.length) startPrompt(idx + 1);
  else finish();
}

// ---- end
const sigOf = () => data.prompts.map((p) => p.id).join(",");
// Each answer is saved as it lands, so a reload picks the building up at the next question instead of starting over.
function progress(done) {
  if (practice) return;
  if (!stats.days) stats.days = {};
  const had = stats.days[data.date];
  stats.days[data.date] = { sig: sigOf(), done, floor: Math.min(MAXF, Math.round(total / 7)), total, ans: answers.filter(Boolean).map((a) => [a.label, a.tier, a.pts]), counted: !!(had && had.counted) };
  for (const d of Object.keys(stats.days).sort().slice(0, -60)) delete stats.days[d];
  save(stats);
}
function finish() {
  phase = "end";
  const F = Math.min(MAXF, Math.round(total / 7));
  if (practice) { renderEnd({ floor: F, total, ans: answers.map((a) => [a.label, a.tier, a.pts]) }); return; }
  const had = stats.days?.[data.date];
  progress(true);
  if (!had || !had.counted) {
    stats.played = (stats.played || 0) + 1;
    stats.sum = (stats.sum || 0) + F;
    stats.best = Math.max(stats.best || 0, F);
    const y = new Date(Date.parse(data.date + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
    stats.streak = stats.last === y ? (stats.streak || 0) + 1 : stats.last === data.date ? (stats.streak || 1) : 1;
    stats.last = data.date;
    stats.days[data.date].counted = true;
    save(stats);
  }
  renderEnd(stats.days[data.date]);
}

// ---- practice: seven prompts from the other lists, nothing written to the day's record
let practice = false, daily = null;
async function startPractice() {
  const btn = $("practice"); btn.disabled = true;
  try {
    daily = daily || data.prompts;
    const today = new Set(daily.map((p) => p.id));
    const mix = (l) => l.map((p) => [Math.random(), p]).sort((x, y) => x[0] - y[0]).map((x) => x[1]);
    const pick = [...mix((data.pool || []).filter((p) => !today.has(p.id))), ...mix((data.pool || []).filter((p) => today.has(p.id)))].slice(0, 7);
    if (pick.length < 7) { toast("No practice building today."); return; }
    const before = data.prompts;
    data.prompts = pick;
    try { await loadLists(pick); } catch (e) { data.prompts = before; loadLists(before).catch(() => {}); throw e; }
    practice = true;
    idx = 0; total = 0; answers = [];
    setFloor(0, false);
    clearInterval(cdT);
    startPrompt(0);
  } catch { toast("The practice lists did not load."); }
  finally { btn.disabled = false; }
}
function renderEnd(rec) {
  phase = "end"; clockStop(); screen("end");
  const F = rec.floor, b = bandOf(F);
  $("e-issue").textContent = practice ? "Practice building · not counted" : `Topfloor No. ${data.no}`;
  $("e-date").textContent = new Date(data.date + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  $("practice-label").textContent = practice ? "Another practice building" : "Practice building";
  $("to-daily").hidden = !practice; $("sharecard").hidden = practice;
  $("e-num").textContent = F;
  $("e-tier").textContent = BANDS[b][0];
  const best = rec.ans.map((a, i) => ({ a, i })).filter((x) => x.a[1] >= 0).sort((x, y) => y.a[1] - x.a[1])[0];
  $("e-line").textContent = best ? `Of 100. Best answer: ${best.a[0]}, ${data.tiers[best.a[1]].name}.` : "Nothing scored.";
  // the seven answers as seven columns, as tall as their tier: what the share text carries, drawn
  const bars = $("bars"); bars.textContent = "";
  rec.ans.forEach((a, i) => { const c = mk("i", a[1] >= 0 ? "t" + a[1] : "tx"); c.style.setProperty("--h", a[1] >= 0 ? (a[1] + 1) / 5 : 0); c.style.setProperty("--i", i); bars.appendChild(c); });
  const ol = $("e-list"); ol.textContent = "";
  rec.ans.forEach((a, i) => {
    const p = data.prompts[i], li = mk("li", a[1] >= 0 ? "t" + a[1] : "tx");
    li.append(mk("span", "n num", String(i + 1)), mk("span", "a", a[0] || "No answer"), mk("span", "p num", a[1] >= 0 ? `+${a[2]}` : "0"));
    const sub = mk("span", "sub");
    sub.append(noun(p.text));
    if (a[1] >= 0) sub.append(" · ", mk("b", "", data.tiers[a[1]].name));
    const rt = info[i]?.rareTier;
    if (rt == null || a[1] < rt) sub.append(` · ${rareLine(p)}`);        // no example for an answer already that high
    li.append(sub); ol.appendChild(li);
  });
  const played = stats.played || 1, sd = $("stats"); sd.textContent = "";
  for (const [k, v] of [["Played", played], ["Streak", stats.streak || 1], ["Best", stats.best ?? F], ["Average", Math.round((stats.sum ?? F) / played)]]) {
    const d = mk("div"); d.append(mk("dd", "num", String(v)), mk("dt", "", k)); sd.appendChild(d);
  }
  $("again").hidden = practice; $("e-top").hidden = true;
  if (!practice) comeBack({ streak: stats.streak || 1, label: "Day streak", played: new Set(Object.entries(stats.days || {}).filter(([, d]) => d.done !== false).map(([k]) => k)), today: data.date });
  topArticle();
  $("share-text").textContent = shareText(rec);
  $("credit").textContent = data.credit;
  let miss = [];
  try { miss = [...new Set(JSON.parse(localStorage.getItem("topfloor:misses") || "[]").filter((m) => m.d === data.date).map((m) => m.g))]; } catch { /* ignore */ }
  $("e-missed").hidden = !miss.length;
  $("e-missed").textContent = miss.length ? `Not on file: ${miss.slice(0, 8).join(", ")}.` : "";
  total = rec.total; floor = F;
  answers = rec.ans.map((a) => ({ label: a[0], tier: a[1], pts: a[2] }));
  clearInterval(cdT); cdT = setInterval(countdown, 1000); countdown();
  requestAnimationFrame(() => $("e-floor").focus({ preventScroll: true }));
}
const shareText = (rec) => `Topfloor No. ${data.no}\nFloor ${rec.floor} of 100\n${rec.ans.map((a) => (a[1] >= 0 ? BARS[a[1]] : "·")).join("")}\nhttps://boardread.news/play/topfloor/?utm_source=share`;
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
    said("share-label", "Copied");
  } catch (e) {
    if (e && e.name === "AbortError") return;      // the share sheet was closed: nothing went wrong
    $("share-text").classList.add("open");
    const r = document.createRange(); r.selectNodeContents($("share-text")); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    toast("Select and copy the text.");
  }
}

// ---- boot
function fit() {
  const vv = window.visualViewport;
  app.style.setProperty("--vh", (vv ? vv.height : innerHeight) + "px");
  // iOS does not resize the page for its keyboard: it scrolls the visual viewport. The app follows it down.
  app.style.transform = vv && vv.offsetTop ? `translateY(${vv.offsetTop}px)` : "";
  if (!data || !ride) return;
  // the drawing is scaled by its width: one floor is --fh pixels high
  K = parseFloat(getComputedStyle($("tower")).getPropertyValue("--fh")) / T.U;
  for (const el of [$("strip"), $("strip-lit")]) { el.style.width = T.VIEW[2] * K + "px"; el.style.height = T.HEIGHT * K + "px"; }
  $("lit").style.top = $("tower").clientHeight * CAR_AT() + "px";
  setFloor(floor, false);
}
async function boot() {
  try {
    const res = await fetch("assets/data/today.json", { cache: "no-cache" });
    data = await res.json();
  } catch (e) {
    $("stage").innerHTML = '<p class="fail">Today’s building did not load. Reload to try again.</p>';
    app.dataset.phase = "prompt"; return;
  }
  if (params.get("t")) SECS = Math.max(3, +params.get("t"));
  else SECS = data.seconds || 25;
  // each prompt's full answer list is its own file, read in a worker; a game waits for it
  loadLists(data.prompts).catch(() => {});
  contrast(app);
  buildTower();
  fit();
  addEventListener("resize", fit);
  window.visualViewport?.addEventListener("resize", fit);
  window.visualViewport?.addEventListener("scroll", fit);

  const d = new Date(data.date + "T12:00:00Z");
  $("issue").textContent = `No. ${data.no} · ${d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}`;
  if (stats.streak && stats.last) $("intro-fine").textContent = `Streak ${stats.streak}. Best floor ${stats.best}.`;

  const sb = $("sound");
  const setSound = (on) => { const v = snd.setEnabled(on); sb.setAttribute("aria-pressed", v); sb.setAttribute("aria-label", v ? "Sound on" : "Sound off"); try { localStorage.setItem("topfloor:sound", v ? "1" : "0"); } catch { /* ignore */ } };
  sb.addEventListener("click", () => { setSound(!snd.isOn()); if (snd.isOn()) snd.ding(1); });

  $("start").addEventListener("click", async () => {
    if (phase !== "intro") return;
    if (localStorage.getItem("topfloor:sound") === "1" && !snd.isOn()) setSound(true);
    phase = "opening";                      // the lists are usually in long before the first tap; if not, the tap waits for them
    try { await ready; } catch { phase = "intro"; toast("Today’s answer lists did not load. Reload to try again."); return; }
    startPrompt(0);
  });
  $("form").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  $("ride").addEventListener("mousedown", (e) => e.preventDefault());       // the tap must not take the keyboard down
  $("ans").addEventListener("input", () => {
    $("ride").classList.toggle("ready", $("ans").value.trim().length > 0);
    if ($("q-note").classList.contains("bad")) { $("q-note").classList.remove("bad"); $("q-note").textContent = `${(info[idx]?.n ?? data.prompts[idx].n).toLocaleString("en-US")} answers on file.`; }
    snd.click();
  });
  $("next").addEventListener("click", next);
  $("share").addEventListener("click", share);
  $("practice").addEventListener("click", startPractice);
  $("to-daily").addEventListener("click", () => location.assign(location.pathname));
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && phase === "result" && !e.repeat && document.activeElement !== $("next")) { e.preventDefault(); next(); } });

  const saved = stats.days?.[data.date];
  if (saved && !params.has("fresh") && (!saved.sig || saved.sig === sigOf())) {
    total = saved.total;
    if (saved.done === false && saved.ans.length < data.prompts.length) {
      // a day left half way: the lift waits at the floor it had reached, on the next question
      answers = saved.ans.map((a) => ({ label: a[0], tier: a[1], pts: a[2] }));
      setFloor(saved.floor, false);
      phase = "opening"; screen("prompt");
      ready.then(() => startPrompt(answers.length), () => toast("Today’s answer lists did not load. Reload to try again."));
    } else { phase = "end"; setFloor(saved.floor, false); ready.then(() => renderEnd(saved), () => renderEnd(saved)); }
  }
  else { phase = "intro"; screen("intro"); }
  window.__tf = { get state() { return { idx, total, floor, phase, answers }; }, get data() { return data; }, next, submit };
}
// The next day's puzzle goes up with the first site build after midnight UTC. A page left open over midnight, or
// opened in those first minutes, asks for it once a minute and loads it when it is there (never in mid-game).
function watchNextDay() {
  setInterval(async () => {
    if (document.hidden || new Date().toISOString().slice(0, 10) <= data.date || !(phase === "end" || phase === "intro")) return;
    try { const d = await (await fetch("assets/data/today.json", { cache: "no-store" })).json(); if (d.date > data.date) location.reload(); } catch { /* offline: try again next minute */ }
  }, 60000);
}
boot().then(watchNextDay);
