/* Yesterday's paper: turn the leaves with the buttons, the arrow keys or a swipe. Under 900 px the pages sit in a
   scroll-snap row instead, and with reduced motion set nothing animates. No network, nothing stored.
   One state machine per mode. Wide: `s` is the page the reader asked for, `shown` is what the DOM has reached; one leaf
   turns at a time, further input only moves `s`, and a timer finishes a turn if transitionend never arrives.
   Narrow: only the scroll row moves; the 3D book is hidden and takes no input. */
(function () {
  "use strict";
  var stage = document.querySelector(".stage[data-labels]");
  if (!stage) return;
  var book = stage.querySelector(".book"), leaves = [].slice.call(book.querySelectorAll(".leaf")), mob = stage.querySelector(".mob");
  var prev = document.querySelector("[data-prev]"), next = document.querySelector("[data-next]"), lab = document.querySelector(".ctl .lab");
  var labels = stage.dataset.labels.split("|"), n = leaves.length;
  var rmq = matchMedia("(prefers-reduced-motion: reduce)");
  var still = rmq.matches;
  var s = 0, shown = 0, busy = null;             // wide: wanted state, state reached, the turn in flight
  var tgt = null, tgtTimer = 0, mi = 0;          // narrow: page being scrolled to, its watchdog, page in view
  var root = document.documentElement;
  function syncRm() { still = rmq.matches; root.classList.toggle("rm", still); }
  syncRm();
  if (rmq.addEventListener) rmq.addEventListener("change", function () { syncRm(); if (still) settle(); });

  function wide() { return innerWidth > 900; }
  function clamp(k, hi) { return Math.max(0, Math.min(hi, k)); }
  function ui(i, last) { prev.disabled = i <= 0; next.disabled = i >= last; }

  // ---- wide: the book
  function paint() {                             // put the DOM at `shown` with no turn in flight
    book.dataset.s = shown;
    if (shown === n) book.setAttribute("data-last", ""); else book.removeAttribute("data-last");
    leaves.forEach(function (e, i) { e.classList.remove("mv"); e.classList.toggle("turned", i < shown); });
  }
  function label() { lab.textContent = labels[shown]; ui(s, n); }   // text follows the page on screen, buttons follow the goal
  function finish() {
    if (!busy) return;
    clearTimeout(busy.t); busy.leaf.removeEventListener("transitionend", busy.on);
    busy.leaf.classList.remove("mv"); busy = null;
    pump();
  }
  function settle() {                            // jump to the end of whatever was asked, no animation
    if (busy) { clearTimeout(busy.t); busy.leaf.removeEventListener("transitionend", busy.on); busy = null; }
    shown = s; paint(); book.classList.remove("fast"); label();
  }
  function pump() {
    if (busy || shown === s) { if (!busy) book.classList.remove("fast"); return; }
    if (still) { settle(); return; }
    var d = s > shown ? 1 : -1, leaf = leaves[d > 0 ? shown : shown - 1];
    var quick = Math.abs(s - shown) > 1;         // held key or a run of clicks: turn faster, same curve
    book.classList.toggle("fast", quick);
    shown += d; label();
    book.dataset.s = shown;
    if (shown === n) book.setAttribute("data-last", ""); else book.removeAttribute("data-last");
    leaf.classList.add("mv");                    // stays above both stacks until it has landed
    leaf.classList.toggle("turned", d > 0);
    var on = function (e) { if (e.target === leaf && e.propertyName === "transform") finish(); };
    leaf.addEventListener("transitionend", on);
    busy = { leaf: leaf, on: on, t: setTimeout(finish, (quick ? 520 : 980) + 120) };
  }

  // ---- narrow: the scroll row
  function pos(i) { var e = mob.children[i]; return e.offsetLeft - (mob.clientWidth - e.offsetWidth) / 2; }
  function nearest() {
    var best = 0, d = 1e9;
    for (var i = 0; i < mob.children.length; i++) { var k = Math.abs(pos(i) - mob.scrollLeft); if (k < d) { d = k; best = i; } }
    return best;
  }
  function mlabel() {
    var m = mob.children.length;
    lab.textContent = "Page " + (mi + 1) + " of " + m; ui(mi, m - 1);
  }
  function mdone() { clearTimeout(tgtTimer); tgt = null; }

  function go(d) {
    if (!wide()) {
      var base = tgt === null ? mi : tgt;
      tgt = clamp(base + d, mob.children.length - 1);
      clearTimeout(tgtTimer); tgtTimer = setTimeout(mdone, 900);   // a missed scroll event cannot hold the lock
      mi = tgt; mlabel();
      mob.scrollTo({ left: pos(tgt), behavior: still ? "auto" : "smooth" });
      return;
    }
    s = clamp(s + d, n); label(); pump();
  }
  prev.addEventListener("click", function () { go(-1); });
  next.addEventListener("click", function () { go(1); });
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey || e.defaultPrevented) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || "") || (e.target && e.target.isContentEditable)) return;
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    if (!wide() && e.target === mob) return;     // the focused row scrolls (and snaps) by itself
    go(e.key === "ArrowRight" ? 1 : -1);
  });

  // swipe on the book; a drag that was a swipe does not also follow the link under it
  var x0 = null, y0 = 0, pid = -1, swiped = false;
  book.addEventListener("pointerdown", function (e) {
    if (!e.isPrimary || (e.pointerType === "mouse" && e.button !== 0)) return;
    x0 = e.clientX; y0 = e.clientY; pid = e.pointerId; swiped = false;
  });
  function drop() { x0 = null; pid = -1; }
  book.addEventListener("pointercancel", drop);
  book.addEventListener("pointerup", function (e) {
    if (x0 === null || e.pointerId !== pid) return;
    var dx = e.clientX - x0, dy = e.clientY - y0; drop();
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) { swiped = true; go(dx < 0 ? 1 : -1); }
  });
  book.addEventListener("click", function (e) { if (swiped) { e.preventDefault(); e.stopPropagation(); swiped = false; } }, true);

  mob.addEventListener("scroll", function () {
    var i = nearest();
    if (tgt !== null) {                          // our own scroll: label already shows the target
      if (Math.abs(pos(tgt) - mob.scrollLeft) < 2) { mi = tgt; mdone(); mlabel(); }
      return;
    }
    mi = i; mlabel();
  }, { passive: true });
  if ("onscrollend" in window) mob.addEventListener("scrollend", function () { if (tgt !== null) { mi = nearest(); mdone(); mlabel(); } });

  // the phone row: pages are 620 wide, scaled to the screen
  function fit() {
    // 901-1240 px: the two-page spread is 1240 wide, so scale the whole book down instead of cutting it off
    var k = Math.min(1, stage.clientWidth / 1240);
    book.style.scale = k < 1 ? k : ""; book.style.marginBottom = k < 1 ? (-880 * (1 - k)) + "px" : "";
    var w = mob.clientWidth - 32;
    if (w <= 0) return;
    [].forEach.call(mob.querySelectorAll(".pgi"), function (e) { e.style.transform = "scale(" + (w / 620) + ")"; });
  }
  // book page of leaf-state k on the phone row, and back
  function toRow(k) { return k === 0 ? 0 : Math.min(mob.children.length - 1, 2 * k - 1); }
  function toBook(i) { return i === 0 ? 0 : clamp(Math.floor((i + 1) / 2), n); }
  var mode = wide();
  function enter() {                             // crossing the 900 px line: carry the reader's page over
    var w = wide();
    if (w === mode) return;
    mode = w;
    if (w) { s = toBook(mi); settle(); label(); }
    else {
      settle(); mdone(); mi = toRow(s); fit();
      mob.scrollTo({ left: pos(mi), behavior: "auto" }); mlabel();
    }
  }
  addEventListener("resize", function () { fit(); enter(); });
  document.addEventListener("visibilitychange", function () { if (!document.hidden && busy) settle(); });
  addEventListener("pageshow", function (e) { if (e.persisted && busy) settle(); });
  fit(); paint();
  if (wide()) label(); else { mi = nearest(); mlabel(); }
})();
