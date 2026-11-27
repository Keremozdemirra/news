"""Narration: the key never leaks, one voice per Short chosen and rotated, a credit guard, the voice over a quiet bed.
(Was tests/test_voice.py until e599392 reused that name for the copy voice gate.)"""
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
    def test_the_switch_decides_and_ships_on(self):
        with mock.patch.dict(desk.CONFIG, {"growth": {}}):
            self.assertFalse(VO.on())
        with mock.patch.dict(desk.CONFIG, {"growth": {"shorts_voice": True}}):
            self.assertTrue(VO.on())
        self.assertTrue(json.load(open(Path(desk.__file__).resolve().parent.parent / "desk.json"))["growth"].get("shorts_voice"))  # on, Kerem 2026-11-27

    def test_key_from_the_environment_only_in_ci(self):
        self.assertEqual(VO.api_key({"ELEVENLABS_API_KEY": SECRET}, keychain=False), SECRET)
        self.assertEqual(VO.api_key({}, keychain=False), "")


class Cap(unittest.TestCase):
    def test_one_narrated_short_a_day(self):
        from aidaily import shorts as SH
        day = f"{desk.now():%Y-%m-%d}"
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(desk.CONFIG, {"growth": {"shorts_voice": True, "shorts_voice_per_day": 1}}), \
                mock.patch.object(VO, "api_key", return_value=SECRET), mock.patch.object(VO, "credits_ok", return_value=True):
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
            VO.speak("GDP fell 0.2% · full story on boardread.news", Path(tmp) / "a.mp3", SECRET, voice="v1", post=post,
                     model="eleven_multilingual_v2")
        self.assertEqual(sent["text"], "GDP fell 0.2 percent , full story on boardread dot news")

    def test_one_pause_before_the_key_number_on_v3_and_v4_only(self):
        t = "France has slid into recession. Its economy shrank by zero point two percent in the third quarter."
        self.assertEqual(VO.deliver(t, "eleven_v4").count("[short pause]"), 1)
        self.assertIn("by [short pause] zero point two", VO.deliver(t, "eleven_v4"))
        self.assertEqual(VO.deliver(t, "eleven_multilingual_v2"), t)


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



class Rotation(unittest.TestCase):
    def test_suited_voice_unless_it_spoke_last_then_the_other(self):
        self.assertEqual(VO.choose_voice({"topic": "Markets"}, None)[0], "mark")
        self.assertEqual(VO.choose_voice({"topic": "Markets"}, "mark")[0], "river")
        self.assertEqual(VO.choose_voice({"topic": "Culture"}, "mark")[0], "river")
        self.assertEqual(VO.choose_voice({"topic": "Politics"}, "river")[0], "mark")
        last = None
        for topic in ("Markets", "Economy", "Politics", "Culture", "Culture"):
            name, _ = VO.choose_voice({"topic": topic}, last)
            self.assertNotEqual(name, last)
            last = name


class Credits(unittest.TestCase):
    def test_a_tenth_left_and_room_for_the_script_or_silent(self):
        self.assertTrue(VO.credits_ok(SECRET, get=lambda: {"character_limit": 40000, "character_count": 7000}))
        self.assertFalse(VO.credits_ok(SECRET, get=lambda: {"character_limit": 40000, "character_count": 36500}))
        self.assertFalse(VO.credits_ok(SECRET, get=lambda: 1 / 0))  # unreadable: silent, never held

    def test_the_narrator_respects_the_guard_and_names_its_voice(self):
        from aidaily import shorts as SH
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(desk.CONFIG, {"growth": {"shorts_voice": True, "shorts_voice_per_day": 2}}), \
                mock.patch.object(VO, "api_key", return_value=SECRET), \
                mock.patch.object(SH, "_state", return_value={"attempted": {"a": {"at": "2000-01-01T00:00:00+00:00", "voice": "mark"}}}):
            with mock.patch.object(VO, "credits_ok", return_value=False):
                self.assertIsNone(SH.narrator(tmp, post={"topic": "Markets"}))
            with mock.patch.object(VO, "credits_ok", return_value=True):
                n = SH.narrator(tmp, post={"topic": "Markets"})
        self.assertEqual((n.name, n.voice), ("river", VO.VOICES["river"]))  # Mark spoke last


class KeysStayPut(unittest.TestCase):
    def test_the_model_cli_never_sees_the_voice_or_youtube_keys(self):
        from aidaily import copy
        env = copy.cli_env({"ELEVENLABS_API_KEY": "x", "YT_REFRESH_TOKEN": "y", "ANTHROPIC_API_KEY": "z", "PATH": "/bin"})
        self.assertNotIn("ELEVENLABS_API_KEY", env)
        self.assertNotIn("YT_REFRESH_TOKEN", env)


if __name__ == "__main__":
    unittest.main()
