import json
import unittest

from aidaily import copy


class R:
    def __init__(self, rows):
        self.returncode, self.stderr = 0, ""
        self.stdout = json.dumps({"result": json.dumps(rows)})


def story():
    return {"title": "Nscale raises $3.36B in convertible financing", "summary": "Ahead of its US IPO.",
            "source": "TechCrunch"}


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
