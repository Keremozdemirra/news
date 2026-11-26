import unittest

from aidaily.__main__ import plan


def st(title, cat, outlets):
    return {"title": title, "category": cat, "outlets": outlets, "url": title}


class Plan(unittest.TestCase):
    def test_discussion_only_story_is_not_breaking(self):
        slots = plan([st("Blog post about Nvidia stock", "markets", ["HN Front Page"]),
                      st("OpenAI ships agent", "launch", ["TechCrunch AI"])])
        self.assertEqual([s["title"] for s in slots["breaking"]], ["OpenAI ships agent"])
        self.assertEqual(slots["business"], [])

    def test_funding_card_does_not_repeat_breaking(self):
        rows = [st(f"Startup {i} raises $10M", "funding", ["TechCrunch AI"]) for i in range(5)]
        slots = plan(rows)
        self.assertFalse({s["title"] for s in slots["funding"]} & {s["title"] for s in slots["breaking"]})
