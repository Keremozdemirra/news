"""The Instagram mix (Kerem, 2026-11-27): formats alternate, slots carry a fixed jitter, stories spread out."""
import unittest
from datetime import timedelta
from unittest import mock

from aidaily import desk
from test_desk import Tmp

CARD = {"shape": "card", "file": "video.mp4"}
REEL = {"shape": "reel", "file": "video.mp4"}


def ago(minutes):
    return (desk.now() - timedelta(minutes=minutes)).isoformat()


class Formats(unittest.TestCase):
    def test_what_instagram_shows(self):
        self.assertEqual(desk.ig_format({}), "photo")
        self.assertEqual(desk.ig_format({"video": CARD}), "card")
        self.assertEqual(desk.ig_format({"video": REEL}), "reel")
        self.assertEqual(desk.ig_format({"video": CARD, "ig_stills": True}), "photo")
        self.assertEqual(desk.ig_format({"kind": "data"}), "data")

    def test_jitter_is_fixed_and_bounded(self):
        vals = {desk.jitter(f"2026-11-27-1300-{i}", 10) for i in range(200)}
        self.assertEqual(desk.jitter("a", 10), desk.jitter("a", 10))
        self.assertTrue(all(-10 <= v <= 10 for v in vals))
        self.assertGreater(len(vals), 10)
        with mock.patch.dict(desk.CONFIG, {"slot_jitter_minutes": 10}):
            self.assertTrue(all(0 <= desk.extra_minutes(f"p{i}") <= 10 for i in range(200)))


class Plan(Tmp):
    def sent(self, pid, minutes, **kw):
        self.write_post(pid, status="published", published=ago(minutes), publish_after=ago(minutes), tier="instagram", **kw)

    def test_video_after_photo_photo_after_video(self):
        self.assertEqual(desk.plan_format(True), "card")  # nothing before: a video
        self.sent("a", 100)
        self.assertEqual(desk.plan_format(True), "card")
        self.assertEqual(desk.plan_format(False), "photo")
        self.sent("b", 50, video=CARD)
        self.assertEqual(desk.plan_format(True), "photo")  # the day is at half video already
        self.sent("c", 10)
        self.assertEqual(desk.plan_format(True), "reel")  # shapes alternate on Instagram

    def test_a_day_short_of_video_takes_the_other_shape_after_a_video(self):
        for i in range(4):
            self.sent(f"p{i}", 200 - i)
        self.sent("v", 20, video=CARD)
        self.assertEqual(desk.plan_format(True), "reel")
        self.sent("w", 10, video=REEL)
        self.assertEqual(desk.plan_format(True), "card")

    def test_web_posts_and_stills_do_not_count_as_shown_video(self):
        self.sent("a", 60, video=REEL, ig_stills=True)
        self.write_post("w", status="web", tier="web", published=ago(5), video=REEL)
        self.assertEqual(desk.plan_format(True), "card")


class Rotate(Tmp):
    def test_another_format_goes_first_unless_breaking(self):
        self.write_post("last", status="published", published=ago(60), publish_after=ago(60), tier="instagram")
        a = self.write_post("a", publish_after=ago(20))
        b = self.write_post("b", publish_after=ago(10), video=CARD)
        due = [({"id": "a", "publish_after": ago(20)}, a), ({"id": "b", "publish_after": ago(10), "video": CARD}, b)]
        self.assertEqual([p["id"] for p, _ in desk.rotate(due)], ["b", "a"])
        due[0][0]["score"] = 99
        self.assertEqual([p["id"] for p, _ in desk.rotate(due)], ["a", "b"])
        due[0][0]["score"] = 0
        due[1][0].pop("video")
        self.assertEqual([p["id"] for p, _ in desk.rotate(due)], ["a", "b"])  # no other format to hand


class StorySpacing(Tmp):
    def test_stories_spread_but_a_pair_keeps_together(self):
        with mock.patch.dict(desk.CONFIG, {"story_spacing_minutes": 40}):
            self.assertIsNone(desk.story_spacing_wait({"id": "x"}))
            self.write_post("s1", kind="story", status="published", published=ago(15))
            self.assertIsNotNone(desk.story_spacing_wait({"id": "x"}))
            self.assertIsNone(desk.story_spacing_wait({"id": "x-a", "after": "s1"}))


class SlotJitter(Tmp):
    def test_story_slots_move_a_fixed_few_minutes_a_day(self):
        with mock.patch.dict(desk.CONFIG, {"story_jitter_minutes": 15}):
            offs = {desk.jitter(f"2026-11-{d:02d}-top5", 15) for d in range(1, 29)}
        self.assertGreater(len(offs), 5)
        self.assertTrue(all(abs(o) <= 15 for o in offs))


if __name__ == "__main__":
    unittest.main()
