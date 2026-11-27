import { comeBack, topArticle, said, contrast } from "./again.js";
import { Tile, TURN } from "./flap.js";
import * as snd from "./sound.js";

const $ = (id) => document.getElementById(id);
const app = $("app");
const params = new URLSearchParams(location.search);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const STORE = "tickerflip:v1";
const ROWS = 6;
const SYM = { correct: "🟩", present: "🟨", absent: "⬛" };
const WORDS_IN = { correct: "right place", present: "in the word, wrong place", absent: "not in the word" };
const KEYS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
const pad = (n) => String(n).padStart(2, "0");
const wait = (ms) => new Promise((r) => setTimeout(r, REDUCED ? 0 : ms));

// ---- storage
const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (o) => { try { localStorage.setItem(STORE, JSON.stringify(o)); } catch { /* private mode */ } };

// ---- state
let data, answer = "", L = 5, valid = new Set();
let tiles = [], rowEls = [], keyEls = {}, ansTiles = [];
let guesses = [], cur = "", phase = "loading", busy = false, helpOpen = false, won = false;
let store = load();
let wordLists = [], extraNo = 0, daily = null;      // extraNo > 0: an extra board from today's news, not the counted one

// ---- scoring: two passes so repeated letters are counted once each
function score(guess, target) {
  const res = Array(guess.length).fill("absent"), left = {};
  for (let i = 0; i < guess.length; i++) {
    if (guess[i] === target[i]) res[i] = "correct";
    else left[target[i]] = (left[target[i]] || 0) + 1;
  }
  for (let i = 0; i < guess.length; i++) {
    if (res[i] === "correct") continue;
    if (left[guess[i]] > 0) { res[i] = "present"; left[guess[i]]--; }
  }
  return res;
}

// ---- build the board
function buildBoard() {
  const board = $("board");
  board.innerHTML = ""; tiles = []; rowEls = [];
  board.style.setProperty("--L", L);
  const ans = $("ans"); ans.style.setProperty("--L", L); ansTiles = [];
  for (let c = 0; c < L; c++) { const t = new Tile(REDUCED); t.el.removeAttribute("role"); ans.appendChild(t.el); ansTiles.push(t); }
  for (let r = 0; r < ROWS; r++) {
    const row = document.createElement("div");
    row.className = "row"; row.setAttribute("role", "row"); row.setAttribute("aria-label", `Guess ${r + 1}`);
    const rt = [];
    for (let c = 0; c < L; c++) { const t = new Tile(REDUCED); t.el.style.setProperty("--i", c); t.el.setAttribute("aria-label", `Row ${r + 1}, letter ${c + 1}, empty`); row.appendChild(t.el); rt.push(t); }
    board.appendChild(row); rowEls.push(row); tiles.push(rt);
  }
}
function buildKeyboard() {
  const kb = $("kb"); kb.innerHTML = ""; keyEls = {};
  KEYS.forEach((letters, i) => {
    const row = document.createElement("div"); row.className = "krow";
    // Enter is the last key of the bottom row, where a phone keyboard has it; delete sits at the left end
    if (i === 2) row.appendChild(mkKey("Backspace", "⌫", "wide", "Delete"));
    for (const ch of letters) { const k = mkKey(ch, ch); keyEls[ch] = k; row.appendChild(k); }
    if (i === 2) row.appendChild(mkKey("Enter", "Enter", "wide"));
    kb.appendChild(row);
  });
}
function mkKey(key, label, cls = "", aria) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "key " + cls; b.dataset.key = key; b.setAttribute("aria-label", aria || label);
  const s = document.createElement("span"); s.textContent = label; b.appendChild(s);
  const m = document.createElement("i"); m.className = "kmark"; m.setAttribute("aria-hidden", "true"); b.appendChild(m);
  return b;
}
function keyState(ch, st) {
  const k = keyEls[ch]; if (!k) return;
  const rank = { absent: 1, present: 2, correct: 3 };
  if ((rank[k.dataset.k] || 0) >= rank[st]) return;
  k.dataset.k = st;
  k.setAttribute("aria-label", `${ch}, ${WORDS_IN[st]}`);
}

// ---- how the board reads, on the start card
function legend() {
  const ul = document.createElement("ul"); ul.className = "legend";
  for (const [ch, st, txt] of [["S", "correct", "Right place"], ["T", "present", "In the word"], ["X", "absent", "Not in it"]]) {
    const li = document.createElement("li");
    const t = new Tile(true); t.set(ch, st); t.el.removeAttribute("role"); t.el.setAttribute("aria-hidden", "true");
    li.append(t.el, txt); ul.appendChild(li);
  }
  return ul;
}

// ---- helpers
let toastT = 0;
function say(msg, bad = false) {
  const m = $("msg"); m.textContent = msg; m.classList.toggle("bad", bad); m.classList.add("show");
  clearTimeout(toastT); toastT = setTimeout(() => m.classList.remove("show"), 2200);
}
const live = (t) => { $("live").textContent = ""; setTimeout(() => { $("live").textContent = t; }, 30); };
function setPhase(p) { phase = p; app.dataset.phase = p; }

function drawRowTyped(r) {
  for (let c = 0; c < L; c++) {
    const t = tiles[r][c], ch = cur[c] || "";
    if (t.letter !== ch) {
      t.flip(ch, ch ? "typed" : "empty", { steps: 1, quick: true });
      t.el.setAttribute("aria-label", `Row ${r + 1}, letter ${c + 1}, ${ch || "empty"}`);
    }
  }
}

// ---- input
function typeLetter(ch) {
  if (busy || phase !== "play" || cur.length >= L) return;
  cur += ch; snd.key();
  const r = guesses.length, c = cur.length - 1, t = tiles[r][c];
  t.flip(ch, "typed", { steps: 1, quick: true });
  t.el.setAttribute("aria-label", `Row ${r + 1}, letter ${c + 1}, ${ch}`);
}
function backspace() {
  if (busy || phase !== "play" || !cur.length) return;
  const r = guesses.length, c = cur.length - 1; cur = cur.slice(0, -1); snd.key();
  tiles[r][c].flip("", "empty", { steps: 1, quick: true });
  tiles[r][c].el.setAttribute("aria-label", `Row ${r + 1}, letter ${c + 1}, empty`);
}
function shake() {
  const row = rowEls[guesses.length]; row.classList.remove("shake"); void row.offsetWidth; if (!REDUCED) row.classList.add("shake"); row.classList.add("bad"); clearTimeout(row._bad); row._bad = setTimeout(() => row.classList.remove("bad"), 700);
  snd.buzz();
}
async function enter() {
  if (busy || phase !== "play") return;
  if (cur.length < L) { say(`Need ${L} letters.`, true); live(`Need ${L} letters.`); shake(); return; }
  const g = cur.toLowerCase();
  if (!valid.has(g)) {
    // kept on this device only, never sent: the words we refused, so the list can be checked against them
    try { const log = JSON.parse(localStorage.getItem("tickerflip:misses") || "[]"); log.push({ d: data.date, g }); localStorage.setItem("tickerflip:misses", JSON.stringify(log.slice(-200))); } catch { /* private mode */ }
  }
  if (!valid.has(g)) { say("Not in the word list.", true); live(`${cur} is not on the word list.`); shake(); return; }
  busy = true;
  const r = guesses.length, res = score(cur, answer);
  guesses.push(cur);
  await reveal(r, cur, res);
  cur = "";
  const win = res.every((x) => x === "correct");
  persistDay(win ? "won" : guesses.length >= ROWS ? "lost" : "play");
  if (win || guesses.length >= ROWS) { await finish(win, true); }
  else {
    if (guesses.length === 3) lightClue();
    busy = false;
  }
}
async function reveal(r, word, res, instant = false) {
  const row = tiles[r], announce = [];
  // Left to right, each card starting before the last has opened: the row is read in under a second.
  for (let i = 0; i < row.length; i++) {
    const t = row[i];
    if (instant || REDUCED) t.set(word[i], res[i]);
    else await t.flip(word[i], res[i], { onContact: () => { snd.clack(); t.el.dataset.done = "1"; keyState(word[i], res[i]); } });
    t.el.dataset.done = "1";
    t.el.setAttribute("aria-label", `Row ${r + 1}, letter ${i + 1}, ${word[i]}, ${WORDS_IN[res[i]]}`);
    keyState(word[i], res[i]);
  }
  if (!instant) {
    await wait(TURN);                       // the last card finishes opening before the next thing happens
    rowEls[r].dataset.done = "1";
    live(`Guess ${r + 1}, ${word}. ` + word.split("").map((ch, i) => `${ch} ${WORDS_IN[res[i]]}`).join("; ") + ".");
  } else rowEls[r].dataset.done = "1";
}
function lightClue() {
  $("clue").classList.add("on");
  $("clue-text").textContent = `Clue: ${data.clue}`;
  live(`Clue: ${data.clue}.`);
}

// ---- persistence of the day in progress
function persistDay(status) {
  if (extraNo) {      // an extra board only remembers that it was finished
    if (status !== "play") { store.extras = { d: data.date, done: [...new Set([...(store.extras?.d === data.date ? store.extras.done : []), extraNo])] }; save(store); }
    return;
  }
  store.days = store.days || {};
  store.days[data.date] = { g: guesses, s: status, L, sig: data.a };
  for (const d of Object.keys(store.days).sort().slice(0, -60)) delete store.days[d];
  save(store);
}

// ---- finish and stats
async function finish(win, animate) {
  won = win;
  setPhase("end"); busy = true;
  if (animate) await wait(250);
  if (win) {
    snd.bell(Math.max(2, 5 - guesses.length));
    if (!REDUCED && animate) { rowEls[guesses.length - 1].classList.add("ripple"); }
    $("app").classList.add("won");
  } else {
    snd.down();
    $("app").classList.add("lost");
    await showAnswerRow(!animate);
  }
  recordStats(win, animate);
  if (animate) await wait(win ? 1000 : 700);          // the finished row, or the answer, is looked at before the result covers it
  renderEnd(win);
  requestAnimationFrame(() => $("e-title").focus({ preventScroll: true }));
}
async function showAnswerRow(instant) {
  // a miss: the word is spelled out on its own row under the board
  $("ans").hidden = false;
  const word = answer.toUpperCase();
  if (!instant) await wait(450);
  await Promise.all(ansTiles.map(async (t, i) => {
    if (instant) { t.set(word[i], "revealed"); return; }
    await wait(i * 90);
    await t.flip(word[i], "revealed", { onContact: () => snd.clack() });
  }));
  $("ans").setAttribute("aria-label", `The word was ${word}`);
}
function recordStats(win) {
  if (extraNo) return;
  const s = store.stats || (store.stats = { played: 0, wins: 0, streak: 0, best: 0, lastWin: "", dist: [0, 0, 0, 0, 0, 0, 0], counted: {} });
  if (s.counted[data.date]) return;
  s.counted[data.date] = 1;
  s.played++;
  if (win) {
    s.wins++;
    const y = new Date(Date.parse(data.date + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
    s.streak = s.lastWin === y ? s.streak + 1 : 1;
    s.best = Math.max(s.best, s.streak); s.lastWin = data.date;
    s.dist[guesses.length - 1]++;
  } else { s.streak = 0; s.dist[6]++; }
  save(store);
}
const hl = (headline, word) => {
  const re = new RegExp(word.split("").join("['’-]?"), "i");
  const m = headline.match(re);
  const frag = document.createDocumentFragment();
  if (!m) { frag.append(headline); return frag; }
  frag.append(headline.slice(0, m.index));
  const mk = document.createElement("mark"); mk.textContent = m[0]; frag.append(mk);
  frag.append(headline.slice(m.index + m[0].length));
  return frag;
};
function renderEnd(win) {
  const n = guesses.length, d = new Date(data.date + "T12:00:00Z");
  $("e-issue").textContent = (extraNo ? `Extra word ${extraNo} · not counted · ` : `Tickerflip No. ${data.no} · `) + `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}`;
  $("e-title").textContent = win ? (n === 1 ? "Solved in one" : `Solved in ${n}`) : "Not today";
  $("e-sub").textContent = `${answer.toUpperCase()}: ${data.clue}.`;
  // the day's board again as squares: what the share text carries, drawn
  const mini = $("mini"); mini.innerHTML = ""; mini.style.setProperty("--L", L);
  for (const g of guesses) for (const st of score(g, answer)) { const i = document.createElement("i"); i.dataset.s = st; mini.appendChild(i); }
  $("e-score").textContent = `${win ? n : "X"}/${ROWS}`;
  // articles behind the word
  const ul = $("arts"); ul.innerHTML = "";
  for (const a of data.articles) {
    const li = document.createElement("li");
    const link = document.createElement("a"); link.href = a.url; link.target = "_blank"; link.rel = "noopener";
    const h = document.createElement("span"); h.className = "a-h"; h.appendChild(hl(a.h, answer));
    const meta = document.createElement("span"); meta.className = "a-m"; meta.textContent = `${a.src ? a.src + " · " : ""}boardread.news/s/${a.id}/`;
    const go = document.createElement("span"); go.className = "a-go"; go.setAttribute("aria-hidden", "true"); go.textContent = "Read it";
    link.append(h, meta, go); li.appendChild(link); ul.appendChild(li);
  }
  // stats
  const s = store.stats, sd = $("stats"); sd.innerHTML = "";
  const y = new Date(Date.parse(data.date + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
  const streak = s.lastWin === data.date || s.lastWin === y ? s.streak : 0;
  for (const [k, v] of [["Played", s.played], ["Win %", s.played ? Math.round((s.wins / s.played) * 100) : 0], ["Streak", streak], ["Best streak", s.best]]) {
    const div = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = k; dd.textContent = v; div.append(dt, dd); sd.appendChild(div);
  }
  const dist = $("dist"); dist.innerHTML = "";
  const max = Math.max(1, ...s.dist);
  dist.setAttribute("aria-label", "Guess distribution: " + s.dist.map((v, i) => `${i < 6 ? i + 1 : "missed"}: ${v}`).join(", "));
  s.dist.forEach((v, i) => {
    const row = document.createElement("div"); row.className = "d-row" + (i === (win ? n - 1 : 6) ? " me" : "") + (i === 6 ? " loss" : "");
    const lab = document.createElement("span"); lab.className = "d-l"; lab.textContent = i < 6 ? i + 1 : "X";
    const bar = document.createElement("span"); bar.className = "d-bar"; bar.style.setProperty("--w", Math.max(8, (v / max) * 100) + "%");
    const num = document.createElement("span"); num.className = "d-n"; num.textContent = v;
    bar.appendChild(num); row.append(lab, bar); dist.appendChild(row);
  });
  comeBack({ streak, label: "Win streak", played: new Set(Object.entries(store.days || {}).filter(([, d]) => d.s && d.s !== "play").map(([k]) => k)), today: data.date });
  topArticle();
  $("share-text").textContent = shareText(win);
  const done = store.extras?.d === data.date ? store.extras.done : [], left = (daily.more || []).map((m, k) => k + 1).filter((k) => !done.includes(k));
  $("extra").hidden = !left.length; $("extra").dataset.k = left[0] || "";
  $("extra-label").textContent = left.length ? `Another word (${left.length} left)` : "";
  $("to-daily").hidden = !extraNo;
  $("credit").textContent = data.credit;
  $("end").hidden = false; $("kb").hidden = true;
  clearInterval(cdT); cdT = setInterval(countdown, 1000); countdown();
}
function shareText(win) {
  const rows = guesses.map((g) => score(g, answer).map((x) => SYM[x]).join(""));
  return `Tickerflip ${extraNo ? "extra" : "No. " + data.no}  ${win ? guesses.length : "X"}/${ROWS}\n${L} letters\n${rows.join("\n")}\nhttps://boardread.news/play/tickerflip/?utm_source=share`;
}
let cdT = 0;
function countdown() {
  if ($("d-next")) { const n0 = new Date(), n1 = Date.UTC(n0.getUTCFullYear(), n0.getUTCMonth(), n0.getUTCDate() + 1), q = Math.max(0, Math.floor((n1 - n0.getTime()) / 1000)); $("d-next").textContent = `${pad(Math.floor(q / 3600))}:${pad(Math.floor((q % 3600) / 60))}:${pad(q % 60)}`; }
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
    const r = document.createRange(); r.selectNodeContents($("share-text")); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    $("share-text").classList.add("open"); toast("Select and copy the text.");
  }
}
let toastTT = 0;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastTT); toastTT = setTimeout(() => t.classList.remove("show"), 2200); }

// ---- overlay (intro and help)
function openIntro(first) {
  helpOpen = true;
  $("intro").hidden = false; $("scrim").hidden = false;
  $("start").textContent = first ? "Play" : "Back";
  $("stage").inert = true; document.querySelector(".top").inert = true;
  $("start").focus({ preventScroll: true });
}
function closeIntro() {
  helpOpen = false;
  $("intro").hidden = true; $("scrim").hidden = true;
  $("stage").inert = false; document.querySelector(".top").inert = false;
  if (phase === "intro") setPhase("play");
}

// ---- which word is on the board
function setWord(d) {
  data = d;
  answer = atob(d.a).split("").reverse().join("").toUpperCase();
  L = answer.length;
  valid = new Set();
  for (const text of wordLists) for (const w of text.split("\n")) if (w.length === L) valid.add(w.trim());
  for (const w of daily.extra) if (w.length === L) valid.add(w);
  valid.add(answer.toLowerCase());
  $("plate-len").textContent = `${L} letters`; $("d-len").textContent = `${L} letters`;
}
let clue0 = "";
function startExtra(k) {
  const m = daily.more?.[k - 1]; if (!m) return;
  extraNo = k;
  setWord({ ...daily, ...m });
  guesses = []; cur = ""; won = false; busy = false;
  app.classList.remove("won", "lost");
  $("ans").hidden = true; $("ans").innerHTML = ""; $("end").hidden = true; $("kb").hidden = false;
  $("clue").classList.remove("on"); $("clue-text").textContent = clue0;
  document.querySelector(".plate-k").textContent = `Extra word ${k}`;
  buildBoard(); buildKeyboard();
  setPhase("play");
  live(`Extra word ${k}. ${L} letters.`);
}

// ---- boot
async function boot() {
  let words = "", more = "";
  try {
    const [res, wr, wm] = await Promise.all([fetch("assets/data/today.json", { cache: "no-cache" }), fetch("assets/data/words.txt"), fetch("assets/data/words-more.txt")]);
    data = await res.json(); words = await wr.text();
    if (wm.ok) more = await wm.text();        // Webster's Second and company names
  } catch (e) {
    $("stage").innerHTML = '<p class="fail">Today’s word did not load. Reload to try again.</p>';
    app.dataset.phase = "play"; return;
  }
  daily = data; wordLists = [words, more];

  setWord(daily);
  buildBoard(); buildKeyboard();
  clue0 = $("clue-text").textContent;
  $("legend-intro").appendChild(legend());
  const d = new Date(data.date + "T12:00:00Z");
  $("issue").textContent = `No. ${data.no} · ${d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })}`;
  const st = store.stats;
  if (st && st.played) {
    const y = new Date(Date.parse(data.date + "T00:00:00Z") - 864e5).toISOString().slice(0, 10);
    const streak = st.lastWin === y || st.lastWin === data.date ? st.streak : 0;
    $("intro-fine").textContent = `Played ${st.played}. Streak ${streak}. Best streak ${st.best}.`;
  }

  // sound toggle
  const sb = $("sound");
  const setSound = (on) => { const v = snd.setEnabled(on); sb.setAttribute("aria-pressed", v); sb.setAttribute("aria-label", v ? "Sound on" : "Sound off"); try { localStorage.setItem("tickerflip:sound", v ? "1" : "0"); } catch { /* ignore */ } };
  sb.addEventListener("click", () => { setSound(!snd.isOn()); if (snd.isOn()) snd.clack(); });
  contrast(app);
  $("help").addEventListener("click", () => (helpOpen ? closeIntro() : openIntro(false)));
  $("start").addEventListener("click", () => { if (localStorage.getItem("tickerflip:sound") === "1" && !snd.isOn()) setSound(true); closeIntro(); });
  $("share").addEventListener("click", share);
  $("extra").addEventListener("click", () => startExtra(+$("extra").dataset.k));
  $("to-daily").addEventListener("click", () => location.assign(location.pathname));
  $("kb").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const k = b.dataset.key;
    if (k === "Enter") enter(); else if (k === "Backspace") backspace(); else typeLetter(k);
  });
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || helpOpen) { if (helpOpen && e.key === "Escape" && phase !== "intro") closeIntro(); return; }
    if (phase !== "play") return;
    // a Turkish keyboard sends ı and İ for the I key; the board has one I
    const key = e.key === "ı" || e.key === "İ" ? "I" : e.key;
    if (key === "Enter") { e.preventDefault(); if (!e.repeat) enter(); }
    else if (key === "Backspace") { e.preventDefault(); backspace(); }
    else if (/^[a-zA-Z]$/.test(key)) { e.preventDefault(); typeLetter(key.toUpperCase()); }
  });
  addEventListener("resize", fit); window.visualViewport?.addEventListener("resize", fit); fit();

  // restore a day already played or in progress
  let day = !params.has("fresh") && store.days?.[data.date];
  // guesses kept from another word of the same day (the day's board was rebuilt) do not fit this board: start clean
  if (day && (day.g || []).some((g) => g.length !== L || !/^[A-Z]+$/.test(g))) day = null;
  if (day && day.L && day.sig !== data.a) day = null;
  if (day && day.g?.length) {
    for (let r = 0; r < day.g.length; r++) { guesses.push(day.g[r]); await reveal(r, day.g[r], score(day.g[r], answer), true); }
    if (guesses.length >= 3) lightClue();
    if (day.s === "won" || day.s === "lost") {
      setPhase("play");
      await finish(day.s === "won", false);
    } else { setPhase("play"); busy = false; }
  } else {
    setPhase("intro"); openIntro(true); clearInterval(cdT); cdT = setInterval(countdown, 1000); countdown();
  }
  if (phase === "intro") { /* waits for the start button */ }
  requestAnimationFrame(() => requestAnimationFrame(() => app.classList.add("ready")));
  if (params.has("debug")) window.__tf = { answer, get state() { return { guesses, cur, phase }; }, valid, typeLetter, enter, backspace };
}
function fit() {
  const vv = window.visualViewport;
  app.style.setProperty("--vh", (vv ? vv.height : innerHeight) + "px");
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
