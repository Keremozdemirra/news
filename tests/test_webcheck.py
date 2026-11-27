"""The site guards that need no browser: page choice and the link and asset checker (scripts/linkcheck.py,
scripts/webcheck.py). The browser runs themselves are the `webcheck` workflow."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LC, WC = load("linkcheck"), load("webcheck")


def write(root, files):
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


class Pages(unittest.TestCase):
    def test_the_newest_article_and_the_fixed_pages_are_chosen(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"index.html": "x", "latest/index.html": "x", "play/index.html": "x",
                      "s/2026-11-26-1/index.html": "x", "s/2026-11-27-2/index.html": "x"})
            self.assertEqual(WC.pick_pages(d), ["/", "/latest/", "/play/", "/s/2026-11-27-2/"])

    def test_noise_is_ignorable_findings_are_not(self):
        self.assertTrue(WC.ignorable("GET /favicon.ico"))
        self.assertFalse(WC.ignorable("Uncaught TypeError: x is undefined"))


class Links(unittest.TestCase):
    def check(self, files, host=None):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "_site"
            write(site, files)
            if host:
                (Path(d) / "desk.json").write_text(json.dumps({"site_url": f"https://{host}"}))
            return LC.check(site)

    PAGE = '<html><head><meta property="og:image" content="/og/a.jpg"></head><body id="top">{}</body></html>'

    def test_a_clean_site_passes(self):
        self.assertEqual(self.check({"index.html": self.PAGE.format('<a href="/s/a/#sec">a</a><img src="/img/a.jpg" srcset="/img/a.jpg 1x, /img/a-2.jpg 2x"><a href="#top">t</a>'),
                                     "s/a/index.html": '<h2 id="sec">x</h2>', "img/a.jpg": "j", "img/a-2.jpg": "j", "og/a.jpg": "j"}), [])

    def test_a_missing_image_a_srcset_candidate_and_the_share_image_are_named(self):
        got = self.check({"index.html": self.PAGE.format('<img src="/img/gone.jpg" srcset="/img/a.jpg 1x, /img/gone-2.jpg 2x">'), "img/a.jpg": "j"})
        self.assertEqual(len(got), 3)
        self.assertTrue(all("missing" in g for g in got), got)

    def test_an_empty_file_is_named(self):
        self.assertIn("empty", self.check({"index.html": self.PAGE.format('<img src="/img/a.jpg">'), "img/a.jpg": "", "og/a.jpg": "j"})[0])

    def test_a_folder_needs_its_index_and_a_fragment_needs_its_id(self):
        got = self.check({"index.html": self.PAGE.format('<a href="/s/a/">a</a><a href="/s/b/#nope">b</a><a href="#nowhere">c</a>'),
                          "s/a/page.html": "x", "s/b/index.html": '<h2 id="yes"></h2>', "og/a.jpg": "j"})
        self.assertEqual(len(got), 3, got)

    def test_css_urls_and_json_ld_images_are_followed(self):
        ld = '<script type="application/ld+json">{"image": ["https://boardread.news/og/x.jpg"], "publisher": {"logo": {"url": "https://boardread.news/logo.png"}}}</script>'
        got = self.check({"index.html": self.PAGE.format(ld), "og/a.jpg": "j", "assets/a.css": "a{background:url(/img/bg.png)}b{background:url(data:image/png;base64,AA)}"},
                         host="boardread.news")
        self.assertEqual(len(got), 3, got)
        self.assertTrue(any("bg.png" in g for g in got))

    def test_external_links_and_mailto_are_not_fetched(self):
        self.assertEqual(self.check({"index.html": self.PAGE.format('<a href="https://example.com/x">x</a><a href="mailto:a@b.c">m</a><a href="//cdn.test/a.js">c</a>'), "og/a.jpg": "j"}), [])

    def test_a_query_string_does_not_hide_a_missing_file(self):
        self.assertEqual(len(self.check({"index.html": self.PAGE.format('<link rel="x" href="/assets/gone.css?v=1">'), "og/a.jpg": "j"})), 1)

    def test_the_committed_checker_runs_on_the_main_entry(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(LC.main([d]), 2)  # not a built site
            write(d, {"index.html": self.PAGE.format("")})
            self.assertEqual(LC.main([d]), 1)  # the og:image is missing


if __name__ == "__main__":
    unittest.main()
