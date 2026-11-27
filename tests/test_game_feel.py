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
ART_BUDGET = 400 * 1024          # bytes of pictures a game may ship in assets/art, share image apart


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

    def test_the_art_of_a_game_stays_inside_its_budget(self):
        for slug in SLUGS:
            art = GAMES / slug / "assets" / "art"
            size = sum(p.stat().st_size for p in art.rglob("*") if p.is_file())
            self.assertLessEqual(size, ART_BUDGET, f"{slug}: {size // 1024} KB of art")

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


class Balance(unittest.TestCase):
    """Face the Figure's balance is seven sprites moved by transforms, not ninety-eight frames drawn on a canvas."""
    def test_the_sprites_the_rig_loads_are_there(self):
        art = GAMES / "face-the-figure" / "assets" / "art"
        meta = json.loads((art / "scale.json").read_text())
        rig = (GAMES / "face-the-figure" / "js" / "rig.js").read_text()
        for name, box in meta["layers"].items():
            self.assertTrue((art / f"{name}.webp").exists(), name)
            self.assertIn(f'"{name}"', rig)
            self.assertTrue(0 <= box["x"] and box["x"] + box["w"] <= meta["w"] and 0 <= box["y"] and box["y"] + box["h"] <= meta["h"], name)
        self.assertEqual(len(meta["frames"]), len(meta["angles"]))
        self.assertEqual(list(art.glob("back_*")) + list(art.glob("front_*")), [])

    def test_no_canvas_and_no_layout_read_in_a_frame(self):
        rig = (GAMES / "face-the-figure" / "js" / "rig.js").read_text()
        self.assertNotIn("getContext", rig)
        draw = rig[rig.index("function draw("):rig.index("// play a score")]
        self.assertNotIn("offsetHeight", draw)
        self.assertNotIn("clientWidth", draw)

    def test_the_scene_keeps_its_height_between_a_call_and_its_result(self):
        css = (GAMES / "face-the-figure" / "css" / "ftf.css").read_text()
        self.assertRegex(css, r'\.panel\[data-s="play"\],\s*\.panel\[data-s="result"\]\s*\{\s*height:')


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
