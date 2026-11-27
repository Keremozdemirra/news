"""Fact gate coverage: the caption, the figure card and the so-what line are written after copy.verify() ran, so a number
on them must come from the article's own text. A ticker, a hashtag and the credit lines are not claims."""
import unittest

from aidaily import copy, desk

POST = {"headlines": ["Taiwan votes Saturday in local elections"], "dek": "More than 11,000 officials are on the ballot.",
        "body": "Voters go to the polls on Saturday, Nov 28.", "sources": ["The Guardian"]}


class Gap(unittest.TestCase):
    def gap(self, **kw):
        return copy.surface_gap({**POST, **kw})

    def test_a_caption_number_the_article_does_not_state_is_named(self):
        self.assertEqual(self.gap(caption="Taiwan votes\n\nVoters will choose leaders across 22 districts."), {"caption": ["22"]})

    def test_numbers_the_article_states_pass_however_they_are_written(self):
        self.assertEqual(self.gap(caption="Over 11000 officials are on the ballot on Nov 28."), {})
        self.assertEqual(self.gap(caption="More than 11,000 officials."), {})

    def test_the_figure_card_and_the_so_what_line_are_covered(self):
        self.assertEqual(self.gap(figure="11,000"), {})
        self.assertEqual(self.gap(figure="12,000"), {"figure": ["12000"]})
        self.assertEqual(self.gap(so_what="It is a test for 2028."), {"so_what": ["2028"]})

    def test_tickers_hashtags_links_and_credit_lines_are_not_claims(self):
        caption = ("Meituan (HKEX: 3690) · Business\n\nVoters go.\n\nReported by Bloomberg 2026.\nSource: wsj.com/2026\n"
                   "Send this to a friend. https://x.test/a/12345 #news2026 #business")
        self.assertEqual(self.gap(caption=caption), {})

    def test_a_post_without_those_fields_has_no_gap(self):
        self.assertEqual(self.gap(), {})


class InTheAudit(unittest.TestCase):
    def test_the_audit_holds_the_post(self):
        post = {"headlines": ["FCC clears SpaceX to deploy 1 million satellites"], "topic": "Tech", "logo_names": ["SpaceX"],
                "body": "The FCC authorized SpaceX on Tuesday. Boston Consulting Group estimates launch costs stay high for every "
                        "operator that plans a network in orbit.",
                "dek": "The approval covers a network meant to run data centers in orbit.",
                "caption": "FCC clears SpaceX\n\n#news #business #spacex", "photo_file": "SpaceX headquarters, Hawthorne.jpg",
                "credit": "Photo: NASA"}
        self.assertEqual(desk.audit(post), [])
        post["caption"] = "FCC clears SpaceX for 4,000 more satellites\n\n#news"
        self.assertTrue(any("caption states numbers the article does not" in p for p in desk.audit(post)))


if __name__ == "__main__":
    unittest.main()
