"""The narration script gate: spoken rhythm, no stock AI phrasing, numbers as words, nothing beyond the copy."""
import unittest

from aidaily import spoken

PUB = ("France enters recession after GDP falls 0.2% in third quarter. The country has now posted two consecutive "
       "quarters of negative growth. INSEE had earlier reported stagnation. Le Monde in English")
GOOD = ("France has entered a recession. Its economy shrank by point two percent in the third quarter. "
        "That's two quarters in a row of negative growth. The statistics office had first called the quarter flat. "
        "So the new number is worse than the first one. Le Monde in English reported the figures this morning, and "
        "the office will publish its full breakdown later.")
FACTS = ["The country has now posted two consecutive quarters of negative growth."]


class Gate(unittest.TestCase):
    def test_a_plain_spoken_script_passes(self):
        self.assertEqual(spoken.gate(GOOD, FACTS, PUB), [])

    def test_stock_phrasing_questions_and_dashes_fail(self):
        for bad, why in (("In a significant development, " + GOOD, "banned"), (GOOD + " What does this mean?", "question"),
                         (GOOD.replace("recession.", "recession — again."), "dash"),
                         (GOOD + " This shows the stakes are high.", "banned"),
                         (GOOD.replace("Its economy", "It's not just the economy but its economy"), "not X but Y")):
            self.assertTrue(any(why in p for p in spoken.gate(bad, FACTS, PUB)), why)

    def test_numbers_must_be_said_as_words(self):
        for n in ("0.2%", "$5 billion", "21.5 trillion", "500bn", "11,000"):
            probs = spoken.gate(GOOD.replace("point two percent", n), FACTS, PUB)
            self.assertTrue(any("number" in p for p in probs), n)
        self.assertEqual(spoken.gate(GOOD.replace("third quarter", "third quarter of 2026"), FACTS, PUB), [])

    def test_length_and_sentence_size(self):
        self.assertTrue(any("words" in p for p in spoken.gate("France is in recession.", FACTS, PUB)))
        long_ = GOOD + " " + " ".join(["word"] * 25) + "."
        self.assertTrue(any("long sentence" in p for p in spoken.gate(long_, FACTS, PUB)))

    def test_nothing_beyond_the_published_copy(self):
        probs = spoken.gate(GOOD.replace("Le Monde in English", "Bloomberg"), FACTS, PUB)
        self.assertTrue(any("Bloomberg" in p for p in probs))
        self.assertTrue(any("not quoted" in p for p in spoken.gate(GOOD, ["France left the euro."], PUB)))
        self.assertTrue(any("no facts" in p for p in spoken.gate(GOOD, [], PUB)))

    def test_one_retry_with_the_findings_then_give_up(self):
        prompts = []

        def ask(p):
            prompts.append(p)
            return '{"script": "Too short.", "facts": []}'
        post = {"headlines": ["France enters recession"], "dek": "", "body": "", "sources": ["Le Monde"]}
        script, probs = spoken.write(post, ask=ask)
        self.assertTrue(probs)
        self.assertEqual(len(prompts), 2)
        self.assertIn("failed these checks", prompts[1])


if __name__ == "__main__":
    unittest.main()
