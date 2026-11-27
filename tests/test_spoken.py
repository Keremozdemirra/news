"""The narration script gate: spoken rhythm, no stock AI phrasing, numbers as words, nothing beyond the copy."""
import unittest

from aidaily import spoken

PUB = ("France enters recession after GDP falls 0.2% in third quarter. The country has now posted two consecutive "
       "quarters of negative growth. INSEE had earlier reported stagnation. Le Monde in English")
GOOD = ("France has slipped into recession, its stats office says. The economy shrank by zero point two percent "
        "in the third quarter. That's the second quarter in a row it got smaller. The office had first called the "
        "quarter flat. For people in France, two shrinking quarters usually mean slower hiring next year, Le Monde in "
        "English reports.")
FACTS = ["The country has now posted two consecutive quarters of negative growth."]


class Gate(unittest.TestCase):
    def test_a_plain_spoken_script_passes(self):
        self.assertEqual(spoken.gate(GOOD, FACTS, PUB), [])

    def test_stock_phrasing_questions_and_dashes_fail(self):
        for bad, why in (("In a significant development, " + GOOD, "banned"), (GOOD + " What does this mean?", "question"),
                         (GOOD.replace("recession,", "recession — again,"), "dash"),
                         (GOOD + " This shows the stakes are high.", "banned"),
                         (GOOD.replace("The economy", "It is not just the economy but the economy"), "not X but Y")):
            self.assertTrue(any(why in p for p in spoken.gate(bad, FACTS, PUB)), why)

    def test_numbers_must_be_said_as_words(self):
        for n in ("0.2%", "$5 billion", "21.5 trillion", "500bn", "11,000"):
            probs = spoken.gate(GOOD.replace("zero point two percent", n), FACTS, PUB)
            self.assertTrue(any("number" in p for p in probs), n)
        self.assertEqual(spoken.gate(GOOD.replace("third quarter", "third quarter of 2026"), FACTS, PUB), [])

    def test_length_and_sentence_size(self):
        self.assertTrue(any("words" in p for p in spoken.gate("France is in recession.", FACTS, PUB)))
        long_ = GOOD.replace("For people", " ".join(["word"] * 22) + ". For people")
        self.assertTrue(any("long sentence" in p for p in spoken.gate(long_, FACTS, PUB)))

    def test_nothing_beyond_the_published_copy(self):
        probs = spoken.gate(GOOD.replace("Le Monde in English", "Bloomberg"), FACTS, PUB)
        self.assertTrue(any("Bloomberg" in p for p in probs))
        self.assertTrue(any("not quoted" in p for p in spoken.gate(GOOD, ["France left the euro."], PUB)))
        self.assertTrue(any("no facts" in p for p in spoken.gate(GOOD, [], PUB)))

    def test_two_retries_with_the_findings_then_give_up(self):
        prompts = []

        def ask(p):
            prompts.append(p)
            return '{"script": "Too short.", "facts": []}'
        post = {"headlines": ["France enters recession"], "dek": "", "body": "", "sources": ["Le Monde"]}
        script, probs = spoken.write(post, ask=ask)
        self.assertTrue(probs)
        self.assertEqual(len(prompts), 3)
        self.assertIn("failed these checks", prompts[2])


if __name__ == "__main__":
    unittest.main()


class Stiff(unittest.TestCase):
    def test_a_sentence_that_restates_an_earlier_one_fails(self):
        bad = GOOD.replace("The office had first called the quarter flat.", "The economy shrank in the third quarter, the office says.")
        self.assertTrue(any("restates" in p for p in spoken.gate(bad, FACTS, PUB)))

    def test_stiff_links_and_a_bare_point_fail(self):
        for bad, why in ((GOOD.replace("The office had first", "Earlier on, the office had first"), "banned"),
                         (GOOD.replace("zero point two", "point two"), "zero point"),
                         (GOOD.replace("The office had first called the quarter flat.", "Le Monde in English reported."), "own")):
            self.assertTrue(any(why in p for p in spoken.gate(bad, FACTS, PUB)), why)

    def test_dollar_amounts_come_from_the_ecb_rates(self):
        m = {"fx": {"rates": {"USD": 1.1, "JPY": 170.0}}}
        self.assertEqual(spoken.conversions("profit of 1.7 trillion yen", m), "1.7 trillion yen = about 11.0 billion dollars")
        self.assertEqual(spoken.conversions("21.5 trillion won", m), "")


class Narration(unittest.TestCase):
    def test_a_long_narration_stretches_the_beats_never_cuts(self):
        from aidaily import shortforms as SF
        plan = SF.timeline("b", [(["h"], 6.0), (["f"], 6.0), (["s"], 6.0)], "e")
        longer = SF.stretch(plan, plan[1] + 6)
        self.assertAlmostEqual(longer[1], plan[1] + 6)
        self.assertEqual(longer[0][-1][3], "end")
        self.assertGreater(longer[0][-1][1], plan[0][-1][1])
        self.assertIs(SF.stretch(plan, plan[1] - 1), plan)
