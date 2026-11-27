/* Theme: the reader's stored choice, else the device's own setting. Loaded in the head, not deferred, so the choice is on the page
   before the first paint. The only thing stored is the word "light" or "dark" under br:theme; it never leaves the device. */
(function () {
  "use strict";
  var KEY = "br:theme", root = document.documentElement, saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
  function apply(t) {
    if (t === "dark") root.setAttribute("data-theme", "dark"); else root.removeAttribute("data-theme");
    var ms = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < ms.length; i++) ms[i].setAttribute("content", t === "dark" ? "#121212" : "#ffffff");
    var b = document.querySelector(".themebtn");
    if (b) { b.setAttribute("aria-pressed", t === "dark" ? "true" : "false"); b.setAttribute("aria-label", t === "dark" ? "Switch to the light theme" : "Switch to the dark theme"); }
  }
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function device() { return mq && mq.matches ? "dark" : "light"; }
  apply(saved === "dark" || saved === "light" ? saved : device());
  // nothing stored: follow the device when its setting changes
  if (mq && !saved) {
    var follow = function () { var s = null; try { s = localStorage.getItem(KEY); } catch (e) { s = null; } if (!s) apply(device()); };
    if (mq.addEventListener) mq.addEventListener("change", follow); else if (mq.addListener) mq.addListener(follow);
  }
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
