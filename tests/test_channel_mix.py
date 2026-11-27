"""Every other channel gets the Instagram treatment (Kerem, 2026-11-27): staggered mirroring with per-platform pace,
a format mix per platform, and text that does not repeat what the card already shows."""
import json
import os
import urllib.parse
from datetime import timedelta
from unittest import mock

from aidaily import desk, platforms
from aidaily import shorts as SH
from test_desk import Tmp
from test_platforms import SECRETS, Fake, post as ppost

DELAYS = {"telegram": [2, 15], "threads": [8, 25], "bluesky": [12, 35], "facebook": [25, 60]}


def ago(minutes):
    return (desk.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")


class Mirror(Tmp):
    def setUp(self):
        super().setUp()
        for p in (mock.patch.dict(os.environ, SECRETS),
                  mock.patch.dict(desk.CONFIG, {"platforms": {n: True for n in platforms.NAMES}, "mirror_delay_minutes": DELAYS,
                                                "facebook_daily_min": 0, "facebook_min_score": 0})):
            p.start()
            self.addCleanup(p.stop)
        self.sent = []

        class FakeClient:
            def __init__(self, name, sent):
                self.name, self.sent = name, sent

            def post(self, post):
                self.sent.append((self.name, post["id"]))
                return {"id": f"{self.name}-{post['id']}", "url": "", "format": "photo"}
        self.fact = {n: (lambda n=n: FakeClient(n, self.sent)) for n in platforms.NAMES}

    def ig(self, pid, minutes, **kw):
        return self.write_post(pid, status="published", published=ago(minutes), tier="instagram", **{"score": 12, **kw})

    def test_instagram_publish_sends_nothing_at_once(self):
        p = self.ig("a", 0)
        desk._cross_post(desk._load(p, {}), p)
        self.assertNotIn("platforms", desk._load(p, {}))

    def test_each_platform_takes_the_post_after_its_own_delay(self):
        self.ig("a", 0)
        self.assertEqual(desk.mirror_social(self.fact), 0)
        self.ig("b", 90)  # older than every delay
        desk.mirror_social(self.fact)
        self.assertEqual(sorted(self.sent), [(n, "b") for n in sorted(platforms.NAMES)])
        delays = {n: desk.mirror_delay(n, {"id": "x"}) for n in DELAYS}
        self.assertTrue(all(DELAYS[n][0] <= d <= DELAYS[n][1] for n, d in delays.items()))

    def test_one_post_per_platform_per_run_then_its_spacing(self):
        self.ig("a", 120)
        self.ig("b", 100)
        desk.mirror_social(self.fact)
        self.assertEqual({i for _, i in self.sent}, {"a"})  # the oldest first
        self.assertEqual(desk.mirror_social(self.fact), 0)  # every platform inside its spacing now
        self.assertEqual(len(self.sent), 4)

    def test_facebook_holds_a_post_below_its_bar_and_takes_the_next_one(self):
        with mock.patch.dict(desk.CONFIG, {"facebook_min_score": 11}):
            self.ig("low", 120, score=9)
            self.ig("high", 100, score=13)
            desk.mirror_social(self.fact)
            self.assertIn(("facebook", "high"), self.sent)
            self.assertNotIn(("facebook", "low"), self.sent)
            self.assertNotIn("facebook", desk._load(desk.QUEUE / "low" / "post.json", {}).get("platforms", {}))

    def test_stories_data_and_web_posts_are_not_mirrored(self):
        self.ig("s", 90, kind="story")
        self.ig("d", 90, kind="data")
        self.write_post("w", status="web", tier="web", published=ago(90), score=12)
        self.assertEqual(desk.mirror_social(self.fact), 0)


class Mix(Tmp):
    def sent(self, pid, name, fmt, minutes):
        self.write_post(pid, status="published", published=ago(minutes),
                        platforms={name: {"id": f"{name}-{pid}", "at": ago(minutes), "format": fmt}})

    def test_after_a_video_something_else_unless_the_day_is_short(self):
        self.assertTrue(desk.platform_wants_video("threads"))
        self.sent("a", "threads", "photo", 100)
        self.sent("b", "threads", "video", 50)
        self.assertFalse(desk.platform_wants_video("threads"))  # half the day is video
        for i in range(4):
            self.sent(f"p{i}", "bluesky", "link", 200 - i)
        self.sent("v", "bluesky", "video", 10)
        self.assertTrue(desk.platform_wants_video("bluesky"))  # 1 in 5

    def test_threads_text_only_after_a_photo(self):
        self.sent("a", "threads", "photo", 30)
        seen = []

        def out(req):
            seen.append(req)
            if "threads_publish" in req.full_url:
                return {"id": "m9"}
            return {"status": "FINISHED"} if req.get_method() == "GET" else {"id": "c1"}
        with mock.patch.dict(os.environ, SECRETS):
            got = platforms.Threads(opener=Fake({"/v1.0/": out}), sleep=lambda s: None).post_stills(ppost())
        first = urllib.parse.parse_qs(seen[0].data.decode())
        self.assertEqual((first["media_type"], got["format"]), (["TEXT"], "text"))
        self.assertNotIn("image_url", first)

    def test_facebook_photo_post_after_a_link_post(self):
        self.sent("a", "facebook", "link", 30)
        fake = Fake({"me/accounts": {"data": [{"id": "111", "name": "Boardread", "access_token": "page-tok"}]},
                     "/111/photos": {"id": "ph1", "post_id": "111_5"}})
        with mock.patch.dict(os.environ, SECRETS):
            got = platforms.Facebook(opener=fake).post_stills(ppost())
        sent = urllib.parse.parse_qs([r for r in fake.seen if "/photos" in r.full_url][0].data.decode())
        self.assertEqual(got["format"], "photo")
        self.assertTrue(sent["caption"][0].startswith("Denny's reshares Nvidia"))  # no preview here: the headline leads
        self.assertIn(desk.story_url(ppost()["id"]), sent["caption"][0])  # find() still sees the post
        self.assertTrue(sent["url"][0].endswith(ppost()["cards"][0]))


class ShortsText(Tmp):
    def test_link_first_and_topic_hashtags(self):
        p = ppost(topic="World")
        d = SH.description(p, "")
        self.assertTrue(d.startswith("Full story and sources: https://"))
        self.assertIn("#Shorts #WorldNews #BusinessNews", d)
        self.assertEqual(d.rsplit("\n", 1)[-1], SH.AI_LINE if SH.cfg("shorts_ai_line", False) else "#Shorts #WorldNews #BusinessNews")


class BlueskyLabel(Tmp):
    def test_the_bot_label_is_added_once_and_the_profile_kept(self):
        from aidaily import platforms
        calls = []
        profile = {"value": {"$type": "app.bsky.actor.profile", "displayName": "Boardread", "description": "Bio."}, "cid": "c1"}

        class Fake(platforms.Bluesky):
            def __init__(self):
                self.env = {"BSKY_HANDLE": "h", "BSKY_APP_PASSWORD": "p"}

            def xrpc(self, name, body, jwt=None, raw=None, mime=None):
                calls.append((name, body))
                return {"accessJwt": "j", "did": "did:x"} if name.endswith("createSession") else {}

            def _open(self, req, label):
                return json.dumps(profile).encode()
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}, "growth": {"caption_ai_line": True}}):
            self.assertEqual(desk.bluesky_bot_label({"bluesky": Fake}), "set")
            put = [b for n, b in calls if n.endswith("putRecord")][0]
            self.assertEqual(put["record"]["labels"]["values"], [{"val": "bot"}])
            self.assertEqual((put["record"]["description"], put["swapRecord"]), ("Bio.", "c1"))
            calls.clear()
            self.assertIsNone(desk.bluesky_bot_label({"bluesky": Fake}))  # recorded: never written again
            self.assertEqual(calls, [])
            profile["value"]["labels"] = {"values": [{"val": "bot"}]}
            self.assertEqual(Fake().ensure_bot_label(), "already")


class Withdrawn(Tmp):
    def test_a_withdrawn_post_goes_nowhere_else(self):
        self.assertFalse(desk.social_allowed({"topic": "Tech", "withdrawn": {"at": "x"}}))
        self.assertTrue(desk.social_allowed({"topic": "Tech"}))
