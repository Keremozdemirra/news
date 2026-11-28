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
