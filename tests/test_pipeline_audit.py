"""The 2026-11-27 site audit, pipeline side: every article carries a real report, figures are not said twice,
deaths stay off, one market wrap per session, a show at a venue is not the venue, the brief is one day's."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from aidaily import copy, desk, entities, rank, site, sitepages, views

TWO = "The company said the change reaches every customer this week. Its rivals have not announced a matching plan so far."


class Reports(unittest.TestCase):
    def test_other_newsrooms_reach_the_copy_and_ground_its_numbers(self):
        now = datetime(2026, 11, 27, 9, tzinfo=timezone.utc)
        src = {"a": {"category": "news", "publisher": "Fortune"}, "b": {"category": "news", "publisher": "Reuters"},
               "c": {"category": "community", "name": "Hacker News"}}
        items = [{"source_id": "a", "title": "Target books $387 million in tariff refunds", "url": "u1", "published": now,
                  "summary": "Target booked refund benefits."},
                 {"source_id": "b", "title": "Retailers book tariff refunds", "url": "u2", "published": now,
                  "summary": "Best Buy booked $112 million and Kohl's $45 million last quarter."},
                 {"source_id": "c", "title": "Retailers tariff refunds thread", "url": "u3", "published": now, "summary": "chat"}]
        lead = items[0]
        got = rank.reports(items, lead, src)
        self.assertEqual([r["outlet"] for r in got], ["Reuters"])
        s = {"title": lead["title"], "summary": lead["summary"], "source": "Fortune", "reports": got}
        self.assertIn("also reported:\n- Reuters: Retailers book tariff refunds.", copy.block([s]))
        c = {"headline": "Target books $387 million in tariff refunds", "dek": "Best Buy booked $112 million.",
             "linkedin_post": "Kohl's booked $45 million last quarter.\n\nSource: Fortune", "figure": ""}
        self.assertEqual(copy.verify(s, c), [])


class Orphans(unittest.TestCase):
    def test_a_sentence_leaning_on_a_cut_one_goes_with_it(self):
        out = copy.drop_repeats("The EU fined the platform over political ads. It concerns the removal and blocking of "
                                "political content. Officials gave the company 60 days to respond.\n\nSource: FT",
                                ["The EU fined the platform over political ads."], "EU fines platform")
        self.assertEqual(out, "Officials gave the company 60 days to respond.\n\nSource: FT")

    def test_a_report_never_opens_leaning_on_nothing(self):
        out = copy.drop_repeats("Markets are also tracking U.S. inventories. Brent rose 2% to $64 a barrel.",
                                ["Oil rises on supply worries."], "Oil climbs")
        self.assertEqual(out, "Brent rose 2% to $64 a barrel.")


class Splitting(unittest.TestCase):
    def test_an_abbreviation_ends_no_sentence(self):
        self.assertEqual(copy.sentences("The boat was found off Ulleungdo on Nov. 3. It was towed to port."),
                         ["The boat was found off Ulleungdo on Nov. 3.", "It was towed to port."])
        self.assertEqual(len(copy.sentences("The U.S. economy grew. Jobs rose.")), 2)

    def test_a_new_number_is_a_new_fact(self):
        out = copy.drop_repeats("Amazon's ad business generates $68.6 billion a year, and Muse commands 51 percent of all "
                                "agentic shopping orders.",
                                ["The sides are stuck on ad revenue; Amazon's ad business generates $68.6 billion a year."],
                                "Amazon and Meta talk about lifting the block on Meta's Muse shopping agent")
        self.assertIn("51 percent", out)


class Thin(unittest.TestCase):
    def test_no_dek_takes_the_reports_first_sentence(self):
        s = {"title": "Argentina's Senate approves bill to suspend primaries", "source": "BA Times",
             "summary": "The Senate approved the bill 40 to 30. The vote is a boost for Milei. The lower house votes next week."}
        rows = [{"id": 0, "headline": "Argentina's Senate approves bill to suspend primaries", "dek": "",
                 "linkedin_post": "The Senate approved the bill 40 to 30. The vote is a boost for Milei. The lower house "
                                  "votes next week.\n\nSource: BA Times", "figure": "", "x_post": ""}]
        copy.apply([s], rows)
        # the first sentence only restated the headline and went; the next one moves up into the dek
        self.assertEqual(s["dek"], "The vote is a boost for Milei.")
        self.assertEqual(desk.body(s), "The lower house votes next week.")

    def test_an_article_needs_a_dek_and_two_sentences_beyond_it(self):
        self.assertEqual(copy.thin({"dek": "", "linkedin_post": TWO}), "no dek")
        self.assertIn("too thin", copy.thin({"dek": "A fact.", "linkedin_post": "The flaw has been fixed.\n\nSource: X"}))
        self.assertEqual(copy.thin({"dek": "A fact.", "linkedin_post": TWO + "\n\nSource: X"}), "")

    def test_audit_holds_a_thin_or_orphan_report(self):
        base = {"headlines": ["Lab ships a model"], "topic": "Tech", "photo_file": "Harbour at dusk.jpg", "photo_kind": "scene",
                "credit": "Photo: A, CC BY 4.0, via Wikimedia Commons", "caption": "x #news", "dek": "It runs on its own chips."}
        self.assertTrue(any("too thin" in p for p in desk.audit({**base, "body": ""})))
        self.assertTrue(any("leaning" in p for p in desk.audit({**base, "body": "It concerns the chips. " + TWO})))
        self.assertEqual(desk.audit({**base, "body": TWO}), [])


class Skip(unittest.TestCase):
    def test_deaths_stay_off_and_market_idioms_do_not(self):
        for t in ("Iranian drone attack in Kuwait kills two Italians", "Tanker capsizes off Ibiza, killing a crew member"):
            self.assertTrue(desk.SKIP.search(t), t)
        for t in ("Airline stock enters a death spiral", "Bitcoin forms a death cross", "Shooting star fund manager quits",
                  "Polls show a dead heat"):
            self.assertFalse(desk.SKIP.search(t), t)


class Wraps(unittest.TestCase):
    def test_two_market_wraps_within_twelve_hours_are_one_event(self):
        a = {"url": "u1", "headline": "Global stocks climb after volatile US trading", "created": "2026-11-26T15:42:00+00:00"}
        b = {"url": "u2", "headline": "Global stocks rally as investors shrug off tariffs", "created": "2026-11-26T18:35:00+00:00"}
        self.assertTrue(desk.same_story(a, b))
        self.assertFalse(desk.same_story(a, {**b, "created": "2026-11-27T08:00:00+00:00"}))
        self.assertFalse(desk.same_story({**a, "headline": "Shares of Nvidia fall after export halt"}, b))


class Venue(unittest.TestCase):
    def test_a_show_at_the_stadium_is_not_the_stadium(self):
        hits = {"query": {"search": [{"title": "File:One Direction - Lincoln Financial Field (14890362356).jpg"},
                                     {"title": "File:Lincoln Financial Field concert 2019.jpg"},
                                     {"title": "File:Lincoln Financial Field aerial.jpg"}]}}
        with mock.patch.object(entities, "_get", return_value=hits):
            self.assertEqual(entities.candidates("Lincoln Financial Field"), ["Lincoln Financial Field aerial.jpg"])


class NumberBox(unittest.TestCase):
    def test_the_box_only_adds_what_the_headline_does_not_say(self):
        p = {"headlines": ["Eagles beat Cowboys 39-38 on a 59-yard field goal"], "dek": "", "body": "", "figure": "59-yard"}
        self.assertEqual(site.number_box(p), "")
        self.assertTrue(site.figure_stated(p))
        p = {"headlines": ["Retailers book tariff refund benefits"], "dek": "Target, Best Buy and Kohl's booked $387M.",
             "body": "", "figure": "$387M"}
        self.assertIn("The number", site.number_box(p))


def art(i, day, hour, score, topic="Economy", head=None):
    return {"id": f"{day}-{i}", "published": f"{day}T{hour:02d}:00:00+00:00", "score": score, "topic": topic,
            "headlines": [head or f"Central bank raises rates {i}"], "dek": "", "sources": ["A"]}


class Brief(unittest.TestCase):
    def test_a_dated_brief_holds_only_that_days_articles(self):
        shown = [art(1, "2026-11-27", 2, 9.0)] + [art(i, "2026-11-26", 15, 12.0) for i in range(2, 12)]
        self.assertEqual([p["id"] for p in sitepages.brief_rows(shown, "2026-11-27")], ["2026-11-27-1"])
        # just after midnight the front brief stays on the last full day
        self.assertEqual(sitepages.brief_day(shown, ["2026-11-27", "2026-11-26"]), "2026-11-26")


class FrontLead(unittest.TestCase):
    def test_a_fresh_story_leads_an_equal_one_from_yesterday(self):
        old = art(1, "2026-11-26", 15, 9.0, head="Trump signals he is ready to escalate tariffs")
        new = art(2, "2026-11-27", 9, 9.0, head="Fed raises rates as inflation stays high")
        self.assertEqual(views.front_score(old), views.front_score(new))
        self.assertEqual(views.front_rank([old, new])[0]["id"], new["id"])


if __name__ == "__main__":
    unittest.main()
