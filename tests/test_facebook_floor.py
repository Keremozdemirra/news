import unittest
from datetime import datetime, timezone
from unittest import mock

from aidaily import desk, platforms


class FacebookFloor(unittest.TestCase):
    def setUp(self):
        self.cfg = mock.patch.dict(desk.CONFIG, {"facebook_min_score": 12, "social_min_score": 8.8,
                                                 "facebook_daily_min": 2, "facebook_floor_hour": 10,
                                                 "facebook_daily_max": 4})
        self.cfg.start()
        self.addCleanup(self.cfg.stop)

    def at(self, hour, sent):
        return (mock.patch.object(desk, "now", return_value=datetime(2026, 11, 27, hour, tzinfo=timezone.utc)),
                mock.patch.object(desk, "platform_sent_last_24h", return_value=sent))

    def test_quiet_page_takes_social_grade_posts_after_floor_hour(self):
        a, b = self.at(11, 0)
        with a, b:
            self.assertEqual(desk.facebook_min_score_now(), 8.8)
            self.assertEqual(platforms.facebook_skip({"score": 9.5}), "")

    def test_morning_and_busy_days_keep_the_high_bar(self):
        for hour, sent in ((8, 0), (11, 2)):
            a, b = self.at(hour, sent)
            with a, b:
                self.assertEqual(desk.facebook_min_score_now(), 12)
                self.assertEqual(platforms.facebook_skip({"score": 9.5}), "below facebook_min_score")

    def test_below_social_grade_never_goes(self):
        a, b = self.at(15, 0)
        with a, b:
            self.assertEqual(platforms.facebook_skip({"score": 7}), "below facebook_min_score")


if __name__ == "__main__":
    unittest.main()
