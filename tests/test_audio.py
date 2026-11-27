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
        self.assertEqual([c["id"] for c in broll.load()["clips"] if c["audio"]], ["wind-farm-albany"])


@unittest.skipUnless(HAVE, "needs ffmpeg")
class Track(unittest.TestCase):
    def test_no_source_is_true_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = audio.track(Path(tmp) / "a.wav", 5.0)
            s = probe(wav)
            self.assertEqual((s["streams"][0]["sample_rate"], s["streams"][0]["channels"]), ("48000", 2))
            self.assertAlmostEqual(float(s["format"]["duration"]), 5.0, delta=0.05)
            self.assertLessEqual(peak(wav), -90.0)  # volumedetect reports digital zero as its floor, -91 dB

    def test_a_source_keeps_its_sound_as_quiet_even_ambience(self):
        with tempfile.TemporaryDirectory() as tmp:
            levels = []
            for k, amp in enumerate((0.01, 0.5)):  # a quiet and a loud recording end up alike
                src = Path(tmp) / f"src{k}.mp4"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anoisesrc=a={amp}:d=8", "-ac", "2",
                                "-c:a", "aac", str(src)], check=True)
                wav = audio.track(Path(tmp) / f"a{k}.wav", 9.0, src)
                self.assertAlmostEqual(float(probe(wav)["format"]["duration"]), 9.0, delta=0.05)
                levels.append(audio.loudness(wav))
                self.assertLess(peak(wav), -6.0)
            for lv in levels:
                self.assertAlmostEqual(lv, audio.TARGET, delta=1.5)
            self.assertLess(abs(levels[0] - levels[1]), 1.0)


if __name__ == "__main__":
    unittest.main()
