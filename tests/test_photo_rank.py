"""Among photos of one subject that all pass, the strongest goes on the card; relevance still decides which compete."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import entities as E
from aidaily import focus

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


class Strongest(unittest.TestCase):
    def test_the_highest_visual_score_wins_and_a_tie_keeps_relevance_order(self):
        passed = [({"n": 1}, "c1", "First.jpg"), ({"n": 2}, "c2", "Second.jpg"), ({"n": 3}, "c3", "Third.jpg")]
        scores = {"First.jpg": 0.5, "Second.jpg": 0.9, "Third.jpg": 0.52}
        with mock.patch.object(E, "_fetched", side_effect=lambda info, credit, f: (Path(f), credit, f)), \
             mock.patch.object(focus, "visual_score", side_effect=lambda p: scores[p.name]):
            self.assertEqual(E._strongest(passed)[2], "Second.jpg")
            scores["Second.jpg"] = 0.53  # within the tie margin of the first: the more relevant one stays
            self.assertEqual(E._strongest(passed)[2], "First.jpg")

    def test_only_a_few_of_the_most_relevant_compete(self):
        self.assertLessEqual(E.RANK_AMONG, 3)


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg")
class Score(unittest.TestCase):
    def make(self, tmp, src):
        p = Path(tmp) / f"{abs(hash(src))}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-frames:v", "1", str(p)], check=True)
        return p

    def test_a_flat_grey_photo_scores_below_a_clear_subject_on_a_plain_ground(self):
        with tempfile.TemporaryDirectory() as tmp:
            flat = self.make(tmp, "color=c=gray:s=640x480")
            subject = self.make(tmp, "color=c=0x202020:s=640x480,drawbox=x=220:y=140:w=200:h=200:color=white:t=fill")
            noise = self.make(tmp, "nullsrc=s=640x480,geq=random(1)*255:128:128")
            self.assertGreater(focus.visual_score(subject), focus.visual_score(flat) + 0.3)
            self.assertGreater(focus.visual_score(subject), focus.visual_score(noise))


if __name__ == "__main__":
    unittest.main()
