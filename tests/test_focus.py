"""Where a photo's subject is, and the rules that keep a photo still: every crop is centred on the face, and no photo moves
while it loads or when it is touched."""
import os
import re
import shutil
import struct
import subprocess
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("DESK_SITE_OFFLINE", "1")
from aidaily import desk, focus, site
from test_desk import Tmp

ASSETS = Path(__file__).resolve().parent.parent / "assets-site"


def jpeg_header(w, h):
    """The few bytes jpeg_size reads: SOI, then a baseline SOF0 segment."""
    return b"\xff\xd8" + b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, h, w, 3) + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"


def blob(w, h, x0, x1, y0, y1):
    return [[1 if x0 <= x <= x1 and y0 <= y <= y1 else 0 for x in range(w)] for y in range(h)]


class Geometry(unittest.TestCase):
    def test_jpeg_size_reads_the_header(self):
        p = Path(self.id() + ".jpg")
        try:
            p.write_bytes(jpeg_header(960, 1280))
            self.assertEqual(focus.jpeg_size(p), (960, 1280))
            p.write_bytes(b"not a jpeg")
            self.assertIsNone(focus.jpeg_size(p))
        finally:
            p.unlink(missing_ok=True)
        self.assertIsNone(focus.jpeg_size("/no/such/file.jpg"))

    def test_window_is_centred_on_the_focus(self):
        # 3:4 portrait in a 4:3 box shows 56% of the height; a face at 36% sits in the middle of that window
        px, py = focus.position((0.5, 0.36), (960, 1280), 4 / 3)
        vis = (960 / 1280) / (4 / 3)
        self.assertAlmostEqual(px, 0.5)
        self.assertAlmostEqual(py * (1 - vis) + vis / 2, 0.36, places=3)

    def test_window_stays_inside_the_photo(self):
        self.assertEqual(focus.object_position((0.5, 0.02), (960, 1280), 4 / 3).split()[1], "0%")
        self.assertEqual(focus.object_position((0.5, 0.99), (960, 1280), 4 / 3).split()[1], "100%")

    def test_wide_photo_in_a_tall_box_moves_sideways(self):
        px, py = focus.position((0.2, 0.5), (1400, 1050), 420 / 630)
        self.assertEqual(py, 0.5)
        self.assertLess(px, 0.5)

    def test_same_shape_needs_no_move(self):
        self.assertEqual(focus.object_position((0.3, 0.3), (960, 640), 3 / 2), "50% 50%")

    def test_face_never_gets_a_strip_wider_than_4_3(self):
        portrait = (960, 1280)
        for wanted in ("16/9", "2/1", "3/2"):
            self.assertEqual(focus.box_ratio(wanted, portrait, True), "4/3")
        self.assertEqual(focus.box_ratio("16/9", portrait, False), "16/9")  # a scene keeps its shape
        self.assertEqual(focus.box_ratio("16/9", (1400, 1050), True), "16/9")  # a landscape photo shows the whole head already
        self.assertEqual(focus.box_ratio("4/3", portrait, True), "4/3")

    def test_every_window_of_a_face_shows_it(self):
        """For each shape a page uses, the face (a head 30% of the height tall, centred on the focus) fits the window."""
        size, at = (960, 1280), (0.5, 0.38)
        for wanted in ("3/2", "4/3", "16/9", "2/1"):
            ratio = focus.ratio_value(focus.box_ratio(wanted, size, True))
            py = focus.position(at, size, ratio)[1]
            vis = (size[0] / size[1]) / ratio
            top, bottom = py * (1 - vis), py * (1 - vis) + vis
            if wanted in ("16/9", "2/1", "4/3"):  # shapes the page controls: the head fits
                self.assertLessEqual(top, at[1] - 0.15, wanted)
                self.assertGreaterEqual(bottom, at[1] + 0.15, wanted)


class Detector(unittest.TestCase):
    def test_a_head_in_the_upper_part_is_found(self):
        fx, fy, hw = focus.head_from_mask(blob(64, 85, 22, 40, 8, 30))
        self.assertTrue(0.4 < fx < 0.6)
        self.assertTrue(0.1 < fy < 0.4)
        self.assertTrue(0.2 < hw < 0.4)

    def test_nothing_or_a_backdrop_is_not_a_head(self):
        self.assertIsNone(focus.head_from_mask(blob(64, 85, 0, 0, 0, 0)))
        self.assertIsNone(focus.head_from_mask(blob(64, 85, 2, 62, 2, 60)))  # skin-toned wall: wider than any head
        self.assertIsNone(focus.head_from_mask(blob(64, 85, 5, 6, 5, 6)))  # a speck

    def test_higher_blob_wins_over_a_lower_one(self):
        m = [[a | b for a, b in zip(r1, r2)] for r1, r2 in zip(blob(64, 85, 24, 40, 8, 26), blob(64, 85, 24, 40, 60, 78))]
        self.assertLess(focus.head_from_mask(m)[1], 0.4)


class Where(unittest.TestCase):
    def test_pinned_focus_wins(self):
        self.assertEqual(focus.for_post({"focus": [0.3, 0.2], "person": "A B"}, None), ((0.3, 0.2), True))

    def test_a_scene_is_not_scanned_for_faces(self):
        with mock.patch.object(focus, "detect_face", side_effect=AssertionError("scanned")):
            at, face = focus.for_post({"photo_file": "Container terminal.jpg"}, "/x.jpg", (1400, 1050))
        self.assertEqual((at, face), (focus.PRIOR_SCENE, False))

    def test_a_person_without_a_detection_gets_the_portrait_prior(self):
        with mock.patch.object(focus, "detect_face", return_value=None):
            self.assertEqual(focus.for_post({"person": "A B"}, "/x.jpg", (1050, 1400)), (focus.PRIOR_PORTRAIT, True))
            self.assertEqual(focus.for_post({"photo_file": "X (cropped).jpg"}, "/x.jpg", (1400, 1050))[0], (0.5, 0.35))

    def test_a_head_that_fills_the_frame_is_held_at_the_eyes(self):
        # light hair reads as skin and drags the blob upwards: a big head is kept where eyes and nose sit
        with mock.patch.object(focus, "detect_face", return_value=(0.5, 0.2, 0.55)):
            at, _ = focus.for_post({"person": "A B"}, "/x.jpg", (1050, 1400))
        self.assertEqual(at[1], 0.36)

    def test_commons_names_that_say_portrait_count(self):
        for name in ("Jensen Huang (cropped).jpg", "Official Presidential Portrait.jpg", "X headshot.jpg"):
            self.assertTrue(focus.about_a_face({"photo_file": name}), name)
        self.assertFalse(focus.about_a_face({"photo_file": "NYSE building.jpg", "person": ""}))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg draws the test photos")
class Rendered(Tmp):
    """The pages the build writes: every image reserves its box and no rule moves one."""

    def build(self, size="300x400"):
        pid = "2026-11-26-1300-1"
        self.write_post(pid, status="published", published=desk.now().isoformat(), headlines=["A portrait story"], dek="Dek.", body="Body.",
                        sources=["CNBC"], source_urls=["https://www.cnbc.com/x"], categories=["tech"], person="Ada Lovelace",
                        photo_file="Ada Lovelace (cropped).jpg", credit="Photo: Test")
        (desk.MEDIA / pid).mkdir(parents=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s={size}", "-frames:v", "1",
                        str(desk.MEDIA / pid / "photo.jpg")], check=True)
        stub = lambda *a, **k: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=lambda ph, dest, *a: stub(dest)), mock.patch.object(site, "share_card", side_effect=lambda p, ph, dest: stub(dest)):
            return site.build(self.root / "_site"), pid

    def test_every_photo_reserves_its_box(self):
        out, pid = self.build()
        n = 0
        for f in out.rglob("index.html"):
            for tag in re.findall(r"<img [^>]*/img/[^>]*>", f.read_text()):
                n += 1
                w, h = (int(re.search(rf'{k}="(\d+)"', tag).group(1)) for k in ("width", "height"))
                self.assertEqual((w, h), (300, 400), (f.name, tag))  # the file's own size, never a made-up 960x640
                self.assertRegex(tag, r"object-position:\d+% \d+%")
        self.assertGreater(n, 3)

    def test_the_crop_is_the_same_focus_everywhere(self):
        out, pid = self.build()
        at = site.PHOTOS[pid]["focus"]
        self.assertTrue(site.PHOTOS[pid]["face"])
        art = (out / "s" / pid / "index.html").read_text()
        fig = re.search(r'<figure><span class="pic" style="aspect-ratio:([^"]+)"><img[^>]*object-position:([^"]+)"', art)
        self.assertEqual(fig.group(1), "4/3")  # the article asks for 16:9; a face portrait is not cut into that strip
        self.assertEqual(fig.group(2), focus.object_position(at, (300, 400), 4 / 3))

    def test_a_wide_photo_keeps_the_wide_figure(self):
        out, pid = self.build("400x300")
        art = (out / "s" / pid / "index.html").read_text()
        self.assertIn('class="pic" style="aspect-ratio:16/9"', art)

    def test_photos_are_only_written_by_one_function(self):
        """A hand-written <img> for a story photo would carry its own size and position again; photo_img is the one place."""
        for f in ("site.py", "views.py", "sitepages.py"):
            for line in (Path(site.__file__).parent / f).read_text().splitlines():
                self.assertFalse("<img" in line and "/img/" in line, (f, line[:90]))


class Still(unittest.TestCase):
    """Nothing about a photo moves when the pointer, a tap or the keyboard touches it."""

    def css(self):
        return {p.name: p.read_text() for p in ASSETS.glob("*.css")}

    def rules(self, text):
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.findall(r"([^{}]+)\{([^{}]*)\}", text)

    def test_no_rule_moves_or_rescales_a_photo(self):
        photo = re.compile(r"\bimg\b|\.pic\b|\.ph\b|figure|\.imgc|\.cv-card|\.fcard")
        for name, text in self.css().items():
            for sel, body in self.rules(text):
                if not photo.search(sel) or "@keyframes" in sel:
                    continue
                touching = re.search(r":hover|:active|:focus", sel)
                self.assertFalse(touching and re.search(r"transform|scale|translate|zoom|transition|width|height|margin|padding|border", body),
                                 (name, sel.strip(), body))
                self.assertNotRegex(body, r"transform\s*:\s*[^;]*scale", (name, sel))
                self.assertNotRegex(body, r"\btransition\s*:\s*[^;]*transform", (name, sel))

    def test_focus_outline_is_outside_the_box(self):
        for name, text in self.css().items():
            for sel, body in self.rules(text):
                if ":focus" in sel and "outline" in body:
                    self.assertNotIn("border", body, (name, sel))


if __name__ == "__main__":
    unittest.main()
