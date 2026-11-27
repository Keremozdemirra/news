"""Face the Figure deals one chain a day: the figure just revealed is A of the next round."""
import hashlib, importlib.util, json, random, shutil, subprocess, sys, unittest
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


class Selection(unittest.TestCase):
    """The rounds published on 27 Nov 2026 that these rules exist to stop."""

    def test_the_gimme_pairs_of_27_november_are_not_dealt(self):
        figs = pool() + [fig("Altria", "usd", 24018000000), fig("Hugging Face", "usd", 15000000),      # 1,601x apart
                         fig("Hugging Face", "people", 250), fig("Microsoft", "people", 228000)]       # 912x apart
        pairs = ftf.build_pairs(figs)
        wide = [p for p in pairs if {p["a"]["subject"], p["b"]["subject"]} in ({"Altria", "Hugging Face"}, {"Hugging Face", "Microsoft"})]
        self.assertEqual(len(wide), 2)
        self.assertTrue(all(p["ratio"] > 900 for p in wide))
        for seed in ("2026-11-27", "2026-11-28", "2026-12-24"):
            for cap in (ftf.MAX_RATIO, ftf.RELAXED_RATIO):
                rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
                for a, b, _ in ftf.chain(figs, pairs, rng, tries=800, max_ratio=cap):
                    if a["kind"] != "founded":
                        self.assertLessEqual(max(a["value"], b["value"]) / min(a["value"], b["value"]), cap, (a["subject"], b["subject"]))
                rng = random.Random(1)
                for p in ftf.choose(pairs, rng, cap) or []:
                    self.assertLessEqual(p["ratio"], cap)

    def test_at_most_two_founding_year_rounds(self):
        # 27 Nov had six; a pool that is mostly founding years must still not deal more than two
        figs = [fig(f"Old{i:02d}", "founded", 1850 + 7 * i, year=2000) for i in range(20)] + pool()
        pairs = ftf.build_pairs(figs)
        for seed in ("2026-11-27", "2026-11-28", "2026-12-24", "2027-01-01"):
            rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
            links = ftf.chain(figs, pairs, rng, tries=800)
            self.assertLessEqual(sum(1 for a, _, _ in links if a["kind"] == "founded"), ftf.MAX_FOUNDED)
            picked = ftf.choose(pairs, random.Random(seed))
            self.assertLessEqual(sum(1 for p in picked if p["kind"] == "founded"), ftf.MAX_FOUNDED)

    def test_a_company_nobody_can_place_is_left_out(self):
        listed, named = ftf.topfloor_names(), {ftf.squash("Hugging Face")}
        # Network For Teaching Entrepreneurship: 4 Wikipedia editions on 27 Nov 2026, on no list, in no story's company field
        self.assertFalse(ftf.known_subject("Network For Teaching Entrepreneurship", 4, listed, named))
        self.assertTrue(ftf.known_subject("Microsoft", 178, listed, named), "widely covered")
        self.assertTrue(ftf.known_subject("Hugging Face", 10, listed, named), "the company of a recent Boardread story")
        self.assertTrue(ftf.known_subject("Lufthansa", 0, listed, named), "on a Topfloor list")

    def test_story_companies_are_the_last_thirty_days_only(self):
        today = ftf.dt.date(2026, 11, 27)
        posts = [{"company": "Acme Corp", "created": "2026-11-20T08:00:00Z"}, {"company": "Old Co", "created": "2026-09-01T08:00:00Z"},
                 {"logo_names": ["Globex"], "created": "2026-10-28"}]
        self.assertEqual(ftf.story_companies(posts, today), {"acmecorp", "globex"})

    def test_a_thin_day_is_dealt_once_more_at_fifteen_times(self):
        # two clusters about 10x apart: three links at the strict cap, a full chain at the relaxed one
        figs = ([fig(f"Small{i}", "usd", v) for i, v in enumerate((1.0e6, 1.1e6, 1.2e6, 1.35e6))]
                + [fig(f"Large{i}", "usd", v) for i, v in enumerate((1.2e7, 1.3e7, 1.4e7, 1.5e7))])
        pairs = ftf.build_pairs(figs)
        self.assertIsNone(ftf.chain(figs, pairs, random.Random(3), tries=300))
        links = ftf.chain(figs, pairs, random.Random(3), tries=300, max_ratio=ftf.RELAXED_RATIO)
        self.assertGreaterEqual(len(links), ftf.CHAIN_MIN)

    def test_the_committed_puzzle_keeps_the_rules(self):
        d = json.loads((GAME / "assets" / "data" / "today.json").read_text())
        self.assertLessEqual(sum(1 for r in d["rounds"] if r["kind"] == "founded"), ftf.MAX_FOUNDED)
        for r in d["rounds"]:
            if r["kind"] != "founded":
                self.assertLessEqual(max(r["a"]["value"], r["b"]["value"]) / min(r["a"]["value"], r["b"]["value"]), d["rules"]["ratio"])


if __name__ == "__main__":
    unittest.main()


class Years(unittest.TestCase):
    """27 Nov: Macy's (1858) against NPR (1970) was dealt. A century apart is no more a question than 2,850 times."""
    def test_founding_years_far_apart_are_not_paired(self):
        figs = [fig("Old", "founded", 1858, year=2000), fig("Mid", "founded", 1915, year=2000), fig("New", "founded", 1970, year=2000), fig("Twin", "founded", 1971, year=2000)]
        got = {frozenset((p["a"]["subject"], p["b"]["subject"])) for p in ftf.build_pairs(figs)}
        self.assertNotIn(frozenset(("Old", "New")), got)
        self.assertNotIn(frozenset(("New", "Twin")), got)        # one year apart: a coin toss
        self.assertIn(frozenset(("Mid", "New")), got)
        self.assertIn(frozenset(("Old", "Mid")), got)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Ranks(unittest.TestCase):
    """Reported 27 Nov: the ladder was cut for ten links, the day had eight, and a perfect run read Chief cashier."""
    def ladder(self, n):
        js = "import { rankOf } from '%s/js/rank.js'; console.log(JSON.stringify([...Array(%d + 1).keys()].map((c) => rankOf(c, %d))));" % (GAME, n, n)
        r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        return json.loads(r.stdout)

    def test_a_perfect_run_is_the_top_rank_whatever_the_chain_length(self):
        order = ["Apprentice", "Junior clerk", "Senior clerk", "Chief cashier", "Auditor", "Comptroller"]
        for n in (6, 7, 8, 9, 10):
            got = self.ladder(n)
            self.assertEqual(got[n], "Comptroller", n)
            self.assertEqual(got[n - 1], "Auditor", n)
            self.assertEqual(got[0], "Apprentice", n)
            self.assertEqual(sorted(set(got), key=order.index), order, f"{n} links: a rank cannot be earned")
            self.assertEqual([order.index(r) for r in got], sorted(order.index(r) for r in got), n)

    def test_todays_chain_reaches_every_rank(self):
        n = len(json.loads((GAME / "assets" / "data" / "today.json").read_text())["rounds"])
        self.assertEqual(self.ladder(n)[n], "Comptroller")
        self.assertEqual(self.ladder(8), ["Apprentice", "Apprentice", "Apprentice", "Junior clerk", "Senior clerk", "Senior clerk", "Chief cashier", "Auditor", "Comptroller"])

    def test_the_page_uses_the_chain_length(self):
        src = (GAME / "js" / "ftf.js").read_text()
        self.assertIn("rankOf(correct, rounds.length)", src)
        self.assertIn('from "./rank.js"', src)
