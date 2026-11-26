import unittest
from datetime import datetime, timedelta, timezone

from aidaily import rank

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
SRC = {"tc": {"name": "TechCrunch", "category": "news"}, "hn": {"name": "Hacker News", "category": "community"},
       "oa": {"name": "OpenAI", "category": "lab"}, "biz": {"name": "CNBC", "category": "business"}}


def it(title, src, hours=1, url=None, **kw):
    return dict(title=title, source_id=src, url=url or f"https://x/{abs(hash(title))}",
                published=NOW - timedelta(hours=hours), summary="", **kw)


class Rank(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(rank.classify("Nscale raises $3.36B ahead of IPO"), "funding")
        self.assertEqual(rank.classify("Google launches Gemini 4"), "launch")
        self.assertEqual(rank.classify("EU court fines Meta over AI training"), "policy")

    def test_cluster_merges_same_event(self):
        items = [it("OpenAI releases GPT-6 with longer memory", "tc"),
                 it("OpenAI releases GPT-6, a model with longer memory", "hn", points=900),
                 it("Anthropic hires new CFO", "tc")]
        stories = rank.rank(items, SRC, now=NOW)
        self.assertEqual(len(stories), 2)
        self.assertEqual(len(stories[0]["outlets"]), 2)
        self.assertEqual(stories[0]["source"], "TechCrunch")

    def test_breadth_beats_single_source(self):
        many = [it("Nvidia unveils Rubin Ultra AI chip", s) for s in ("tc", "hn", "oa")]
        one = [it("Small AI startup ships a plugin", "tc")]
        stories = rank.rank(many + one, SRC, now=NOW)
        self.assertIn("Rubin", stories[0]["title"])

    def test_drops_old_items_and_off_topic_board_posts(self):
        # newsroom items stay whatever the topic (relevance is judged per story later); a discussion
        # board's post stays only when it is about AI
        src = dict(SRC, hn={"name": "HN Front Page", "category": "community"})
        items = [it("OpenAI launches something", "tc", hours=50), it("Best pizza in Berlin", "hn"),
                 it("Election results reshape parliament", "tc")]
        self.assertEqual([s["title"] for s in rank.rank(items, src, now=NOW)], ["Election results reshape parliament"])

    def test_business_filler_kept_and_labelled(self):
        stories = rank.rank([it("Fed holds rates steady", "biz")], SRC, now=NOW)
        self.assertEqual(stories[0]["category"], "business")


class Research(unittest.TestCase):
    def test_papers_rank_below_news(self):
        src = dict(SRC, ax={"name": "arXiv", "category": "research"})
        items = [it(f"New benchmark for LLM agents number {i} released", "ax") for i in range(8)]
        items.append(it("Meta acquires AI chip startup", "tc", hours=6))
        stories = rank.rank(items, src, now=NOW)
        self.assertEqual(stories[0]["source"], "TechCrunch")
        self.assertTrue(all(s["category"] == "research" for s in stories[1:]))

    def test_one_source_cannot_fill_the_top(self):
        items = [it(f"OpenAI ships feature {w}", "tc") for w in "abcdefg"] + [it("Google ships Gemini tool", "hn")]
        top = [s["source"] for s in rank.rank(items, SRC, now=NOW)[:5]]
        self.assertIn("Hacker News", top)


class Paraphrase(unittest.TestCase):
    def test_paraphrases_merge(self):
        a = rank.tokens("Anthropic’s CEO is about to have dinner with President Trump")
        b = rank.tokens("Dario Amodei to have dinner with President Trump in a rare meeting")
        c = rank.tokens("Trump said he would dine with Anthropic CEO amid mounting AI debate - AP News")
        self.assertTrue(rank.similar(a, b))
        self.assertTrue(rank.similar(a, c))

    def test_different_launches_stay_apart(self):
        a = rank.tokens("OpenAI launches new image model for designers")
        b = rank.tokens("OpenAI launches new model for enterprise search")
        self.assertFalse(rank.similar(a, b))


class Trace(unittest.TestCase):
    def test_one_newsroom_counts_once(self):
        src = {"a": {"name": "TechCrunch AI"}, "b": {"name": "TechCrunch Main"}, "g": {"name": "Google News AI Search"}}
        items = [it("Story", "a", hours=3), it("Story", "b", hours=5), it("Story - AP News", "g", hours=1)]
        tl = rank.trace(items, src)
        self.assertEqual([p for p, _ in tl], ["TechCrunch", "AP News"])


class Credit(unittest.TestCase):
    def test_techmeme_credits_the_original_outlet(self):
        src = {"tm": {"name": "Techmeme"}}
        item = it("Startup raises $36M (Georgia Wells/Wall Street Journal)", "tm")
        self.assertEqual(rank.publisher(item, src), "Wall Street Journal")
