"""The five growth switches (desk.json "growth"): off by default, and each one correct when on."""
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import copy, desk, instagram, reel
from aidaily import templates as T
from test_desk import FakeIG, Tmp


def on(**names):
    return mock.patch.dict(desk.CONFIG["growth"], {k: True for k in names})


ST = {"title": "Norse Atlantic suspends all flights as it faces potential collapse",
      "summary": "The carrier is looking for urgent funding, but will file for bankruptcy without a financial lifeline."}
ROW = {"headline": "Norse Atlantic suspends all flights as it faces potential collapse",
       "dek": "The carrier seeks urgent funding and will file for bankruptcy without it.",
       "linkedin_post": "Norse Atlantic has suspended all flights as it faces potential collapse. The carrier is looking for "
                        "urgent funding. It will file for bankruptcy without a financial lifeline.\n\nSource: BBC"}
GOOD = "Passengers booked with the carrier cannot fly while all of its flights are suspended."


class Defaults(unittest.TestCase):
    def test_every_switch_ships_off(self):
        cfg = json.loads((desk.HERE / "desk.json").read_text())["growth"]
        for name in ("so_what", "send_prompt", "alt_text", "keyword_caption", "daily_reel"):
            self.assertIs(cfg[name], False, name)
        self.assertEqual(cfg["reel_trial"], "")

    def test_prompt_has_no_so_what_field_while_off(self):
        with mock.patch.object(copy, "switch", lambda n: False):
            self.assertNotIn("so_what", copy.prompt("S"))
        with mock.patch.object(copy, "switch", lambda n: True):
            self.assertIn("- so_what:", copy.prompt("S"))


class SoWhat(unittest.TestCase):
    def check(self, text, st=ST, row=ROW):
        return copy.check_so_what(st, row, text)

    def test_accepts_a_grounded_consequence(self):
        self.assertEqual(self.check(GOOD), [])

    def test_rejects_restatement_of_headline_dek_or_any_body_sentence(self):
        for t in ("Norse Atlantic suspends all flights as it faces collapse for passengers.",
                  "The carrier is looking for urgent funding from lenders.",  # a body sentence
                  "Passengers see it file for bankruptcy without a financial lifeline."):  # another body sentence
            self.assertTrue(any("repeats" in p for p in self.check(t)), t)

    def test_rejects_a_line_that_names_no_group(self):
        self.assertIn("names no affected group", self.check("The airline has stopped flying and faces bankruptcy unless it secures funding."))

    def test_a_consequence_with_sell_or_buy_is_not_advice(self):
        st = {"title": "New York bans sale of chatbot toys", "summary": "The ban lasts five years."}
        row = {"headline": "New York bans sale of chatbot toys", "dek": "The ban lasts five years."}
        got = copy.check_so_what(st, row, "Retailers cannot sell the toys to buy-side clients there.")
        self.assertFalse([p for p in got if "advice" in p], got)

    def test_rejects_new_number_and_new_name(self):
        self.assertTrue(any("numbers" in p for p in self.check("Customers face delays on 40 routes without funding.")))
        self.assertTrue(any("name not in source" in p for p in self.check("Customers of the carrier turn to Lufthansa without funding.")))

    def test_rejects_advice_speculation_slop_and_shape(self):
        for t in ("Investors should avoid the carrier without funding.", "Customers of the carrier could lose out without funding.",
                  "Delays hit the carrier, not just its funding, but its customers.", "What happens to customers without funding?",
                  "Customers face a landscape of funding trouble without a lifeline."):
            self.assertTrue(self.check(t), t)

    def test_rejects_long_and_empty(self):
        self.assertIn("too long", self.check(" ".join(["carrier funding"] * 14)))
        self.assertEqual(self.check(""), ["empty"])

    def test_apply_keeps_the_line_only_when_on_and_clean(self):
        good = GOOD
        rows = [{"id": 0, **ROW, "topic": "Business", "so_what": good, "relevant": True, "fits_category": True}]
        for state, want in ((True, good), (False, "")):
            story = dict(ST, source="BBC")
            with mock.patch.object(copy, "switch", lambda n, s=state: s):
                self.assertEqual(copy.apply([story], rows), [])
            self.assertEqual(story["so_what"], want)
            self.assertEqual(story["copy_status"], "ok")

    def test_bad_line_costs_only_itself(self):
        rows = [{"id": 0, **ROW, "topic": "Business", "so_what": "Shipments fall 40% on this.", "relevant": True}]
        story = dict(ST, source="BBC")
        with mock.patch.object(copy, "switch", lambda n: True):
            self.assertEqual(copy.apply([story], rows), [])
        self.assertEqual((story["so_what"], story["copy_status"]), ("", "ok"))

    def test_detail_slide_shows_label_only_with_a_line(self):
        story = {"title": "H", "headline": "H", "dek": "d", "_assets": {"logo": "", "credit": "", "photo": ""}}
        self.assertNotIn("What it means", T.detail(story, "Body text.", ["BBC"]))
        page = T.detail(story, "Body text.", ["BBC"], so_what="It matters this way.")
        self.assertIn("What it means", page)
        self.assertIn("It matters this way.", page)

    def test_caption_line_only_when_on(self):
        m = {"headline": "Lab ships a model", "source": "BBC"}
        s = {"topic": "AI", "linkedin_post": "It ships.\n\nSource: BBC", "so_what": "Buyers get a new option.", "outlets": ["BBC"]}
        self.assertNotIn("What it means", desk.caption(m, s))
        with on(so_what=True):
            self.assertIn("What it means: Buyers get a new option.", desk.caption(m, s))
            self.assertEqual(desk.so_what({"so_what": "x."}), "x.")
        self.assertEqual(desk.so_what({"so_what": "x."}), "")


class SendPrompt(unittest.TestCase):
    def test_off_keeps_the_old_line(self):
        self.assertEqual(desk.send_line({"headline": "h"}, {"topic": "Markets"}), desk.CONFIG["send_line"])

    def test_on_picks_an_approved_line_for_the_topic_and_is_stable(self):
        approved = {r["line"]: r["topics"] for r in desk.CONFIG["send_prompts"]}
        self.assertEqual(len(approved), 6)
        with on(send_prompt=True):
            for topic in ("AI", "Tech", "Business", "Markets", "Economy", "Politics", "World", "Culture"):
                seen = set()
                for i in range(40):
                    line = desk.send_line({"headline": f"headline {i}"}, {"topic": topic})
                    seen.add(line)
                    self.assertIn(topic, approved[line])
                    self.assertEqual(line, desk.send_line({"headline": f"headline {i}"}, {"topic": topic}))
                self.assertTrue(seen, topic)
            self.assertGreater(len({desk.send_line({"headline": f"h{i}"}, {"topic": "Business"}) for i in range(40)}), 1)

    def test_lines_are_plain(self):
        for r in desk.CONFIG["send_prompts"]:
            self.assertTrue(r["line"].startswith("Send this to"), r)
            self.assertFalse(desk.SLOP.search(r["line"]))
            self.assertNotRegex(r["line"], r"[^\x00-\x7f]|[?!]")
            self.assertLess(len(r["line"]), 60)


class KeywordCaption(unittest.TestCase):
    S = {"topic": "Tech", "company": "Anthropic", "person": "Dario Amodei", "linkedin_post": "The lab shipped an agent.\n\nSource: X",
         "outlets": ["X"]}

    def test_hashtags_at_most_two_when_on(self):
        with on(keyword_caption=True):
            self.assertEqual(desk.hashtags({}, self.S), ["#tech", "#news"])
            self.assertEqual(desk.hashtags({}, {"topic": "Business"}), ["#business", "#news"])
            self.assertEqual(desk.hashtags({}, {}), ["#news"])
        self.assertGreater(len(desk.hashtags({}, self.S)), 2)

    def test_missing_names_land_in_the_first_125_characters(self):
        m = {"headline": "Lab ships a coding agent and a model", "source": "X"}
        with on(keyword_caption=True):
            text = desk.caption(m, self.S)
        self.assertTrue(text.startswith("Lab ships a coding agent and a model\n\nAnthropic, Dario Amodei · Tech\n\n"))
        self.assertIn("Anthropic", text[:125])
        self.assertIn("Dario Amodei", text[:125])

    def test_no_line_when_the_headline_has_the_names(self):
        m = {"headline": "Anthropic ships an agent, Dario Amodei says", "source": "X"}
        with on(keyword_caption=True):
            text = desk.caption(m, self.S)
        self.assertTrue(text.startswith("Anthropic ships an agent, Dario Amodei says\n\nThe lab shipped"))

    def test_line_never_pushes_a_name_past_125(self):
        long_head = "H" * 80
        line = desk.keyword_line(long_head, "lead", {"company": "A Very Long Company Name Incorporated", "topic": "Markets"})
        self.assertLessEqual(len(long_head) + 2 + len(line), desk.KEY_WINDOW)

    def test_off_is_the_old_caption(self):
        m = {"headline": "Lab ships a coding agent and a model", "source": "X"}
        text = desk.caption(m, self.S)
        self.assertTrue(text.startswith("Lab ships a coding agent and a model\n\nThe lab shipped"))
        self.assertIn("#anthropic", text)


class Alt(Tmp):
    POST = {"headlines": ["Lab ships a model"], "dek": "It runs faster.", "cards": ["card.jpg", "detail.jpg"]}

    def test_off_gives_none_and_on_gives_one_text_per_image(self):
        self.assertIsNone(desk.alt_texts(self.POST))
        with on(alt_text=True):
            self.assertEqual(desk.alt_texts(self.POST), ["Lab ships a model", "Lab ships a model. It runs faster."])
            long = dict(self.POST, dek="x" * 2000)
            self.assertLessEqual(len(desk.alt_texts(long)[1]), 1000)

    def test_publish_passes_alt_text_only_when_on(self):
        class Spy(FakeIG):
            def post_carousel(self, urls, caption, alt_texts=None):
                self.alts = alt_texts
                return super().post_carousel(urls, caption)
        self.write_post("a", cards=["card.jpg", "detail.jpg"], dek="It runs faster.")
        ig = Spy()
        self.assertEqual(desk.publish(client=ig), 1)
        self.assertIsNone(ig.alts)
        self.write_post("b", cards=["card.jpg", "detail.jpg"], dek="It runs faster.", headlines=["Other lab ships"])
        ig = Spy()
        with on(alt_text=True), mock.patch.object(desk, "published_last_24h", return_value=0), \
                mock.patch.object(desk, "last_published", return_value=None):
            self.assertEqual(desk.publish(client=ig), 1)
        self.assertEqual(ig.alts[0], "Other lab ships")


class Opener:
    def __init__(self, fail_alt=False):
        self.bodies, self.fail_alt = [], fail_alt

    def __call__(self, req, timeout=None, context=None):
        body = (req.data or b"").decode()
        self.bodies.append(body)
        if self.fail_alt and "alt_text" in body:
            import io
            import urllib.error
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error":{"message":"Invalid parameter alt_text"}}'))
        import io
        return io.BytesIO(json.dumps({"id": "c1", "status_code": "FINISHED"}).encode())


class Client(unittest.TestCase):
    def test_alt_text_is_sent_on_each_carousel_image(self):
        op = Opener()
        c = instagram.Client("tok", "17", opener=op)
        c.post_carousel(["u1", "u2"], "cap", sleep=lambda s: None, alt_texts=["card alt", "detail alt"])
        self.assertIn("alt_text=card+alt", op.bodies[0])
        self.assertIn("alt_text=detail+alt", op.bodies[1])

    def test_refused_alt_text_does_not_lose_the_image(self):
        op = Opener(fail_alt=True)
        c = instagram.Client("tok", "17", opener=op)
        self.assertEqual(c.image_item("u", "alt"), "c1")
        self.assertNotIn("alt_text", op.bodies[-1])

    def test_no_alt_text_means_the_old_request(self):
        op = Opener()
        instagram.Client("tok", "17", opener=op).image_item("u")
        self.assertNotIn("alt_text", op.bodies[0])

    def test_reel_request_has_the_documented_fields(self):
        op = Opener()
        c = instagram.Client("tok", "17", opener=op)
        c.reel("https://x/reel.mp4", "cap", share_to_feed=True, trial="MANUAL", sleep=lambda s: None)
        body = op.bodies[0]
        for part in ("media_type=REELS", "video_url=https%3A%2F%2Fx%2Freel.mp4", "share_to_feed=true", "trial_params="):
            self.assertIn(part, body)
        self.assertIn("MANUAL", body)
        op2 = Opener()
        instagram.Client("tok", "17", opener=op2).reel("v", "c", sleep=lambda s: None)
        self.assertNotIn("trial_params", op2.bodies[0])


class Reel(Tmp):
    def posts(self, n, score0=5):
        for i in range(n):
            self.write_post(f"2026-11-26-1000-{i}", status="published", published=desk.now().isoformat(timespec="seconds"),
                            headlines=[f"Story {i} happens"], score=score0 + i, topic="Business")

    def at(self, hour):
        t = desk.now().replace(hour=hour, minute=5)
        return mock.patch.object(desk, "now", return_value=t)

    def test_not_due_while_off(self):
        self.posts(5)
        with self.at(19):
            self.assertEqual(reel.due(), (False, "switch off"))

    def test_due_rules(self):
        self.posts(5)
        with on(daily_reel=True):
            with self.at(17):
                self.assertEqual(reel.due(), (False, "before reel_hour"))
            with self.at(18):
                self.assertEqual(reel.due(), (True, ""))
                reel._save({"date": reel.today()})
                self.assertEqual(reel.due(), (False, "already handled today"))
                reel._save({})
                desk.PAUSED.write_text("")
                self.assertEqual(reel.due(), (False, "paused"))

    def test_too_few_posts(self):
        self.posts(2)
        with on(daily_reel=True), self.at(19):
            self.assertEqual(reel.due(), (False, "too few posts today"))

    def test_top_posts_by_score_skip_stories_and_other_days(self):
        self.posts(7)
        self.write_post("2026-11-26-1000-story", status="published", published=desk.now().isoformat(), kind="story", score=99)
        self.write_post("old", status="published", published=(desk.now() - timedelta(days=2)).isoformat(), score=98,
                        headlines=["Old"])
        self.write_post("queued-one", status="queued", score=97)
        got = [p["headlines"][0] for p in reel.top_posts()]
        self.assertEqual(got, [f"Story {i} happens" for i in (6, 5, 4, 3, 2)])

    def test_caption_is_a_numbered_list_and_the_sources_line(self):
        self.posts(3)
        text = reel.caption(reel.top_posts())
        self.assertEqual(text.splitlines()[:3], ["1. Story 2 happens", "2. Story 1 happens", "3. Story 0 happens"])
        self.assertIn("Sources for each story: keremozdemir.de/news", text)

    def test_reel_is_not_cross_posted(self):
        self.assertIn("reel", desk.NO_CROSSPOST)
        post = {"id": "r", "kind": "reel"}
        with mock.patch.object(desk, "cross_post") as cp:
            desk._cross_post(post, Path("x"))
        cp.assert_not_called()

    def test_send_marks_the_day_first_and_posts_once(self):
        self.posts(4)
        reel._save({"build_date": reel.today(), "id": "2026-11-26-1805-reel", "posts": ["2026-11-26-1000-3", "2026-11-26-1000-2"]})

        class IG:
            calls = []

            def reel(self, url, caption, share_to_feed, trial):
                self.calls.append((url, caption, share_to_feed, trial))
                assert reel._state()["attempted"], "marker must be on disk before the call"
                return "m9", "https://instagram.com/reel/x"
        ig = IG()
        with on(daily_reel=True):
            self.assertEqual(reel.send(ig), "m9")
            self.assertIsNone(reel.send(ig))
        self.assertEqual(len(ig.calls), 1)
        self.assertEqual(ig.calls[0][0], "https://raw.example/r/main/2026-11-26-1805-reel/reel.mp4")
        self.assertTrue(ig.calls[0][2])
        self.assertEqual(reel._state()["permalink"], "https://instagram.com/reel/x")

    def test_failed_send_is_not_retried(self):
        reel._save({"build_date": reel.today(), "id": "rid", "posts": []})

        class Bad:
            def reel(self, *a, **k):
                raise instagram.IGError("boom")
        with on(daily_reel=True):
            self.assertIsNone(reel.send(Bad()))
            self.assertIsNone(reel.send(Bad()))
        self.assertEqual(reel._state()["error"], "boom")

    def test_repeated_build_failures_stop_the_day(self):
        self.posts(5)
        with on(daily_reel=True), self.at(19), mock.patch.object(reel, "frames", side_effect=RuntimeError("chrome")):
            for _ in range(3):
                self.assertIsNone(reel.build())
            self.assertEqual(reel.due(), (False, "build failed repeatedly today"))

    def test_trial_param_is_passed_from_config(self):
        reel._save({"build_date": reel.today(), "id": "rid", "posts": []})
        seen = {}

        class IG:
            def reel(self, url, caption, share_to_feed, trial):
                seen["trial"] = trial
                return "m", ""
        with on(daily_reel=True), mock.patch.dict(desk.CONFIG["growth"], {"reel_trial": "SS_PERFORMANCE"}):
            reel.send(IG())
        self.assertEqual(seen["trial"], "SS_PERFORMANCE")

    def test_prune_removes_old_reel_video(self):
        d = desk.MEDIA / "2026-11-10-1800-reel"
        d.mkdir(parents=True)
        (d / "reel.mp4").write_bytes(b"x")
        desk.prune_media()
        self.assertFalse((d / "reel.mp4").exists())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
class Assemble(unittest.TestCase):
    def test_video_meets_the_reels_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            pngs = []
            for i, color in enumerate(("white", "gray", "black")):
                p = Path(tmp) / f"{i}.png"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920",
                                "-frames:v", "1", str(p)], check=True)
                pngs.append(p)
            out = reel.assemble(pngs, Path(tmp) / "out" / "reel.mp4", seconds=1, cover_seconds=1, end_seconds=1)
            probe = json.loads(subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(out)],
                capture_output=True, text=True, check=True).stdout)
            v = next(s for s in probe["streams"] if s["codec_type"] == "video")
            a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
            self.assertEqual((v["codec_name"], v["width"], v["height"], v["pix_fmt"]), ("h264", 1080, 1920, "yuv420p"))
            self.assertEqual(v["r_frame_rate"], "30/1")
            self.assertEqual((a["codec_name"], int(a["sample_rate"])), ("aac", 48000))
            self.assertGreaterEqual(float(probe["format"]["duration"]), 3)
            data = out.read_bytes()
            self.assertNotIn(b"elst", data)  # no edit lists
            self.assertLess(data.find(b"moov"), data.find(b"mdat"))  # moov atom first


if __name__ == "__main__":
    unittest.main()
