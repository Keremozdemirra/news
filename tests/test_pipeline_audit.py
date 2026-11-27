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

    def test_a_fresh_story_outweighs_one_more_newsroom_from_yesterday(self):
        old = {**art(1, "2026-11-26", 15, 9.6, head="Trump signals he is ready to escalate tariffs"), "sources": list("ABCD")}
        new = {**art(2, "2026-11-27", 10, 8.0, topic="Politics", head="UK benefits department takes services offline"),
               "sources": list("ABC")}
        self.assertEqual(views.front_rank([old, new])[0]["id"], new["id"])


if __name__ == "__main__":
    unittest.main()


class PersonInCompanyPhoto(unittest.TestCase):
    CATS = ("Personality rights warning|Files from external sources with reviewed licenses|Female vocalists from South "
            "Korea in 2025|Stella (South Korean pop singer)")

    def test_a_company_photo_of_a_person_the_story_does_not_name_is_refused(self):
        f = "Stella di Musinsa Beauty Festa Pop-Up Store 2025.jpg"
        self.assertEqual(entities.shows_person(f, self.CATS, "Musinsa operating profit jumps 67% Musinsa", depicted=[]), "Stella")
        self.assertEqual(entities.shows_person(f, "", "Musinsa profit", depicted=["Stella"]), "Stella")
        # named in the headline: the photo may stand
        self.assertEqual(entities.shows_person(f, self.CATS, "Stella signs with Musinsa", depicted=["Stella"]), "")
        # premises with nobody in them pass
        self.assertEqual(entities.shows_person("Musinsa store Hongdae.jpg", "Shops in Seoul", "Musinsa profit", depicted=[]), "")

    STELLA = "Stella di Musinsa Beauty Festa Pop-Up Store 2025.jpg"

    def pick(self, files, allow):
        def info(f, width=None):
            cats = self.CATS if f == self.STELLA else "Shops in Seoul"
            return {"extmetadata": {"Categories": {"value": cats}, "LicenseShortName": {"value": "CC BY 3.0"}},
                    "width": 1600, "height": 2000, "url": "u"}
        with mock.patch.object(entities, "candidates", return_value=files), \
             mock.patch.object(entities, "_commons_info", side_effect=info), \
             mock.patch.object(entities, "_depicted_humans", side_effect=lambda f: ["Stella"] if f == self.STELLA else []), \
             mock.patch.object(entities, "photo_ok", return_value=(True, "Photo: X, CC BY 3.0")), \
             mock.patch.object(entities, "_fetched", side_effect=lambda info, credit, f: ("path", credit, f)):
            return entities.fresh_photo([("Musinsa", False)], set(), allow=allow)[2]

    def test_a_person_at_the_companys_own_event_is_the_last_resort_on_good_news(self):
        # Kerem, 2026-11-27: the most related picture may stand when nothing else relates
        self.assertEqual(self.pick([self.STELLA], "Musinsa operating profit jumps 67% Musinsa"), self.STELLA)

    def test_a_photo_without_the_person_wins_when_there_is_one(self):
        self.assertEqual(self.pick([self.STELLA, "Musinsa store Seongsu.jpg"], "Musinsa profit jumps Musinsa"),
                         "Musinsa store Seongsu.jpg")

    def test_never_beside_bad_news(self):
        self.assertEqual(self.pick([self.STELLA], "Musinsa cuts 200 jobs after a loss Musinsa"), "")
        self.assertEqual(self.pick([self.STELLA], "Musinsa sued over counterfeit sales Musinsa"), "")


class WriterReview(unittest.TestCase):
    """The 2026-11-27 deep review of the live site, writer side."""
    H = "Zelenskyy compares Trump calling Putin a friend to befriending Hitler in WW2"
    D = "Ukraine's president calls the comments strange and urges Washington to increase pressure on Moscow."

    def test_a_report_about_another_event_does_not_stand_under_the_headline(self):
        out = copy.drop_offtopic("Overnight, Nato fighter jets and an interceptor drone were scrambled in Latvia after a "
                                 "drone briefly entered its airspace near the Russian border, the army said.", self.H, self.D)
        self.assertEqual(out, "")

    def test_a_name_the_lead_source_carries_is_on_topic(self):
        body = "Governor Kazuo Ueda will give a speech on Nov 30, ahead of the Dec 18 BOJ decision."
        self.assertEqual(copy.drop_offtopic(body, "Tokyo core inflation hits 16-month high", "",
                                            "Tokyo core CPI rises; Governor Kazuo Ueda speaks next week"), body)

    def test_source_meta_and_another_story_are_cut_and_held(self):
        self.assertEqual(copy.drop_offtopic("Thomas Frank has his first Palace win, with Dwight McNeil named in the "
                                            "report's headline. Palace trailed to a Sarr goal.", "Thomas Frank earns first "
                                            "Crystal Palace win"), "Palace trailed to a Sarr goal.")
        self.assertEqual(copy.drop_offtopic("Separately, the Liberal Democrats want an immigration plan.", "Mandelson tried "
                                            "to influence the reshuffle"), "")
        base = {"headlines": ["Lab ships a model"], "topic": "Tech", "photo_file": "Harbour at dusk.jpg", "photo_kind": "scene",
                "credit": "Photo: A, CC BY 4.0, via Wikimedia Commons", "caption": "x #news", "dek": "It runs on its own chips."}
        self.assertTrue(any("another story" in p for p in desk.audit({**base, "body": TWO + " Separately, rivals cut prices."})))

    def test_a_chamber_goes_by_its_own_name(self):
        self.assertEqual(copy.fix_legislature("Japan's Senate narrowly rejects censure motion"),
                         "Japan's upper house narrowly rejects censure motion")
        self.assertEqual(copy.fix_legislature("Argentina's Senate approves bill"), "Argentina's Senate approves bill")
        post = {"headlines": ["Japan's Senate narrowly rejects censure motion"], "topic": "Politics", "dek": "x.", "body": TWO}
        self.assertTrue(any("Senate" in p for p in desk.audit(post)))
