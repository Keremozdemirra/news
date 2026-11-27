import { rankOf } from "./rank.js";
import * as snd from "./sound.js";

// Face the Figure. Two figures side by side; the one on the right is sealed until the call. The reveal is the one
// moment that moves: the seal turns over and the figure counts up in tabular numerals. Everything else is set at once.
const $ = (id) => document.getElementById(id);
const app = $("app"), panel = $("panel");
const params = new URLSearchParams(location.search);
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches || params.has("rm");
const STORE = "ftf:v1";
const EASE = "cubic-bezier(0.23, 1, 0.32, 1)";
const COUNT = 520;      // ms the sealed figure takes to count up
const pad = (n) => String(n).padStart(2, "0");

const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (o) => { try { localStorage.setItem(STORE, JSON.stringify(o)); } catch { /* private mode */ } };

let data, idx = 0, streak = 0, bestRun = 0, points = 0, phase = "loading", locked = true, results = [];
// R is the chain in play: the day's links, or a practice chain dealt link by link from the day's figures
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
  fig.dataset.k = key; fig.className = "fig num";
  const len = (p.cur ? 1 : 0) + p.num.length + (p.u ? 1 : 0);      // a long figure is set smaller so it stays inside its column
  fig.dataset.len = len >= 8 ? "xl" : len >= 6 ? "l" : "";
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
  const lab = f.src.name === "Wikidata" ? (f.kind === "founded" ? "" : SYM[f.kind] ? `FY${f.year} · ` : `${f.year} · `) : `${f.year} · `;
  return `${lab}<a href="${f.src.url}" target="_blank" rel="noopener">${f.src.name}</a>`;
}
function fill(card, f, sealed) {
  card.querySelector(".subj").textContent = f.subject;
  card.querySelector(".what").textContent = f.headline || f.what;
  const fig = card.querySelector(".fig");
  fig.dataset.k = ""; fig.dataset.len = "";
  card.classList.toggle("sealed", sealed);
  if (sealed) { fig.textContent = "?"; fig.className = "fig num"; card.querySelector(".src").textContent = ""; }
  else { setFig(fig, f.kind, f.value); card.querySelector(".src").innerHTML = srcLine(f); }
}
// The weighing: each figure has a bar. Until the call they say nothing (A at a neutral length, B empty); at the reveal
// both run to their true proportion, the larger one filling its column.
const REST = 0.6;
function shares(r) {
  const a = r.a.value, b = r.b.value, hi = Math.max(a, b);
  if (r.kind === "founded") { const lo = Math.min(a, b) - Math.max(8, Math.abs(a - b)); return [(a - lo) / (hi - lo), (b - lo) / (hi - lo)]; }
  return [Math.max(0.03, a / hi), Math.max(0.03, b / hi)];
}
function bars(wa, wb, ms) {
  [[pa, wa], [pb, wb]].forEach(([card, w]) => {
    const el = card.querySelector(".bar i"), to = `scaleX(${w.toFixed(4)})`;
    if (ms && !RM && el.animate) el.animate([{ transform: el.style.transform || "scaleX(0)" }, { transform: to }], { duration: ms, easing: EASE });
    el.style.transform = to;
  });
}
function relation(r) {
  const a = r.a.value, b = r.b.value;
  if (r.kind === "founded") { const d = Math.abs(b - a); return `${d} year${d === 1 ? "" : "s"} ${b > a ? "later" : "earlier"}`; }
  const hi = Math.max(a, b), lo = Math.min(a, b), word = b > a ? "higher" : "lower";
  if (hi / lo >= 2) { const x = hi / lo; return `${x.toFixed(x < 10 ? 1 : 0)}x ${word}`; }
  return `${Math.round(b > a ? (b / a - 1) * 100 : (1 - b / a) * 100)}% ${word}`;
}
const gapOf = (r) => (r.kind === "founded" ? Math.abs(r.b.value - r.a.value) / 40 : Math.log(Math.max(r.a.value, r.b.value) / Math.min(r.a.value, r.b.value)));
const mk = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };

// ---------------------------------------------------------------- screens
function screen(name) {
  phase = name === "result" ? "result" : name;
  app.dataset.phase = name === "result" ? "play" : name;
  $("intro").hidden = name !== "intro"; $("end").hidden = name !== "end"; $("game").hidden = name === "end";
  panel.dataset.s = name;
  $("keys").hidden = name !== "play"; $("next").hidden = name !== "result";
}
function pipsRender() {
  const ol = $("pips"); ol.textContent = "";
  ol.hidden = mode !== "daily";
  for (let i = 0; i < data.rounds.length && mode === "daily"; i++) {
    const r = results[i], li = mk("li", r ? (r.ok ? "ok" : "no") : i === idx && phase !== "intro" ? "now" : "");
    li.setAttribute("aria-label", `Link ${i + 1}${r ? (r.ok ? ", right" : ", wrong") : ""}`);
    ol.appendChild(li);
  }
}
function hud() {
  $("streak").textContent = streak;
  $("score-l").textContent = mode === "daily" ? "Score" : "Best";
  $("score").textContent = mode === "daily" ? points : Math.max(stats.practice || 0, streak);
}
// the links already called, newest first: as many as the screen has room for
function linksRender() {
  const ol = $("links"); ol.textContent = "";
  for (let i = results.length - 1; i >= 0; i--) {
    const r = results[i], q = R[i]; if (!r || !q) continue;
    const li = mk("li", r.ok ? "ok" : "no");
    li.append(mk("span", "n num", String(i + 1)), mk("span", "a", `${q.a.subject} · ${q.b.subject}`), mk("span", "m", r.ok ? "Right" : "Wrong"), mk("span", "p num", r.ok ? `+${r.pts}` : "0"));
    ol.appendChild(li);
  }
}
let toastT = 0;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2200); }

// ---------------------------------------------------------------- rounds
function startRound(i) {
  const carried = phase === "result" && i > 0 && R[i].link !== "turn";      // the figure just revealed moves over to A
  idx = i; locked = false;
  const r = R[i];
  screen("play");
  $("kind").textContent = KIND[r.kind] || r.what;
  $("q").textContent = r.kind === "founded" ? `Was ${r.b.subject} founded later or earlier than ${r.a.subject}?` : `Is ${r.b.subject} higher or lower than ${r.a.subject}?`;
  const sub = SUBS[r.kind] || ["more", "less"];
  $("k-up").querySelector(".kl").textContent = r.kind === "founded" ? "Later" : "Higher";
  $("k-down").querySelector(".kl").textContent = r.kind === "founded" ? "Earlier" : "Lower";
  $("ks-up").textContent = r.kind === "founded" ? "higher" : sub[0]; $("ks-down").textContent = r.kind === "founded" ? "lower" : sub[1];
  for (const k of [$("k-up"), $("k-down")]) { k.disabled = false; k.classList.remove("picked", "fade"); }
  $("vtag").hidden = true; $("v-line").textContent = "";
  const shift = pb.getBoundingClientRect().left - pa.getBoundingClientRect().left;
  fill(pa, r.a, false); fill(pb, r.b, true);
  bars(REST, 0, 0);
  if (!RM && i > 0 && phase !== "intro") {
    pa.animate([{ transform: carried ? `translateX(${shift}px)` : "translateY(6px)", opacity: carried ? 1 : 0 }, { transform: "none", opacity: 1 }], { duration: 220, easing: EASE });
    pb.animate([{ transform: "translateY(6px)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 200, delay: 60, easing: EASE, fill: "backwards" });
  }
  pipsRender(); hud(); linksRender();
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

function pick(choice) {
  if (phase !== "play" || locked) return;
  locked = true; snd.press();
  const r = R[idx];
  $("k-up").disabled = $("k-down").disabled = true;
  (choice === "higher" ? $("k-up") : $("k-down")).classList.add("picked");
  (choice === "higher" ? $("k-down") : $("k-up")).classList.add("fade");
  const fig = pb.querySelector(".fig"), end = r.b.value, from = r.kind === "founded" ? end - 24 : end * 0.2;
  const land = () => { setFig(fig, r.b.kind, end); pb.querySelector(".src").innerHTML = srcLine(r.b); settle(choice); };
  const [wa, wb] = shares(r);
  if (RM || !fig.animate) { pb.classList.remove("sealed"); bars(wa, wb, 0); land(); return; }
  bars(wa, wb, COUNT + 220);
  // the seal closes to a line, opens as the figure, and the figure runs up to its value
  fig.animate([{ transform: "scaleY(1)" }, { transform: "scaleY(0.04)" }], { duration: 90, easing: "cubic-bezier(0.55, 0, 0.85, 0.3)" }).onfinish = () => {
    pb.classList.remove("sealed");
    setFig(fig, r.b.kind, from);
    fig.animate([{ transform: "scaleY(0.04)" }, { transform: "scaleY(1)" }], { duration: 130, easing: EASE });
    const t0 = performance.now(); let last = 0;
    const step = (now) => {
      const u = Math.min(1, (now - t0) / COUNT), e = 1 - Math.pow(1 - u, 3);
      if (setFig(fig, r.b.kind, from + (end - from) * e) && now - last > 55) { snd.tick(u); last = now; }
      if (u < 1) requestAnimationFrame(step); else land();
    };
    requestAnimationFrame(step);
  };
}

function settle(choice) {
  const r = R[idx], ok = choice === r.answer;
  if (ok) { streak++; bestRun = Math.max(bestRun, streak); snd.ding(streak); } else { if (mode === "daily") streak = 0; snd.thud(); }
  const pts = ok ? streak : 0;
  points += pts;
  results[idx] = { ok, pick: choice, pts, gap: gapOf(r) };
  screen("result");
  nextAt = performance.now() + 350;      // the button lands where the keys were: the tap that made the call must not also press it
  const tag = $("vtag"); tag.hidden = false; tag.textContent = ok ? "Right" : "Wrong"; tag.className = "verdict-tag " + (ok ? "ok" : "no");
  if (!RM) tag.animate([{ transform: "scale(1.25)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 160, easing: EASE });
  $("v-line").textContent = `${plain(r.b.kind, r.b.value)}: ${relation(r)} than ${r.a.subject}.` + (ok && mode === "daily" ? ` +${pts}` : "");
  $("back").hidden = true;
  if (mode === "practice") {
    let more = null;
    if (ok) { more = deal(); if (more) R.push(more); }
    const over = !ok || !more;
    if (over && streak > (stats.practice || 0)) { stats.practice = streak; save(stats); }
    if (over) $("v-line").textContent += !ok ? ` Chain ended at ${streak}.` : ` No figures left. Chain of ${streak}.`;
    $("next-label").textContent = over ? "New practice chain" : "Next";
    $("back").hidden = !over;
    hud(); linksRender(); $("next").focus({ preventScroll: true });
    return;
  }
  $("next-label").textContent = idx === R.length - 1 ? "See your result" : "Next";
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
function renderEnd(rec) {
  screen("end");
  const res = rec.res, correct = res.filter((r) => r[0]).length, rounds = data.rounds, when = new Date(data.date + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  $("e-issue").textContent = `Face the Figure No. ${data.no}`;
  $("e-date").textContent = when;
  $("e-score").innerHTML = `${correct}<small>/${rounds.length}</small>`;
  $("e-rank").textContent = rankOf(correct, rounds.length);
  $("e-line").textContent = correct ? `Score ${rec.score} of ${rounds.length * (rounds.length + 1) / 2}. Longest chain ${rec.run}.` : "No call landed.";
  const sq = $("squares"); sq.textContent = "";
  res.forEach((r, i) => { const s = mk("i", r[0] ? "ok" : "no"); s.style.setProperty("--i", i); sq.appendChild(s); });
  const best = res.map((r, i) => ({ r, i })).filter((x) => x.r[0] && rounds[x.i]).sort((x, y) => x.r[3] - y.r[3]).slice(0, 3);
  const ob = $("e-best"); ob.textContent = "";
  best.forEach(({ r, i }) => {
    const q = rounds[i], li = mk("li", "ok");
    li.append(mk("span", "n num", String(i + 1)), mk("span", "a", `${q.a.subject} · ${q.b.subject}`), mk("span", "p num", `+${r[2]}`));
    const sub = mk("span", "sub"); sub.append(`${relation(q)}. `, link(q.a, "Source A"), " · ", link(q.b, "Source B")); li.append(sub); ob.appendChild(li);
  });
  ob.parentElement.hidden = !best.length;
  const ol = $("e-rows"); ol.textContent = "";
  res.forEach((r, i) => {
    const q = rounds[i]; if (!q) return;
    const li = mk("li", r[0] ? "ok" : "no");
    li.append(mk("span", "n num", String(i + 1)), mk("span", "a", `${q.a.subject} · ${q.b.subject}`), mk("span", "p num", r[0] ? `+${r[2]}` : "0"));
    const sub = mk("span", "sub");
    sub.append(`${plain(q.a.kind, q.a.value)} and ${plain(q.b.kind, q.b.value)}. You said ${r[1]}. `, link(q.a, "A"), " · ", link(q.b, "B")); li.append(sub); ol.appendChild(li);
  });
  const played = stats.played || 1, sd = $("stats"); sd.textContent = "";
  for (const [k, v] of [["Played", played], ["Day streak", stats.streak || 1], ["Best score", stats.best ?? rec.score], ["Avg right", ((stats.sumCorrect ?? correct) / played).toFixed(1)]]) {
    const d = mk("div"); d.append(mk("dd", "num", String(v)), mk("dt", "", k)); sd.appendChild(d);
  }
  $("share-text").textContent = `Face the Figure No. ${data.no}\n${correct}/${rounds.length} · chain ${rec.run} · ${rec.score} pts\n${res.map((r) => (r[0] ? "■" : "□")).join("")}\nhttps://boardread.news/play/face-the-figure/?utm_source=share`;
  $("credit").textContent = data.credit;
  clearInterval(cdT); cdT = setInterval(countdown, 1000); countdown();
  requestAnimationFrame(() => $("e-score").focus({ preventScroll: true }));
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
  } catch (e) {
    if (e && e.name === "AbortError") return;      // the share sheet was closed: nothing went wrong
    const r = document.createRange(); r.selectNodeContents($("share-text")); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    $("share-text").classList.add("open"); toast("Select and copy the text.");
  }
}

// ---------------------------------------------------------------- boot
async function boot() {
  try { data = await (await fetch("assets/data/today.json", { cache: "no-cache" })).json(); }
  catch { $("stage").innerHTML = '<p class="fail">Today’s figures did not load. Reload to try again.</p>'; app.dataset.phase = "play"; return; }

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
  fill(pa, data.rounds[0].a, false); fill(pb, data.rounds[0].b, true); bars(REST, 0, 0);
  // a record from before today's chain was dealt (another build of the day) does not fit these rounds: play again
  if (saved && !params.has("fresh") && (saved.sig || "") === (data.sig || "")) restore(saved);
  else { screen("intro"); pipsRender(); hud(); }
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
