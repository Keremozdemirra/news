/* Theme: light unless the reader chose dark. Loaded in the head, not deferred, so the choice is on the page before the first
   paint. The only thing stored is the word "light" or "dark" under br:theme; it never leaves the device. */
(function () {
  "use strict";
  var KEY = "br:theme", root = document.documentElement, saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
  function apply(t) {
    if (t === "dark") root.setAttribute("data-theme", "dark"); else root.removeAttribute("data-theme");
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.setAttribute("content", t === "dark" ? "#121212" : "#ffffff");
    var b = document.querySelector(".themebtn");
    if (b) { b.setAttribute("aria-pressed", t === "dark" ? "true" : "false"); b.setAttribute("aria-label", t === "dark" ? "Switch to the light theme" : "Switch to the dark theme"); }
  }
  apply(saved === "dark" ? "dark" : "light");
  document.addEventListener("DOMContentLoaded", function () {
    var b = document.querySelector(".themebtn");
    if (!b) return;
    apply(root.getAttribute("data-theme") === "dark" ? "dark" : "light");
    b.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      apply(next);
      try { localStorage.setItem(KEY, next); } catch (e) { /* private mode: the choice lasts for this page only */ }
    });
  });
})();
