"""Narration: off by default, the key never leaks, beats wait for their line, the voice sits over a quiet bed."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import desk
from aidaily import shortforms as SF
from aidaily import voice as VO

HAVE = bool(shutil.which("ffmpeg"))
SECRET = "-".join(["fixture", "value", "never", "printed"])  # built at runtime: not credential-shaped


def tone(path, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=220:d={seconds}", "-c:a", "libmp3lame",
                    str(path)], check=True)
    return Path(path)


class Switch(unittest.TestCase):
    def test_off_unless_switched_on(self):
        with mock.patch.dict(desk.CONFIG, {"growth": {}}):
            self.assertFalse(VO.on())
        with mock.patch.dict(desk.CONFIG, {"growth": {"shorts_voice": True}}):
            self.assertTrue(VO.on())
        self.assertFalse(json.load(open(Path(desk.__file__).resolve().parent.parent / "desk.json"))["growth"].get("shorts_voice", False))

    def test_key_from_the_environment_only_in_ci(self):
        self.assertEqual(VO.api_key({"ELEVENLABS_API_KEY": SECRET}, keychain=False), SECRET)
        self.assertEqual(VO.api_key({}, keychain=False), "")


class Cap(unittest.TestCase):
    def test_one_narrated_short_a_day(self):
        from aidaily import shorts as SH
        day = f"{desk.now():%Y-%m-%d}"
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(desk.CONFIG, {"growth": {"shorts_voice": True, "shorts_voice_per_day": 1}}), \
                mock.patch.object(VO, "api_key", return_value=SECRET):
            with mock.patch.object(SH, "_state", return_value={"attempted": {}}):
                self.assertIsNotNone(SH.narrator(tmp))
            with mock.patch.object(SH, "_state", return_value={"attempted": {"a": {"at": day + "T08:00:00+00:00", "narrated": True}}}):
                self.assertIsNone(SH.narrator(tmp))
                self.assertIsNotNone(SH.narrator(tmp, narrate=True))  # a sample is not counted


class Speak(unittest.TestCase):
    def test_a_refusal_names_the_status_and_code_never_the_key(self):
        def post(url, headers, body):
            self.assertEqual(headers["xi-api-key"], SECRET)
            self.assertNotIn(SECRET, url)
            return 401, json.dumps({"detail": {"status": "invalid_api_key", "message": f"bad key {SECRET}"}}).encode()
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(VO.VoiceError) as cm:
            VO.speak("Hello.", Path(tmp) / "a.mp3", SECRET, voice="v1", post=post)
        self.assertIn("401", str(cm.exception))
        self.assertIn("invalid_api_key", str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))

    def test_the_words_spoken_are_the_words_on_screen(self):
        sent = {}

        def post(url, headers, body):
            sent.update(json.loads(body))
            return 200, b"ID3fake"
        with tempfile.TemporaryDirectory() as tmp:
            VO.speak("GDP fell 0.2% · full story on boardread.news", Path(tmp) / "a.mp3", SECRET, voice="v1", post=post)
        self.assertEqual(sent["text"], "GDP fell 0.2 percent , full story on boardread dot news")


@unittest.skipUnless(HAVE, "needs ffmpeg")
class Timing(unittest.TestCase):
    def test_a_beat_holds_until_its_line_is_spoken(self):
        with tempfile.TemporaryDirectory() as tmp:
            nar = VO.Narrator(tmp, SECRET, "v1", speak_fn=lambda text, out, key, voice: tone(out, 6.0 if "long" in text else 1.0))
            plan = SF.timeline("b", [(["h"], 4.0, "short line"), (["f"], 4.0, "a long line"), (["s"], 3.0, "short")], "e",
                               say=nar.seconds, end_said="end")
            pages, total = plan
            starts = [p[1] for p in pages if p[3] == "text"]
            self.assertGreaterEqual(starts[2] - starts[1], 6.0 + VO.GAP - 0.01)
            self.assertEqual([w for _, w in plan.cues], ["short line", "a long line", "short", "end"])
            self.assertEqual(len(nar.cues(plan.cues)), 4)

    def test_the_voice_is_loud_and_the_bed_stays_quiet(self):
        from aidaily import audio
        with tempfile.TemporaryDirectory() as tmp:
            bed = audio.silence(Path(tmp) / "bed.wav", 6.0)
            out = VO.mix(bed, [(0.5, tone(Path(tmp) / "a.mp3", 2.0)), (3.0, tone(Path(tmp) / "b.mp3", 2.0))], Path(tmp) / "o.wav", 6.0)
            self.assertAlmostEqual(VO.duration(out), 6.0, delta=0.1)
            self.assertGreater(audio.loudness(out), -22)


if __name__ == "__main__":
    unittest.main()
