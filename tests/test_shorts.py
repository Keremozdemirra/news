import json
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import cardvideo as CV
from aidaily import desk, platforms, render
from aidaily import shorts as SH
from test_desk import Tmp

CREDIT = "Photo: Jane Roe, CC BY 4.0, via Wikimedia Commons"
GROWTH_ON = {"shorts": True, "shorts_per_day": 2, "shorts_spacing_minutes": 180, "shorts_max_age_hours": 12}


def post(**kw):
    p = {"id": "a", "headlines": ["Spain holds snap election, its fifth general vote in over a decade"],
         "dek": "Center-right leader Alberto Núñez Feijóo is bidding to end Pedro Sánchez's eight-year run in power.",
         "body": "Sánchez called the snap vote, arguing his minority government needs broader support.",
         "sources": ["Bloomberg", "France 24"], "topic": "Politics", "photo_file": "Roe.jpg", "credit": CREDIT}
    p.update(kw)
    return p


class Content(unittest.TestCase):
    def test_facts_skip_the_headline_repeat_and_long_sentences(self):
        p = post(dek="Spain holds a snap election, its fifth general vote in over a decade.", body="x " * 150 + ". Short one here.")
        self.assertEqual(SH.facts(p), ["Short one here."])

    def test_beats_stay_well_under_a_minute(self):
        names = [n for n, _ in SH.beats(post())]
        self.assertEqual(names, ["head", "fact0", "fact1", "sources", "end"])
        self.assertLess(sum(d for _, d in SH.beats(post(dek="w " * 60, body="v " * 60))), 40)

    def test_outlets_line(self):
        self.assertEqual(SH.outlets_line(post()), "Bloomberg and France 24")
        self.assertEqual(SH.outlets_line(post(sources=["A", "B", "C"])), "A, B and C")
        self.assertEqual(SH.outlets_line(post(sources=[])), "")


class Metadata(unittest.TestCase):
    def test_resource_matches_the_channel_rules(self):
        with mock.patch.dict(desk.CONFIG, {"site_url": "https://boardread.news"}):
            m = SH.metadata(post(), CREDIT)
        self.assertEqual(m["snippet"]["categoryId"], "25")
        self.assertIs(m["status"]["selfDeclaredMadeForKids"], False)
        self.assertIs(m["status"]["containsSyntheticMedia"], False)
        d = m["snippet"]["description"]
        self.assertIn("https://boardread.news/s/a/", d)
        self.assertIn("Reported by Bloomberg and France 24.", d)
        self.assertIn("CC BY 4.0, via Wikimedia Commons. Edited", d)
        self.assertIn("#Shorts", d)
        for text in (d, m["snippet"]["title"]):
            self.assertNotRegex(text.lower(), r"written by ai|ai[- ]generated")

    def test_title_and_description_limits(self):
        p = post(headlines=["<b>" + "word " * 40 + "</b>"], dek="é" * 6000)
        self.assertLessEqual(len(SH.title(p)), 100)
        self.assertNotIn("<", SH.title(p))
        self.assertTrue(SH.title(p).endswith("…"))
        self.assertLessEqual(len(SH.description(p, CREDIT).encode("utf-8")), 5000)


class Choice(Tmp):
    def setUp(self):
        super().setUp()
        g = dict(desk.CONFIG.get("growth", {}), **GROWTH_ON)
        p = mock.patch.dict(desk.CONFIG, {"growth": g, "social_min_score": 8.8})
        p.start()
        self.addCleanup(p.stop)

    def good(self, pid="a", **kw):
        base = dict(post(id=pid), status="web", score=9.1, published=desk.now().isoformat())
        base.update(kw)
        return self.write_post(pid, **base)

    def test_due_only_with_the_switch_and_a_candidate(self):
        self.assertEqual(SH.due(), (False, "no candidate"))
        self.good()
        self.assertEqual(SH.due(), (True, ""))
        with mock.patch.dict(desk.CONFIG["growth"], {"shorts": False}):
            self.assertEqual(SH.due(), (False, "switch off"))

    def test_candidates_follow_the_social_bar_and_licence(self):
        self.good("ok")
        self.good("sa", credit="Photo: X, CC BY-SA 4.0, via Wikimedia Commons", headlines=["Other one"])
        self.good("sport", topic="Sport", headlines=["Match won"])
        self.good("low", score=7.0, headlines=["Low score"])
        self.good("old", published=(desk.now() - timedelta(hours=20)).isoformat(), headlines=["Old story"])
        self.good("queued", status="queued", headlines=["Not on the site yet"])
        self.good("nofacts", dek="", body="", headlines=["No facts"])
        self.assertEqual([p["id"] for p in SH.candidates()], ["ok"])

    def test_a_story_is_never_uploaded_twice(self):
        self.good("a")
        self.good("b", headlines=post()["headlines"])  # the same story queued again under a new id
        SH._save({"attempted": {"a": {"at": (desk.now() - timedelta(days=1)).isoformat(), "headline": post()["headlines"][0]}}})
        self.assertEqual(SH.candidates(), [])

    def test_cap_and_spacing(self):
        self.good("c", headlines=["Fresh story"])
        SH._save({"attempted": {"x": {"at": (desk.now() - timedelta(minutes=30)).isoformat(), "headline": "x"}}})
        self.assertEqual(SH.due(), (False, "spacing"))
        SH._save({"attempted": {k: {"at": desk.now().replace(hour=0, minute=1).isoformat(), "headline": k} for k in "xy"}})
        self.assertEqual(SH.due(), (False, "daily cap reached"))
        with mock.patch.dict(desk.CONFIG["growth"], {"shorts_per_day": 500}):
            self.assertEqual(SH.per_day(), SH.HARD_CAP)


class Fake:
    """Answers YouTube's token and upload calls from a script; records each one."""

    def __init__(self, put=None, token=200):
        self.calls, self.put, self.token = [], list(put or [(200, {}, b'{"id": "vid1"}')]), token

    def __call__(self, method, url, headers=None, body=None, timeout=0):
        self.calls.append((method, url, dict(headers or {}), body))
        if url == SH.TOKEN_URL:
            return (self.token, {}, b'{"access_token": "at"}' if self.token == 200 else b'{"error": "invalid_grant"}')
        if method == "POST":
            return 200, {"Location": "https://upload/session/1"}, b""
        r = self.put.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


ENV = {"YT_CLIENT_ID": "id", "YT_CLIENT_SECRET": "secret-abc", "YT_REFRESH_TOKEN": "refresh-xyz"}


class Upload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mp4 = Path(self.tmp.name) / "s.mp4"
        self.mp4.write_bytes(b"x" * 300)

    def test_token_needs_all_three_secrets_and_never_echoes_them(self):
        with self.assertRaises(platforms.Missing):
            SH.access_token(Fake(), env={"YT_CLIENT_ID": "id"})
        f = Fake()
        self.assertEqual(SH.access_token(f, env=ENV), "at")
        self.assertIn(b"grant_type=refresh_token", f.calls[0][3])
        with self.assertRaises(SH.Rejected) as e:
            SH.access_token(Fake(token=400), env=ENV)
        self.assertNotIn("refresh-xyz", str(e.exception))
        self.assertNotIn("secret-abc", str(e.exception))
        self.assertIn("invalid_grant", str(e.exception))

    def test_resumable_session_then_bytes(self):
        f = Fake()
        self.assertEqual(SH.upload(self.mp4, {"snippet": {}}, "at", f), "vid1")
        method, url, h, body = f.calls[0]
        self.assertIn("uploadType=resumable", url)
        self.assertIn("part=snippet%2Cstatus", url)
        self.assertEqual(h["X-Upload-Content-Length"], "300")
        self.assertEqual(h["Authorization"], "Bearer at")
        self.assertEqual(f.calls[1][3], b"x" * 300)

    def test_a_broken_transfer_resumes_where_it_stopped(self):
        f = Fake(put=[OSError("reset"), (308, {"Range": "bytes=0-99"}, b""), (200, {}, b'{"id": "vid2"}')])
        self.assertEqual(SH.upload(self.mp4, {}, "at", f), "vid2")
        last = f.calls[-1]
        self.assertEqual(last[2]["Content-Range"], "bytes 100-299/300")
        self.assertEqual(len(last[3]), 200)

    def test_a_refusal_is_not_retried(self):
        f = Fake(put=[(403, {}, b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}')])
        with self.assertRaises(SH.Rejected) as e:
            SH.upload(self.mp4, {}, "at", f)
        self.assertIn("quotaExceeded", str(e.exception))
        self.assertEqual(sum(1 for c in f.calls if c[0] == "PUT"), 1)


class Run(Choice):
    def render(self, p, out, **kw):
        Path(out).write_bytes(b"mp4")
        return Path(out), CREDIT

    def test_marked_before_upload_and_recorded_after(self):
        self.good()
        with mock.patch.dict("os.environ", ENV), mock.patch.object(CV, "audit_file", return_value=[]):
            self.assertEqual(SH.run(Fake(), render=self.render), "vid1")
        rec = SH._state()["attempted"]["a"]
        self.assertEqual(rec["url"], "https://youtube.com/shorts/vid1")
        self.assertEqual(SH.due(), (False, "spacing"))

    def test_failed_upload_is_never_retried(self):
        self.good()
        f = Fake(put=[(400, {}, b'{"error": {"message": "bad"}}')])
        with mock.patch.dict("os.environ", ENV), mock.patch.object(CV, "audit_file", return_value=[]):
            self.assertIsNone(SH.run(f, render=self.render))
        self.assertIn("bad", SH._state()["attempted"]["a"]["error"])
        self.assertEqual(SH.candidates(), [])

    def test_no_secrets_no_attempt(self):
        self.good()
        with mock.patch.dict("os.environ", {k: "" for k in ENV}):
            self.assertIsNone(SH.run(Fake(), render=self.render))
        self.assertEqual(SH._state().get("attempted", {}), {})

    def test_a_video_off_spec_is_not_uploaded(self):
        self.good()
        f = Fake()
        with mock.patch.dict("os.environ", ENV), mock.patch.object(CV, "audit_file", return_value=["frame rate 25/1"]):
            self.assertIsNone(SH.run(f, render=self.render))
        self.assertFalse(any(c[0] == "PUT" for c in f.calls))
        self.assertEqual(SH._state()["build_failures"], 1)


HAVE_TOOLS = shutil.which("ffmpeg") and (Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME))


class Render(Tmp):
    @unittest.skipUnless(HAVE_TOOLS, "needs ffmpeg and Chrome")
    def test_render_passes_the_vertical_spec(self):
        d = desk.MEDIA / "a"
        d.mkdir(parents=True)
        render.subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1600x1200",
                               "-frames:v", "1", str(d / "photo.jpg")], check=True)
        p = post(dek="", body="")  # no fact beats: a short render
        with mock.patch.multiple(SH, HEAD_SECONDS=2.0, SOURCES_SECONDS=1.5, END_SECONDS=1.5):
            out, credit = SH.build(p, Path(self.tmp.name) / "s.mp4", fetch=False)
        self.assertEqual(credit, CREDIT)
        self.assertEqual(CV.audit_file(out, "reel"), [])


if __name__ == "__main__":
    unittest.main()
