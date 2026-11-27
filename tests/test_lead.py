import io
import json
import os
from contextlib import redirect_stdout
from datetime import timedelta
from unittest import mock

from aidaily import desk, platforms, site
from test_desk import FakeIG as _FakeIG, Tmp
from test_platforms import SECRETS
from test_tiers import stamp


class FakeIG(_FakeIG):
    def post_carousel(self, urls, caption, **kw):
        return super().post_carousel(urls, caption)


class Lead(Tmp):
    """While Instagram is blocked, due queued posts go to the other platforms on a per-platform schedule."""

    def setUp(self):
        _floor = mock.patch.dict(desk.CONFIG, {"facebook_daily_min": 0})  # the quiet-day floor has its own tests
        _floor.start()
        self.addCleanup(_floor.stop)
        super().setUp()
        for p in (mock.patch.dict(os.environ, SECRETS), mock.patch.dict(desk.CONFIG, {"platforms": {n: True for n in platforms.NAMES}})):
            p.start()
            self.addCleanup(p.stop)
        self.sent = []

        class Fake:
            def __init__(self, name, sent):
                self.name, self.sent = name, sent

            def post(self, post):
                self.sent.append((self.name, post["id"]))
                return {"id": f"{self.name}-{post['id']}", "url": ""}
        self.fact = {n: (lambda n=n: Fake(n, self.sent)) for n in platforms.NAMES}
        self.cooldown()

    def cooldown(self, on=True):
        f = desk.STATE / "cooldown.json"
        if on:
            desk._save(f, {"until": (desk.now() + timedelta(hours=5)).isoformat(), "error": "x"})
        elif f.exists():
            f.unlink()

    def post(self, pid, score=10.0, **kw):
        return self.write_post(pid, score=score, headlines=[f"Story {pid}"], **kw)

    def load(self, path):
        return json.loads(path.read_text())

    def at(self, minutes):
        """Run the code `minutes` from now."""
        return mock.patch.object(desk, "now", lambda t=desk.now(): t + timedelta(minutes=minutes))

    def only(self, name):
        return [pid for n, pid in self.sent if n == name]

    def test_best_post_goes_to_every_platform_but_facebook_below_its_floor(self):
        self.post("low", 9.0)
        p = self.post("high", 11.0)
        desk.lead_social(self.fact)
        self.assertEqual(sorted(self.sent), [("bluesky", "high"), ("telegram", "high"), ("threads", "high")])
        got = self.load(p)
        self.assertEqual(got["status"], "queued")  # Instagram still gets it
        self.assertEqual(sorted(got["platforms"]), ["bluesky", "telegram", "threads"])
        self.assertTrue(got["lead_published"])

    def test_facebook_takes_only_what_clears_facebook_min_score(self):
        self.post("big", desk.CONFIG["facebook_min_score"])
        desk.lead_social(self.fact)
        self.assertEqual(self.only("facebook"), ["big"])

    def test_one_post_per_platform_per_run_then_spacing_then_next_best(self):
        self.post("a", 11.0)
        self.post("b", 10.0)
        desk.lead_social(self.fact)
        desk.lead_social(self.fact)
        self.assertEqual(len(self.sent), 3)  # the second run is inside every spacing
        with self.at(31):
            desk.lead_social(self.fact)
        self.assertEqual(sorted(self.sent[3:]), [("bluesky", "b"), ("telegram", "b")])  # threads waits 40
        with self.at(41):
            desk.lead_social(self.fact)
        self.assertEqual(self.only("threads"), ["a", "b"])

    def test_fresher_story_first_at_equal_score(self):
        self.post("old", 10.0, created=stamp(hours=3))
        self.post("new", 10.0, created=stamp(minutes=5))
        desk.lead_social(self.fact)
        self.assertEqual(self.only("threads"), ["new"])

    def test_facebook_daily_max_and_its_90_minute_spacing(self):
        big = desk.CONFIG["facebook_min_score"] + 1
        for i in range(3):
            self.post(f"f{i}", big - i * 0.1)
        with mock.patch.dict(desk.CONFIG, {"facebook_daily_max": 2}):
            desk.lead_social(self.fact)
            with self.at(60):
                desk.lead_social(self.fact)
            self.assertEqual(self.only("facebook"), ["f0"])
            with self.at(91):
                desk.lead_social(self.fact)
            with self.at(200):
                desk.lead_social(self.fact)
        self.assertEqual(self.only("facebook"), ["f0", "f1"])

    def test_ordinary_sport_never_goes_out(self):
        p = self.post("sport", desk.CONFIG["sport_social_min_score"] - 0.5, topic="Sport")
        self.assertEqual(desk.lead_social(self.fact), 0)
        self.assertEqual(self.sent, [])
        self.assertNotIn("platforms", self.load(p))

    def test_floors_age_window_audit_and_future_posts_are_respected(self):
        self.post("below", desk.CONFIG["social_min_score"] - 0.1)
        self.post("stale", 12.0, created=stamp(hours=desk.CONFIG["max_publish_age_hours"] + 1))
        self.post("later", 12.0, publish_after=(desk.now() + timedelta(hours=1)).isoformat())
        self.post("dirty", 12.0, topic="Gardening")
        self.post("web", 12.0, status="web", published=stamp(minutes=1))
        self.assertEqual(desk.lead_social(self.fact), 0)
        self.assertEqual(self.sent, [])

    def test_platform_cooldown_and_switch_are_left_alone(self):
        self.post("a", 11.0)
        desk._save(desk.STATE / "cooldown-bluesky.json", {"until": (desk.now() + timedelta(hours=2)).isoformat()})
        with mock.patch.dict(desk.CONFIG, {"platforms": {**desk.CONFIG["platforms"], "telegram": False}}):
            desk.lead_social(self.fact)
        self.assertEqual(self.sent, [("threads", "a")])

    def test_quiet_hour_holds_threads_and_bluesky_but_not_a_breaking_story(self):
        self.post("calm", 10.0)
        with mock.patch("aidaily.insights.learned_value", lambda k, d=None: [desk.now().hour] if k == "quiet_hours" else d):
            desk.lead_social(self.fact)
            self.assertEqual(self.only("threads") + self.only("bluesky"), [])
            self.assertEqual(self.only("telegram"), ["calm"])
            self.post("breaking", desk.CONFIG["breaking_score"])
            desk.lead_social(self.fact)
        self.assertEqual(self.only("threads"), ["breaking"])

    def test_off_switch(self):
        self.post("a", 11.0)
        with mock.patch.dict(desk.CONFIG, {"lead_when_ig_blocked": False}):
            desk.publish(client=FakeIG())
        self.assertEqual(self.sent, [])

    def test_instagram_not_blocked_keeps_the_old_behaviour(self):
        self.cooldown(False)
        a, b = self.post("a", 11.0), self.post("b", 10.0)
        self.assertFalse(desk.lead_active(FakeIG()))
        ig = FakeIG()
        with mock.patch.dict(platforms.CLIENTS, self.fact):
            self.assertEqual(desk.publish(client=ig), 1)
        self.assertEqual(len(ig.posted), 1)
        self.assertEqual(self.load(b)["status"], "queued")  # not mirrored: it never reached Instagram
        self.assertNotIn("platforms", self.load(b))
        self.assertEqual({pid for _, pid in self.sent}, {"a"})

    def test_publish_leads_when_instagram_is_blocked(self):
        self.post("a", 11.0)
        ig = FakeIG()
        with mock.patch.dict(platforms.CLIENTS, self.fact):
            self.assertEqual(desk.publish(client=ig), 0)
        self.assertEqual(ig.posted, [])
        self.assertEqual(sorted(self.sent), [("bluesky", "a"), ("telegram", "a"), ("threads", "a")])

    def test_leads_when_instagram_is_not_connected(self):
        self.cooldown(False)
        self.post("a", 11.0)
        with mock.patch.dict(os.environ, {"IG_TOKEN": "", "IG_USER_ID": ""}), mock.patch.dict(platforms.CLIENTS, self.fact):
            desk.publish()
        self.assertEqual(self.only("threads"), ["a"])

    def test_web_social_does_not_double_a_platform_inside_its_spacing(self):
        self.post("a", 11.0)
        w = self.write_post("w", status="web", tier="web", score=12.0, urls=["w"], headlines=["Story w"], published=stamp(minutes=1))
        desk.lead_social(self.fact)
        self.assertEqual(desk.web_social(self.fact), 0)
        self.assertNotIn("platforms", self.load(w))
        with self.at(45):
            self.assertEqual(desk.web_social(self.fact), 1)

    def test_no_duplicates_when_instagram_resumes(self):
        p = self.post("a", 11.0)
        desk.lead_social(self.fact)
        first = list(self.sent)
        self.cooldown(False)
        ig = FakeIG()
        with mock.patch.dict(platforms.CLIENTS, self.fact), self.at(5):
            self.assertEqual(desk.publish(client=ig), 1)
        self.assertEqual(len(ig.posted), 1)  # Instagram still gets it
        self.assertEqual(self.load(p)["status"], "published")
        self.assertEqual(self.sent, first)  # and nothing is sent twice
        # facebook was below its floor, so it is still unmarked and nothing else changed
        self.assertEqual(len(set(self.sent)), len(self.sent))

    def test_expired_lead_post_goes_to_the_web_tier_without_resending(self):
        p = self.post("a", 11.0)
        desk.lead_social(self.fact)
        first = list(self.sent)
        with self.at(desk.CONFIG["max_publish_age_hours"] * 60 + 10):
            desk.expire_stale()
            desk.web_social(self.fact)
        self.assertEqual(self.load(p)["status"], "web")
        self.assertEqual(self.sent, first)

    def test_story_page_exists_for_a_led_post(self):
        p = self.post("a", 11.0)
        self.assertEqual(site.published(), [])
        desk.lead_social(self.fact)
        self.assertEqual([x["id"] for x in site.published()], ["a"])
        self.assertEqual(site.published()[0]["published"], self.load(p)["lead_published"])

    def test_failed_send_leaves_no_page_and_is_not_retried(self):
        class Boom:
            def post(self, post):
                raise RuntimeError("down")
        p = self.post("a", 11.0)
        desk.lead_social({n: Boom for n in platforms.NAMES})
        self.assertNotIn("lead_published", self.load(p))
        self.assertEqual(site.published(), [])
        with self.at(60):
            self.assertEqual(desk.lead_social(self.fact), 0)

    def test_dry_run_prints_the_plan_and_sends_nothing(self):
        self.post("a", 11.0)
        self.post("b", 10.0)
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.dict(platforms.CLIENTS, self.fact):
            desk.publish(client=FakeIG(), dry=True)
        text = out.getvalue()
        self.assertIn("threads: now  a", text)
        self.assertRegex(text, r"threads: \d\d:\d\d UTC  b")
        self.assertIn("facebook: nothing due", text)
        self.assertEqual(self.sent, [])
