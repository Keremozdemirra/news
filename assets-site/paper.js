/* Yesterday's paper: turn the leaves with the buttons, the arrow keys or a swipe. Under 900 px the pages sit in a
   scroll-snap row instead, and with reduced motion set nothing animates. No network, nothing stored. */
(function () {
  "use strict";
  var stage = document.querySelector(".stage[data-labels]");
  if (!stage) return;
  var book = stage.querySelector(".book"), leaves = [].slice.call(book.querySelectorAll(".leaf")), mob = stage.querySelector(".mob");
  var prev = document.querySelector("[data-prev]"), next = document.querySelector("[data-next]"), lab = document.querySelector(".ctl .lab");
  var labels = stage.dataset.labels.split("|"), n = leaves.length, s = 0;
  var still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (still) document.documentElement.classList.add("rm");

  function wide() { return innerWidth > 900; }
  function set(k) {
    s = Math.max(0, Math.min(n, k));
    book.dataset.s = s;
    if (s === n) book.setAttribute("data-last", ""); else book.removeAttribute("data-last");
    leaves.forEach(function (e, i) { e.classList.toggle("turned", i < s); });
    lab.textContent = labels[s];
    prev.disabled = s === 0; next.disabled = s === n;
  }
  // the phone row: pages are 620 wide, scaled to the screen; the label follows the page in view
  function fit() {
    var w = mob.clientWidth - 32;
    [].forEach.call(mob.querySelectorAll(".pgi"), function (e) { e.style.transform = "scale(" + (w / 620) + ")"; });
  }
  function go(d) {
    if (!wide()) { mob.scrollBy({ left: d * mob.clientWidth * 0.92, behavior: still ? "auto" : "smooth" }); return; }
    set(s + d);
  }
  prev.addEventListener("click", function () { go(-1); });
  next.addEventListener("click", function () { go(1); });
  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || "")) return;
    if (e.key === "ArrowRight") { go(1); } else if (e.key === "ArrowLeft") { go(-1); }
  });
  var x0 = null;
  book.addEventListener("pointerdown", function (e) { x0 = e.clientX; });
  book.addEventListener("pointerup", function (e) {
    if (x0 === null) return;
    var d = e.clientX - x0; x0 = null;
    if (Math.abs(d) > 50) go(d < 0 ? 1 : -1);
  });
  mob.addEventListener("scroll", function () {
    var i = Math.round(mob.scrollLeft / (mob.clientWidth * 0.92));
    lab.textContent = "Page " + (i + 1) + " of " + mob.children.length;
    prev.disabled = i <= 0; next.disabled = i >= mob.children.length - 1;
  }, { passive: true });
  addEventListener("resize", fit);
  fit(); set(0);
})();
