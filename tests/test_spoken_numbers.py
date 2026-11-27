"""Narration numbers: a figure the script says in words must be one the published copy states (rounded the way speech
rounds), or one of the day's conversions of a published sum. A bare count or a year is not a claim."""
import unittest

from aidaily import spoken as S

PUB = ("Retailer books $387 million in tariff refunds. Net profit rose 2.9% to 21.5 trillion won, and the firm cut 250 jobs. "
       "Rates stayed at 0.25%.")


class Parse(unittest.TestCase):
    def test_numbers_said_in_words_become_values(self):
        got = dict((p, v) for v, p in S.spoken_numbers(
            "It rose zero point two percent. A deal worth two point five billion dollars. Twenty-one and a half trillion won. "
            "Two hundred and fifty jobs. A hundred thousand customers."))
        self.assertEqual(got["zero point two percent"], 0.2)
        self.assertEqual(got["two point five billion"], 2.5e9)
        self.assertEqual(got["twenty one and a half trillion"], 21.5e12)
        self.assertEqual(got["two hundred and fifty"], 250)
        self.assertEqual(got["a hundred thousand"], 1e5)

    def test_counts_and_years_are_not_claims(self):
        self.assertEqual(S.spoken_numbers("Three people met on the third floor in twenty twenty six, hundreds more came, millions watched."), [])

    def test_published_numbers_carry_their_scale(self):
        vals = S.published_values(PUB)
        for v in (387e6, 387, 2.9, 21.5e12, 250, 0.25):
            self.assertIn(v, vals)


class Gaps(unittest.TestCase):
    def gaps(self, script, extra=""):
        return S.number_gaps(script, PUB, extra)

    def test_stated_figures_pass_even_rounded(self):
        self.assertEqual(self.gaps("It booked about three hundred and ninety million dollars."), [])
        self.assertEqual(self.gaps("Profit rose nearly three percent, to about twenty-one and a half trillion won."), [])
        self.assertEqual(self.gaps("The firm cut two hundred and fifty jobs."), [])
        self.assertEqual(self.gaps("Rates stayed at zero point two five percent."), [])

    def test_an_invented_or_changed_figure_is_a_gap(self):
        self.assertEqual(self.gaps("It booked three hundred and eighty seven billion dollars."), ["three hundred and eighty seven billion"])
        self.assertEqual(self.gaps("Profit rose twelve percent."), ["twelve percent"])
        self.assertEqual(self.gaps("The firm cut two thousand five hundred jobs."), ["two thousand five hundred"])

    def test_a_conversion_of_a_published_sum_is_allowed(self):
        self.assertEqual(self.gaps("That is about two point six billion dollars.", "¥400 billion = about 2.6 billion dollars"), [])
        self.assertEqual(self.gaps("That is about two point six billion dollars."), ["two point six billion"])


class InTheGate(unittest.TestCase):
    SCRIPT = ("Retailer books about three hundred and ninety million dollars in tariff refunds. Net profit rose nearly three percent "
              "at the firm and it cut jobs. That is the figure to watch for the next quarter today and it is a plain one for now.")

    def test_the_gate_names_a_number_that_is_not_in_the_copy(self):
        bad = self.SCRIPT.replace("nearly three percent", "twelve percent")
        got = S.gate(bad, ["Net profit rose 2.9%"], PUB)
        self.assertIn("number not in the published copy: 'twelve percent'", got)
        self.assertFalse([p for p in S.gate(self.SCRIPT, ["Net profit rose 2.9%"], PUB) if p.startswith("number not")])


if __name__ == "__main__":
    unittest.main()
