/* Boardread's reader: a headline on a list opens the article in a full-screen layer; up and down move through the list.
   The article's own page stays the real page (its URL, its markup, what search engines index): the layer only shows that page's
   <article>, fetched from the same site, and the address bar follows it. Without this script a headline is a plain link.
   No dependencies; the only requests are same-origin page fetches. */
(function () {
  "use strict";
  var root = document.getElementById("reader");
  if (!root || !window.fetch || !window.DOMParser || !history.pushState) return;
  var scroller = root.querySelector(".rscroll"), body = root.querySelector(".rbody"), pos = root.querySelector(".rpos"),
      bPrev = root.querySelector(".rprev"), bNext = root.querySelector(".rnext"), bClose = root.querySelector(".rclose");
  var STORY = /\/s\/[^\/]+\/$/;
  var calm = matchMedia("(prefers-reduced-motion: reduce)");
  var cache = {}, list = [], at = -1, opener = null, shown = false, token = 0, pushed = false, pageTitle = document.title;
  var behind = Array.prototype.slice.call(document.querySelectorAll(".skip, .mh, main, .foot"));

  // the stories of this page in the order they are listed; the same story twice counts once
  function collect() {
    var seen = {}, out = [];
    document.querySelectorAll("main a[href]").forEach(function (a) {
      if (a.target || a.getAttribute("href").charAt(0) === "#" || a.closest(".related, .prevnext, aside, .rates")) return;  // a chip is a link to this page, not a story
      var u = new URL(a.href, location.href);
      if (u.origin !== location.origin || !STORY.test(u.pathname) || seen[u.pathname]) return;
      seen[u.pathname] = 1; out.push({ url: u.pathname, a: a });
    });
    return out;
  }

  // the <article> of a story page, as markup the layer can show; fetched once, kept
  function load(url) {
    if (!cache[url]) cache[url] = fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.text();
    }).then(function (t) {
      var doc = new DOMParser().parseFromString(t, "text/html"), art = doc.querySelector("article.art");
      if (!art) throw new Error("no article");
      art.querySelectorAll(".prevnext, .related").forEach(function (n) { n.remove(); });
      return { node: document.importNode(art, true), title: doc.title };
    });
    cache[url].catch(function () { delete cache[url]; });
    return cache[url];
  }

  function setInert(on) { behind.forEach(function (n) { if (on) n.setAttribute("inert", ""); else n.removeAttribute("inert"); }); }

  function render(i, dir, mode) {
    var my = ++token, item = list[i];
    at = i;
    bPrev.disabled = i <= 0; bNext.disabled = i >= list.length - 1;
    pos.textContent = (i + 1) + " of " + list.length;
    if (mode === "push") { history.pushState({ br: item.url }, "", item.url); pushed = true; }
    else if (mode === "replace") history.replaceState({ br: item.url }, "", item.url);
    load(item.url).then(function (r) {
      if (my !== token) return;
      body.textContent = ""; body.appendChild(r.node.cloneNode(true));
      document.title = r.title;
      scroller.scrollTop = 0;
      body.classList.remove("up", "down");
      if (dir && !calm.matches) { void body.offsetWidth; body.classList.add(dir > 0 ? "up" : "down"); }
      var h = body.querySelector("h1"); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
      if (list[i + 1]) load(list[i + 1].url).catch(function () {});  // the next one is ready before it is asked for
      if (list[i - 1]) load(list[i - 1].url).catch(function () {});
    }).catch(function () { if (my === token) location.href = item.url; });  // no layer: the page itself
  }

  function open(i, from) {
    list = collect();
    if (i < 0 || i >= list.length) return;
    if (!shown) {
      shown = true; opener = from || document.activeElement;
      root.hidden = false; setInert(true); document.documentElement.classList.add("reader-open");
      render(i, 0, "push");
    } else render(i, 0, "replace");
  }

  function hide() {
    if (!shown) return;
    shown = false; token++; pushed = false;
    root.hidden = true; setInert(false); document.documentElement.classList.remove("reader-open");
    body.textContent = ""; document.title = pageTitle;
    if (opener && opener.focus && document.contains(opener)) opener.focus({ preventScroll: true });
  }

  function close() {
    if (!shown) return;
    if (history.state && history.state.br && pushed) history.back(); else hide();  // Back and Close are the same step
  }

  function step(d) {
    var n = at + d;
    if (!shown || n < 0 || n >= list.length) return;
    render(n, d, "replace");
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("main a[href]");
    if (!a || shown) return;
    var items = collect(), u = new URL(a.href, location.href);
    for (var i = 0; i < items.length; i++) if (items[i].url === u.pathname && !a.target && u.origin === location.origin) {
      e.preventDefault(); open(i, a); return;
    }
  });
  bClose.addEventListener("click", close);
  bPrev.addEventListener("click", function () { step(-1); });
  bNext.addEventListener("click", function () { step(1); });

  window.addEventListener("popstate", function (e) {
    if (e.state && e.state.br) {   // Forward into an article, or a Back inside the layer
      list = shown ? list : collect();
      for (var i = 0; i < list.length; i++) if (list[i].url === e.state.br) {
        if (!shown) { shown = true; root.hidden = false; setInert(true); document.documentElement.classList.add("reader-open"); }
        pushed = true; render(i, 0, null); return;
      }
      location.reload(); return;
    }
    hide();
  });

  document.addEventListener("keydown", function (e) {
    if (!shown || e.metaKey || e.ctrlKey || e.altKey) return;
    var k = e.key;
    if (k === "Escape") { e.preventDefault(); close(); }
    else if (k === "ArrowDown" || k === "j") { e.preventDefault(); step(1); }
    else if (k === "ArrowUp" || k === "k") { e.preventDefault(); step(-1); }
    else if (k === "Tab") {   // focus stays in the layer
      var f = Array.prototype.filter.call(root.querySelectorAll("a[href], button:not([disabled]), [tabindex='0']"), function (n) { return n.offsetParent; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === first || !root.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  // a swipe up from the end of an article goes to the next one, a swipe down from its start to the previous one
  var y0 = null, x0 = 0, edge = 0;
  scroller.addEventListener("touchstart", function (e) {
    if (e.touches.length !== 1) { y0 = null; return; }
    y0 = e.touches[0].clientY; x0 = e.touches[0].clientX;
    edge = (scroller.scrollTop <= 1 ? -1 : 0) + (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2 ? 1 : 0);
  }, { passive: true });
  scroller.addEventListener("touchend", function (e) {
    if (y0 === null) return;
    var t = e.changedTouches[0], dy = y0 - t.clientY, dx = x0 - t.clientX; y0 = null;
    if (Math.abs(dy) < 80 || Math.abs(dy) < Math.abs(dx) * 1.5) return;
    if (dy > 0 && edge >= 0 && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2) step(1);
    else if (dy < 0 && edge <= 0 && scroller.scrollTop <= 1) step(-1);
  }, { passive: true });
})();
