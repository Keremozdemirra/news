#!/usr/bin/env python3
"""Browser checks on a built site directory, with Playwright and the Chrome the runner already has.

  python3 scripts/webcheck.py site  [DIR] [--shots OUT] [--motion]   key pages at 390 and 1280 px, light and dark
  python3 scripts/webcheck.py games [DIR] [--shots OUT]   one scripted round of each game, to its end screen

Exit 1 with one line per finding. `site` fails on: a horizontal scroll, a console or page error, a same-origin request that
failed or answered 4xx/5xx, a stylesheet that did not load, a page where the light and dark themes look the same, a theme
toggle that does not switch (or does not remember), a front page whose panel and rail do not start on one line, a
broken image. `games` fails on a console error, a game that never reaches its end screen, and a 4xx on its files.

DIR is the output of `python3 -m aidaily site` (default _site). Needs: pip install playwright (no browser download: it
drives the installed Google Chrome, channel "chrome"). The pure parts (page choice, finding text) are unit-tested in
tests/test_webcheck.py without a browser.
"""
import argparse
import functools
import http.server
import json
import re
import sys
import threading
from pathlib import Path

VIEWPORTS = {"phone": (390, 844), "desktop": (1280, 800)}
SCHEMES = ("light", "dark")
NEVER_MIND = ("favicon", "google8ab", "/_vercel", "net::ERR_BLOCKED_BY_CLIENT")


def pick_pages(site):
    """Paths worth a look: the front page, latest, the games hub, about, and the newest article (by its folder name)."""
    site = Path(site)
    pages = ["/", "/latest/", "/play/", "/about/"]
    arts = sorted(p.parent.name for p in (site / "s").glob("*/index.html")) if (site / "s").is_dir() else []
    if arts:
        pages.append(f"/s/{arts[-1]}/")
    return [p for p in pages if p == "/" or (site / p.strip("/") / "index.html").exists()]


def ignorable(text):
    return any(n in text for n in NEVER_MIND)


def serve(site):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class Page:
    """One open page with everything it said to the console and every response it got."""

    def __init__(self, browser, base, viewport, scheme, motion="no-preference"):
        w, h = VIEWPORTS[viewport]
        self.ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, reduced_motion=motion)
        self.page = self.ctx.new_page()
        self.base, self.errors, self.bad = base, [], []
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.errors.append(f"page error: {e}"))
        self.page.on("requestfailed", lambda r: self.bad.append(f"failed {r.url} ({r.failure})"))
        self.page.on("response", lambda r: self.bad.append(f"{r.status} {r.url}") if r.status >= 400 and r.url.startswith(base) else None)

    def go(self, path):
        self.page.goto(self.base + path, wait_until="load")
        self.page.wait_for_timeout(250)
        return self

    def close(self):
        self.ctx.close()

    def findings(self, where):
        out = [f"{where}: console error: {e[:160]}" for e in self.errors if not ignorable(e)]
        out += [f"{where}: {b[:200]}" for b in self.bad if not ignorable(b)]
        return out


def bg(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def check_layout(p, where, viewport):
    out = []
    pg = p.page
    wide = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    if wide[0] > wide[1] + 1:
        culprit = pg.evaluate("""() => { const w = document.documentElement.clientWidth;
            const el = [...document.querySelectorAll('body *')].find(e => e.getBoundingClientRect().right > w + 1 && getComputedStyle(e).position !== 'fixed');
            return el ? el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : '') : ''; }""")
        out.append(f"{where}: horizontal scroll ({wide[0]} px wide in {wide[1]}){' at ' + culprit if culprit else ''}")
    sheets = pg.evaluate("""() => [...document.querySelectorAll('link[rel=stylesheet]')].filter(l => !l.sheet).map(l => l.href)""")
    out += [f"{where}: stylesheet not applied: {s}" for s in sheets]
    broken = pg.evaluate("""() => [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.currentSrc).map(i => i.currentSrc)""")
    out += [f"{where}: broken image {b}" for b in broken[:5]]
    if viewport == "desktop":
        # the rail's box starts above its heading (padding): the lines a reader sees are the panel's frame and the rail's
        # heading at the top, the two boxes' bottoms at the foot
        box = pg.evaluate("""() => { const a = document.querySelector('.panelbox'), b = document.querySelector('.frail'),
            h = b && b.querySelector('h2'); if (!a || !b || !h) return null;
            const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(), rh = h.getBoundingClientRect();
            return [ra.top, rh.top, ra.bottom, rb.bottom, rb.right, getComputedStyle(b).display]; }""")
        if box and box[5] != "none":
            if abs(box[0] - box[1]) > 3:
                out.append(f"{where}: the panel starts at {box[0]:.0f} px and the rail's heading at {box[1]:.0f} px")
            if abs(box[2] - box[3]) > 3:
                out.append(f"{where}: the panel ends at {box[2]:.0f} px and the rail at {box[3]:.0f} px")
            if box[4] > VIEWPORTS["desktop"][0] + 1:
                out.append(f"{where}: the rail runs past the right edge")
    return out


def check_theme(base, browser, path, viewport):
    """The device scheme decides the first paint; the button flips it, remembers it, and the page looks different."""
    out, seen = [], {}
    for scheme in SCHEMES:
        p = Page(browser, base, viewport, scheme).go(path)
        where = f"{path} {viewport} {scheme}"
        first = p.page.evaluate("document.documentElement.getAttribute('data-theme')")
        if first != scheme:
            out.append(f"{where}: first paint is data-theme={first!r}, the device asked for {scheme}")
        seen[scheme] = bg(p.page)
        btn = p.page.query_selector(".themebtn")
        if btn is None:
            out.append(f"{where}: no theme button")
        else:
            other = "dark" if scheme == "light" else "light"
            if not btn.is_visible():  # behind the phone menu: open it
                menu = p.page.query_selector("details.menu summary, .menu summary")
                if menu:
                    menu.click()
            btn.click()
            now = p.page.evaluate("[document.documentElement.getAttribute('data-theme'), document.querySelector('.themebtn').getAttribute('aria-pressed'), localStorage.getItem('br:theme')]")
            if now[0] != other or now[2] != other or now[1] != ("true" if other == "dark" else "false"):
                out.append(f"{where}: the toggle left data-theme={now[0]}, aria-pressed={now[1]}, stored={now[2]} (wanted {other})")
            if bg(p.page) == seen[scheme]:
                out.append(f"{where}: the page looks the same after switching to {other}")
            p.page.reload(wait_until="load")
            kept = p.page.evaluate("document.documentElement.getAttribute('data-theme')")
            if kept != other:
                out.append(f"{where}: the choice was not kept over a reload ({kept})")
            p.page.click(".themebtn")
            back = p.page.evaluate("document.documentElement.getAttribute('data-theme')")
            if back != scheme:
                out.append(f"{where}: a second click did not switch back ({back})")
        out += p.findings(where)
        p.close()
    if seen.get("light") and seen.get("light") == seen.get("dark"):
        out.append(f"{path} {viewport}: light and dark have the same background {seen['light']}")
    return out


def run_motion(site):
    """--motion: the front page for a reader who asked for reduced motion (the market strip scrolls by hand then)."""
    from playwright.sync_api import sync_playwright
    srv, base = serve(site)
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-gpu"])
        for viewport in VIEWPORTS:
            p = Page(browser, base, viewport, "light", motion="reduce").go("/")
            out += [f for f in check_layout(p, f"/ {viewport} reduced-motion", viewport) if "horizontal scroll" in f]
            p.close()
        browser.close()
    srv.shutdown()
    return out


def run_site(site, shots=None):
    from playwright.sync_api import sync_playwright
    srv, base = serve(site)
    out = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-gpu"])
        for path in pick_pages(site):
            for viewport in VIEWPORTS:
                for scheme in SCHEMES:
                    where = f"{path} {viewport} {scheme}"
                    p = Page(browser, base, viewport, scheme).go(path)
                    out += p.findings(where) + check_layout(p, where, viewport)
                    if shots:
                        Path(shots).mkdir(parents=True, exist_ok=True)
                        name = re.sub(r"[^a-z0-9]+", "-", f"{path}-{viewport}-{scheme}".lower()).strip("-")
                        p.page.screenshot(path=str(Path(shots) / f"{name}.png"), full_page=False)
                    p.close()
        for viewport in VIEWPORTS:
            out += check_theme(base, browser, "/", viewport)
        browser.close()
    srv.shutdown()
    return out


# games: every one is a static page with a #end section that opens when the round is over

def play_ftf(pg):
    for _ in range(150):
        if pg.is_visible("#end"):
            return
        if pg.is_visible("#next"):
            pg.click("#next")
        elif pg.is_visible("#k-up"):
            pg.keyboard.press("ArrowUp")  # its documented shortcut: the keys sit under the phone's own bar on some sizes
        pg.wait_for_timeout(120)


def play_topfloor(pg, answers):
    """answers: the day's "easy" answer for each question, from today.json (an unknown answer is refused by the game)."""
    for _ in range(160):
        if pg.is_visible("#end"):
            return
        if pg.is_visible("#next"):
            pg.click("#next")
        elif pg.is_visible("#ans"):
            m = re.search(r"question (\d+)", pg.inner_text("#q-count"), re.I)
            if not m:
                pg.wait_for_timeout(250)
                continue
            n = int(m.group(1))
            pg.wait_for_timeout(500)
            pg.fill("#ans", answers[min(n, len(answers)) - 1])
            pg.click("#ride", force=True)
            try:
                pg.wait_for_selector("#next", state="visible", timeout=4000)  # the list is read off the page's worker first
            except Exception:  # noqa: BLE001  not answered: the loop asks again, and gives up after its turns
                pass
        pg.wait_for_timeout(250)


def play_tickerflip(pg, words):
    for w in words[:40]:
        if pg.is_visible("#end"):
            return
        for ch in w:
            pg.keyboard.press(ch)
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(1400)  # the tiles flip before the next row takes input


def run_games(site, shots=None, fast=False):
    from playwright.sync_api import sync_playwright
    srv, base = serve(site)
    out = []
    today = json.loads((Path(site) / "play/tickerflip/assets/data/today.json").read_text())
    words = [w for w in today.get("extra", []) if len(w) == today.get("len", 6)]
    tf = json.loads((Path(site) / "play/topfloor/assets/data/today.json").read_text())
    answers = [(q.get("easy") or ["a"])[0] for q in tf["prompts"]]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-gpu"])
        for slug, play in (("face-the-figure", play_ftf), ("topfloor", lambda pg: play_topfloor(pg, answers)), ("tickerflip", lambda pg: play_tickerflip(pg, words))):
            for viewport in (("phone",) if fast else VIEWPORTS):
                p = Page(browser, base, viewport, "light").go(f"/play/{slug}/")
                where = f"/play/{slug}/ {viewport}"
                try:
                    if p.page.is_visible("#start"):  # the how-to-play sheet every game opens with
                        p.page.click("#start")
                        p.page.wait_for_timeout(400)
                    play(p.page)
                    p.page.wait_for_selector("#end:not([hidden])", timeout=8000)
                except Exception as e:  # noqa: BLE001  a timeout is the finding: the round never ended
                    out.append(f"{where}: the round did not reach its end screen ({type(e).__name__})")
                else:
                    if not (p.page.inner_text("#share-text") or "").strip():
                        out.append(f"{where}: the end screen has no share text")
                    if shots:
                        Path(shots).mkdir(parents=True, exist_ok=True)
                        p.page.screenshot(path=str(Path(shots) / f"game-{slug}-{viewport}.png"))
                out += p.findings(where)
                p.close()
        browser.close()
    srv.shutdown()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=("site", "games"))
    ap.add_argument("dir", nargs="?", default="_site")
    ap.add_argument("--shots", help="write screenshots into this folder")
    ap.add_argument("--fast", action="store_true", help="games: the phone size only")
    ap.add_argument("--motion", action="store_true", help="also load the front page with reduced motion (known to scroll sideways, 2026-11-27)")
    a = ap.parse_args(argv)
    if not (Path(a.dir) / "index.html").exists():
        print(f"{a.dir} is not a built site (no index.html)")
        return 2
    found = run_site(a.dir, a.shots) if a.mode == "site" else run_games(a.dir, a.shots, a.fast)
    if a.motion and a.mode == "site":
        found += run_motion(a.dir)
    for f in found:
        print("FAIL", f)
    print(f"webcheck {a.mode}: {'clean' if not found else str(len(found)) + ' finding(s)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
