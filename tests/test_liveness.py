"""Silence alarms (liveness.py): a platform, the stories or the Shorts quiet for too long inside the day, one headline
sent twice, a token date close, and that status.problems() carries them to the health issue."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from aidaily import desk, liveness, status

T = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)


def ago(**kw):
    return (T - timedelta(**kw)).isoformat(timespec="seconds")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.n = 0
        cfg = {**desk.CONFIG, "platforms": {"threads": True, "bluesky": True, "telegram": True, "facebook": True},
               "growth": {**desk.CONFIG.get("growth", {}), "shorts": True}, "token_expiry": {}}
        for p in (mock.patch.object(desk, "QUEUE", root / "queue"), mock.patch.object(desk, "STATE", root / "state"),
                  mock.patch.object(desk, "PAUSED", root / "PAUSED"), mock.patch.object(desk, "HERE", root),
                  mock.patch.object(desk, "now", lambda: T), mock.patch.object(desk, "CONFIG", cfg)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def post(self, headline=None, **kw):
        self.n += 1
        p = {"id": f"p{self.n}", "created": ago(hours=30), "status": "web", "headlines": [headline or f"Story number {self.n}"]}
        if "published" in kw:
            p.update(status="published", media_id="1")
        p.update(kw)
        path = desk.QUEUE / p["id"] / "post.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(p))
        return p

    def sent(self, name, **ago_kw):
        return self.post(platforms={name: {"id": "x", "at": ago(**ago_kw)}})

    def keys(self, fn, *a):
        return [k for k, _ in fn([p for p, _ in desk.posts()], *a)]


class Platforms(Base):
    def test_a_platform_quiet_past_its_limit_is_named(self):
        self.sent("threads", hours=5)
        self.sent("bluesky", hours=1)
        self.assertEqual(self.keys(liveness.silent_platforms, T), ["silent-threads"])

    def test_facebook_has_a_longer_limit_than_the_others(self):
        self.sent("facebook", hours=30)
        self.assertEqual(self.keys(liveness.silent_platforms, T), [])  # 7 h since 08:00
        self.assertEqual(self.keys(liveness.silent_platforms, T.replace(hour=17)), ["silent-facebook"])

    def test_instagram_feed_posts_count_as_instagram_sends(self):
        self.post(published=ago(hours=5))
        self.assertEqual(self.keys(liveness.silent_platforms, T), ["silent-instagram"])
        self.post(published=ago(minutes=30))
        self.assertEqual(self.keys(liveness.silent_platforms, T), [])

    def test_the_night_never_alarms(self):
        self.sent("threads", hours=20)
        night = T.replace(hour=3)
        self.assertEqual(self.keys(liveness.silent_platforms, night), [])

    def test_the_morning_counts_from_the_window_start_not_from_last_night(self):
        self.sent("threads", hours=15)  # 00:00
        self.assertEqual(self.keys(liveness.silent_platforms, T.replace(hour=9)), [])
        self.assertEqual(self.keys(liveness.silent_platforms, T.replace(hour=11, minute=30)), ["silent-threads"])

    def test_a_platform_dead_for_a_week_is_not_this_alarm(self):
        self.sent("threads", days=8)
        self.assertEqual(self.keys(liveness.silent_platforms, T), [])

    def test_a_cooldown_explains_the_silence_until_twice_the_limit(self):
        self.sent("telegram", hours=30)
        desk._save(desk.STATE / "cooldown-telegram.json", {"until": (T + timedelta(hours=1)).isoformat(), "error": "rate"})
        self.assertEqual(self.keys(liveness.silent_platforms, T.replace(hour=14, minute=30)), [])  # 6.5 h, limit 3.5
        self.assertEqual(self.keys(liveness.silent_platforms, T.replace(hour=18, minute=30)), ["silent-telegram"])

    def test_a_platform_switched_off_is_not_watched(self):
        self.sent("threads", hours=6)
        with mock.patch.dict(desk.CONFIG["platforms"], {"threads": False}):
            self.assertEqual(self.keys(liveness.silent_platforms, T), [])


class Stories(Base):
    def story(self, **kw):
        return self.post(kind="story", **kw)

    def test_no_story_for_over_three_hours_is_named(self):
        self.story(published=ago(hours=4))
        self.assertEqual(self.keys(liveness.silent_stories, T), ["silent-stories"])

    def test_a_story_inside_three_hours_is_fine(self):
        self.story(published=ago(hours=2))
        self.assertEqual(self.keys(liveness.silent_stories, T), [])

    def test_a_facebook_story_alone_keeps_the_stories_alive(self):
        self.story(published=ago(hours=9), fb_story={"id": "f", "at": ago(hours=1)})
        self.assertEqual(self.keys(liveness.silent_stories, T), [])

    def test_no_alarm_before_the_first_slots_or_when_stories_were_never_made(self):
        self.story(published=ago(hours=12))
        self.assertEqual(self.keys(liveness.silent_stories, T.replace(hour=7)), [])
        self.assertEqual(self.keys(liveness.silent_stories, T.replace(hour=23, minute=30)), [])

    def test_no_stories_this_week_is_not_this_alarm(self):
        self.story(published=ago(days=9))
        self.assertEqual(self.keys(liveness.silent_stories, T), [])


class Shorts(Base):
    def shorts(self, **at):
        desk._save(desk.STATE / "shorts.json", {"attempted": {k: {"at": v} for k, v in at.items()}})

    def test_no_short_by_two_pm_is_named(self):
        self.shorts(a=ago(hours=24))
        self.assertEqual([k for k, _ in liveness.silent_shorts(T)], ["silent-shorts"])

    def test_a_short_today_is_fine(self):
        self.shorts(a=ago(hours=24), b=ago(hours=2))
        self.assertEqual(liveness.silent_shorts(T), [])

    def test_before_two_pm_is_fine(self):
        self.shorts(a=ago(hours=24))
        self.assertEqual(liveness.silent_shorts(T.replace(hour=13)), [])

    def test_switched_off_or_never_uploaded_this_week_is_fine(self):
        self.shorts(a=ago(days=9))
        self.assertEqual(liveness.silent_shorts(T), [])
        self.shorts(a=ago(hours=24))
        with mock.patch.dict(desk.CONFIG["growth"], {"shorts": False}):
            self.assertEqual(liveness.silent_shorts(T), [])

    def test_the_last_build_error_is_in_the_message_without_control_characters(self):
        desk._save(desk.STATE / "shorts.json", {"attempted": {"a": {"at": ago(hours=24)}}, "build_date": "2026-11-27",
                                                "build_error": "k: no footage\x00"})
        self.assertIn("no footage", liveness.silent_shorts(T)[0][1])


class Duplicates(Base):
    def test_one_headline_twice_on_one_platform_is_named(self):
        self.post("Lab ships a model", platforms={"threads": {"id": "1", "at": ago(hours=5)}}, published=ago(hours=60))
        self.post("Lab ships a model!", platforms={"threads": {"id": "2", "at": ago(hours=2)}}, published=ago(hours=60))
        self.assertEqual(self.keys(liveness.duplicates, T), ["dup-threads"])

    def test_one_headline_on_two_platforms_is_a_crosspost(self):
        self.post("Lab ships a model", platforms={"threads": {"id": "1", "at": ago(hours=5)}, "bluesky": {"id": "2", "at": ago(hours=5)}})
        self.assertEqual(self.keys(liveness.duplicates, T), [])

    def test_two_instagram_posts_with_one_headline_are_named(self):
        self.post("Lab ships a model", published=ago(hours=5))
        self.post("Lab ships a model", published=ago(hours=3))
        self.assertEqual(self.keys(liveness.duplicates, T), ["dup-instagram"])

    def test_stories_and_data_posts_repeat_by_design(self):
        self.post("Last 12 hours", kind="story", published=ago(hours=5))
        self.post("Last 12 hours", kind="story", published=ago(hours=3))
        self.post("Markets close", kind="data", published=ago(hours=5))
        self.post("Markets close", kind="data", published=ago(hours=3))
        self.assertEqual(self.keys(liveness.duplicates, T), [])

    def test_a_repeat_older_than_two_days_is_history(self):
        self.post("Lab ships a model", published=ago(days=3))
        self.post("Lab ships a model", published=ago(hours=3))
        self.assertEqual(self.keys(liveness.duplicates, T), [])


class Tokens(Base):
    def test_a_date_inside_two_weeks_or_past_is_named(self):
        with mock.patch.dict(desk.CONFIG, {"token_expiry": {"threads": "2026-12-05", "facebook": "2027-01-25", "x": "2026-11-01"}}):
            got = dict(liveness.token_dates(T.date()))
        self.assertEqual(sorted(got), ["token-threads", "token-x"])
        self.assertIn("8 days", got["token-threads"])
        self.assertIn("expired", got["token-x"])

    def test_a_date_that_is_not_a_date_is_named_not_raised(self):
        with mock.patch.dict(desk.CONFIG, {"token_expiry": {"threads": "soon"}}):
            self.assertEqual([k for k, _ in liveness.token_dates(T.date())], ["token-threads"])


class InHealth(Base):
    def snap(self, **w):
        return {"paused": False, "platforms": {}, "errors": [], "queue": {"oldest_due": None}, "instagram": {"cooldown_until": None},
                "workflows": w}

    def wf(self, streak, **kw):
        return {"failure_streak": streak, "failures_6h": streak, "last_url": "u", "active": True, **kw}

    def test_silence_reaches_status_problems(self):
        self.sent("threads", hours=5)
        with mock.patch.object(status, "now", lambda: T):
            self.assertEqual([k for k, _ in status.problems(self.snap())], ["silent-threads"])

    def test_two_red_runs_in_a_row_are_enough_for_a_desk_workflow(self):
        with mock.patch.object(status, "now", lambda: T):
            got = status.problems(self.snap(publish=self.wf(2), tick={**self.wf(0)}))
        self.assertEqual([k for k, _ in got], ["wf-publish"])
        with mock.patch.object(status, "now", lambda: T):
            self.assertEqual(status.problems(self.snap(publish=self.wf(1), tick=self.wf(0))), [])

    def test_a_paused_desk_is_silent_on_purpose(self):
        self.sent("threads", hours=5)
        with mock.patch.object(status, "now", lambda: T):
            self.assertEqual(status.problems({**self.snap(), "paused": True}), [])

    def test_health_json_carries_the_active_problems_in_words(self):
        self.sent("threads", hours=5)
        with mock.patch.object(status, "now", lambda: T), mock.patch.object(status.github, "enabled", lambda: False):
            status.health(self.snap())
        state = json.loads((desk.STATE / "health.json").read_text())
        self.assertIn("Threads has sent nothing", state["active"]["silent-threads"])


if __name__ == "__main__":
    unittest.main()
