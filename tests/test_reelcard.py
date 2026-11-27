"""The 9:16 video card's layouts: the text stays off the subject, consecutive Reels differ, the fact comes from the dek."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import cardvideo as CV
from aidaily import reelcard as RC
from aidaily import render
from aidaily import templates as T
from test_desk import Tmp

HAVE = shutil.which("ffmpeg") and (Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME))
WIDE = (3840, 2560)  # a landscape photo: a 9:16 crop takes its full height, so fy maps straight onto the frame
STORY = {"title": "South Korean banks' net profit rises 2.1% to 21.5 trillion won",
         "headline": "South Korean banks' net profit rises 2.1% to 21.5 trillion won",
         "dek": "South Korean banks earned more in the third quarter. Net profit of 20 banks rose 500 billion won from 21 "
                "trillion won a year earlier on higher interest income.",
         "topic": "Business", "outlets": ["The Korea Herald", "Yonhap", "Reuters"], "source": "The Korea Herald"}


class Where(unittest.TestCase):
    def test_a_face_keeps_the_text_off_it(self):
        high = RC.allowed(WIDE, (0.5, 0.2), face=True)  # a head in the upper part: the text may go low, not high
        self.assertIn("lower", high)
        self.assertNotIn("top", high)
        low = RC.allowed(WIDE, (0.5, 0.8), face=True)
        self.assertIn("top", low)
        self.assertNotIn("lower", low)
        mid = RC.allowed(WIDE, (0.5, 0.5), face=True)  # in the middle: only the band layouts, text never on the photo
        self.assertEqual(mid, ["photo-top", "photo-bottom"])

    def test_the_face_margin_is_measured_on_the_frame(self):
        for fy in (0.1, 0.2, 0.3, 0.42, 0.6, 0.8, 0.9):
            y, m = RC.subject_y(*WIDE, 0.5, fy), RC.face_margin(WIDE, None)
            for name in RC.allowed(WIDE, (0.5, fy), face=True):
                if name in RC.PLACES:
                    a, b = RC.GEO[name]["span"]
                    self.assertTrue(b < y - m or a > y + m, f"{name} at fy={fy}")

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_a_scene_puts_the_text_over_its_quieter_half(self):
        with tempfile.TemporaryDirectory() as tmp:
            # flat grey above, noise below: the quiet half is the top
            p = Path(tmp) / "p.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=gray:s=1600x1200", "-f", "lavfi",
                            "-i", "nullsrc=s=1600x600,geq=random(1)*255:128:128", "-filter_complex",
                            "[1:v]format=rgb24[n];[0:v][n]overlay=0:600", "-frames:v", "1", str(p)], check=True)
            got = RC.allowed((1600, 1200), (0.5, 0.4), face=False, path=p)
            self.assertEqual(got, ["top"])  # the sky, not the scaffolding: the Spain election Reel of 27 Nov

    def test_a_close_up_head_keeps_the_text_off_its_chin(self):
        # a head 56% of the photo's height, centred at 36%: the chin reaches far below the point
        self.assertNotIn("lower", RC.allowed((2211, 2929), (0.5, 0.36), face=True, head=0.56))
        self.assertIn("lower", RC.allowed((2211, 2929), (0.5, 0.15), face=True, head=0.28))
        self.assertGreater(RC.face_margin((2211, 2929), 0.56), RC.face_margin((2211, 2929), 0.28))

    def test_footage_allows_every_layout(self):
        self.assertEqual(RC.allowed(None, None, False), list(RC.PLACES))

    def test_the_next_reel_takes_another_layout(self):
        for seed in ("a", "b", "c", "2026-11-27-0641-3"):
            first = RC.pick(seed, RC.LAYOUTS)
            self.assertEqual(RC.pick(seed, RC.LAYOUTS), first)  # deterministic
            self.assertNotEqual(RC.pick(seed, RC.LAYOUTS, avoid=first), first)
        self.assertEqual(RC.pick("a", ["lower"], avoid="lower"), "lower")  # nothing else fits: it repeats


class Says(unittest.TestCase):
    def test_the_fact_is_a_dek_sentence_the_headline_lacks_and_its_figure_is_in_it(self):
        big, line = RC.fact(STORY)
        self.assertIn(line, STORY["dek"])
        self.assertEqual(big, "500B won")
        self.assertIn("500 billion won", line)

    def test_no_dek_no_fact_and_the_headline_holds_longer(self):
        s = dict(STORY, dek="")
        self.assertEqual(RC.fact(s), ("", ""))
        parts, total = RC.plan(s)
        self.assertEqual([p[0] for p in parts], ["base", "meta", "head", "source", "end"])
        self.assertEqual(parts[2][2], RC.HEAD_ALONE)

    def test_a_dek_that_restates_the_headline_is_skipped(self):
        s = dict(STORY, dek="South Korean banks' net profit rises 2.1% to 21.5 trillion won.")
        self.assertEqual(RC.fact(s), ("", ""))

    def test_source_line_names_the_newsrooms_only_when_the_meta_line_does_not(self):
        self.assertEqual(RC.source_line(STORY), "Reported by The Korea Herald, Yonhap and Reuters")
        self.assertEqual(RC.source_line(dict(STORY, outlets=["The Korea Herald"])), "")
        self.assertEqual(RC.source_line(dict(STORY, primary="OpenAI blog")), "Announced by OpenAI")

    def test_plan_order_and_length(self):
        parts, total = RC.plan(STORY)
        self.assertEqual([p[0] for p in parts], ["base", "meta", "head", "fact", "source", "end"])
        for (_, a_in, a_out), (_, b_in, _) in zip(parts[2:], parts[3:]):
            self.assertAlmostEqual(a_out, b_in)  # each beat hands over to the next
        self.assertLessEqual(total, 15)
        self.assertAlmostEqual(total, parts[-1][1] + RC.END_SECONDS)


@unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
class SafeArea(unittest.TestCase):
    def test_every_text_layer_of_every_layout_stays_in_the_safe_area(self):
        from test_safe_area import bbox
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "p.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1600x1200", "-frames:v", "1",
                            str(photo)], check=True)
            s = dict(STORY, headline="Taiwan votes Saturday in local elections as officials warn of China interference over "
                                     "the island's referendum", published="2026-11-27T08:00:00+00:00",
                     _assets={"photo": photo.as_uri(), "credit": "Photo: K. Zirkel, CC BY 4.0, via Wikimedia Commons",
                              "file": "P.jpg", "kind": "photo", "logos": []})
            for name in RC.LAYOUTS:
                for part in ("base", "meta", "head", "fact", "source"):
                    png = Path(tmp) / f"{name}-{part}.png"
                    page = RC.layer(s, name, part)
                    if part == "base":  # the wordmark and credit only: the scrim and black ground run edge to edge
                        page = page.replace("</body>", '<style>div[style*="background"]{visibility:hidden}</style></body>')
                    CV.shoot_layer(page, png, CV.W, CV.HEIGHT["reel"])
                    x1, y1, x2, y2 = bbox(png)
                    where = f"{name}/{part}"
                    # the player crops ~54 px a side on a tall phone: 120 px leaves ~6% of the screen; 880 clears the buttons
                    self.assertGreaterEqual(x1, 112, where)
                    self.assertLessEqual(x2, 885, f"{where} reaches x={x2}")
                    self.assertLessEqual(y2, CV.HEIGHT["reel"] - max(T.REEL_SAFE_BOTTOM, 380), f"{where} reaches y={y2}")
                    self.assertGreaterEqual(y1, 200, where)
                    if part == "head" and RC.GEO[name]["band"] != (0, CV.HEIGHT["reel"]):
                        b0, b1 = RC.GEO[name]["band"]
                        self.assertTrue(y2 < b0 or y1 > b1, f"{where}: the headline sits on the photo band")


class Desk(Tmp):
    def test_a_reel_records_its_layout_and_the_next_avoids_it(self):
        from aidaily import desk
        self.write_post("old", video={"shape": "reel", "file": "video.mp4", "layout": "photo-top"})
        seen = {}

        def fake_build(story, out, shape="card", seconds=8, footage=None, layout=None):
            seen.update(shape=shape, seconds=seconds, layout=layout)
            Path(out).write_bytes(b"x")
            return Path(out)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CV, "eligible", return_value=""), mock.patch.object(CV, "build", side_effect=fake_build), \
                mock.patch.object(CV, "cover"), mock.patch.object(CV, "audit_file", return_value=[]), \
                mock.patch.object(CV, "focus", return_value=(0.5, 0.5)), \
                mock.patch.object(CV, "reel_layout", side_effect=lambda s, seed, footage=False, avoid=None: (seen.update(avoid=avoid), "top")[1]):
            rec = desk.make_video(dict(STORY, _assets={}), Path(tmp), "new", shape="reel")
        self.assertEqual(seen["avoid"], "photo-top")
        self.assertEqual((rec["layout"], seen["layout"]), ("top", "top"))
        self.assertEqual(rec["seconds"], RC.plan(STORY)[1])

    def test_the_carousel_card_keeps_its_one_layout(self):
        from aidaily import desk
        seen = {}

        def fake_build(story, out, shape="card", seconds=8, footage=None, layout=None):
            seen.update(layout=layout, seconds=seconds)
            Path(out).write_bytes(b"x")
            return Path(out)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(CV, "eligible", return_value=""), mock.patch.object(CV, "build", side_effect=fake_build), \
                mock.patch.object(CV, "cover"), mock.patch.object(CV, "audit_file", return_value=[]), \
                mock.patch.object(CV, "focus", return_value=(0.5, 0.5)), mock.patch.object(CV, "photo_fits", return_value=True):
            rec = desk.make_video(dict(STORY, _assets={}), Path(tmp), "new", shape="card")
        self.assertIsNone(seen["layout"])
        self.assertNotIn("layout", rec)


if __name__ == "__main__":
    unittest.main()


class FaceAnywhere(unittest.TestCase):
    def test_a_face_counts_even_when_the_story_names_no_person(self):
        from aidaily import focus as F
        s = {"headline": "Musinsa profit jumps", "_assets": {"file": "Model.jpg", "kind": "company"}}
        with mock.patch.object(CV, "photo_path", return_value="p.jpg"), mock.patch.object(CV, "probe_size", return_value=(1000, 1500)), \
                mock.patch.object(F, "detect_face", return_value=(0.6, 0.2, 0.4)):
            fx, fy, face, head = CV.reel_focus(s)
        self.assertTrue(face)
        self.assertEqual((fx, fy), (0.6, 0.2))
        self.assertGreater(head, 0)


class CardVideoFit(Tmp):
    def test_no_card_video_for_a_photo_that_does_not_show_the_story(self):
        from aidaily import desk
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(CV, "eligible", return_value=""), \
                mock.patch.object(CV, "photo_fits", return_value=False), mock.patch.object(CV, "build") as build:
            self.assertIsNone(desk.make_video(dict(STORY, _assets={}), Path(tmp), "x", shape="card"))
        build.assert_not_called()

    def test_the_video_credit_is_set_larger_than_the_still_card(self):
        s = dict(STORY, _assets={"photo": "file:///p.jpg", "credit": "Photo: A, CC0, via Wikimedia Commons", "file": "p.jpg",
                                 "kind": "person", "logos": []})
        with mock.patch.object(T, "layout", return_value="photo"):
            self.assertIn("font-size:22px!important", CV.layer_html(s, "card", "base"))


class Gated(unittest.TestCase):
    def test_a_reel_that_fails_the_gate_is_set_on_black_then_given_up(self):
        calls = []

        def build(story, out, shape="card", seconds=8, footage=None, layout=None):
            calls.append(layout)
            if layout != "plain":
                raise CV.GateFail("text in the app's zone")
            return Path(out)
        with mock.patch.object(CV, "build", side_effect=build):
            self.assertEqual(CV.build_gated({}, "x.mp4", "reel", layout="lower")[1], "plain")
        self.assertEqual(calls, ["lower", "plain"])
        with mock.patch.object(CV, "build", side_effect=CV.GateFail("still bad")), self.assertRaises(CV.GateFail):
            CV.build_gated({}, "x.mp4", "reel", layout="plain")

    @unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
    def test_text_under_the_buttons_or_on_the_wordmark_fails(self):
        s = dict(STORY, headline="Short headline", published="2026-11-27T08:00:00+00:00",
                 _assets={"photo": "", "credit": "Photo: K. Zirkel, CC BY 4.0, via Wikimedia Commons", "file": "P.jpg",
                          "kind": "person", "logos": []})
        base = RC.layer(s, "lower", "base")
        low = RC._wrap('<div style="position:absolute;left:120px;top:1700px;font-size:60px">Under the caption</div>')
        with self.assertRaises(CV.GateFail):
            CV.gate_pages([(base, 0, None, "base"), (low, 0, 3, "text")])
        CV.gate_pages([(base, 0, None, "base"), (RC.layer(s, "lower", "head"), 0, 3, "text")])  # the real headline passes
