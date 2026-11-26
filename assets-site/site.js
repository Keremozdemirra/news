/* Two jobs: the copy-link button and the search. No dependencies, no network except the same-origin search index. */
(function () {
  "use strict";
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    if (!navigator.clipboard) return;
    b.hidden = false;
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(b.dataset.copy).then(function () {
        var t = b.textContent; b.textContent = "Copied";
        setTimeout(function () { b.textContent = t; }, 1800);
      });
    });
  });

  // on a phone the current section may sit off screen in the sideways row; bring it into view
  var cur = document.querySelector(".sections [aria-current]");
  if (cur && cur.closest("ul")) { var ul = cur.closest("ul"); ul.scrollLeft = Math.max(0, cur.getBoundingClientRect().left - ul.getBoundingClientRect().left + ul.scrollLeft ); }

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
