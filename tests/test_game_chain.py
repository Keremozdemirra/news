"""Face the Figure deals one chain a day: the figure just revealed is A of the next round."""
import hashlib, importlib.util, json, random, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "games" / "face-the-figure"
spec = importlib.util.spec_from_file_location("ftf_build", GAME / "build_data.py")
ftf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ftf)


def fig(name, kind, value, year=2025, src="Wikidata"):
    return {"qid": "Q" + name, "subject": name, "kind": kind, "value": float(value), "year": year, "what": ftf.WHAT[kind],
            "headline": "", "src": {"name": src, "url": "https://example.org/" + name, "label": src}}


def pool():
    r = random.Random(7)
    figs = []
    for i in range(16):
        n = f"Co{i:02d}"
        figs.append(fig(n, "usd", r.uniform(1e8, 9e11)))
        if i % 2 == 0:
            figs.append(fig(n, "people", r.randint(200, 900000)))
        if i % 3 != 1:
            figs.append(fig(n, "founded", r.randint(1850, 2022), year=2000))
    figs.append(fig("Tie1", "usd", 5e9)); figs.append(fig("Tie2", "usd", 5.1e9))      # inside 5 percent of each other
    return figs


def deal(seed="2026-11-27"):
    figs = pool()
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
    return ftf.chain(figs, ftf.build_pairs(figs), rng, tries=1500)


class Chain(unittest.TestCase):
    def test_the_revealed_figure_carries_into_the_next_round(self):
        links = deal()
        self.assertEqual(len(links), ftf.ROUNDS)
        self.assertEqual(links[0][2], "start")
        for (a0, b0, _), (a1, b1, link) in zip(links, links[1:]):
            self.assertEqual(a1["subject"], b0["subject"], "pan A holds the company just weighed")
            if link == "same":
                self.assertIs(a1, b0, "same column: the very figure that was revealed")
            else:
                self.assertEqual(link, "turn"); self.assertNotEqual(a1["kind"], b0["kind"])

    def test_no_company_twice_and_no_tie(self):
        for seed in ("2026-11-27", "2026-11-28", "2026-12-24", "2027-01-01"):
            links = deal(seed)
            names = [links[0][0]["subject"]] + [b["subject"] for _, b, _ in links]
            self.assertEqual(len(names), len(set(names)), names)
            for a, b, _ in links:
                self.assertEqual(a["kind"], b["kind"])
                d, ok = ftf.gap(a, b)
                self.assertTrue(ok, (a["subject"], b["subject"]))
                self.assertNotEqual(a["value"], b["value"])

    def test_same_day_same_chain(self):
        one, two = deal("2026-12-01"), deal("2026-12-01")
        self.assertEqual([(a["subject"], b["subject"], l) for a, b, l in one], [(a["subject"], b["subject"], l) for a, b, l in two])
        self.assertNotEqual([b["subject"] for _, b, _ in one], [b["subject"] for _, b, _ in deal("2026-12-02")])

    def test_not_one_answer_all_the_way(self):
        links = deal()
        ans = ["h" if b["value"] > a["value"] else "l" for a, b, _ in links]
        run = max(len(s) for s in "".join(ans).replace("hl", "h l").replace("lh", "l h").split())
        self.assertLessEqual(run, ftf.MAX_SAME_ANSWER)
        self.assertIn("h", ans); self.assertIn("l", ans)

    def test_a_story_figure_never_meets_a_reported_one(self):
        figs = [fig("A", "people", 100000), fig("B", "people", 2000), {**fig("Cuts", "people", 10000, src="Boardread"), "qid": "", "headline": "x cuts 10,000 jobs"}]
        for p in ftf.build_pairs(figs):
            self.assertEqual(p["a"]["src"]["name"], p["b"]["src"]["name"])

    def test_todays_file_is_a_chain_or_says_it_is_not(self):
        d = json.loads((GAME / "assets/data/today.json").read_text())
        self.assertIn("pool", d); self.assertIn("sig", d)
        for prev, r in zip(d["rounds"], d["rounds"][1:]):
            if r["link"] != "start":
                self.assertEqual(r["a"]["subject"], prev["b"]["subject"])


if __name__ == "__main__":
    unittest.main()
