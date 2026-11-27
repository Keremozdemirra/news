"""The Short's structures: varied, 20 to 45 seconds, every line from the published copy or the publisher's series."""
import unittest
from datetime import date, timedelta
from unittest import mock

from aidaily import desk
from aidaily import shortforms as SF
from aidaily import shorts as SH
from test_desk import Tmp
from test_shorts import GROWTH_ON, post


def series(vals, start=date(2026, 8, 1)):
    return [[(start + timedelta(days=i)).isoformat(), v] for i, v in enumerate(vals)]


class Rotation(unittest.TestCase):
    def test_no_two_shorts_in_a_row_share_a_structure(self):
        avail = {"story", "figure", "brief"}
        last, seen = None, []
        for _ in range(6):
            name = SF.choose(avail, last)
            self.assertNotEqual(name, last)
            seen.append(name)
            last = name
        self.assertGreater(len(set(seen)), 1)

    def test_the_same_structure_only_when_nothing_else_has_the_material(self):
        self.assertEqual(SF.choose({"story"}, "story"), "story")
        self.assertIsNone(SF.choose(set(), "story"))


class Material(unittest.TestCase):
    def test_a_quote_needs_six_words_and_a_speaker(self):
        self.assertEqual(SF.quote_of(post(dek="She spoke on Bloomberg's “Horizons Middle East and Africa.”", body="")), "")
        q = "“We will not cut output while demand holds up this well,” the minister said on Friday."
        self.assertEqual(SF.quote_of(post(dek="", body=q)), q)

    def test_what_we_dont_know_is_a_published_sentence(self):
        u = "The company did not disclose the size of the loss."
        self.assertEqual(SF.unknown_of(post(body="Shares fell. " + u)), u)
        self.assertEqual(SF.unknown_of(post()), "")

    def test_structures_need_their_material(self):
        p = post()
        got = SF.post_structures(p, SH._light_story(p), SH.facts(p, 3))
        self.assertIn("story", got)
        self.assertNotIn("quote", got)
        self.assertNotIn("figure", got)


class Length(unittest.TestCase):
    def test_timelines_run_20_to_45_seconds(self):
        short = SF.timeline("b", [(["h"], 5.0), (["f"], 5.0), (["s"], 4.0)], "e")
        self.assertGreaterEqual(short[1], SF.MIN_SECONDS)
        self.assertIsNone(SF.timeline("b", [(["h"], 4.0), (["s"], 2.0)], "e"))  # too thin even stretched
        long = SF.timeline("b", [([str(i)], 7.0) for i in range(10)], "e")
        self.assertLessEqual(long[1], SF.MAX_SECONDS)
        pages = long[0]
        self.assertEqual((pages[0][3], pages[-1][3]), ("base", "end"))


class Data(unittest.TestCase):
    def test_the_number_of_the_day_is_a_high_low_or_big_move_from_the_series(self):
        flat = [100 + (i % 3) * 0.1 for i in range(60)]
        m = {"series": {"brent": series(flat[:-1] + [110.0]), "wti": series(flat)}}
        key, why = SF.data_pick(m, today=date(2026, 9, 30))
        self.assertEqual((key, why[0]), ("brent", "high"))
        value, caption, title, src = SF.data_text(m, key, why)
        self.assertEqual(value, "$110.00")
        self.assertIn("up $9.", caption)
        self.assertIn("on the day", caption)
        self.assertIn("Energy Information Administration", src)
        self.assertLessEqual(len(title), 100)

    def test_used_or_stale_series_are_skipped(self):
        flat = [100 + (i % 3) * 0.1 for i in range(60)]
        m = {"series": {"brent": series(flat[:-1] + [110.0])}}
        d = m["series"]["brent"][-1][0]
        self.assertIsNone(SF.data_pick(m, used={f"brent-{d}"}, today=date(2026, 9, 30)))
        self.assertIsNone(SF.data_pick(m, today=date(2026, 12, 30)))
        self.assertIsNone(SF.data_pick({"series": {"wti": series(flat)}}, today=date(2026, 9, 30)))


class Plan(Tmp):
    def test_the_brief_runs_once_a_day_and_is_recorded(self):
        with mock.patch.dict(desk.CONFIG, {"growth": dict(GROWTH_ON)}):
            now = desk.now().isoformat()
            for i, topic in enumerate(("Markets", "Economy", "Business")):
                self.write_post(f"p{i}", status="published", published=now, topic=topic, score=10,
                                headlines=[f"Story number {i} about rates and prices"], photo_file="", credit="")
            job = SH.plan_next({"last_structure": "story"})
            self.assertEqual(job["structure"], "brief")
            self.assertTrue(job["markets"])
            self.assertIsNone(SH.plan_next({"last_structure": "story", "brief_day": f"{desk.now():%Y-%m-%d}"}))

    def test_metadata_for_the_brief_names_every_story_and_link(self):
        with mock.patch.dict(desk.CONFIG, {"site_url": "https://boardread.news"}):
            posts = [post(id=f"p{i}", headlines=[f"Headline {i}"]) for i in range(3)]
            m = SH.metadata_job({"structure": "brief", "posts": posts, "markets": False})
        d = m["snippet"]["description"]
        for i in range(3):
            self.assertIn(f"Headline {i}", d)
            self.assertIn(f"https://boardread.news/s/p{i}/", d)
        self.assertTrue(m["status"]["containsSyntheticMedia"])
        self.assertFalse(m["status"]["selfDeclaredMadeForKids"])
        self.assertLessEqual(len(m["snippet"]["title"]), 100)


if __name__ == "__main__":
    unittest.main()
