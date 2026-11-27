"""Facebook Page stories: the same story frames Instagram gets, sent to the Page on their own clock, one per run."""
import json
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import desk, platforms
from tests.test_desk import Tmp, _at


class FakePage:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    last = None

    def last_story_at(self):
        return self.last

    def post_story(self, url):
        if self.fail:
            raise platforms.PlatformError(self.fail)
        self.sent.append(url)
        return {"id": f"9{len(self.sent)}", "url": f"https://www.facebook.com/9{len(self.sent)}"}


class Stories(Tmp):
    def setUp(self):
        super().setUp()
        on = mock.patch.dict(desk.CONFIG, {"facebook_stories": True, "facebook_story_daily_max": 3, "story_spacing_minutes": 40,
                                           "platforms": {**desk.CONFIG["platforms"], "facebook": True}})
        on.start()
        self.addCleanup(on.stop)
        self.t = _at(2, 12)
        clock = mock.patch.object(desk, "now", return_value=self.t)
        clock.start()
        self.addCleanup(clock.stop)

    def story(self, pid, minutes_ago=5, **kw):
        return self.write_post(pid, kind="story", story="story.jpg", urls=[], cards=[],
                               created=(self.t - timedelta(minutes=minutes_ago)).isoformat(),
                               publish_after=(self.t - timedelta(minutes=minutes_ago)).isoformat(), **kw)

    def test_one_frame_per_run_marked_with_its_page_story(self):
        a, b = self.story("2026-11-25-last12", 30), self.story("2026-11-25-number", 10)
        page = FakePage()
        self.assertEqual(desk.fb_stories(lambda: page), 1)
        self.assertEqual(page.sent, ["https://raw.example/r/main/2026-11-25-last12/story.jpg"])
        self.assertEqual(json.loads(a.read_text())["fb_story"]["id"], "91")
        # the next frame waits out story_spacing_minutes after the Page's last story
        self.assertEqual(desk.fb_stories(lambda: page), 0)
        self.assertNotIn("fb_story", json.loads(b.read_text()))

    def test_the_page_is_asked_before_a_send_so_a_stale_run_sends_nothing(self):
        """2026-11-27: runs at 19:00 and 19:02 started from one commit and both sent 2026-11-27-today."""
        p = self.story("2026-11-25-today", 30)
        page = FakePage()
        page.last = self.t - timedelta(minutes=1)  # the other run's send, not yet in this checkout
        self.assertEqual(desk.fb_stories(lambda: page), 0)
        self.assertEqual(page.sent, [])
        self.assertNotIn("fb_story", json.loads(p.read_text()))
        page.last = self.t - timedelta(hours=2)
        self.assertEqual(desk.fb_stories(lambda: page), 1)

    def test_an_unreadable_page_sends_nothing(self):
        self.story("2026-11-25-today", 30)
        page = FakePage()
        page.last_story_at = lambda: (_ for _ in ()).throw(platforms.PlatformError("HTTP 500"))
        self.assertEqual(desk.fb_stories(lambda: page), 0)
        self.assertEqual(page.sent, [])

    def test_an_instagram_tag_frame_never_reaches_the_page(self):
        self.story("2026-11-25-follow", 10, user_tags=[{"username": "boardread", "x": 0.5, "y": 0.5}])
        self.assertIsNone(desk.fb_story_due())

    def test_it_does_not_wait_for_instagram(self):
        self.story("2026-11-25-last12", 30, status="expired", error="too old to go out")
        desk._save(desk.STATE / "cooldown.json", {"until": (self.t + timedelta(hours=5)).isoformat()})
        self.assertEqual(desk.fb_stories(FakePage), 1)

    def test_an_answer_follows_only_a_question_the_page_showed(self):
        self.story("2026-11-25-quiz", 20)
        ans = self.story("2026-11-25-quiz-a", 10, after="2026-11-25-quiz")
        page = FakePage()
        with mock.patch.dict(desk.CONFIG, {"story_spacing_minutes": 0}):
            desk.fb_stories(lambda: page)
            desk.fb_stories(lambda: page)
        self.assertEqual(len(page.sent), 2)
        self.assertEqual(json.loads(ans.read_text())["fb_story"]["id"], "92")
        lone = self.story("2026-11-25-bigger-a", 5, after="2026-11-25-bigger")  # its question never reached the Page
        with mock.patch.dict(desk.CONFIG, {"story_spacing_minutes": 0}):
            self.assertEqual(desk.fb_stories(lambda: page), 0)
        self.assertNotIn("fb_story", json.loads(lone.read_text()))

    def test_daily_cap(self):
        with mock.patch.dict(desk.CONFIG, {"story_spacing_minutes": 0, "facebook_story_daily_max": 1}):
            self.story("2026-11-25-a", 10)
            self.story("2026-11-25-b", 9)
            self.assertEqual(desk.fb_stories(FakePage), 1)
            self.assertEqual(desk.fb_stories(FakePage), 0)

    def test_an_old_frame_or_a_switched_off_page_takes_nothing(self):
        self.story("2026-11-25-old", 4 * 60)  # older than story_max_age_hours: its hour has passed
        self.assertIsNone(desk.fb_story_due())
        self.story("2026-11-25-new", 5)
        self.assertEqual(desk.fb_story_due()[0]["id"], "2026-11-25-new")
        with mock.patch.dict(desk.CONFIG, {"facebook_stories": False}):
            self.assertIsNone(desk.fb_story_due())

    def test_a_failed_send_is_never_repeated_and_auth_pauses_the_page(self):
        p = self.story("2026-11-25-last12", 10)
        with mock.patch.object(desk, "platform_pause") as pause:
            self.assertEqual(desk.fb_stories(lambda: FakePage("(#190) Error validating access token")), 0)
        self.assertIn("error", json.loads(p.read_text())["fb_story"])
        self.assertTrue(pause.called)
        self.assertIsNone(desk.fb_story_due())

    def test_instagram_never_sends_a_page_only_story(self):
        self.story("2026-11-25-games", 10, only="facebook")
        ig = mock.Mock()
        with mock.patch.object(desk, "cooldown_until", return_value=None), mock.patch.object(desk, "fb_stories"), \
             mock.patch.object(desk, "mirror_social"), mock.patch.object(desk, "web_social"), \
             mock.patch.object(desk, "lead_active", return_value=False), mock.patch.object(desk, "evening_digest"):
            desk.publish(ig)
        ig.story.assert_not_called()

    def test_games_story_built_for_the_page_from_puzzle_numbers_only(self):
        from aidaily import games_post
        seen = {}
        live = {"topfloor": {"no": 12, "date": "x", "answer": "SECRET"}, "tickerflip": {"no": 40}, "face-the-figure": {"no": 7}}
        slots = {"games": desk.STORY_SLOTS["games"]}
        with mock.patch.object(games_post, "live_puzzles", return_value=live), mock.patch.object(desk, "STORY_SLOTS", slots), \
             mock.patch.object(desk, "now", return_value=_at(2, 9, 45)), \
             mock.patch.object(desk.R, "shoot", side_effect=lambda html, png, w, h: seen.setdefault("html", html)), \
             mock.patch.object(desk.R, "jpeg"), mock.patch.object(Path, "unlink"):
            made = desk.scheduled_stories()
        self.assertEqual(len(made), 1)
        post = json.loads(Path(made[0]).read_text())
        self.assertEqual(post["only"], "facebook")
        self.assertIn("Topfloor", seen["html"])
        self.assertIn("No. 40", seen["html"])
        self.assertNotIn("SECRET", seen["html"])

    def test_stories_are_still_built_for_the_page_while_instagram_cools_down(self):
        desk._save(desk.STATE / "cooldown.json", {"until": (self.t + timedelta(hours=5)).isoformat()})
        with mock.patch.object(desk, "STORY_SLOTS", {}):
            self.assertEqual(desk.scheduled_stories(), [])  # runs instead of returning early
        with mock.patch.dict(desk.CONFIG, {"facebook_stories": False}), \
             mock.patch.object(desk, "STORY_SLOTS", {"x": (range(7), lambda d, s, l: self.fail("built"))}):
            self.assertEqual(desk.scheduled_stories(), [])


class Client(Tmp):
    def test_photo_is_uploaded_unpublished_then_made_the_story(self):
        fb = platforms.Facebook.__new__(platforms.Facebook)
        fb.env = {"FB_PAGE_TOKEN": "t", "FB_PAGE_ID": "123"}
        fb._page_token = "pt"
        calls = []

        def call(path, params):
            calls.append((path, params))
            return {"id": "555"} if path.endswith("/photos") else {"success": True, "post_id": "777"}
        fb.call = call
        got = fb.post_story("https://raw.example/r/main/x/story.jpg")
        self.assertEqual(calls, [("123/photos", {"url": "https://raw.example/r/main/x/story.jpg", "published": "false"}),
                                 ("123/photo_stories", {"photo_id": "555"})])
        self.assertEqual(got["id"], "777")
        fb.call = lambda path, params: {"id": "1"} if path.endswith("/photos") else {"success": False}
        with self.assertRaises(platforms.PlatformError):
            fb.post_story("https://raw.example/r/main/x/story.jpg")
