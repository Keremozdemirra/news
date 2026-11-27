import { createRig, tiltFor, score as keyed, ease } from "./rig.js";
import * as snd from "./sound.js";

const $ = (id) => document.getElementById(id);
const app = $("app"), stage = $("stage"), panel = $("panel");
const params = new URLSearchParams(location.search);
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches || params.has("rm");
const STORE = "ftf:v1";
const IDLE = -2.2;     // sealed B is the lighter pan until it is weighed
const RANKS = [[0, "Apprentice"], [3, "Junior clerk"], [5, "Senior clerk"], [7, "Chief cashier"], [9, "Auditor"], [10, "Comptroller"]];
const pad = (n) => String(n).padStart(2, "0");

const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (o) => { try { localStorage.setItem(STORE, JSON.stringify(o)); } catch { /* private mode */ } };

let data, rig, S = 1, idx = 0, streak = 0, bestRun = 0, points = 0, phase = "loading", locked = true, results = [];
// R is the chain on the balance: the day's ten links, or a practice chain dealt link by link from the day's figures
let R = [], mode = "daily", dealt = null;
const stats = load();
const pa = $("pa"), pb = $("pb");

// ---------------------------------------------------------------- number display
const SYM = { usd: "$", eur: "€", gbp: "£" };
const UNITS = [[1e12, "tn"], [1e9, "bn"], [1e6, "m"], [1e3, "k"]];
function compact(v) {
  for (const [u, s] of UNITS) if (v >= u * 0.9995) { const x = v / u; return [x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2), s]; }
  return [String(Math.round(v)), ""];
}
function parts(kind, v) {
  v = Math.max(0, v);
  if (SYM[kind]) { const [n, u] = compact(v); return { cur: SYM[kind], num: n, u }; }
  if (kind === "people") return v >= 1e6 ? { num: compact(v)[0], u: "m" } : { num: Math.round(v).toLocaleString("en-US"), u: "" };
  if (kind === "pct") return { num: v < 10 ? v.toFixed(1) : String(Math.round(v)), u: "%", pct: true };
  return { num: String(Math.round(v)), u: "" };
}
const plain = (kind, v) => { const p = parts(kind, v); return `${p.cur || ""}${p.num}${p.pct ? p.u : p.u ? " " + p.u : ""}`; };
function setFig(fig, kind, v) {
  const p = parts(kind, v), key = JSON.stringify(p);
  if (fig.dataset.k === key) return false;
  fig.dataset.k = key; fig.className = "fig";
  let h = p.cur ? `<span class="cur">${p.cur}</span>` : "";
  for (const ch of p.num) h += /\d/.test(ch) ? `<span class="d">${ch}</span>` : `<span class="p">${ch}</span>`;
  if (p.u) h += p.pct ? `<span class="p" style="width:auto">%</span>` : `<span class="u">${p.u}</span>`;
  fig.innerHTML = h;
  return true;
}

// ---------------------------------------------------------------- copy
const KIND = { usd: "Annual revenue · USD", eur: "Annual revenue · EUR", gbp: "Annual revenue · GBP", people: "People", founded: "Year founded", pct: "Percentage" };
const SUBS = { founded: ["later", "earlier"] };
function srcLine(f) {
  const lab = f.src.name === "Wikidata" ? (f.kind === "founded" ? "Founded" : SYM[f.kind] ? `FY${f.year}` : `${f.year}`) : `${f.year}`;
  return `${lab} · <a href="${f.src.url}" target="_blank" rel="noopener">${f.src.name}</a>`;
}
function fillTicket(pl, f, hidden) {
  pl.querySelector(".subj").textContent = f.subject;
  pl.querySelector(".subj").classList.toggle("long", f.subject.split(/\s+/).some((w) => w.length > 12));
  pl.querySelector(".what").textContent = f.what;
  const fig = pl.querySelector(".fig");
  pl.querySelector(".head").textContent = f.headline || "";
  pl.querySelectorAll(".stamp,.tally,.coin").forEach((n) => n.remove());
  pl.querySelector(".tape")?.getAnimations().forEach((x) => x.cancel());   // the last round's torn tape must not stay torn
  pl.querySelectorAll("[hidden]").forEach((n) => { n.hidden = false; });
  if (hidden) { fig.dataset.k = ""; fig.className = "fig sealed"; fig.textContent = "0.00"; pl.classList.add("sealed-on"); pl.querySelector(".src").textContent = ""; }
  else { pl.classList.remove("sealed-on"); setFig(fig, f.kind, f.value); pl.querySelector(".src").innerHTML = srcLine(f); }
}
function seatTape() { const t = pb.querySelector(".tape"), fg = pb.querySelector(".fig"); t.style.top = fg.offsetTop + 3 + "px"; }
function relation(r) {
  const a = r.a.value, b = r.b.value;
  if (r.kind === "founded") { const d = Math.abs(b - a); return `${d} year${d === 1 ? "" : "s"} ${b > a ? "later" : "earlier"}`; }
  const hi = Math.max(a, b), lo = Math.min(a, b), word = b > a ? "higher" : "lower";
  if (hi / lo >= 2) { const x = hi / lo; return `${x.toFixed(x < 10 ? 1 : 0)}x ${word}`; }
  return `${Math.round(b > a ? (b / a - 1) * 100 : (1 - b / a) * 100)}% ${word}`;
}
const gapOf = (r) => (r.kind === "founded" ? Math.abs(r.b.value - r.a.value) / 40 : Math.log(Math.max(r.a.value, r.b.value) / Math.min(r.a.value, r.b.value)));

// ---------------------------------------------------------------- layout
function fit() {
  const vv = window.visualViewport, w = vv ? vv.width : innerWidth, h = vv ? vv.height : innerHeight;
  S = Math.max(0.7, Math.min(1.3, Math.min(w / 390, h / 700)));
  app.style.setProperty("--s", S.toFixed(4));
  app.style.setProperty("--H", (h / S).toFixed(1) + "px");
  requestAnimationFrame(relayout);
}
function relayout() { rig.layout(); seatTape(); }

function show(name) {
  for (const s of panel.querySelectorAll(".screen")) s.hidden = s.dataset.s !== name;
  panel.dataset.s = name;
  app.dataset.phase = name === "result" ? "play" : name;
  panel.scrollTop = 0;
  requestAnimationFrame(relayout);
}
function pipsRender() {
  const ol = $("pips"); ol.innerHTML = "";
  ol.hidden = mode !== "daily";
  for (let i = 0; i < data.rounds.length && mode === "daily"; i++) {
    const li = document.createElement("li"), r = results[i];
    li.className = r ? (r.ok ? "ok" : "no") : i === idx && (phase === "play" || phase === "result") ? "now" : "";
    li.setAttribute("aria-label", `Round ${i + 1}${r ? (r.ok ? ", right" : ", wrong") : ""}`);
    ol.appendChild(li);
  }
}
function hud() {
  $("streak").textContent = streak;
  $("score-l").textContent = mode === "daily" ? "Score" : "Best";
  $("score").textContent = mode === "daily" ? points : Math.max(stats.practice || 0, streak);
}
let toastT = 0;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2200); }

// ---------------------------------------------------------------- rounds
function equalize() { pa.style.height = pb.style.height = ""; const h = Math.max(pa.offsetHeight, pb.offsetHeight); pa.style.height = pb.style.height = h + "px"; }
function startRound(i) {
  const from = phase === "result" && i > 0 ? R[i - 1] : null;      // coming from a reveal: the chain moves on
  idx = i; phase = "play"; locked = false;
  const r = R[i];
  show("play");
  $("kind").textContent = (r.link === "turn" && i ? "New column · " : "") + (KIND[r.kind] || r.what);
  $("q").innerHTML = r.kind === "founded" ? "Was <em>B</em> founded later or earlier than <em>A</em>?" : "Is <em>B</em> higher or lower than <em>A</em>?";
  const sub = SUBS[r.kind] || ["more", "less"];
  $("ks-up").textContent = sub[0]; $("ks-down").textContent = sub[1];
  for (const k of [$("k-up"), $("k-down")]) { k.disabled = false; k.classList.remove("picked", "fade"); }
  const gapX = pb.getBoundingClientRect().left - pa.getBoundingClientRect().left;
  fillTicket(pa, r.a, false); fillTicket(pb, r.b, true);
  equalize(); seatTape();
  if (from && !RM) {
    // The link: the ticket just weighed crosses to pan A in six stepped frames (or turns over to its next column),
    // a sealed one is set down in B, and the beam comes back to rest with a small overshoot.
    const steps = { duration: 300, easing: "steps(6, end)" };
    if (r.link === "same") pa.animate({ translate: [`${gapX}px 0`, `${gapX * 0.5}px ${-14 * S}px`, "0 0"] }, steps);
    else pa.animate({ scale: ["1 1", "0.06 1", "1 1"] }, steps);
    pb.animate({ translate: [`0 ${-46 * S}px`, "0 0"], opacity: [0, 1] }, { duration: 200, delay: 160, easing: "steps(4, end)", fill: "backwards" });
    const t0 = rig.theta;
    rig.play(keyed([[0, t0], [300, IDLE - 1.4, "inOut"], [450, IDLE + 0.5, "inOut"], [580, IDLE, "inOut"]]), 580);
    setTimeout(() => rig.squash(pa), 300); setTimeout(() => rig.squash(pb), 360);
    snd.press();
  } else {
    rig.set(IDLE);
    requestAnimationFrame(() => { rig.squash(pa); setTimeout(() => rig.squash(pb), 70); });   // both tickets set down in the pans
  }
  pipsRender(); hud();
  $("q").focus({ preventScroll: true });
}

// ---------------------------------------------------------------- practice: a chain dealt from the day's figures, until a miss
const fair = (a, b) => {
  if (a.kind !== b.kind || a.k === b.k || (a.src.name === "Boardread") !== (b.src.name === "Boardread")) return false;
  if (a.kind === "founded") return Math.abs(a.value - b.value) >= data.rules.year_gap;
  const hi = Math.max(a.value, b.value), lo = Math.min(a.value, b.value);
  return lo > 0 && (hi - lo) / hi >= data.rules.gap && hi / lo <= (data.rules.ratio || 15) && Math.abs(a.year - b.year) <= data.rules.years_apart;
};
const draw = (list) => list[Math.floor(Math.random() * list.length)];
function deal() {
  const pool = data.pool || [];
  if (!R.length) {
    dealt = new Set();
    const firsts = pool.filter((a) => pool.some((b) => fair(a, b)));
    if (!firsts.length) return null;
    const a = draw(firsts), b = draw(pool.filter((x) => fair(a, x)));
    dealt.add(a.k); dealt.add(b.k);
    return { kind: a.kind, what: a.what, a, b, answer: b.value > a.value ? "higher" : "lower", link: "start" };
  }
  const last = R[R.length - 1].b;
  const same = pool.filter((x) => !dealt.has(x.k) && fair(last, x));
  const turns = pool.filter((a) => a.k === last.k && a.kind !== last.kind).flatMap((a) => pool.filter((x) => !dealt.has(x.k) && fair(a, x)).map((x) => [a, x]));
  let a = last, b, link = "same";
  if (same.length && (!turns.length || Math.random() < 0.72)) b = draw(same);
  else if (turns.length) { [a, b] = draw(turns); link = "turn"; }
  else return null;
  dealt.add(b.k);
  return { kind: a.kind, what: a.what, a, b, answer: b.value > a.value ? "higher" : "lower", link };
}
function startPractice() {
  mode = "practice"; R = []; results = []; streak = 0; points = 0; bestRun = 0;
  const first = deal();
  if (!first) { toast("Not enough figures today for a practice chain."); mode = "daily"; R = data.rounds; return; }
  R.push(first); phase = "intro"; startRound(0);
}
function backToDaily() {
  const saved = stats.days?.[data.date];
  mode = "daily"; R = data.rounds;
  if (saved) restore(saved); else location.reload();
}

// The reveal score. Anticipation, a count the beam follows, contact, overshoot, settle.
function pick(choice) {
  if (phase !== "play" || locked) return;
  locked = true; snd.press();
  const r = R[idx];
  $("k-up").disabled = $("k-down").disabled = true;
  (choice === "higher" ? $("k-up") : $("k-down")).classList.add("picked");
  (choice === "higher" ? $("k-down") : $("k-up")).classList.add("fade");
  const fig = pb.querySelector(".fig");
  const end = r.b.value, from = r.kind === "founded" ? end - 34 : 0, D = r.kind === "founded" ? 1100 : 1500;
  const fin = tiltFor(r.kind, end, r.a.value), sgn = Math.sign(fin) || 1, mag = Math.abs(fin);
  // tear the tape off in five stepped frames
  const tape = pb.querySelector(".tape");
  if (!RM) tape.animate([{ transform: "translate(0,0) rotate(0)", opacity: 1 }, { transform: "translate(24px,-6px) rotate(6deg)", opacity: 1, offset: 0.4 }, { transform: "translate(58px,-22px) rotate(14deg)", opacity: 0 }], { duration: 200, easing: "steps(5)", fill: "forwards" }).onfinish = () => pb.classList.remove("sealed-on");
  else pb.classList.remove("sealed-on");
  fig.className = "fig";
  const val = (t) => from + (end - from) * ease.outQ(Math.min(1, t / D));
  // beam: dip toward A (0-120 ms), then follow the running value, lagging a little; after contact, overshoot offsets
  const post = keyed([[0, -0.06 * mag - 0.6, "linear"], [110, 0.2 * mag + 1.0, "out"], [250, -0.08 * mag - 0.5, "inOut"], [390, 0.06 * mag + 0.3, "inOut"], [520, -0.02 * mag - 0.1, "inOut"], [650, 0, "inOut"]]);
  const dip = keyed([[0, IDLE], [120, IDLE - 1.6, "out"]]);
  const theta = (t) => {
    if (t >= D) return fin + sgn * post(t - D);
    const track = tiltFor(r.kind, val(t), r.a.value) * 0.94, w = ease.inOut(Math.min(1, t / 280));
    return dip(t) * (1 - w) + track * w;
  };
  let lastTick = 0, contact = false, stamped = false;
  const onFrame = (t) => {
    const v = val(t);
    if (setFig(fig, r.b.kind, v) && t - lastTick > 55 && t < D) { snd.tick(t / D); lastTick = t; }
    if (t >= D && !contact) { contact = true; rig.squash(pb); (choice === r.answer ? snd.ding(streak + 1) : snd.thud()); }
    if (t >= D + 190 && !stamped) { stamped = true; stamp(choice === r.answer); }
  };
  const done = () => { setFig(fig, r.b.kind, end); pb.querySelector(".src").innerHTML = srcLine(r.b); if (!stamped) { stamped = true; stamp(choice === r.answer); } setTimeout(() => settle(choice), RM ? 0 : 380); };
  if (RM) { setFig(fig, r.b.kind, end); rig.set(fin); done(); return; }
  rig.play(theta, D + 650, done, onFrame);
}

function stamp(ok) {
  const s = document.createElement("div"); s.className = "stamp " + (ok ? "right" : "wrong"); s.textContent = ok ? "Right" : "Wrong"; pb.appendChild(s);
  if (!RM) s.animate([{ transform: "translate(-50%,-50%) rotate(-3deg) scale(1.7)", opacity: 0 }, { transform: "translate(-50%,-50%) rotate(-9deg) scale(1)", opacity: 1, offset: 0.55 }, { transform: "translate(-50%,-50%) rotate(-9deg) scale(1.04)", offset: 0.75 }, { transform: "translate(-50%,-50%) rotate(-9deg) scale(1)" }], { duration: 160, easing: "steps(8)", fill: "forwards" });
  if (ok) coins();
}
function coins() {
  if (RM) return;
  const w = pb.offsetWidth, h = pb.offsetHeight;
  for (let i = 0; i < 9; i++) {
    const c = document.createElement("i"); c.className = "coin"; c.style.left = w / 2 + "px"; c.style.top = h - 4 + "px"; pb.appendChild(c);
    const dx = (Math.random() - 0.5) * 110, up = 60 + Math.random() * 60;
    c.animate([{ transform: "translate(0,0)", opacity: 1 }, { transform: `translate(${dx * 0.5}px,${-up}px)`, opacity: 1, offset: 0.4 }, { transform: `translate(${dx}px,${40}px)`, opacity: 0 }], { duration: 700 + Math.random() * 250, easing: "cubic-bezier(.3,.6,.5,1)" }).onfinish = () => c.remove();
  }
}

function settle(choice) {
  const r = R[idx], ok = choice === r.answer;
  if (ok) { streak++; bestRun = Math.max(bestRun, streak); } else if (mode === "daily") streak = 0;
  const pts = ok ? streak : 0;
  points += pts;
  results[idx] = { ok, pick: choice, pts, gap: gapOf(r) };
  phase = "result"; show("result");
  panel.querySelector(".verdict").classList.toggle("miss", !ok);
  const line = `${r.b.subject}: ${plain(r.b.kind, r.b.value)}, ${relation(r)} than ${r.a.subject}.`;
  $("back").hidden = true;
  if (mode === "practice") {
    let more = null;
    if (ok) { more = deal(); if (more) R.push(more); }
    const over = !ok || !more;
    if (over && streak > (stats.practice || 0)) { stats.practice = streak; save(stats); }
    $("v-word").textContent = !ok ? `Chain broken at ${streak}` : more ? `Right, chain of ${streak}` : `Ledger emptied at ${streak}`;
    $("v-pts").textContent = over ? `Best ${stats.practice || 0}` : "";
    $("v-line").textContent = line;
    $("next-label").textContent = over ? "New practice chain" : "Next link";
    $("back").hidden = !over;
    hud(); $("next").focus({ preventScroll: true });
    return;
  }
  $("v-word").textContent = ok ? (streak >= 3 ? `Right, chain of ${streak}` : "Right call") : "Missed it, chain broken";
  $("v-pts").textContent = ok ? `+${pts}` : "+0";
  $("v-line").textContent = line;
  $("next-label").textContent = idx === R.length - 1 ? "See your result" : "Next link";
  progress(false);
  pipsRender(); hud();
  $("next").focus({ preventScroll: true });
}
let nextAt = 0;
function next() {
  if (phase !== "result" || performance.now() < nextAt) return;
  nextAt = performance.now() + 350;               // a double tap or a held Enter moves one link, not two
  if (mode === "practice") { if ($("back").hidden) startRound(idx + 1); else startPractice(); return; }
  if (idx + 1 < R.length) startRound(idx + 1); else finish();
}

// ---------------------------------------------------------------- end
const rankOf = (c) => RANKS.filter(([n]) => c >= n).pop()[1];
const record = (done) => ({ sig: data.sig, done, score: points, run: bestRun, res: results.map((r) => [r.ok ? 1 : 0, r.pick, r.pts, +r.gap.toFixed(4)]) });
// every answered link is saved at once, so a reload resumes the chain instead of dealing the same sealed figure again
function progress(done) {
  if (!stats.days) stats.days = {};
  const had = stats.days[data.date], counted = had && had.counted;
  stats.days[data.date] = { ...record(done), counted: !!counted };
  for (const d of Object.keys(stats.days).sort().slice(0, -60)) delete stats.days[d];     // two months of days is plenty
  save(stats);
}
function finish() {
  const correct = results.filter((r) => r.ok).length;
  const had = stats.days?.[data.date];
  progress(true);
  if (!had || !had.counted) {
    stats.played = (stats.played || 0) + 1;
    stats.sumCorrect = (stats.sumCorrect || 0) + correct;
    stats.best = Math.max(stats.best || 0, points);
    const y = new Date(Date.parse(data.date + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
    stats.streak = stats.last === y ? (stats.streak || 0) + 1 : stats.last === data.date ? (stats.streak || 1) : 1;
    stats.last = data.date;
    stats.days[data.date].counted = true;
    save(stats);
  }
  renderEnd(stats.days[data.date]);
}
function restore(saved) {
  mode = "daily"; R = data.rounds;
  points = saved.score; bestRun = saved.run;
  results = saved.res.map((r) => ({ ok: !!r[0], pick: r[1], pts: r[2], gap: r[3] }));
  streak = 0; for (let i = results.length - 1; i >= 0 && results[i].ok; i--) streak++;
  if (saved.done === false && results.length < R.length) { phase = "intro"; startRound(results.length); }
  else renderEnd(saved);
}
function link(f, text) { const a = document.createElement("a"); a.href = f.src.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = text; return a; }
function tally(n) {
  const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"); svg.setAttribute("class", "tally");
  const groups = Math.ceil(n / 5) || 1; svg.setAttribute("viewBox", `0 0 ${groups * 40} 26`); svg.setAttribute("width", groups * 40); svg.setAttribute("height", 26);
  for (let g = 0; g < groups; g++) {
    const c = Math.min(5, n - g * 5);
    for (let i = 0; i < Math.min(4, c); i++) { const l = document.createElementNS(NS, "line"); l.setAttribute("x1", g * 40 + 4 + i * 7); l.setAttribute("x2", g * 40 + 4 + i * 7); l.setAttribute("y1", 2); l.setAttribute("y2", 24); svg.appendChild(l); }
    if (c === 5) { const l = document.createElementNS(NS, "line"); l.setAttribute("x1", g * 40 + 1); l.setAttribute("x2", g * 40 + 31); l.setAttribute("y1", 21); l.setAttribute("y2", 5); svg.appendChild(l); }
  }
  return svg;
}
function renderEnd(rec) {
  phase = "end"; show("end");
  const res = rec.res, correct = res.filter((r) => r[0]).length, rounds = data.rounds, miss = rounds.length - correct;
  $("e-issue").textContent = `Face the Figure No. ${data.no} · ${new Date(data.date + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}`;
  $("e-score").innerHTML = `${correct}<small>/${rounds.length}</small>`;
  $("e-rank").textContent = rankOf(correct);
  $("e-line").textContent = correct ? `Score ${rec.score} of ${rounds.length * (rounds.length + 1) / 2}. Longest chain ${rec.run}.` : "No call landed.";
  const mk = (cls, txt) => { const s = document.createElement("span"); s.className = cls; s.textContent = txt; return s; };
  const best = res.map((r, i) => ({ r, i })).filter((x) => x.r[0] && rounds[x.i]).sort((x, y) => x.r[3] - y.r[3]).slice(0, 3);
  const ob = $("e-best"); ob.innerHTML = "";
  best.forEach(({ r, i }) => {
    const q = rounds[i];
    const li = document.createElement("li");
    li.append(mk("n", String(i + 1)), mk("a", `${q.a.subject} vs ${q.b.subject}`), mk("p", `+${r[2]}`));
    const sub = document.createElement("span"); sub.className = "sub"; sub.append(`B was ${relation(q)}. `, link(q.a, "Source A"), " · ", link(q.b, "Source B")); li.append(sub); ob.appendChild(li);
  });
  ob.hidden = !best.length;
  const ol = $("e-rows"); ol.innerHTML = "";
  res.forEach((r, i) => {
    const q = rounds[i]; if (!q) return;
    const li = document.createElement("li"); li.className = r[0] ? "ok" : "no";
    li.append(mk("n", String(i + 1)), mk("a", `${q.a.subject} → ${q.b.subject}`), mk("p", r[0] ? `+${r[2]}` : "0"));
    const sub = document.createElement("span"); sub.className = "sub";
    sub.append(`${plain(q.a.kind, q.a.value)} vs ${plain(q.b.kind, q.b.value)} · you said ${r[1]} · `, link(q.a, "A"), " · ", link(q.b, "B")); li.append(sub); ol.appendChild(li);
  });
  const played = stats.played || 1, sd = $("stats"); sd.innerHTML = "";
  for (const [k, v] of [["Played", played], ["Day streak", stats.streak || 1], ["Best score", stats.best ?? rec.score], ["Avg right", ((stats.sumCorrect ?? correct) / played).toFixed(1)]]) {
    const d = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = k; dd.textContent = v; d.append(dd, dt); sd.appendChild(d);
  }
  $("share-text").textContent = `Face the Figure No. ${data.no}\n${correct}/${rounds.length} · chain ${rec.run} · ${rec.score} pts\n${res.map((r) => (r[0] ? "■" : "□")).join("")}\nboardread.news/play/face-the-figure`;
  $("credit").textContent = data.credit;
  // the tickets become two tallies on the pans: misses weigh down A, right calls weigh down B
  for (const [pl, n, name, what] of [[pa, miss, "Missed", "Calls that slipped"], [pb, correct, "Called it", "Right calls"]]) {
    fillTicket(pl, { subject: name, what, kind: "count", value: n, year: 0, src: { name: "", url: "" } }, false);
    pl.querySelector(".src").textContent = ""; pl.querySelector(".head").textContent = ""; pl.classList.remove("sealed-on");
    pl.append(tally(n));
  }
  equalize();
  const fin = 11 * Math.tanh((correct - miss) / 4);
  pipsRender(); hud();
  clearInterval(cdT); cdT = setInterval(countdown, 1000); countdown();
  requestAnimationFrame(() => { relayout(); rig.play(keyed([[0, IDLE], [250, IDLE - 1.2, "out"], [900, fin + Math.sign(fin) * (0.2 * Math.abs(fin) + 1), "inOut"], [1150, fin - Math.sign(fin) * 0.07 * Math.abs(fin), "inOut"], [1400, fin, "inOut"]]), 1400); $("e-score").focus({ preventScroll: true }); });
}
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
    toast("Copied.");
  } catch {
    const r = document.createRange(); r.selectNodeContents($("share-text")); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    toast("Select and copy the text.");
  }
}

// ---------------------------------------------------------------- boot
async function boot() {
  try { data = await (await fetch("assets/data/today.json", { cache: "no-cache" })).json(); }
  catch { panel.innerHTML = '<p class="lede">Today’s figures did not load. Reload to try again.</p>'; app.dataset.phase = "intro"; return; }
  rig = createRig({ zone: $("scale"), back: $("art-back"), front: $("art-front"), plate: $("art-plate"), pa, pb, reduced: RM });
  try { await rig.load("assets/art/"); } catch { toast("The balance art did not load."); }
  fit();
  addEventListener("resize", fit);
  window.visualViewport?.addEventListener("resize", fit);
  document.fonts?.ready.then(() => { equalize(); relayout(); });

  $("issue").textContent = `No. ${data.no} · ${new Date(data.date + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}`;
  if (stats.streak && stats.last) $("intro-fine").textContent = `Day streak ${stats.streak}. Best score ${stats.best}.`;

  const sb = $("sound");
  const setSound = (on) => { const v = snd.setEnabled(on); sb.setAttribute("aria-pressed", v); sb.setAttribute("aria-label", v ? "Sound on" : "Sound off"); try { localStorage.setItem("ftf:sound", v ? "1" : "0"); } catch { /* ignore */ } };
  sb.addEventListener("click", () => { setSound(!snd.isOn()); if (snd.isOn()) snd.ding(2); });

  R = data.rounds;
  $("start").addEventListener("click", () => { if (phase !== "intro") return; if (localStorage.getItem("ftf:sound") === "1" && !snd.isOn()) setSound(true); startRound(0); });
  $("practice").addEventListener("click", startPractice);
  $("back").addEventListener("click", backToDaily);
  $("k-up").addEventListener("click", () => pick("higher"));
  $("k-down").addEventListener("click", () => pick("lower"));
  $("next").addEventListener("click", next);
  $("share").addEventListener("click", share);
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (phase === "play" && !locked && !e.repeat) {
      if (k === "arrowup" || k === "h" || k === "1") { e.preventDefault(); pick("higher"); }
      else if (k === "arrowdown" || k === "l" || k === "2") { e.preventDefault(); pick("lower"); }
    } else if (phase === "result" && !e.repeat && k === "enter" && !["BUTTON", "A"].includes(document.activeElement?.tagName)) { e.preventDefault(); next(); }
  });

  const saved = stats.days?.[data.date];
  fillTicket(pa, data.rounds[0].a, false); fillTicket(pb, data.rounds[0].b, true);
  equalize(); seatTape(); rig.set(IDLE);
  // a record from before today's chain was dealt (another build of the day) does not fit these rounds: play again
  if (saved && !params.has("fresh") && (saved.sig || "") === (data.sig || "")) restore(saved);
  else { phase = "intro"; show("intro"); pipsRender(); hud(); }
  requestAnimationFrame(() => requestAnimationFrame(() => { app.dataset.phase = panel.dataset.s === "play" || panel.dataset.s === "result" ? "play" : panel.dataset.s; relayout(); }));
  window.__ff = { get state() { return { idx, streak, points, phase, results, mode, R }; }, data, pick, next, startRound, startPractice };
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
