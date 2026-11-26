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
        var l = b.querySelector(".t") || b, t = l.textContent; l.textContent = "Copied"; b.setAttribute("aria-label", "Link copied");
        setTimeout(function () { l.textContent = t; b.setAttribute("aria-label", "Copy link"); }, 1800);
      });
    });
  });

  // on a phone the current section may sit off screen in the sideways row; bring it into view
  var cur = document.querySelector(".sections [aria-current]");
  if (cur && cur.closest("ul")) { var ul = cur.closest("ul"); ul.scrollLeft = Math.max(0, cur.getBoundingClientRect().left - ul.getBoundingClientRect().left + ul.scrollLeft ); }


  // new since your last visit: two timestamps. A "visit" is a page load more than 30 minutes after the previous one.
  var KEY = "br:visit", GAP = 30 * 60 * 1000, prev = null;
  try {
    var st = JSON.parse(localStorage.getItem(KEY) || "null"), t = Date.now();
    if (st && t - st.last > GAP) st = { prev: st.last, last: t };
    else if (st) st.last = t;
    else st = { prev: null, last: t };
    localStorage.setItem(KEY, JSON.stringify(st));
    prev = st.prev;
  } catch (e) { prev = null; }
  if (prev) {
    var seen = {}, count = 0;
    document.querySelectorAll("a[href*='/s/']").forEach(function (a) {
      var tm = a.querySelector("time[datetime]");
      if (!tm || Date.parse(tm.getAttribute("datetime")) <= prev) return;
      var m = a.querySelector(".meta") || a, tag = document.createElement("span");
      tag.className = "new"; tag.textContent = "New"; m.insertBefore(tag, m.firstChild);
      if (!seen[a.getAttribute("href")]) { seen[a.getAttribute("href")] = 1; count++; }
    });
    var since = document.getElementById("since");
    if (since && count) { since.textContent = count + (count === 1 ? " story" : " stories") + " since your last visit."; since.hidden = false; }
  }

  // keyboard: j and k step through the stories on the page (on a story, to the older and newer one), o opens, / searches, ? helps
  var panel = null;
  function typing(el) { return el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable); }
  function showKeys(on) {
    if (!panel) {
      panel = document.createElement("div"); panel.className = "keys"; panel.hidden = true; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Keyboard shortcuts");
      panel.innerHTML = "<div><h2>Keyboard shortcuts</h2><dl><dt><kbd>j</kbd></dt><dd>Next story</dd><dt><kbd>k</kbd></dt><dd>Previous story</dd><dt><kbd>o</kbd></dt><dd>Open the story</dd><dt><kbd>/</kbd></dt><dd>Search</dd><dt><kbd>?</kbd></dt><dd>This panel</dd></dl><button type=\"button\">Close</button></div>";
      panel.addEventListener("click", function (e) { if (e.target === panel || e.target.tagName === "BUTTON") showKeys(false); });
      document.body.appendChild(panel);
    }
    panel.hidden = !on;
    if (on) panel.querySelector("button").focus();
  }
  document.querySelectorAll("[data-keys]").forEach(function (b) { b.hidden = false; b.addEventListener("click", function () { showKeys(true); }); });
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
    if (e.metaKey || e.ctrlKey || e.altKey) return;
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
    status.textContent = !q ? index.length + " stories. Type to search." :
      list.length ? list.length + (list.length === 1 ? " story" : " stories") + " for “" + q + "”" : "No story matches “" + q + "”. Try a company, a topic or a shorter word.";
  }
  function run() {
    var q = input.value.trim();
    if (!index) return;
    var terms = norm(q).split(/\s+/).filter(Boolean);
    if (!terms.length) { render([], ""); return; }
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
  status.textContent = "Loading the index";
  fetch(form.dataset.index).then(function (r) { return r.json(); }).then(function (data) {
    index = data.map(function (it) {
      it._h = norm(it.headline); it._d = norm(it.dek); it._t = norm(it.topic); it._c = norm(it.company); it._s = norm(it.sources);
      return it;
    });
    run();
  }).catch(function () { status.textContent = "The search index could not be loaded."; });
})();
