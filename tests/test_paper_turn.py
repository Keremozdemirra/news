"""Page-turn behaviour of /paper/, driven in a real browser. Skipped when Playwright or Chrome is missing.

    python3 -m venv /tmp/pwv && /tmp/pwv/bin/pip install playwright && /tmp/pwv/bin/python -m unittest tests.test_paper_turn

The page is rebuilt from the shipped CSS/JS around six synthetic pages, so no site build or network is needed.
PAPER_ASSETS points at another assets dir to run the same checks against an older copy of the script.
"""
import os
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ASSETS = Path(os.environ.get("PAPER_ASSETS") or Path(__file__).resolve().parent.parent / "assets-site")


def page_html():
    css = "".join((ASSETS / f).read_text() for f in ("site.css", "views.css", "paper.css"))
    pages = [f'<div class="pg"><div class="hd"><span>P{i}</span></div><h3>Page {i}</h3><a href="#p{i}">link {i}</a></div>' for i in range(1, 7)]
    leaves = "".join(f'<div class="leaf" style="--i:{i // 2 + 1}"><div class="face r">{pages[i]}</div><div class="face bk">{pages[i + 1]}</div></div>' for i in range(0, 6, 2))
    mob = "".join(f'<div class="pgw"><div class="pgi">{p}</div></div>' for p in pages)
    labels = "Page 1|Pages 2 and 3|Pages 4 and 5|Page 6"
    return (f'<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><style>{css}</style><body class="v-paper">'
            f'<div class="pp-wrap"><div class="ctl"><button data-prev disabled>&larr;</button><span class="lab">Page 1</span><button data-next>&rarr;</button></div>'
            f'<div class="stage" data-labels="{labels}"><div class="book" data-s="0">{leaves}</div><div class="mob" tabindex="0">{mob}</div></div></div>'
            f'<script>{(ASSETS / "paper.js").read_text()}</script>')


STATE = """() => { const L = [...document.querySelectorAll('.leaf')], b = document.querySelector('.book');
  return { s: +b.dataset.s, last: b.hasAttribute('data-last'), lab: document.querySelector('.lab').textContent,
    turned: L.filter(l => l.classList.contains('turned')).length, mv: L.filter(l => l.classList.contains('mv')).length,
    ang: L.map(l => Math.round(Math.acos(Math.max(-1, Math.min(1, new DOMMatrix(getComputedStyle(l).transform).a))) * 180 / Math.PI)),
    z: L.map(l => +getComputedStyle(l).zIndex), prev: document.querySelector('[data-prev]').disabled, next: document.querySelector('[data-next]').disabled }; }"""


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class PaperTurn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            cls.br = cls.pw.chromium.launch(channel="chrome")
        except Exception:
            try:
                cls.br = cls.pw.chromium.launch()
            except Exception as e:  # no browser binary
                cls.pw.stop()
                raise unittest.SkipTest(f"no browser: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.br.close()
        cls.pw.stop()

    def open(self, w=1440, h=900, **kw):
        ctx = self.br.new_context(viewport={"width": w, "height": h}, **kw)
        self.addCleanup(ctx.close)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errs, []))
        pg.set_content(page_html())
        pg.wait_for_timeout(1200)  # the opening slide of the cover
        return pg

    def state(self, pg):
        return pg.evaluate(STATE)

    def assertSettled(self, pg, s, msg=""):
        st = self.state(pg)
        n = 3
        self.assertEqual((st["s"], st["turned"], st["mv"]), (s, s, 0), msg + str(st))
        self.assertEqual(st["ang"], [180] * s + [0] * (n - s), msg + str(st))
        self.assertEqual(st["z"], [i + 1 for i in range(s)] + [10 - (i + 1) for i in range(s, n)], msg + str(st))
        self.assertEqual((st["prev"], st["next"], st["last"]), (s == 0, s == n, s == n), msg + str(st))
        return st

    def test_turning_leaf_stays_on_top(self):
        pg = self.open()
        pg.click("[data-next]")
        seen = 0
        for _ in range(6):
            pg.wait_for_timeout(150)
            st = self.state(pg)
            if 0 < st["ang"][0] < 180:  # in the air: it must be above both stacks, not hidden under the next pages
                self.assertEqual(st["z"][0], max(st["z"]), st)
                seen += 1
        self.assertGreater(seen, 2)
        pg.wait_for_timeout(500)
        self.assertSettled(pg, 1)

    def test_rapid_clicks_forward_and_back(self):
        pg = self.open()
        for _ in range(10):
            pg.click("[data-next]", force=True)
            pg.wait_for_timeout(40)
        pg.wait_for_timeout(3500)
        st = self.assertSettled(pg, 3)
        self.assertEqual(st["lab"], "Page 6")
        for _ in range(10):
            pg.click("[data-prev]", force=True)
            pg.wait_for_timeout(40)
        pg.wait_for_timeout(3500)
        self.assertSettled(pg, 0)

    def test_held_arrow_keys(self):
        pg = self.open()
        for _ in range(12):
            pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(3500)
        self.assertSettled(pg, 3)
        for _ in range(12):
            pg.keyboard.press("ArrowLeft")
        pg.wait_for_timeout(3500)
        self.assertSettled(pg, 0)

    def test_reverse_mid_turn(self):
        pg = self.open()
        pg.click("[data-next]")
        pg.wait_for_timeout(300)
        pg.click("[data-prev]")
        pg.wait_for_timeout(3500)
        self.assertSettled(pg, 0)
        pg.click("[data-next]")
        pg.wait_for_timeout(100)
        pg.click("[data-next]")
        pg.click("[data-prev]")
        pg.wait_for_timeout(3500)
        self.assertSettled(pg, 1)

    def test_missed_transitionend_cannot_freeze(self):
        pg = self.open()
        pg.evaluate("document.addEventListener('transitionend', e => e.stopImmediatePropagation(), true)")
        pg.click("[data-next]")
        pg.wait_for_timeout(1500)
        self.assertSettled(pg, 1)
        pg.click("[data-next]")
        pg.click("[data-next]")
        pg.wait_for_timeout(3500)
        self.assertSettled(pg, 3)

    def test_swipe_and_partial_swipe(self):
        pg = self.open()
        pg.mouse.move(900, 400); pg.mouse.down(); pg.mouse.move(700, 410, steps=5); pg.mouse.up()
        pg.wait_for_timeout(1500)
        self.assertSettled(pg, 1)
        pg.mouse.move(900, 400); pg.mouse.down(); pg.mouse.move(880, 400, steps=3); pg.mouse.up()  # too short
        pg.mouse.move(900, 300); pg.mouse.down(); pg.mouse.move(850, 600, steps=3); pg.mouse.up()  # mostly vertical
        pg.wait_for_timeout(1200)
        self.assertSettled(pg, 1)
        pg.mouse.move(700, 400); pg.mouse.down(); pg.mouse.move(900, 400, steps=5); pg.mouse.up()
        pg.wait_for_timeout(1500)
        self.assertSettled(pg, 0)

    def test_reduced_motion_is_instant(self):
        pg = self.open(reduced_motion="reduce")
        pg.click("[data-next]")
        self.assertSettled(pg, 1)
        pg.keyboard.press("ArrowRight"); pg.keyboard.press("ArrowRight"); pg.keyboard.press("ArrowRight")
        self.assertSettled(pg, 3)

    def test_phone_row_rapid_taps_and_label(self):
        pg = self.open(390, 844, has_touch=True, is_mobile=True)
        lab = lambda: pg.inner_text(".lab")
        self.assertEqual(lab(), "Page 1 of 6")
        for _ in range(9):
            pg.click("[data-next]", force=True)
            pg.wait_for_timeout(50)
        pg.wait_for_timeout(1500)
        self.assertEqual(lab(), "Page 6 of 6")
        self.assertTrue(pg.evaluate("document.querySelector('[data-next]').disabled"))
        off = pg.evaluate("(() => { const m = document.querySelector('.mob'), e = m.children[5]; return m.scrollLeft - (e.offsetLeft - (m.clientWidth - e.offsetWidth) / 2); })()")
        self.assertLess(abs(off), 2)
        for _ in range(3):
            pg.click("[data-prev]", force=True)
            pg.wait_for_timeout(50)
        pg.wait_for_timeout(1500)
        self.assertEqual(lab(), "Page 3 of 6")
        self.assertEqual(self.state(pg)["turned"], 0, "the hidden 3D book must not move on a phone")

    def test_resize_across_breakpoint_keeps_the_page(self):
        pg = self.open()
        pg.click("[data-next]"); pg.wait_for_timeout(1300)
        pg.click("[data-next]")
        pg.wait_for_timeout(200)  # mid-turn
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.wait_for_timeout(600)
        self.assertEqual(pg.inner_text(".lab"), "Page 4 of 6")
        pg.set_viewport_size({"width": 1440, "height": 900})
        pg.wait_for_timeout(600)
        self.assertSettled(pg, 2)
        self.assertEqual(pg.inner_text(".lab"), "Pages 4 and 5")


if __name__ == "__main__":
    unittest.main()
