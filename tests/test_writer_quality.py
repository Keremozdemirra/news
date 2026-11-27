"""The writer's checks that a headline, a dek and a report belong to one story, and the rules for how they are worded."""
import json
import unittest

from aidaily import copy


def story(title, summary="", source="Reuters", reports=()):
    return {"title": title, "summary": summary, "source": source, "reports": list(reports), "lane": "news"}


def row(**kw):
    base = {"id": 0, "relevant": True, "fits_category": True, "topic": "World", "company": "", "backer": "", "person": "",
            "person_role": "", "orgs": [], "figure": "", "image_query": "", "venue": "", "company_domain": ""}
    base.update(kw)
    return base


ZELENSKYY = ("Zelenskyy compares Trump calling Putin a friend to befriending Hitler in WW2",
             "Ukraine's president says the comments are strange and urges Washington to increase pressure on Moscow. "
             "Overnight, Nato fighter jets and an interceptor drone were scrambled in Latvia after a drone briefly "
             "entered its airspace near the Russian border.")


class HeadlineSupport(unittest.TestCase):
    def test_zelenskyy_headline_over_a_latvia_report_is_withheld(self):
        s = story(*ZELENSKYY, source="Kyiv Independent")
        rows = [row(headline="Zelenskyy compares Trump calling Putin a friend to befriending Hitler in WW2",
                    dek="Ukraine's president calls the comments strange and urges Washington to increase pressure on Moscow.",
                    x_post="Zelenskyy compares Trump calling Putin a friend to befriending Hitler in WW2",
                    linkedin_post="Overnight, Nato fighter jets and an interceptor drone were scrambled in Latvia after a "
                                  "drone briefly entered its airspace near the Russian border. Several countries have "
                                  "reported drone and missile incursions since February 2022.\n\nSource: Kyiv Independent")]
        rejected = copy.apply([s], rows)
        self.assertEqual(s["copy_status"], "fallback")
        self.assertEqual(len(rejected), 1)
        self.assertIn("do not support the headline", rejected[0][1][0])

    def test_report_that_names_the_headlines_people_is_kept(self):
        s = story("Spain heads to early election Sunday as housing and immigration dominate debate",
                  "Spain votes Sunday and the vote may usher in a right-wing coalition to replace Prime Minister Pedro "
                  "Sanchez. The struggle "
                  "many face in buying a home has been the biggest issue of a bitter campaign.")
        rows = [row(headline="Spain heads to early election Sunday as housing and immigration dominate debate",
                    dek="The vote may usher in a right-wing coalition to replace Prime Minister Pedro Sanchez.",
                    x_post="x", linkedin_post="The struggle many face in buying a home has been the biggest issue of a "
                                              "bitter campaign. Sanchez is one of Europe's last leftist leaders.\n\nSource: Reuters")]
        copy.apply([s], rows)
        self.assertEqual(s["copy_status"], "ok")
        self.assertTrue(s["supported"])

    def test_headline_number_in_the_report_supports_it(self):
        self.assertEqual(copy.headline_gap("Tokyo core inflation hits 16-month high", "The reading backs a rate increase.",
                                           "Core prices were 2.9% higher than a year earlier, the 16-month high."), "")

    def test_gap_on_the_page_alone(self):
        head = ZELENSKYY[0]
        self.assertTrue(copy.headline_gap(head, "Ukraine's president calls the comments strange.",
                                          "Overnight, Nato fighter jets were scrambled in Latvia after a drone entered its airspace."))
        self.assertEqual(copy.headline_gap(head, "", ""), "")  # an empty report is thin(), not a gap

    def test_audit_holds_an_edited_post_with_a_gap(self):
        from aidaily import desk
        post = {"headlines": [ZELENSKYY[0]], "dek": "Ukraine's president calls the comments strange.",
                "body": "Overnight, Nato fighter jets were scrambled in Latvia after a drone entered its airspace near the border."}
        gap = "the dek and report do not support the headline"
        post["supported"] = copy.fingerprint(post["headlines"][0], post["dek"], post["body"])
        self.assertNotIn(gap, desk.audit(post))  # the writer checked this text with the sources in hand
        post["body"] += " A second drone was shot down."
        self.assertIn(gap, desk.audit(post))  # edited since: checked on the page's own words


FRANCE = story("France inflation slows more than expected in November",
               "Consumer prices fell 0.7% in November from October, after rising 0.4% a month earlier. Annual inflation "
               "slowed to 2.9% from 3.2% a year earlier, Insee said Friday.", source="Bloomberg")


class Periods(unittest.TestCase):
    def apply(self, headline, dek, post):
        s = dict(FRANCE)
        rows = [row(headline=headline, dek=dek, x_post=headline, linkedin_post=post + "\n\nSource: Bloomberg")]
        return s, copy.apply([s], rows)

    def test_each_figure_names_its_period(self):
        s, rejected = self.apply("French annual inflation slows to 2.9% in November",
                                 "Consumer prices fell 0.7% on the month, Insee said.",
                                 "Annual inflation was 3.2% a year earlier. Prices had risen 0.4% in October.")
        self.assertEqual(rejected, [])
        self.assertEqual(s["copy_status"], "ok")

    def test_a_headline_figure_without_its_period_is_rejected(self):
        s, rejected = self.apply("French inflation slows to 2.9% in November", "Consumer prices fell 0.7% in November.",
                                 "Prices had risen 0.4% in October. Insee published the figures on Friday.")
        self.assertEqual(s["copy_status"], "fallback")
        self.assertIn("2.9%", rejected[0][1][0])

    def test_a_report_sentence_without_its_period_is_cut_not_the_story(self):
        s, rejected = self.apply("French annual inflation slows to 2.9% in November", "Consumer prices fell 0.7% on the month.",
                                 "Prices had risen 0.4%. Insee published the figures on Friday.")
        self.assertEqual(rejected, [])
        self.assertEqual(s["copy_status"], "ok")
        self.assertNotIn("0.4", s["linkedin_post"])

    def test_a_period_the_source_does_not_give_is_rejected(self):
        s, rejected = self.apply("French inflation slows to 2.9% year on year", "Consumer prices fell 0.7% year on year.",
                                 "Prices had risen 0.4% in October. Insee published the figures on Friday.")
        self.assertEqual(s["copy_status"], "fallback")

    def test_one_percentage_needs_no_period(self):
        s = story("Oil falls 3%", "Brent fell 3% on Friday.")
        rows = [row(headline="Oil falls 3%", dek="Brent fell 3% on Friday.", x_post="x", linkedin_post="")]
        self.assertEqual(copy.apply([s], rows), [])


if __name__ == "__main__":
    unittest.main()
