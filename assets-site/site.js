/* Boardread's script: copy link, search, "new since your last visit", keyboard shortcuts and the quiz.
   No dependencies and no network except the same-origin search index. The only thing stored on the reader's device is
   two timestamps in localStorage (when they last came, and the visit before), which never leave it. */
(function () {
  "use strict";
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    if (!navigator.clipboard) return;
    b.hidden = false;
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(b.dataset.copy).then(function () {
        var l = b, t = l.textContent; l.textContent = "Copied"; b.setAttribute("aria-label", "Link copied");
        setTimeout(function () { l.textContent = t; b.setAttribute("aria-label", "Copy link"); }, 1800);
      });
    });
  });

  // a phone with a share sheet: one "Share" button replaces the links
  document.querySelectorAll("[data-share]").forEach(function (b) {
    if (!navigator.share || !window.matchMedia || !matchMedia("(pointer:coarse)").matches) return;
    b.hidden = false; b.parentNode.classList.add("native");
    b.addEventListener("click", function () { navigator.share({ title: b.dataset.title, url: b.dataset.url }).catch(function () {}); });
  });

  // on a phone the current section may sit off screen in the sideways row; bring it into view
  var cur = document.querySelector(".sections [aria-current]");
  if (cur && cur.closest("ul")) { var ul = cur.closest("ul"); ul.scrollLeft = Math.max(0, cur.getBoundingClientRect().left - ul.getBoundingClientRect().left + ul.scrollLeft ); }


  // the menu is a details element: Escape and a click elsewhere close it, and Escape hands focus back to the button
  var menu = document.querySelector("details.menu");
  if (menu) {
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.open) { menu.open = false; menu.querySelector("summary").focus(); }
    });
    document.addEventListener("click", function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
  }

  // "new since your last visit" was removed (2026-11-27): storing a visit time on the reader's device needs consent under
  // § 25 TDDDG unless it is strictly necessary, and it is not. Clear the old value from browsers that still hold it.
  try { localStorage.removeItem("br:visit"); } catch (e) { /* storage blocked */ }

  // keyboard: j and k step through the stories on the page (on a story, to the older and newer one), o opens, / searches, ? helps
  var panel = null;
  function typing(el) { return el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable); }
  function showKeys(on) {
    if (!panel) {
      panel = document.createElement("div"); panel.className = "keys"; panel.hidden = true; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Keyboard shortcuts");
      panel.innerHTML = "<div><h2>Keyboard shortcuts</h2><dl><dt><kbd>j</kbd></dt><dd>Next article</dd><dt><kbd>k</kbd></dt><dd>Previous article</dd><dt><kbd>o</kbd></dt><dd>Open the article</dd><dt><kbd>/</kbd></dt><dd>Search</dd><dt><kbd>?</kbd></dt><dd>This panel</dd></dl><button type=\"button\">Close</button></div>";
      panel.addEventListener("click", function (e) { if (e.target === panel || e.target.tagName === "BUTTON") showKeys(false); });
      document.body.appendChild(panel);
    }
    panel.hidden = !on;
    if (on) panel.querySelector("button").focus();
  }
  // the shortcuts need a keyboard: a phone has none, so it never sees the button
  var keyboard = matchMedia("(hover: hover) and (pointer: fine)").matches;
  document.querySelectorAll("[data-keys]").forEach(function (b) { b.hidden = !keyboard; b.addEventListener("click", function () { showKeys(true); }); });

  // the markets strip moves on its own: a button stops it (a touch screen has no hover), and a reader who asked for less motion
  // gets a strip that scrolls by hand and can be reached with the keyboard
  document.querySelectorAll(".mstrip").forEach(function (strip) {
    var btn = strip.querySelector(".mpause"), track = strip.querySelector(".mtrack");
    if (btn) btn.addEventListener("click", function () {
      var on = btn.getAttribute("aria-pressed") !== "true";
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.setAttribute("aria-label", on ? "Play the ticker" : "Pause the ticker");
      strip.classList.toggle("paused", on);
    });
    if (track && matchMedia("(prefers-reduced-motion: reduce)").matches) { track.tabIndex = 0; track.setAttribute("role", "region"); track.setAttribute("aria-label", "Markets, scrolls sideways"); }
  });

  var list = [], at = -1;
  function stories() {
    var seenHref = {};
    return Array.prototype.filter.call(document.querySelectorAll("main a[href*='/s/']"), function (a) {
      var h = a.getAttribute("href");
      if (seenHref[h] || a.closest(".prevnext,.related") || !a.offsetParent) return false;
      return (seenHref[h] = true);
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || document.documentElement.classList.contains("reader-open")) return;  // the reader has its own keys
    if (e.key === "Escape" && panel && !panel.hidden) { showKeys(false); return; }
    if (typing(e.target)) return;
    var k = e.key;
    if (k === "?") { e.preventDefault(); showKeys(!(panel && !panel.hidden)); return; }
    if (k === "/") {
      var q = document.getElementById("q");
      if (q) { e.preventDefault(); q.focus(); } else { e.preventDefault(); location.href = (document.querySelector(".find") || {}).href || "/search/"; }
      return;
    }
    if (k !== "j" && k !== "k" && k !== "o") return;
    var onStory = document.querySelector("article.art");
    if (onStory) {
      var rel = document.querySelector(k === "j" ? "a[rel=prev]" : k === "k" ? "a[rel=next]" : "none");
      if (rel) location.href = rel.href;
      return;
    }
    list = stories();
    if (k === "o") { if (list[at]) location.href = list[at].href; return; }
    if (!list.length) return;
    if (list[at]) list[at].classList.remove("cur");
    at = k === "j" ? Math.min(at + 1, list.length - 1) : Math.max(at - 1, 0);
    list[at].classList.add("cur");
    list[at].focus({ preventScroll: true });
    list[at].scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });


  // "2h 14m ago" on the Board: the page is built a few times a day, so the age is worked out here; without the script the date stays
  var ages = document.querySelectorAll("time[data-age]");
  if (ages.length) {
    var tick = function () {
      var now = Date.now();
      ages.forEach(function (t) {
        var m = Math.max(0, Math.round((now - Date.parse(t.getAttribute("datetime"))) / 60000));
        t.textContent = m < 1 ? "now" : m < 60 ? m + " min ago" : m < 1440 ? Math.floor(m / 60) + " h ago" : Math.floor(m / 1440) + " d ago";
      });
    };
    tick(); setInterval(tick, 60000);
  }

  // "Updated 12:29 UTC" is the build time; past three hours the page says the desk is behind, so a quiet front page is not read as a quiet day
  document.querySelectorAll(".upd[data-built]").forEach(function (u) {
    var late = Date.now() - Date.parse(u.getAttribute("data-built")) > 3 * 36e5;
    if (late) { u.firstChild.textContent += ". The next update is late."; u.classList.add("late"); }
  });

  // quiz: the answer is in the page (inside a details element, so it works without this script); a click only marks the choice
  var quiz = document.querySelector("[data-quiz]");
  if (quiz) {
    var asked = 0, right = 0, total = quiz.querySelectorAll(".q").length, tally = quiz.querySelector(".tally");
    quiz.querySelectorAll(".q").forEach(function (q) {
      var ans = +q.dataset.answer, opts = q.querySelectorAll(".opt");
      opts.forEach(function (b, i) {
        b.addEventListener("click", function () {
          opts.forEach(function (o) { o.disabled = true; });
          opts[ans].classList.add("right");
          if (i !== ans) b.classList.add("wrong");
          q.querySelector(".ans").open = true;
          asked++; if (i === ans) right++;
          if (asked === total) tally.textContent = right + " of " + total + " right.";
        });
      });
    });
  }

  var form = document.querySelector("form[data-index]");
  if (!form) return;
  var input = form.querySelector("input"), out = document.getElementById("hits"), status = document.getElementById("sstatus");
  var index = null;

  function norm(s) { return (s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, ""); }
  function fmt(iso) {
    var d = new Date(iso);
    return d.getUTCDate() + " " + ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getUTCMonth()] + " " + d.getUTCFullYear();
  }
  // a term matches at the start of a word: "ai" finds AI, not "said"
  function has(str, w) { return (" " + str).indexOf(" " + w) > -1; }
  function score(item, terms) {
    var s = 0;
    for (var i = 0; i < terms.length; i++) {
      var w = terms[i], hit = 0;
      if (has(item._h, w)) hit += item._h.indexOf(w) === 0 ? 6 : 4;
      if (has(item._c, w)) hit += 5;
      if (has(item._t, w)) hit += 3;
      if (has(item._d, w)) hit += 2;
      if (has(item._s, w)) hit += 1;
      if (!hit) return 0;
      s += hit;
    }
    return s;
  }
  function render(list, q) {
    out.textContent = "";
    list.forEach(function (it) {
      var li = document.createElement("li"), a = document.createElement("a");
      a.className = "row text"; a.href = it.url;
      var box = document.createElement("div"), m = document.createElement("span"), h = document.createElement("h2"), p = document.createElement("p");
      m.className = "meta"; m.textContent = it.topic + " · " + fmt(it.date);
      h.className = "h-l"; h.textContent = it.headline;
      p.className = "dek"; p.textContent = it.dek;
      box.appendChild(m); box.appendChild(h); box.appendChild(p); a.appendChild(box); li.appendChild(a); out.appendChild(li);
    });
    status.textContent = !q ? "Type to search." :
      list.length ? list.length + (list.length === 1 ? " article" : " articles") + " for “" + q + "”" : "No article matches “" + q + "”. Try a company, a topic or a shorter word.";
  }
  function run() {
    var q = input.value.trim();
    if (!index) return;
    var terms = norm(q).split(/\s+/).filter(Boolean);
    if (!terms.length) { render([], ""); if (history.replaceState && location.search) history.replaceState(null, "", location.pathname); return; }
    var hits = index.map(function (it) { return { it: it, s: score(it, terms) }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s || (a.it.date < b.it.date ? 1 : -1); })
      .map(function (x) { return x.it; });
    render(hits, q);
    if (history.replaceState) history.replaceState(null, "", q ? "?q=" + encodeURIComponent(q) : location.pathname);
  }
  form.addEventListener("submit", function (e) { e.preventDefault(); run(); });
  input.addEventListener("input", run);
  var start = new URLSearchParams(location.search).get("q");
  if (start) input.value = start;
  status.textContent = "Loading";
  fetch(form.dataset.index).then(function (r) { return r.json(); }).then(function (data) {
    index = data.map(function (it) {
      it._h = norm(it.headline); it._d = norm(it.dek); it._t = norm(it.topic); it._c = norm(it.company); it._s = norm(it.sources);
      return it;
    });
    run();
  }).catch(function () { status.textContent = "Search could not load."; });
})();
