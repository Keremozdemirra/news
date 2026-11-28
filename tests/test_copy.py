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
