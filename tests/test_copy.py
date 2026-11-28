import json
import unittest
from unittest import mock

from aidaily import copy


class R:
    def __init__(self, rows):
        self.returncode, self.stderr = 0, ""
        self.stdout = json.dumps({"result": json.dumps(rows)})


def story():
    return {"title": "Nscale raises $3.36B in convertible financing", "summary": "Ahead of its US IPO.",
            "source": "TechCrunch"}


class SixWordRule(unittest.TestCase):
    """The legal answer's rules, switched on here: they ship off until the owner decides (see VERBATIM_WORDS)."""
    def setUp(self):
        for name, v in (("VERBATIM_WORDS", 6), ("HEADLINE_RUN", 6)):
            p = mock.patch.object(copy, name, v)
            p.start()
            self.addCleanup(p.stop)

    SRC = {"title": "Number of Neets in UK falls below a million as Burnham pushes to tackle crisis", "summary": "", "source": "Guardian",
           "reports": [{"outlet": "BBC", "title": "Youth jobless count drops under one million", "summary": ""}]}

    def test_a_six_word_run_from_the_source_is_copied(self):
        s = dict(self.SRC, summary="Oil futures ended the session lower with the market awaiting the weekend meeting of OPEC.")
        self.assertTrue(copy.copied_run("Oil futures ended the session lower on Friday.", copy.source_text(s)))
        self.assertEqual(copy.copied_run("Oil futures ended lower on Friday.", copy.source_text(s)), "")

    def test_a_headline_equal_to_or_running_six_words_with_a_source_headline_is_rejected(self):
        self.assertTrue(copy.headline_copied(self.SRC, "Youth jobless count drops under one million"))   # equal to another newsroom's
        self.assertTrue(copy.headline_copied(self.SRC, "Youth jobless count drops under one million, ONS says"))
        self.assertTrue(copy.headline_copied(self.SRC, "Number of Neets in UK falls below a million this quarter"))
        self.assertEqual(copy.headline_copied(self.SRC, "UK youth Neet count dips under 1 million"), "")

    def test_verify_reports_it(self):
        row = {"headline": "Number of Neets in UK falls below a million", "dek": "", "x_post": "", "linkedin_post": ""}
        self.assertTrue(any("copies a source headline" in p for p in copy.verify(self.SRC, row)))


class NoHoleLeftBehind(unittest.TestCase):
    """2026-11-28-0736-1 printed "Analysts describe the scale of the walkovers as ." : the hype filter removed the predicate
    "unprecedented" and left its sentence behind."""
    SRC = {"title": "Sarawak GPS wins 29 seats unopposed at close of nominations", "source": "CNA", "reports": [],
           "summary": "Gabungan Parti Sarawak won 29 of 82 seats uncontested. The big peninsular parties stayed out of the state polls. "
                      "Analysts say the scale of the walkovers is unprecedented. Forming the state government takes 42 seats."}
    ROW = {"id": 0, "headline": "Sarawak's GPS wins a record 29 state seats unopposed", "dek": "Gabungan Parti Sarawak won 29 of 82 seats uncontested.",
           "x_post": "GPS wins 29 seats unopposed", "linkedin_post": "The big peninsular parties stayed out of the polls. "
           "Analysts describe the scale of the walkovers as unprecedented. Forming the government takes 42 seats.\n\nSource: CNA"}

    def test_a_sentence_whose_only_content_was_the_hype_word_is_dropped_whole(self):
        s = dict(self.SRC)
        copy.apply([s], [dict(self.ROW)])
        self.assertEqual(s["copy_status"], "ok")
        self.assertNotIn("walkovers", s["linkedin_post"])
        shown = s["dek"] + " " + s["linkedin_post"]
        self.assertNotIn("as .", shown)
        self.assertFalse(copy.GAP.search(shown))
        self.assertIn("Forming the government takes 42 seats.", shown)

    def test_hype_that_is_only_an_intensifier_still_goes_and_the_fact_stays(self):
        self.assertEqual(copy.remove_hype("linkedin_post", "The firm made a massive revision to its forecast.\n\nSource: CNA"),
                         "The firm made a revision to its forecast.\n\nSource: CNA")

    def test_a_headline_keeps_its_words_rather_than_a_hole(self):
        self.assertEqual(copy.remove_hype("headline", "Walkovers seen as unprecedented"), "Walkovers seen as unprecedented")

    def test_any_other_step_that_leaves_a_hole_costs_only_that_sentence(self):
        c = {"dek": "A fact stands.", "linkedin_post": "One fact. The scale was described as . Another fact.\n\nSource: CNA", "x_post": "x"}
        self.assertEqual(copy.drop_gaps(c), ["The scale was described as ."])
        self.assertEqual(c["linkedin_post"], "One fact. Another fact.\n\nSource: CNA")

    def test_a_headline_with_a_hole_is_rejected(self):
        row = {"headline": "Walkovers described as .", "dek": "", "x_post": "", "linkedin_post": ""}
        self.assertTrue(any("word is missing" in p for p in copy.verify(self.SRC, row)))


class ExactHeadline(unittest.TestCase):
    SRC = {"title": "Iran denies involvement in Kuwait strike that killed two Italians", "summary": "", "source": "Africanews", "reports": []}

    def test_a_headline_equal_to_the_source_headline_is_rejected_by_default(self):
        self.assertTrue(copy.headline_copied(self.SRC, "Iran denies involvement in Kuwait strike that killed two Italians"))
        self.assertTrue(copy.headline_copied(self.SRC, "Iran Denies Involvement In Kuwait Strike That Killed Two Italians."))
        self.assertTrue(copy.headline_copied(self.SRC, "Iran denies involvement in the Kuwait strike that killed two Italians"))  # a small word

    def test_a_partial_run_is_allowed_by_default(self):
        self.assertEqual(copy.headline_copied(self.SRC, "Iran denies involvement in Kuwait strike, Tehran says"), "")
        self.assertEqual(copy.headline_copied(self.SRC, "Two Italians killed in Kuwait strike; Iran denies a role"), "")

    def test_the_prompt_tells_the_writer(self):
        self.assertIn("never reuse a source headline", copy.prompt("S"))


class ThinWithContext(unittest.TestCase):
    CTX = [{"text": "A fact.", "label": "ECB", "url": "https://x.test/a"}, {"text": "Another fact.", "label": "ECB", "url": "https://x.test/b"}]

    def test_a_dek_and_two_gated_facts_are_not_thin(self):
        self.assertEqual(copy.thin({"dek": "A dek.", "linkedin_post": "", "context": self.CTX}), "")

    def test_one_fact_is_still_thin(self):
        self.assertTrue(copy.thin({"dek": "A dek.", "linkedin_post": "", "context": self.CTX[:1]}))

    def test_no_dek_is_held_whatever_the_context(self):
        self.assertEqual(copy.thin({"dek": "", "linkedin_post": "", "context": self.CTX}), "no dek")


class Copy(unittest.TestCase):
    def test_good_copy_is_kept(self):
        s = story()
        rows = [{"id": 0, "headline": "Nscale raises $3.36B before its US IPO", "dek": "Convertible notes.",
                 "company": "Nscale", "figure": "$3.36B", "script": "Nscale raised 3.36 billion dollars.",
                 "x_post": "Nscale raises $3.36B", "linkedin_post": "Nscale raised $3.36B.\n\nSource: TechCrunch"}]
        self.assertEqual(copy.write([s], runner=lambda *a, **k: R(rows)), [])
        self.assertEqual(s["copy_status"], "ok")
        self.assertEqual(s["figure"], "$3.36B")

    def test_invented_number_falls_back_to_source(self):
        s = story()
        rows = [{"id": 0, "headline": "Nscale raises $4B at a $20B valuation", "dek": "", "figure": "$4B",
                 "script": "", "x_post": "", "linkedin_post": ""}]
        rejected = copy.write([s], runner=lambda *a, **k: R(rows))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(s["copy_status"], "fallback")
        self.assertEqual(s["headline"], s["title"])

    def test_dashes_are_removed(self):
        s = story()
        rows = [{"id": 0, "headline": "Nscale — raises $3.36B", "dek": "", "figure": "", "script": "",
                 "x_post": "", "linkedin_post": ""}]
        copy.write([s], runner=lambda *a, **k: R(rows))
        self.assertNotIn("—", s["headline"])


class Grounding(unittest.TestCase):
    SRC = ("Big companies warn lack of AI openness could hit investment in Europe. Multinationals evaluating "
           "countries' approach to AI before making expansion plans, say executives")

    def test_commentary_closers_are_caught(self):
        for s in ["For Europe, AI policy has become investment policy.",
                  "A shift worth watching for anyone exposed to Nvidia's China revenue.",
                  "The product question is settled faster than the trust question."]:
            self.assertTrue(copy.ungrounded(s, self.SRC), s)

    def test_reported_sentence_passes(self):
        self.assertFalse(copy.ungrounded(
            "Multinationals say they evaluate each country's approach to AI before expansion plans.", self.SRC))

    def test_story_out_of_slot_falls_back(self):
        s = story()
        rows = [{"id": 0, "headline": "Nscale raises $3.36B", "dek": "", "figure": "", "script": "",
                 "x_post": "", "linkedin_post": "", "fits_category": False}]
        self.assertEqual(len(copy.write([s], runner=lambda *a, **k: R(rows))), 1)

    def test_quoted_id_still_matches(self):
        s = story()
        rows = [{"id": "0", "headline": "Nscale raises $3.36B", "dek": "", "figure": "", "x_post": "", "linkedin_post": ""}]
        self.assertEqual(copy.apply([s], rows), [])
        self.assertEqual(s["copy_status"], "ok")


class ShortArticles(unittest.TestCase):
    """Kerem, 2026-11-28, "more news + shorter articles": a dek and one report sentence of 12+ words that adds a fact."""
    HEAD = "S&P upgrades South Africa's credit rating"
    DEK = "The agency lifted the rating after years of stagnation."

    def thin(self, report):
        return copy.thin({"headline": self.HEAD, "dek": self.DEK, "linkedin_post": report})

    def test_one_sentence_with_a_new_fact_passes(self):
        self.assertEqual(self.thin("The upgrade moves the long-term foreign currency rating to BB, its first rise since 2005."), "")

    def test_a_sentence_that_only_rewords_the_dek_does_not(self):
        self.assertTrue(self.thin("The agency upgraded South Africa's credit rating after years of stagnation in the country."))

    def test_under_twelve_words_does_not(self):
        self.assertTrue(self.thin("The rating is now BB since 2005."))

    def test_a_short_article_is_not_indexed(self):
        from aidaily import site
        p = {"dek": self.DEK, "body": "The upgrade moves the long-term foreign currency rating to BB, its first rise since 2005.",
             "sources": ["Reuters", "Bloomberg"]}
        self.assertTrue(copy.short(p))
        self.assertFalse(site.indexable(p))
        self.assertFalse(copy.short(dict(p, body=p["body"] + " Treasury welcomed the decision on Saturday.")))
