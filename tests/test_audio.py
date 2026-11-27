import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aidaily import audio

HAVE = bool(shutil.which("ffmpeg"))


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    return json.loads(out)


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])
    peak = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)[-1])
    return i, peak


class Files(unittest.TestCase):
    def test_owned_beds_and_sting_ship_with_their_note(self):
        self.assertEqual(len(audio.beds()), 3)
        self.assertTrue((audio.DIR / "sting.m4a").exists())
        self.assertIn("belong to Boardread", (audio.DIR / "OWNERSHIP.md").read_text())

    def test_the_story_picks_the_bed_the_same_way_every_time(self):
        self.assertEqual(audio.pick("a"), audio.pick("a"))
        self.assertGreater(len({audio.pick(f"story-{i}")[0] for i in range(30)}), 1)


@unittest.skipUnless(HAVE, "needs ffmpeg")
class Track(unittest.TestCase):
    def test_mobile_loudness_stereo_48k_and_the_sting(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = audio.track(Path(tmp) / "a.wav", 12.0, "story", sting_at=9.5)
            s = probe(wav)["streams"][0]
            self.assertEqual((s["sample_rate"], s["channels"]), ("48000", 2))
            self.assertAlmostEqual(float(probe(wav)["format"]["duration"]), 12.0, delta=0.1)
            i, peak = loudness(wav)
            self.assertAlmostEqual(i, -16, delta=1.5)
            self.assertLess(peak, -1.0)


if __name__ == "__main__":
    unittest.main()
