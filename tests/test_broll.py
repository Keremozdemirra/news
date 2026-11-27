import json
import unittest
from unittest import mock

from aidaily import broll, desk

OIL = {"id": "pumpjack", "file": "Pumpjack.webm", "path": "a/ab", "source": "commons", "licence": "CC0", "author": "T. Farley",
       "page": "https://commons.wikimedia.org/wiki/File:Pumpjack.webm", "start": 2, "seconds": 30, "people": False,
       "match": r"\b(oil|crude|opec|drilling)\b", "skip": r"\b(gas|lng)\b"}
PORT = dict(OIL, id="terminal", licence="CC BY 4.0", author="R. Abrams", seconds=12,
            match=r"\b(ports?|containers?|shipping|freight)\b", skip="")
CROWD = dict(OIL, id="crowd", people=True, match=r"\boil\b")
SKYLINE = dict(OIL, id="skyline", place=["Singapore"], match=r"\b(property|economy)\b", skip="")
DATA = {"clips": [OIL, PORT, CROWD, SKYLINE]}


class Fit(unittest.TestCase):
    def test_the_clip_must_fit_the_headline(self):
        self.assertEqual(broll.pick("Oil prices rise as OPEC cuts output", data=DATA)["id"], "pumpjack")
        self.assertIsNone(broll.pick("Australia clears law requiring LNG exporters to keep 20% for domestic use", data=DATA))
        self.assertIsNone(broll.pick("Oil and gas groups merge", data=DATA))  # an oil field is no picture of gas
        self.assertIsNone(broll.pick("Eagles beat Cowboys on a late field goal", data=DATA))

    def test_people_place_and_length(self):
        self.assertNotEqual(broll.pick("Oil prices rise", data=DATA, used=["pumpjack"])["id"], "crowd")
        self.assertIsNone(broll.pick("Hong Kong economy grows", data=DATA))
        self.assertEqual(broll.pick("Singapore economy grows", data=DATA)["id"], "skyline")
        self.assertIsNone(broll.pick("Port strike halts container traffic", data=DATA, min_seconds=20))
        self.assertEqual(broll.pick("Port strike halts container traffic", data=DATA, min_seconds=8)["id"], "terminal")

    def test_credit_says_archive_and_names_the_licence(self):
        self.assertEqual(broll.credit(OIL), "Archive footage, not from this event. Video: T. Farley, CC0, via Wikimedia Commons")
        self.assertTrue(broll.credit(PORT).endswith("CC BY 4.0, via Wikimedia Commons. Edited"))

    def test_transcode_url(self):
        self.assertEqual(broll.source_url(dict(OIL, file="Malmö kombiterminal 01.webm", path="f/fa")),
                         "https://upload.wikimedia.org/wikipedia/commons/transcoded/f/fa/Malm%C3%B6_kombiterminal_01.webm/"
                         "Malm%C3%B6_kombiterminal_01.webm.1080p.vp9.webm")

    def test_licence_read_again_at_render(self):
        def info(lic, artist="T. Farley", credit="Own work"):
            return lambda f: {"query": {"pages": {"1": {"imageinfo": [{"extmetadata": {
                "LicenseShortName": {"value": lic}, "Artist": {"value": artist}, "Credit": {"value": credit}}}]}}}}
        self.assertEqual(broll.still_ok(OIL, info("CC0")), (True, ""))
        ok, why = broll.still_ok(OIL, info("CC BY-SA 4.0"))
        self.assertFalse(ok)
        self.assertIn("CC BY-SA", why)
        self.assertFalse(broll.still_ok(OIL, lambda f: 1 / 0)[0])


class Library(unittest.TestCase):
    def test_every_shipped_clip_is_complete_and_open(self):
        clips = broll.load()["clips"]
        self.assertGreaterEqual(len(clips), 8)
        ids = [c["id"] for c in clips]
        self.assertEqual(len(ids), len(set(ids)))
        for c in clips:
            for k in ("file", "path", "source", "licence", "author", "page", "match", "seconds", "checked"):
                self.assertTrue(c.get(k) not in (None, ""), f"{c['id']}: {k}")
            self.assertRegex(c["licence"], r"^(CC0|CC BY \d\.\d|Public domain)$", c["id"])
            self.assertFalse(c.get("people"), c["id"])
            self.assertGreaterEqual(c["seconds"] - c.get("start", 0), 8, c["id"])


class Checks(unittest.TestCase):
    def post(self, **v):
        rec = {"shape": "card", "file": "video.mp4", "cover": "cover.jpg", "spec": [], "headline": "Oil prices rise as OPEC cuts output",
               "photo_file": "P.jpg", "credit": "Photo: A, CC0, via Wikimedia Commons",
               "footage": {"id": "pumpjack", "credit": broll.credit(OIL)}}
        rec.update(v)
        return {"id": "a", "headlines": ["Oil prices rise as OPEC cuts output"], "photo_file": "P.jpg",
                "credit": "Photo: A, CC0, via Wikimedia Commons", "video": rec}

    def test_footage_must_still_be_in_the_library_and_fit(self):
        with mock.patch.object(broll, "load", return_value=DATA):
            self.assertEqual(desk.video_problems(self.post()), [])
            self.assertTrue(desk.video_problems(self.post(footage={"id": "gone", "credit": "x"})))
            self.assertTrue(desk.video_problems(self.post(footage={"id": "pumpjack", "credit": "Video: someone else"})))
            p = self.post()
            p["headlines"] = ["Gas prices rise"]
            p["video"]["headline"] = "Gas prices rise"
            self.assertTrue(desk.video_problems(p))


class MakeVideo(unittest.TestCase):
    def test_footage_that_fails_falls_back_to_the_moving_photo(self):
        from aidaily import cardvideo as CV
        import tempfile
        from pathlib import Path
        built = []

        def fake_build(story, out, shape="card", seconds=8, footage=None):
            built.append((footage, story["_assets"]["credit"]))
            Path(out).write_bytes(b"x")
            return Path(out)
        s = {"title": "Oil prices rise", "headline": "Oil prices rise", "_assets": {"credit": "Photo: A, CC0", "file": "P.jpg"}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(desk, "pick_footage", return_value=OIL), mock.patch.object(CV, "eligible", return_value=""), \
                mock.patch.object(CV, "build", side_effect=fake_build), mock.patch.object(CV, "cover"), \
                mock.patch.object(CV, "audit_file", return_value=[]), mock.patch.object(CV, "focus", return_value=(0.5, 0.5)), \
                mock.patch.object(broll, "fetch", side_effect=RuntimeError("429")), mock.patch.object(desk, "video_shape", return_value="card"):
            rec = desk.make_video(s, Path(tmp), "a")
        self.assertEqual(built, [(None, "Photo: A, CC0")])
        self.assertNotIn("footage", rec)

    def test_off_switch(self):
        with mock.patch.dict(desk.CONFIG, {"video": {"footage": False}}):
            self.assertIsNone(desk.pick_footage({"title": "Oil prices rise"}, "a", 8))


if __name__ == "__main__":
    unittest.main()
