"""What makes the three games feel slow or cheap on a phone, pinned so it does not come back.

Measured 27 Nov on a 4x throttled CPU at 390 px: Topfloor dropped 73% of its opening frames while 30,000 names were
parsed on the page's thread, Face the Figure fetched 7 MB of balance frames and the scene jumped at every result,
Tickerflip's two hall backdrops were 3.4 MB of PNG.
"""
import json, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES = ROOT / "games"
SLUGS = ("topfloor", "tickerflip", "face-the-figure")


def without_hover_media(css):
    """The stylesheet with every @media (hover: hover) block cut out."""
    out, i = [], 0
    for m in re.finditer(r"@media\s*\(hover:\s*hover\)[^{]*\{", css):
        if m.start() < i:
            continue
        depth, j = 1, m.end()
        while depth and j < len(css):
            depth += {"{": 1, "}": -1}.get(css[j], 0); j += 1
        out.append(css[i:m.start()]); i = j
    return "".join(out) + css[i:]


class Weight(unittest.TestCase):
    def test_no_game_ships_a_png(self):
        for slug in SLUGS:
            self.assertEqual([p.name for p in (GAMES / slug / "assets").rglob("*.png")], [], slug)

    def test_a_game_without_its_data_and_share_image_is_small(self):
        # code, style and markup: what a visitor fetches before the day's data
        for slug in SLUGS:
            size = sum(p.stat().st_size for p in (GAMES / slug).rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".html"))
            self.assertLessEqual(size, 120 * 1024, f"{slug}: {size // 1024} KB")

    def test_render_sources_are_not_copied_to_the_site(self):
        src = (ROOT / "aidaily" / "play.py").read_text()
        skip = src[src.index("SKIP = "):src.index("\n", src.index("SKIP = "))]
        self.assertIn('"frames"', skip)
        self.assertIn('"png"', skip)

    def test_every_picture_a_stylesheet_names_exists(self):
        for slug in SLUGS:
            for css in (GAMES / slug / "css").glob("*.css"):
                for ref in re.findall(r'url\("?(\.\./assets/[^")]+)"?\)', css.read_text()):
                    self.assertTrue((css.parent / ref).resolve().exists(), f"{slug}: {ref}")


class System(unittest.TestCase):
    """Kerem, 27 Nov, after seeing both: the flat site system. Paper and ink, the site's two type families, no
    rendered art, no gradients or shadows, motion on transform and opacity alone."""
    def css(self, slug):
        return re.sub(r"/\*.*?\*/", "", next((GAMES / slug / "css").glob("*.css")).read_text(), flags=re.S)

    def test_only_the_sites_type_families_and_its_own_font_files(self):
        for slug in SLUGS:
            css = self.css(slug)
            fams = set(re.findall(r'font-family:\s*"([^"]+)"', css))
            self.assertEqual(fams, {"Libre Franklin", "Newsreader", "Franklin Fallback"}, slug)
            for url in re.findall(r'url\("([^"]+\.woff2[^"]*)"\)', css):
                self.assertTrue(url.startswith("/fonts/"), f"{slug}: {url}")       # the files the site already serves and caches
            self.assertFalse((GAMES / slug / "assets" / "fonts").exists(), slug)

    def test_no_rendered_art_no_shadow_no_blur_no_radius(self):
        for slug in SLUGS:
            css = self.css(slug)
            self.assertFalse((GAMES / slug / "assets" / "art").exists(), slug)
            self.assertFalse((GAMES / slug / "art").exists(), slug)
            for banned in ("drop-shadow", "blur(", "gradient", "backdrop-filter", "text-shadow"):
                self.assertNotIn(banned, css, f"{slug}: {banned}")
            for m in re.finditer(r"box-shadow:\s*([^;]+);", css):
                self.assertTrue(all(part.strip().startswith("inset") for part in m.group(1).split(",")), f"{slug}: {m.group(0)}")   # a flat inset rule, never a cast shadow
            for m in re.finditer(r"border-radius:\s*([^;]+);", css):
                self.assertEqual(m.group(1).strip(), "0", f"{slug}: {m.group(0)}")

    def test_motion_is_transform_and_opacity_and_short(self):
        for slug in SLUGS:
            css = self.css(slug)
            for m in re.finditer(r"transition:\s*([^;]+);", css):
                for part in m.group(1).split(","):
                    prop = part.split()[0]
                    self.assertIn(prop, ("transform", "opacity", "none"), f"{slug}: {m.group(0)}")
                    ms = re.search(r"(\d+)ms", part)
                    if ms: self.assertLessEqual(int(ms.group(1)), 250, f"{slug}: {m.group(0)}")
            for body in re.findall(r"@keyframes\s+\w+\s*\{((?:[^{}]*\{[^{}]*\})*)", css):
                for prop in re.findall(r"([a-z-]+)\s*:", re.sub(r"[\d%a-z, ]+\{", "", body)):
                    self.assertIn(prop, ("transform", "opacity"), f"{slug}: keyframes animate {prop}")
            self.assertIn("prefers-reduced-motion", css, slug)

    def test_the_page_has_no_frame_loop_for_its_clock(self):
        page = (GAMES / "topfloor" / "js" / "topfloor.js").read_text()
        clock = page[page.index("function clockRun"):page.index("function onClock")]
        self.assertNotIn("requestAnimationFrame", clock)
        self.assertIn(".animate(", clock)


class Lists(unittest.TestCase):
    """Topfloor's answer lists are read and searched in a worker."""
    def test_the_page_never_parses_a_list(self):
        page = (GAMES / "topfloor" / "js" / "topfloor.js").read_text()
        self.assertNotIn("match.js", page)
        self.assertNotIn(".entries.", page)
        self.assertIn("lists.worker.js", page)
        worker = (GAMES / "topfloor" / "js" / "lists.worker.js").read_text()
        self.assertIn('from "./match.js"', worker)


class Touch(unittest.TestCase):
    def test_hover_styles_are_for_pointers_that_hover(self):
        # a finger leaves :hover on what it tapped; on a phone that looked like a key still held down
        for slug in SLUGS:
            for css in (GAMES / slug / "css").glob("*.css"):
                left = without_hover_media(re.sub(r"/\*.*?\*/", "", css.read_text(), flags=re.S))
                self.assertNotIn(":hover", left, f"{slug}/{css.name}")


class ShareDate(unittest.TestCase):
    """The link preview carries the puzzle's number and date. Pillow draws it at build time and only there."""
    def test_pillow_is_pinned_for_the_build_and_imported_nowhere_else(self):
        req = [l.strip() for l in (ROOT / "requirements-build.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(len(req), 1)
        self.assertRegex(req[0], r"^Pillow==\d+\.\d+\.\d+$")
        self.assertIn("pip install --quiet -r requirements-build.txt", (ROOT / ".github" / "workflows" / "site.yml").read_text())
        users = [p.name for p in (ROOT / "aidaily").glob("*.py") if re.search(r"^\s*(from PIL|import PIL)", p.read_text(), re.M)]
        self.assertEqual(users, ["play.py"])
        src = (ROOT / "aidaily" / "play.py").read_text()
        self.assertNotRegex(src, r"(?m)^(from PIL|import PIL)")          # inside the function: a machine without it still builds

    def test_the_card_is_dated_and_the_preview_url_changes_with_the_day(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        import shutil, sys, tempfile
        sys.path.insert(0, str(ROOT))
        from aidaily import play
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "topfloor"
            shutil.copytree(GAMES / "topfloor", dest, ignore=shutil.ignore_patterns("*.py", "lists"))
            before = Image.open(dest / "assets" / "share.jpg").convert("RGB")
            self.assertTrue(play.dated_share("topfloor", dest))
            after = Image.open(dest / "assets" / "share.jpg").convert("RGB")
            self.assertEqual(after.size, (1200, 630))
            box = (60, 496, 600, 536)                                     # where the date line is set
            self.assertNotEqual(list(before.crop(box).getdata()), list(after.crop(box).getdata()))
            day = json.loads((dest / "assets" / "data" / "today.json").read_text())["date"]
            html = (dest / "index.html").read_text()
            self.assertEqual(html.count(f"/assets/share.jpg?d={day}\""), 2)
            self.assertNotIn("/assets/share.jpg\"", html)

    def test_no_today_file_leaves_the_card_as_it_is(self):
        import shutil, sys, tempfile
        sys.path.insert(0, str(ROOT))
        from aidaily import play
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "g"; (dest / "assets").mkdir(parents=True)
            shutil.copy(GAMES / "topfloor" / "assets" / "share.jpg", dest / "assets" / "share.jpg"); (dest / "index.html").write_text("x")
            size = (dest / "assets" / "share.jpg").stat().st_size
            self.assertFalse(play.dated_share("g", dest))
            self.assertEqual((dest / "assets" / "share.jpg").stat().st_size, size)
