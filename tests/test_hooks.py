"""Cover hooks and covers (samples until Kerem approves): true, plain, from the headline's own words; faithful when
read alone; covers inside the Reels safe area with no empty band."""
import shutil
import unittest
from pathlib import Path

from aidaily import covers as CO
from aidaily import hooks as HK
from aidaily import render

PUB = "Sarawak's GPS wins a record 29 state seats unopposed on nomination day GPS needs 13 of the 53 remaining seats."
HAVE = shutil.which("ffmpeg") and (Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME))


class Gate(unittest.TestCase):
    def test_true_short_hooks_pass(self):
        self.assertEqual(HK.gate("29 SEATS UNOPPOSED", "GPS needs 13 of the 53 remaining seats.", PUB), [])

    def test_hype_new_words_numbers_and_length_fail(self):
        for hook, why in (("SHOCKING WIN", "hype"), ("30 SEATS", "number"), ("LANDSLIDE VICTORY", "not in the published"),
                          ("GPS", "words"), ("GPS WINS BIG?", "question")):
            self.assertTrue(any(why in p for p in HK.gate(hook, "GPS needs 13 seats.", PUB)), hook)

    def test_a_hook_that_misleads_read_alone_is_rewritten_or_refused(self):
        calls = []

        def ask(prompt):
            calls.append(prompt)
            if prompt.startswith("A news cover"):
                return "MISLEADING"
            return '{"hook": "29 SEATS UNOPPOSED", "line": "GPS needs 13 of the 53 remaining seats."}'
        hook, line, probs = HK.write({"headlines": ["Sarawak's GPS wins a record 29 state seats unopposed on nomination day"],
                                      "dek": "GPS needs 13 of the 53 remaining seats."}, ask)
        self.assertTrue(probs)  # refused after three tries: no hook cover is made
        self.assertIn("read alone", probs[0])


class Covers(unittest.TestCase):
    def test_chips_are_who_sector_event(self):
        self.assertEqual(CO.chips({"headline": "Hackers breach Air Force cloud", "company": "Air Force", "topic": "Tech"}),
                         ["Air Force", "Tech", "Cybersecurity"])

    @unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
    def test_type_cover_and_today_card_pass_the_gate(self):
        # a typical hook and line; a very short line leaves an empty band and the gate refuses that cover (the Reel then
        # keeps its usual first frame)
        import tempfile
        from aidaily import gate as G
        s = {"headline": "Sarawak's GPS wins a record 29 state seats unopposed", "topic": "Politics"}
        with tempfile.TemporaryDirectory() as tmp:
            for html, fmt, h in ((CO.cover(s, "29 SEATS UNOPPOSED", "GPS needs 13 of the 53 remaining contested seats to secure a state majority.",
                                           kind="short"), "reel", 1920),
                                 (CO.today_card(["Allstate outage hits its website", "US aircraft fire on ship Pacific Archer over Iran blockade",
                                                "Sarawak's GPS wins a record 29 state seats unopposed",
                                                "India finds second unsafe Bisleri water sample"], "Saturday 28 November", "feed"), "feed", 1350)):
                png = Path(tmp) / f"{fmt}.png"
                render.shoot(html, png, 1080, h)
                self.assertEqual(G.check(html, fmt, png=png), [], fmt)


if __name__ == "__main__":
    unittest.main()


class CoverOrder(unittest.TestCase):
    """A photo of the subject first, then the key number, type alone last (Kerem, 2026-11-28)."""

    def make(self, fits=False, found=None, hook="UNSAFE BISLERI SAMPLE", head="India finds second unsafe Bisleri water sample"):
        import json
        from unittest import mock
        from aidaily import covers as CO
        post = {"headlines": [head], "dek": "A sample contained bacteria.",
                "published": "2026-11-28T08:41:47+00:00", "topic": "Business", "company": "Bisleri"}
        ask = lambda p: "FAITHFUL" if "FAITHFUL or MISLEADING" in p else json.dumps({"hook": hook, "line": "A sample had bacteria."})  # noqa: E731
        with mock.patch("aidaily.cardvideo.photo_fits", return_value=fits), \
                mock.patch("aidaily.cardvideo.reel_focus", return_value=(0.5, 0.4, None, None)), \
                mock.patch("aidaily.covers.cover_photo", return_value=found), \
                mock.patch("aidaily.render.shoot"), mock.patch("aidaily.gate.check", return_value=[]):
            html = CO.make_cover(post, {"headline": post["headlines"][0]}, "/tmp/x.jpg" if fits else None, ask=ask)
        return html, CO.LAST_KIND[0]

    def test_the_card_photo_when_it_shows_the_subject(self):
        self.assertEqual(self.make(fits=True)[1], "photo")

    def test_another_photo_of_the_subject_before_the_number_or_type(self):
        from pathlib import Path
        html, kind = self.make(found=(Path("/tmp/b.jpg"), "Photo: someone, CC BY 4.0"), hook="29 SEATS UNOPPOSED", head="GPS wins 29 seats unopposed")
        self.assertEqual(kind, "photo")
        self.assertIn("CC BY 4.0", html)

    def test_the_number_next_then_type_with_its_date(self):
        self.assertEqual(self.make(hook="29 SEATS UNOPPOSED", head="GPS wins 29 seats unopposed")[1], "number")
        html, kind = self.make()
        self.assertEqual(kind, "type")
        self.assertIn("28 November 2026", html)
