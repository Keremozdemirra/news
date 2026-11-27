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


class Conversions(unittest.TestCase):
    def test_a_conversion_is_a_parenthesis_given_once(self):
        c = {"headline": "Coupang posts 405.8 billion won revenue",
             "dek": "Revenue rose to 405.8 billion won, or $303 million, in the quarter.",
             "x_post": "", "linkedin_post": "Operating profit reached 19.6 billion won ($14.5 million). That equals $14.5 million. "
                                          "Sales were 405.8 billion won ($303 million) again.\n\nSource: Yonhap"}
        cut = copy.fix_conversions(c)
        self.assertEqual(cut, ["That equals $14.5 million."])
        self.assertEqual(c["dek"], "Revenue rose to 405.8 billion won ($303 million) in the quarter.")
        self.assertEqual(c["linkedin_post"], "Operating profit reached 19.6 billion won ($14.5 million). "
                                             "Sales were 405.8 billion won again.\n\nSource: Yonhap")

    def test_apply_cuts_the_sentence_that_is_only_a_conversion(self):
        s = story("Coupang revenue rises 34.2% to 405.8 billion won",
                  "Revenue rose 34.2% to 405.8 billion won ($303 million) in the third quarter. Operating profit was "
                  "19.6 billion won ($14.5 million).", source="Yonhap")
        rows = [row(headline="Coupang revenue rises 34.2% to 405.8 billion won",
                    dek="Operating profit was 19.6 billion won ($14.5 million).", x_post="x",
                    linkedin_post="Revenue was 405.8 billion won ($303 million) in the third quarter. That equals $303 million.\n\n"
                                  "Source: Yonhap")]
        copy.apply([s], rows)
        self.assertNotIn("That equals", s["linkedin_post"])

    def test_audit_holds_a_post_with_a_conversion_sentence(self):
        from aidaily import desk
        post = {"headlines": ["Coupang posts record revenue"], "dek": "Revenue was 405.8 billion won.",
                "body": "Sales rose in the quarter. That is about $303 million."}
        self.assertTrue(any("currency conversion on its own" in p for p in desk.audit(post)))


GUARDIAN = story("Labour MPs write to Starmer urging him to name a successor",
                 "Dozens of Labour MPs signed a letter to Keir Starmer. A handful of frontbenchers joined scores of colleagues.",
                 source="The Guardian", reports=[{"outlet": "Financial Times", "title": "Labour MPs press Starmer",
                                                  "summary": "The letter was sent on Thursday."}])


class Attribution(unittest.TestCase):
    def run_apply(self, dek, post, s=None):
        s = dict(s or GUARDIAN)
        rows = [row(headline="Labour MPs write to Starmer urging him to name a successor", dek=dek, x_post="x",
                    linkedin_post=post + "\n\nSource: The Guardian")]
        copy.apply([s], rows)
        return s

    def test_an_opener_naming_a_newsroom_is_cut_and_the_clause_stands(self):
        c = {"dek": "", "linkedin_post": "The Guardian reports that dozens of Labour MPs signed a letter to Keir Starmer.\n\n"
                                         "Source: The Guardian"}
        self.assertEqual(copy.strip_attributions(GUARDIAN, c), [])
        self.assertEqual(c["linkedin_post"], "Dozens of Labour MPs signed a letter to Keir Starmer.\n\nSource: The Guardian")
        c = {"dek": "According to the Financial Times, the letter was sent on Thursday.", "linkedin_post": ""}
        copy.strip_attributions(GUARDIAN, c)
        self.assertEqual(c["dek"], "The letter was sent on Thursday.")

    def test_a_sentence_about_the_source_is_cut(self):
        c = {"dek": "", "linkedin_post": "The Guardian describes the letter as exposing a split in Labour. The letter was sent "
                                         "on Thursday.\n\nSource: The Guardian"}
        self.assertEqual(copy.strip_attributions(GUARDIAN, c), ["The Guardian describes the letter as exposing a split in Labour."])

    def test_only_one_attribution_survives(self):
        c = {"dek": "A handful of frontbenchers joined, the Financial Times reported.",
             "linkedin_post": "The letter was sent on Thursday, according to the Financial Times. Dozens of MPs signed it.\n\n"
                              "Source: The Guardian"}
        copy.strip_attributions(GUARDIAN, c)
        self.assertEqual(c["dek"], "A handful of frontbenchers joined, the Financial Times reported.")
        self.assertEqual(c["linkedin_post"], "The letter was sent on Thursday. Dozens of MPs signed it.\n\nSource: The Guardian")

    def test_source_meta_sentences_are_rejected(self):
        for x in ("The report cites sources.", "The report cites unnamed officials.", "With Dwight McNeil named in the report's headline."):
            self.assertTrue(copy.META.search(x), x)
        self.assertFalse(copy.META.search("The IMF report found growth of 3%."))

    def test_apply_drops_the_meta_report_sentence(self):
        s = self.run_apply("A handful of frontbenchers joined scores of colleagues.",
                           "The report cites sources. Dozens of Labour MPs signed a letter to Keir Starmer.")
        self.assertNotIn("cites sources", s["linkedin_post"])

    def test_audit_holds_a_post_that_opens_with_a_newsroom(self):
        from aidaily import desk
        post = {"headlines": ["Labour MPs write to Starmer"], "dek": "Dozens signed.", "sources": ["The Guardian", "Financial Times"],
                "body": "The Guardian reports that the letter was sent on Thursday. A handful of frontbenchers joined."}
        self.assertTrue(any("opens with a newsroom" in p for p in desk.audit(post)))


class Glossary(unittest.TestCase):
    def test_a_chamber_goes_by_its_own_name_everywhere(self):
        for wrong, right in [("Japan's Senate", "Japan's upper house"), ("The Japanese Senate", "The Japanese upper house"),
                             ("Britain's Congress", "Britain's Parliament"), ("Germany's Congress", "Germany's Bundestag"),
                             ("South Korea's Congress", "South Korea's National Assembly"), ("Russia's Senate", "Russia's upper house")]:
            self.assertEqual(copy.fix_legislature(wrong), right, wrong)

    def test_a_chamber_the_country_has_is_left_alone(self):
        for ok in ("Australia's Senate", "Canada's Senate", "France's Senate", "Italy's Senate", "Spain's Senate",
                   "The Philippines' Senate", "Argentina's Senate", "India's Congress party", "India's Congress leader says",
                   "Mexico's Congress", "the US Senate", "Japan's upper house", "Japan's Diet"):
            self.assertEqual(copy.fix_legislature(ok), ok, ok)

    def test_apply_fixes_the_dek_the_report_and_the_x_post_too(self):
        s = story("Japan's upper house rejects censure motion against Education Minister Seki",
                  "The Senate vote was narrow. Japan's Senate voted 120 to 118 on Friday.", source="NHK")
        rows = [row(headline="Japan's Senate narrowly rejects censure motion against Education Minister Seki",
                    dek="Japan's Senate voted 120 to 118 on Friday.", x_post="Japan's Senate rejects the motion.",
                    linkedin_post="The motion was brought by opposition parties. Japan's Senate sat on Friday.\n\nSource: NHK")]
        copy.apply([s], rows)
        for f in ("headline", "dek", "x_post", "linkedin_post"):
            self.assertNotIn("Senate", s[f], f)
        self.assertIn("upper house", s["headline"])

    def test_audit_holds_the_dek_body_and_caption_not_only_the_headline(self):
        from aidaily import desk
        base = {"headlines": ["Japan rejects censure motion"], "dek": "Japan's upper house voted on Friday.", "body": "", "caption": "x #news"}
        self.assertFalse(any("another country's name" in p for p in desk.audit(base)))
        for field in ("dek", "body", "caption"):
            post = {**base, field: "Japan's Senate voted narrowly on Friday."}
            self.assertTrue(any(f"{field} calls a chamber by another country's name" in p for p in desk.audit(post)), field)

    def test_the_prompt_carries_the_glossary(self):
        text = copy.prompt("id: 0")
        self.assertIn("House of Councillors", text)
        self.assertIn("Legislative Yuan", text)


if __name__ == "__main__":
    unittest.main()
