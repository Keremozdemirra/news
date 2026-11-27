import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from aidaily import audio, broll

HAVE = bool(shutil.which("ffmpeg"))


def probe(path):
    return json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                     capture_output=True, text=True).stdout)


def peak(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.findall(r"max_volume: (-?[\d.inf]+) dB", r.stderr)[-1])


class NoMusic(unittest.TestCase):
    def test_no_generated_music_ships(self):
        root = Path(audio.__file__).resolve().parent.parent
        self.assertFalse((root / "scripts" / "make_audio.py").exists())
        self.assertFalse(list((root / "aidaily").glob("audio/*.m4a")))

    def test_only_checked_clips_keep_their_sound(self):
        for c in broll.load()["clips"]:
            self.assertIn("audio", c, c["id"])
            if c["audio"]:
                self.assertIn("no music or speech", c.get("audio_note", ""), c["id"])


@unittest.skipUnless(HAVE, "needs ffmpeg")
class Track(unittest.TestCase):
    def test_no_source_is_true_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = audio.track(Path(tmp) / "a.wav", 5.0)
            s = probe(wav)
            self.assertEqual((s["streams"][0]["sample_rate"], s["streams"][0]["channels"]), ("48000", 2))
            self.assertAlmostEqual(float(s["format"]["duration"]), 5.0, delta=0.05)
            self.assertLessEqual(peak(wav), -90.0)  # volumedetect reports digital zero as its floor, -91 dB

    def test_a_source_keeps_its_sound_levelled_and_padded(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            # a quiet noise track stands in for a field recording: it is raised, but at most MAX_GAIN dB
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=a=0.01:d=4", "-ac", "2",
                            "-c:a", "aac", str(src)], check=True)
            before = audio.loudness(src)
            wav = audio.track(Path(tmp) / "a.wav", 6.0, src)
            self.assertAlmostEqual(float(probe(wav)["format"]["duration"]), 6.0, delta=0.05)
            after = audio.loudness(wav)
            self.assertLessEqual(after - before, audio.MAX_GAIN + 1)
            self.assertGreater(after, before)
            self.assertLess(peak(wav), -1.0)


if __name__ == "__main__":
    unittest.main()
