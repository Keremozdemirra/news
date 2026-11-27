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
                    linkedin_post="Nato jets and an interceptor drone were scrambled over Latvia after a drone crossed into "
                                  "its airspace near the Russian border. Several countries have reported drone and missile "
                                  "incursions since February 2022.\n\nSource: Kyiv Independent")]
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


class DekSubject(unittest.TestCase):
    def test_a_dek_about_another_subject_is_dropped_and_the_report_stays(self):
        s = story("Mandelson tried to influence Starmer's cabinet reshuffle, report says",
                  "Sources say Peter Mandelson pressed Keir Starmer on who should get which job. Starmer turned down the "
                  "suggestion during a Monday phone call. The Liberal Democrats want an immigration plan, spokesperson Paul "
                  "Kohler said.", source="Politico")
        rows = [row(headline="Mandelson tried to influence Starmer's cabinet reshuffle",
                    dek="The Liberal Democrats want an immigration plan, spokesperson Paul Kohler said.", x_post="x",
                    linkedin_post="Mandelson pressed the prime minister on cabinet jobs. Starmer declined during a phone call "
                                  "on Monday.\n\nSource: Politico")]
        copy.apply([s], rows)
        self.assertEqual(s["copy_status"], "ok")
        self.assertNotIn("Liberal Democrats", s["dek"])
        self.assertIn("Starmer", s["dek"] + s["linkedin_post"])

    def test_a_dek_that_names_only_what_the_story_names_stays(self):
        s = story("SAP explores at least 10,000 job cuts", "The German software group is weighing a large restructuring. Talks are at an early stage.",
                  source="FT")
        rows = [row(headline="SAP explores at least 10,000 job cuts", dek="The software group is weighing a large restructuring.",
                    x_post="x", linkedin_post="Talks are at an early stage, the people said.\n\nSource: FT")]
        copy.apply([s], rows)
        self.assertIn("restructuring", s["dek"])

    def test_the_tokyo_dek_about_the_bank_of_japan_gives_way_to_the_reading_itself(self):
        s = story("Tokyo core inflation hits 16-month high", "Tokyo's core consumer price index rose 2.9% in November. Economists say "
                  "it strengthens expectations that the Bank of Japan will raise rates in December.", source="Reuters")
        rows = [row(headline="Tokyo core inflation hits 16-month high", dek="The reading backs the case for a Bank of Japan rate "
                    "increase in December.", x_post="x", linkedin_post="The consumer price index excluding fresh food rose 2.9% in "
                    "November. Economists expect the Bank of Japan to move in December.\n\nSource: Reuters")]
        copy.apply([s], rows)
        self.assertEqual(s["dek"], "The consumer price index excluding fresh food rose 2.9% in November.")


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
        s, rejected = self.apply("French consumer prices fall 0.7% year on year", "Annual inflation slowed to 2.9% year on year.",
                                 "Prices had risen 0.4% in October. Insee published the figures on Friday.")
        self.assertEqual(s["copy_status"], "fallback")
        # the same slip in the dek only costs the dek
        s, rejected = self.apply("French inflation slows to 2.9% year on year", "Consumer prices fell 0.7% year on year.",
                                 "Prices had risen 0.4% in October. Insee published the figures on Friday.")
        self.assertEqual(s["copy_status"], "ok")
        self.assertNotIn("0.7", s["dek"])

    def test_twelve_months_is_a_year_and_weekdays_and_bare_years_name_no_period(self):
        self.assertEqual(copy._period_kinds("Prices rose 3% over the past 12 months."), {"year"})
        self.assertEqual(copy._period_kinds("The margin was 4% on Tuesday."), set())
        self.assertEqual(copy._period_kinds("Sales fell 4% in 2025."), set())
        s = story("Inflation hits 3.1%", "Prices rose 3.1% over the past 12 months. Rates stayed at 4.5%.")
        rows = [row(headline="Inflation hits 3.1% year on year", dek="Rates stayed at 4.5%.", x_post="x", linkedin_post="")]
        self.assertEqual(copy.apply([s], rows), [])

    def test_the_figure_after_from_is_a_reference_not_a_claim(self):
        s = story("Inflation slows to 2.1%", "Annual inflation slows to 2.1% from 2.6%. Rates held at 4.5% on Tuesday.")
        rows = [row(headline="Annual inflation slows to 2.1% from 2.6%", dek="Rates held at 4.5% on Tuesday.", x_post="x", linkedin_post="")]
        self.assertEqual(copy.apply([s], rows), [])

    def test_a_dek_figure_without_its_period_trims_the_dek_not_the_story(self):
        s, rejected = self.apply("French annual inflation slows to 2.9% in November", "Prices fell 0.7% in the month, Insee said.",
                                 "Prices had risen 0.4% in October. Insee published the figures on Friday.")
        self.assertEqual(rejected, [])
        self.assertEqual(s["copy_status"], "ok")

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
                "body": "Sales rose to 405.8 billion won in the quarter. That equals about $303 million."}
        self.assertTrue(any("currency conversion on its own" in p for p in desk.audit(post)))

    def test_audit_leaves_a_real_dollar_fact_alone(self):
        from aidaily import desk
        for body in ("The deal is worth $5 billion. It is about $20 per share.", "The total is $12 billion, the largest on record.",
                     "The price is $1.2 million.", "Sales rose to 405.8 billion won. The deal is worth $5 billion."):
            post = {"headlines": ["Coupang posts record revenue"], "dek": "Revenue was 405.8 billion won.", "body": body}
            self.assertFalse(any("currency conversion" in p for p in desk.audit(post)), body)

    def test_money_phrases_that_are_not_conversions_stay_as_written(self):
        for t in ("a deal worth $5 billion", "funds of about $5 million", "valued at roughly $2 billion", "priced at $5 or $6",
                  "Fines reached 30 million, or $37,000, last year", "raised about $18.6 billion this year",
                  "the bid is worth $5.8 billion"):
            c = {"headline": t, "dek": "", "linkedin_post": "", "x_post": ""}
            self.assertEqual(copy.fix_conversions(c), [])
            self.assertEqual(c["headline"], t)

    def test_a_conversion_after_a_foreign_amount_swallows_its_comma(self):
        c = {"headline": "", "dek": "Revenue was 405.8 billion won, or $303 million, in the quarter. It cost EUR 5, or $6.", "linkedin_post": "", "x_post": ""}
        copy.fix_conversions(c)
        self.assertEqual(c["dek"], "Revenue was 405.8 billion won ($303 million) in the quarter. It cost EUR 5, or $6.")
        c = {"headline": "Deal of \u20ac40 million, equivalent to $43 million, signed", "dek": "", "linkedin_post": "", "x_post": ""}
        copy.fix_conversions(c)
        self.assertEqual(c["headline"], "Deal of \u20ac40 million ($43 million) signed")

    def test_a_sentence_after_a_dollar_sentence_is_not_a_conversion(self):
        self.assertFalse(copy.is_conversion("It equals $5 billion.", "Sales were $2 billion."))
        self.assertTrue(copy.is_conversion("It equals $5 billion.", "Sales were 7 billion euros."))


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

    def test_a_hedged_or_sourced_claim_keeps_its_newsroom(self):
        for x in ("Reuters reported the revival, citing people familiar with the matter.",
                  "Bloomberg reports that Intel is in talks to buy Y.",
                  "Bloomberg said it will cut 100 jobs.",
                  "Bloomberg said that it will cut 100 jobs.",
                  "The Guardian reports that the minister could resign by Friday.",
                  "According to the Financial Times, the firm plans to list in March."):
            s = {**GUARDIAN, "source": "Bloomberg", "reports": [{"outlet": "Reuters", "title": "t", "summary": "s"},
                                                                 {"outlet": "Financial Times", "title": "t", "summary": "s"},
                                                                 {"outlet": "The Guardian", "title": "t", "summary": "s"}]}
            c = {"dek": "", "linkedin_post": x}
            copy.strip_attributions(s, c)
            self.assertEqual(c["linkedin_post"], x)

    def test_a_single_newsroom_story_keeps_its_attribution(self):
        one = story("Labour MPs write", "Dozens signed.", source="The Guardian")
        c = {"dek": "", "linkedin_post": "The Guardian reports that dozens of Labour MPs signed a letter to Keir Starmer."}
        copy.strip_attributions(one, c)
        self.assertTrue(c["linkedin_post"].startswith("The Guardian reports that"))

    def test_the_live_1117_sentence_is_not_broken(self):
        s = story("Talks revive", "x", source="Reuters", reports=[{"outlet": "Bloomberg", "title": "t", "summary": "s"}])
        c = {"dek": "", "linkedin_post": "Reuters reported the revival, citing people familiar with the matter."}
        copy.strip_attributions(s, c)
        self.assertEqual(c["linkedin_post"], "Reuters reported the revival, citing people familiar with the matter.")

    def test_audit_leaves_a_hedged_attribution_alone(self):
        from aidaily import desk
        post = {"headlines": ["Intel eyes deal"], "dek": "Talks are reported.", "sources": ["Bloomberg", "Reuters"],
                "body": "Bloomberg reports that Intel is in talks to buy Y. Shares rose."}
        self.assertFalse(any("opens with a newsroom" in p for p in desk.audit(post)))

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

    def test_countries_with_a_real_senate_and_names_that_only_look_like_a_chamber_are_left_alone(self):
        for ok in ("Pakistan's Senate approves the bill", "Thailand's Senate", "Poland's Senate", "Belgium's Senate", "Czech Republic's Senate",
                   "Romania's Senate", "Kenya's Senate", "Nigeria's Senate", "Egypt's Senate", "Kazakhstan's Senate", "Jordan's Senate",
                   "Netherlands' Senate", "Ireland's Senate", "Malaysia's Senate", "Irish Senate",
                   "Irish Congress of Trade Unions", "Nigeria's Senate President Godswill Akpabio", "Japan's Senate Majority Leader",
                   "Britain's Congress Party", "Ireland's Senate minority leader"):
            self.assertEqual(copy.fix_legislature(ok), ok, ok)
            self.assertEqual(copy.wrong_chamber(ok), "", ok)

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


class CompanyTag(unittest.TestCase):
    def tagged(self, title, headline, summary="", company="", orgs=()):
        s = story(title, summary or title)
        rows = [row(headline=headline, dek="", x_post="x", linkedin_post="", company=company, orgs=list(orgs))]
        copy.apply([s], rows)
        return s

    def test_the_company_the_headline_names_is_tagged(self):
        s = self.tagged("OpenAI raises $40 billion", "OpenAI raises $40 billion")
        self.assertEqual(s["company"], "OpenAI")
        self.assertEqual(s["orgs"][0], "OpenAI")
        self.assertEqual(self.tagged("Nvidia chips face new China limits", "Nvidia chips face new China limits")["company"], "Nvidia")

    def test_a_product_stands_for_its_maker(self):
        s = self.tagged("Apple unveils new iPhone", "Apple unveils a new iPhone")
        self.assertEqual(s["company"], "Apple")
        self.assertEqual(self.tagged("The new iPhone sells out", "The new iPhone sells out")["company"], "Apple")

    def test_a_company_the_model_listed_is_tagged_when_the_headline_names_it(self):
        s = self.tagged("Swiggy's Instamart to lay off 340 employees", "Swiggy's Instamart to lay off 340 employees",
                        orgs=["Swiggy", "Instamart"])
        self.assertEqual(s["company"], "Swiggy")

    def test_a_company_the_headline_does_not_name_is_replaced_by_the_one_it_does(self):
        s = self.tagged("Meta and Amazon talk about lifting the block on its agent", "Meta and Amazon talk about lifting the block on its agent",
                        company="Muse", orgs=["Meta", "Amazon"])
        self.assertEqual(s["company"], "Meta")

    def test_the_models_own_company_stands_when_the_headline_has_it(self):
        s = self.tagged("Coupang revenue rises", "Coupang revenue rises", company="Coupang", orgs=["Coupang"])
        self.assertEqual(s["company"], "Coupang")

    def test_ordinary_words_are_not_companies(self):
        for h in ("Police target a ring of smugglers", "Shell shock hits markets as ceasefire fails", "Wall Street rises as AI trade rebounds"):
            self.assertEqual(self.tagged(h, h)["company"], "", h)

    def test_a_name_missing_from_the_source_is_not_tagged(self):
        s = story("Chipmaker raises $40 billion", "A chipmaker raised money.")
        rows = [row(headline="Nvidia raises $40 billion", dek="", x_post="x", linkedin_post="")]
        copy.apply([s], rows)
        self.assertEqual(s["company"], "")


SRC_A = ("Official results were published on Friday for this month's election, showing the right-leaning ruling bloc "
         "led by the National Party two seats short of a majority.")
SRC_B = "Prime Minister Christopher Luxon needs the centrist Opportunity Party's support to remain in power, officials said."


class Depth(unittest.TestCase):
    def two_outlets(self):
        return story("New Zealand's ruling coalition falls just short of majority in final count", SRC_A, source="RNZ",
                     reports=[{"outlet": "Reuters", "title": "Luxon needs a third partner", "summary": SRC_B},
                              {"outlet": "AP", "title": "NZ count ends", "summary": "Turnout was 82 percent."}])

    def test_the_prompt_asks_for_two_sentences_from_one_newsroom_and_three_to_five_from_more(self):
        text = copy.prompt("id: 0")
        self.assertIn("Two sentences when one newsroom reported", text)
        self.assertIn("three to five when two or more newsrooms", text)
        self.assertIn("under 600 characters", text)

    def test_the_writer_sees_the_whole_summary_the_feeds_kept(self):
        long = "x " * 295 + "end600"
        s = story("T", long)
        s["reports"] = [{"outlet": "AP", "title": "t", "summary": long}]
        self.assertEqual(copy.block([s]).count("end600"), 2)

    def test_a_copied_sentence_is_cut_and_the_other_facts_stay(self):
        s = self.two_outlets()
        rows = [row(headline="New Zealand's ruling coalition falls just short of majority", dek="Luxon needs a third partner.",
                    x_post="x", linkedin_post="Official results were published on Friday for this month's election, showing the "
                                              "right-leaning ruling bloc led by the National Party. Turnout was 82 percent. "
                                              "The count ended with the bloc two seats short.\n\nSource: RNZ")]
        copy.apply([s], rows)
        self.assertNotIn("Official results were published", s["linkedin_post"])
        self.assertIn("Turnout was 82 percent", s["linkedin_post"])

    def test_own_words_pass(self):
        self.assertEqual(copy.copied_run("The final tally left the National Party-led bloc two seats shy of a majority.", SRC_A), "")
        self.assertTrue(copy.copied_run("Results were published on Friday for this month's election, showing the right-leaning ruling bloc.", SRC_A))

    def test_one_short_quote_is_allowed_and_a_second_or_long_one_is_cut(self):
        s = story("Minister vows reform", "The minister told parliament the budget will protect schools and hospitals. "
                  "She also said taxes would not rise this year for any household.", source="BBC")
        c = {"dek": "", "x_post": "", "headline": "h", "linkedin_post":
             'She said "the budget will protect schools and hospitals". She added "taxes would not rise this year for any household".\n\n'
             'Source: BBC'}
        cut = copy.strip_copied(s, c)
        self.assertEqual(len(cut), 1)
        self.assertIn("protect schools", c["linkedin_post"])
        c = {"dek": "", "x_post": "", "headline": "h", "linkedin_post":
             'She said "we will protect schools and hospitals and keep taxes flat for every single household in the whole country".'}
        self.assertEqual(len(copy.strip_copied(s, c)), 1)

    def test_a_term_in_quote_marks_is_not_a_quote(self):
        s = story("Court rules", "The ruling is a landmark.")
        c = {"dek": "", "x_post": "", "headline": "h", "linkedin_post": 'The court called the move "underhanded". It also called it "unlawful".'}
        self.assertEqual(copy.strip_copied(s, c), [])

    def test_the_report_is_capped_to_what_the_slide_holds_but_keeps_two_sentences(self):
        sents = ["A fact number %d states something specific about the story in about twenty words, with names and places." % i
                 for i in range(1, 6)]
        post = " ".join(sents) + "\n\nSource: RNZ"
        out = copy.cap_report("A dek of some length.", post)
        self.assertLessEqual(len("A dek of some length.") + len(copy.body_of(out)), copy.MAX_REPORT)
        self.assertEqual(len(copy.sentences(copy.body_of(out))), 5 if len(" ".join(sents)) + 21 <= copy.MAX_REPORT else len(copy.sentences(copy.body_of(out))))
        self.assertTrue(out.endswith("Source: RNZ"))
        two = copy.cap_report("D" * 590, sents[0] + " " + sents[1])
        self.assertEqual(len(copy.sentences(two)), 2)

    def test_a_single_source_story_is_still_thin_below_two_sentences(self):
        self.assertIn("too thin", copy.thin({"dek": "A fact.", "linkedin_post": "One sentence only here.\n\nSource: RNZ"}))


def grouped():
    return story("Spain heads to a snap election on Sunday",
                 "Prime Minister Pedro Sanchez called the vote after his coalition lost its budget majority. Polls open at 9am.",
                 source="Reuters",
                 reports=[{"outlet": "Bloomberg Politics", "title": "Spain's election tests the far right",
                           "summary": "The People's Party leads the polls with 33 percent, ahead of the Socialists on 27 percent."},
                          {"outlet": "AP", "title": "Spanish voters pick a new parliament",
                           "summary": "Housing costs and immigration dominate the campaign, voters told reporters."}])


class BySource(unittest.TestCase):
    GOOD = [{"outlet": "Reuters", "line": "Sanchez called the vote once his coalition could no longer pass a budget."},
            {"outlet": "Bloomberg Politics", "line": "The People's Party is ahead in the polls on 33 percent against 27 for the Socialists."},
            {"outlet": "AP", "line": "Voters list housing costs and immigration as the issues of the campaign."}]

    def setUp(self):
        # the switch ships off (desk.json growth.by_source); these tests run with it on
        self._switch = copy.switch
        copy.switch = lambda name: True if name == "by_source" else self._switch(name)
        self.addCleanup(setattr, copy, "switch", self._switch)

    def test_lines_that_pass_are_kept_per_newsroom(self):
        kept = copy.check_by_source(grouped(), self.GOOD)
        self.assertEqual([k["outlet"] for k in kept], ["Reuters", "Bloomberg Politics", "AP"])

    def test_a_number_from_another_newsroom_fails_that_line(self):
        rows = [self.GOOD[0], {"outlet": "AP", "line": "The People's Party leads with 33 percent of the vote."}, self.GOOD[2]]
        kept = copy.check_by_source(grouped(), rows)
        self.assertEqual([k["outlet"] for k in kept], ["Reuters", "AP"])

    def test_an_unlisted_outlet_a_copy_a_quote_and_a_second_line_fail(self):
        rows = [{"outlet": "The Times", "line": "Sanchez called the vote."},
                {"outlet": "Reuters", "line": "Prime Minister Pedro Sanchez called the vote after his coalition lost its budget majority."},
                {"outlet": "AP", "line": 'Voters said "housing costs and immigration dominate the campaign" in many towns.'},
                {"outlet": "AP", "line": "Housing costs and immigration worry voters."}]
        self.assertEqual(copy.check_by_source(grouped(), rows), [])  # one passes: a list needs two
        rows.append(self.GOOD[0])
        self.assertEqual([k["outlet"] for k in copy.check_by_source(grouped(), rows)], ["AP", "Reuters"])

    def test_a_list_of_one_is_dropped_and_an_outlet_is_used_once(self):
        self.assertEqual(copy.check_by_source(grouped(), self.GOOD[:1]), [])
        self.assertEqual(copy.check_by_source(grouped(), [self.GOOD[0], self.GOOD[0]]), [])

    def test_commentary_another_newsroom_and_attribution_openers_fail(self):
        rows = [{"outlet": "Reuters", "line": "For Europe, the vote has become a referendum on the whole political order."},
                {"outlet": "AP", "line": "Bloomberg says housing costs and immigration dominate the campaign."},
                {"outlet": "Bloomberg Politics", "line": "Bloomberg reports that the People's Party leads."}]
        self.assertEqual(copy.check_by_source(grouped(), rows), [])

    def test_two_sentences_and_garbage_rows_fail(self):
        rows = [{"outlet": "Reuters", "line": "Sanchez called the vote. His coalition lost its budget majority."}, "x", None,
                {"outlet": "AP"}, {"line": "orphan"}]
        self.assertEqual(copy.check_by_source(grouped(), rows), [])
        self.assertEqual(copy.check_by_source(grouped(), "not a list"), [])

    def test_apply_stores_the_list_and_the_post_carries_it_unrendered(self):
        s = grouped()
        rows = [row(headline="Spain heads to a snap election on Sunday", dek="Polls open at 9am.", x_post="x",
                    linkedin_post="The People's Party leads the polls with 33 percent against 27 for the Socialists. Housing costs "
                                  "and immigration dominate the campaign.\n\nSource: Reuters", by_source=self.GOOD)]
        copy.apply([s], rows)
        self.assertEqual(s["copy_status"], "ok")
        self.assertEqual(len(s["by_source"]), 3)

    def test_a_fallback_story_has_none(self):
        s = grouped()
        copy.apply([s], [row(headline="Spain votes on 99 percent", dek="", x_post="", linkedin_post="", by_source=self.GOOD)])
        self.assertEqual(s["by_source"], [])

    def test_the_switch_ships_off_and_the_prompt_example_has_single_braces(self):
        import pathlib
        cfg = json.loads((pathlib.Path(copy.__file__).parent.parent / "desk.json").read_text())
        self.assertFalse(cfg["growth"]["by_source"])
        text = copy.prompt("id: 0")
        self.assertIn('{"outlet": "<name exactly as listed>"', text)
        self.assertNotIn('{{"outlet"', text)

    def test_the_prompt_asks_for_it_and_the_switch_turns_it_off(self):
        self.assertIn("- by_source:", copy.prompt("id: 0"))
        orig = copy.switch
        try:
            copy.switch = lambda name: False if name == "by_source" else orig(name)
            self.assertNotIn("- by_source:", copy.prompt("id: 0"))
            s = grouped()
            copy.apply([s], [row(headline="Spain heads to a snap election on Sunday", dek="Polls open at 9am.", x_post="",
                                 linkedin_post="", by_source=self.GOOD)])
            self.assertEqual(s["by_source"], [])
        finally:
            copy.switch = orig

    def test_no_page_prints_it(self):
        import pathlib
        for f in ("site.py", "templates.py", "sitepages.py", "views.py"):
            self.assertNotIn("by_source", (pathlib.Path(copy.__file__).parent / f).read_text(), f)


if __name__ == "__main__":
    unittest.main()


class CompanyTag(unittest.TestCase):
    def test_visa_applications_are_not_the_card_company(self):
        s = story("Visa applications from India fall 20%", "Visa applications from India fell 20% this year.")
        s.update({"headline": "Visa applications from India fall 20%", "company": "", "orgs": []})
        copy.tag_company(s)
        self.assertEqual(s["company"], "")

    def test_a_court_or_a_central_bank_is_not_a_company(self):
        for org in ("Supreme Court", "Federal Reserve", "European Central Bank", "Bank of England"):
            s = story(f"{org} holds firm", f"The {org} held.")
            s.update({"headline": f"{org} holds firm", "company": "", "orgs": [org]})
            copy.tag_company(s)
            self.assertEqual(s["company"], "", org)
        s = story("Bank of America profit rises", "Bank of America said profit rose.")
        s.update({"headline": "Bank of America profit rises", "company": "", "orgs": ["Bank of America"]})
        copy.tag_company(s)
        self.assertEqual(s["company"], "Bank of America")


class CopiedRuns(unittest.TestCase):
    def test_a_run_of_proper_nouns_is_not_a_copy(self):
        src = "Figures come from the Office for National Statistics and the Home Office, the department said."
        self.assertEqual(copy.copied_run("It comes from the Office for National Statistics and the Home Office.", src), "")

    def test_a_copied_plain_run_is_still_cut(self):
        src = "The minister said prices would keep rising through the winter because of weak supply."
        self.assertNotEqual(copy.copied_run("Prices would keep rising through the winter because of weak supply, he said.", src), "")


class ReportCap(unittest.TestCase):
    SENTS = ["Spain's coalition lost its budget majority on Thursday after two junior partners walked out of the talks.",
             "Prime Minister Pedro Sanchez then called a snap election for Sunday, four months before the term ends.",
             "The People's Party leads the polls with 33 percent against 27 percent for the Socialists in the latest survey.",
             "Housing costs and immigration dominate the campaign, voters told reporters in Madrid and Valencia this week.",
             "Polls open at 9am local time and the first projections are due shortly after they close in the evening."]

    def test_the_site_report_is_whole_and_the_slide_text_is_capped(self):
        from aidaily import desk
        sents = [x[:-1] + ", according to figures released by the government and the pollsters on Friday." for x in self.SENTS]
        s = {"dek": "Voters go to the polls on Sunday.", "linkedin_post": " ".join(sents) + "\n\nSource: Reuters"}
        self.assertEqual(len(copy.sentences(copy.body_of(s["linkedin_post"]))), 5)
        text = desk.detail_text({}, s, False, [])
        self.assertLessEqual(len(text), copy.MAX_REPORT + 1)
        self.assertLess(len(copy.sentences(text)), 6)
        self.assertGreaterEqual(len(copy.sentences(text)), 2)
