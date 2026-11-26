"""One test per editorial failure class found in the 2026-11-26 audit of a full rendered batch.

Each test names the post that showed the failure, so a regression points at the real-world case it reopens.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from aidaily import copy, desk, entities as E, rank, templates as T

NOW = datetime(2026, 11, 26, 18, tzinfo=timezone.utc)


def item(title, src, hours=1, summary=""):
    return {"title": title, "source_id": src, "url": f"https://x/{abs(hash((title, src)))}",
            "published": NOW - timedelta(hours=hours), "summary": summary}


SRC = {f"n{i}": {"name": f"Newsroom {i}", "category": "news"} for i in range(12)}
SRC.update({"bbcw": {"name": "BBC World", "category": "world"}, "bbcb": {"name": "BBC Business", "category": "business"},
            "bbct": {"name": "BBC Technology", "category": "news"}, "gn": {"name": "Google News AI Search", "category": "community"}})
# filler so the clusterer has a day's worth of titles to learn which words are common: unrelated, older titles
def _word(i, k):
    return "".join(chr(97 + (i * 7 + k * 13 + j * 5) % 26) + chr(97 + (i // 26 + j + k) % 26) for j in range(4))


FILLER = [item(" ".join(_word(i, k) for k in range(4)), f"n{i % 12}", 30) for i in range(60)]


class Clustering(unittest.TestCase):
    def test_common_names_do_not_chain_unrelated_pieces(self):
        # 2026-11-26: a Denny's PR item, two columns and an investigation shared "Jensen Huang Nvidia" and became
        # one 16-outlet cluster led by a personal-finance column
        huang = [item("'Your booth is waiting': Denny's welcomes Jensen Huang back as Nvidia CEO", "n0"),
                 item("Jensen Huang is back, and so is his plaque at Denny's", "n1"),
                 item("Jensen Huang broke Nvidia's code of conduct, staff may not forget it", "n2"),
                 item("The investigations facing Nvidia and Jensen Huang", "n3"),
                 item("Jensen Huang, Trump and the 11 days that rocked Nvidia", "n4")]
        others = [item(t, f"n{5 + i}") for i, t in enumerate([
            "How Jensen Huang's return as Nvidia's CEO is going over in China", "Vance assured Jensen Huang not under DOJ investigation",
            "Nvidia shares swing as Jensen Huang returns", "Jensen Huang's Nvidia return lifts chip stocks",
            "Nvidia board backs Jensen Huang", "Jensen Huang meets Nvidia staff after return",
            "Nvidia investors weigh Jensen Huang comeback", "Jensen Huang outlines Nvidia priorities"])]
        stories = rank.rank(huang + others + FILLER, SRC, now=NOW)
        dennys = next(s for s in stories if "Denny" in s["title"])
        self.assertEqual(len(dennys["newsrooms"]), 2)

    def test_one_newsroom_counts_once_in_breadth(self):
        # BBC World, Business and Technology carrying one wire is one newsroom, not three
        bbc = [item("Spain's De Cos chosen as next ECB president", s) for s in ("bbcw", "bbcb", "bbct")]
        two = [item("Spain's De Cos chosen as next ECB president", s) for s in ("n0", "n1")]
        a = rank.rank(bbc + FILLER, SRC, now=NOW)[0]
        b = rank.rank(two + FILLER, SRC, now=NOW)[0]
        self.assertEqual(a["newsrooms"], ["BBC"])
        self.assertLess(a["score"], b["score"])

    def test_search_feeds_are_not_newsrooms(self):
        items = [item("FCC clears SpaceX satellites", "n0"), item("FCC clears SpaceX satellites - Oncodaily", "gn")]
        self.assertEqual(rank.rank(items + FILLER, SRC, now=NOW)[0]["newsrooms"], ["Newsroom 0"])

    def test_columns_rank_below_news_and_never_lead(self):
        col = [item("I hate that Jensen Huang is back at Nvidia. Am I a hypocrite?", "n0")]
        news = [item("SAP explores at least 10,000 job cuts", "n1")]
        stories = rank.rank(col + news + FILLER, SRC, now=NOW)
        order = [s["title"] for s in stories if s["title"] in (col[0]["title"], news[0]["title"])]
        self.assertEqual(order[0], news[0]["title"])
        pair = [item("Opinion | Altria's deal for Imperial makes no sense", "n2", 0),
                item("Altria explores deal for Imperial Brands", "n3", 2)]
        lead = rank.rank(pair + FILLER, SRC, now=NOW)
        self.assertTrue(any(s["title"] == "Altria explores deal for Imperial Brands" for s in lead))
        self.assertFalse(any(s["title"].startswith("Opinion") and len(s["newsrooms"]) > 1 for s in lead))

    def test_hard_news_outranks_a_lab_launch_post(self):
        src = dict(SRC, lab={"name": "NVIDIA Blog", "category": "lab"})
        items = [item("Come for the games, stay for the community with GeForce Now", "lab"),
                 item("ECB raises interest rates to curb inflation", "n0")]
        top = rank.rank(items + FILLER, src, now=NOW)[0]
        self.assertIn("ECB", top["title"])


class Skips(unittest.TestCase):
    def test_every_form_of_a_death_is_skipped(self):
        for t in ("Iranian drone attack in Kuwait kills two Italians", "Diesel tanker capsizes near Ibiza, killing one",
                  "Cairo fuel tanker fire that killed 31", "Deadly fire near Cairo", "Nine injured after refinery blast"):
            self.assertTrue(desk.SKIP.search(t), t)
        for t in ("Trump kills tariff exemption for small parcels", "EU AI Act deadline slips", "SAP explores 10,000 job cuts"):
            self.assertFalse(desk.SKIP.search(t), t)

    def test_select_skips_commentary_formats(self):
        rows = [{"title": t, "url": f"https://x/{i}", "links": [], "score": 12, "outlets": ["FT"],
                 "published": desk.now().isoformat()} for i, t in enumerate(
            ["What will Trump's latest tariffs mean for the world?", "SpaceX gets FCC nod: What it means for data centres",
             "Health Care Roundup: Market Talk", "SAP explores at least 10,000 job cuts"])]
        with mock.patch.object(desk, "_recent_posts", return_value=[]):
            self.assertEqual([s["title"] for s in desk.select(rows)], ["SAP explores at least 10,000 job cuts"])


class Copy(unittest.TestCase):
    def test_word_figures_and_qualified_figures_are_dropped(self):
        # "a quarter" and "a million" were set at 300 px; "£400m" dropped the source's "more than"
        self.assertFalse(copy.figure_ok("a quarter", "Only a quarter of workers voted for it"))
        self.assertFalse(copy.figure_ok("£400m", "Road schemes cut to move more than £400m to defence"))
        self.assertFalse(copy.figure_ok("£400m", "UK shelves road schemes to move £400m+ to defence"))
        self.assertFalse(copy.figure_ok("7,000 tonnes", "Tanker with up to 7,000 tonnes capsizes"))
        self.assertTrue(copy.figure_ok("77,000", "UK net migration falls to 77,000"))

    def test_headline_figure_fallback_respects_the_qualifier(self):
        s = {"headline": "Government moves more than £400m to defence", "title": "x", "dek": "", "figure": "",
             "_assets": {"photo": "", "logo": "", "logos": [], "credit": "", "file": ""}}
        self.assertEqual(T.layout(s), "headline")

    def test_report_does_not_open_by_restating_the_headline(self):
        out = copy.drop_restated_lead("SAP is exploring at least 10,000 job cuts. The software group is the latest to "
                                      "restructure.\n\nSource: FT", "SAP explores at least 10,000 job cuts")
        self.assertTrue(out.startswith("The software group"))
        self.assertTrue(out.endswith("Source: FT"))
        # a sentence that leans on the restated one keeps it
        kept = copy.drop_restated_lead("Elon Musk pledged two SpaceX shares for every US child. One share would come "
                                       "from him personally.", "Musk pledges two SpaceX shares for every US child")
        self.assertTrue(kept.startswith("Elon Musk pledged"))
        # a single sentence stays: an empty report is worse than a repeated one
        self.assertEqual(copy.drop_restated_lead("SAP explores 10,000 job cuts.", "SAP explores 10,000 job cuts"),
                         "SAP explores 10,000 job cuts.")

    def test_a_commentary_sentence_is_cut_and_the_news_kept(self):
        # one padded sentence used to drop the whole story: SAP's 10,000 job cuts fell off the day
        s = {"title": "SAP explores at least 10,000 job cuts", "summary": "The software group is restructuring.",
             "source": "FT"}
        rows = [{"id": 0, "headline": "SAP explores at least 10,000 job cuts", "dek": "", "x_post": "",
                 "linkedin_post": "The software group is restructuring. For Europe, software policy has become industrial "
                                  "policy.\n\nSource: FT", "figure": ""}]
        self.assertEqual(copy.apply([s], rows), [])
        self.assertEqual(s["copy_status"], "ok")
        self.assertNotIn("industrial", s["linkedin_post"])
        self.assertIn("restructuring", s["linkedin_post"])

    def test_hype_is_cut_and_a_long_headline_falls_back_to_the_source(self):
        s = {"title": "Trump demands probe after GDP data revision", "summary": "A massive revision to GDP data lifted growth.", "source": "CNBC"}
        rows = [{"id": 0, "headline": "Trump demands a probe into the massive GDP revision after the third-quarter data came out",
                 "dek": "The massive revision lifted growth.", "x_post": "", "linkedin_post": "", "figure": ""}]
        self.assertEqual(copy.apply([s], rows), [])
        self.assertEqual(s["headline"], "Trump demands probe after GDP data revision")
        self.assertEqual(s["dek"], "The revision lifted growth.")

    def test_a_dek_that_restates_the_headline_is_dropped(self):
        s = {"title": "Argentina's Congress approves central bank overhaul", "summary": "", "source": "BA Times"}
        rows = [{"id": 0, "headline": "Argentina's Congress gives final approval to central bank overhaul",
                 "dek": "Congress approves the central bank overhaul in Argentina.", "x_post": "", "linkedin_post": "", "figure": ""}]
        copy.apply([s], rows)
        self.assertEqual(s["dek"], "")

    def test_person_not_named_in_our_text_is_not_pictured(self):
        s = {"title": "Argentina's Congress approves central bank overhaul backed by Milei", "summary": "", "source": "BA Times"}
        rows = [{"id": 0, "headline": "Argentina's Congress approves central bank overhaul", "dek": "", "x_post": "",
                 "linkedin_post": "The bill passed the Senate.", "figure": "", "person": "Javier Milei"}]
        copy.apply([s], rows)
        self.assertEqual(s["person"], "")

    def test_outlet_digits_are_not_a_claim(self):
        s = {"title": "Spain's De Cos chosen as next ECB president", "summary": "", "source": "France 24"}
        self.assertEqual(copy.verify(s, {"headline": "De Cos chosen as next ECB president", "dek": "",
                                         "linkedin_post": "De Cos was chosen.\n\nSource: France 24"}), [])

    def test_plus_after_a_number_is_rejected(self):
        s = {"title": "Road projects shelved to move more than £400m to defence", "summary": ""}
        self.assertIn("a '+' after a number: write 'more than'",
                      copy.verify(s, {"headline": "UK moves £400m+ to defence", "dek": ""}))

    def test_same_event_in_one_run_is_one_post_with_both_newsrooms(self):
        a = {"title": "Trump proposes new tariffs on trading partners", "summary": "", "source": "NPR",
             "newsrooms": ["NPR", "Axios"], "links": ["https://npr/x"]}
        b = {"title": "US announces new tariffs on host of countries", "summary": "", "source": "BBC",
             "newsrooms": ["BBC"], "links": ["https://bbc/y"]}
        rows = [{"id": 0, "headline": "Trump proposes new tariffs on trading partners", "dek": "", "linkedin_post": "",
                 "x_post": "", "figure": "", "same_event": ""},
                {"id": 1, "headline": "US announces new tariffs", "dek": "", "linkedin_post": "", "x_post": "",
                 "figure": "", "same_event": "0"}]
        copy.apply([a, b], rows)
        self.assertEqual(b["copy_status"], "duplicate")
        self.assertEqual(a["newsrooms"], ["NPR", "Axios", "BBC"])
        self.assertIn("https://bbc/y", a["links"])

    def test_repeat_of_a_recent_post_is_dropped(self):
        a = {"title": "Trump tariffs", "summary": "", "source": "NPR"}
        copy.apply([a], [{"id": 0, "headline": "Trump tariffs", "same_event": "R3"}])
        self.assertEqual(a["copy_status"], "repeat")

    def test_prompt_lists_recent_headlines_for_same_event(self):
        p = copy.request([{"title": "t", "source": "s"}], ["Nvidia halts chip shipments"])
        self.assertIn("R1: Nvidia halts chip shipments", p)
        self.assertIn("person_role", p)


class Photos(unittest.TestCase):
    def search(self, titles):
        return {"query": {"search": [{"title": "File:" + t} for t in titles]}}

    def test_company_photo_shows_its_premises_not_a_product(self):
        # an Nvidia graphics card from 2008 ran on a credit-rating post, power cables on another
        hits = ["Nvidia SLI GTX280.jpg", "2023 Adapter NVIDIA 12VHPWR (1).jpg", "NVIDIA Headquarters.jpg"]
        with mock.patch.object(E, "_get", return_value=self.search(hits)):
            self.assertEqual(E.candidates("Nvidia", company=True), ["NVIDIA Headquarters.jpg"])

    def test_airline_photo_may_be_its_own_aircraft(self):
        hits = ["Norse Atlantic Airways Boeing 787-9 (G-CKWS).jpg", "Norse Atlantic Airways crew party.jpg"]
        with mock.patch.object(E, "_get", return_value=self.search(hits)):
            self.assertEqual(E.candidates("Norse Atlantic Airways", company=True),
                             ["Norse Atlantic Airways Boeing 787-9 (G-CKWS).jpg"])

    def test_person_is_the_namesake_whose_role_matches(self):
        # the FBI's Andrew Bailey once ran on a Bank of England governor's post
        hits = {"search": [{"id": "Q1", "label": "Andrew Bailey", "description": "American lawyer, FBI deputy director"},
                           {"id": "Q2", "label": "Andrew Bailey", "description": "British economist, Governor of the Bank of England"}]}
        ent = {"entities": {"Q2": {"labels": {"en": {"value": "Andrew Bailey"}}, "claims": {"P18": ["x"]}}}}
        with mock.patch.object(E, "_get", side_effect=[hits, ent]):
            label, claims = E.person_entity("Andrew Bailey", "British economist, Bank of England governor")
        self.assertEqual(claims, {"P18": ["x"]})
        with mock.patch.object(E, "_get", return_value=hits):
            self.assertEqual(E.person_entity("Andrew Bailey", "Australian cricketer"), (None, {}))
        self.assertEqual(E.person_entity("Andrew Bailey", ""), (None, {}))  # no role, no guess

    def test_main_company_without_a_logo_shows_no_other_logo(self):
        s = {"headline": "Z.AI and Moonshot AI delay flagship models", "company": "Z.AI", "orgs": ["Moonshot AI"]}
        with mock.patch.object(E, "logo", side_effect=lambda n, *a, **k: None if n == "Z.AI" else Path("/tmp/m.svg")), \
             mock.patch.object(E, "fresh_photo", return_value=(None, "", "")), mock.patch.object(E, "ticker", return_value=None):
            self.assertEqual(T.assets(s)["logo_names"], [])


class Newsrooms(unittest.TestCase):
    def test_card_count_matches_the_list(self):
        # the card said "Reported by 8 newsrooms" over a slide listing four, one of them an aggregator
        s = {"source": "TechCrunch", "newsrooms": ["TechCrunch", "Techmeme", "Engadget", "FT", "The Decoder", "BBC", "CNBC"],
             "timeline": [["x", ""]] * 9}
        names = desk.outlets(s, s)
        self.assertNotIn("Techmeme", names)
        self.assertIn(f"Reported by {len(names)} newsrooms", T._sourceline(s))
        self.assertEqual(desk.reported_by(names), "TechCrunch; Engadget; Financial Times; The Decoder and 2 more")
        one = {"source": "CNBC Top News", "newsrooms": ["CNBC"]}
        self.assertEqual(T._sourceline(one), "Source: CNBC")


class Caption(unittest.TestCase):
    def test_keyword_line_names_companies_and_people_not_institutions(self):
        s = {"topic": "World", "person": "", "company": "", "orgs": ["EU"], "_assets": {"logo_names": []}}
        self.assertEqual(desk.keyword_line("Italy's PM rebukes Ukraine over ship attacks", "She spoke.", s), "")
        s = {"topic": "Business", "person": "", "company": "", "orgs": ["Imperial Brands"],
             "_assets": {"logo_names": ["Imperial Brands"]}}
        self.assertEqual(desk.keyword_line("Tobacco group explores a takeover", "A bid.", s), "Imperial Brands · Business")


class Typography(unittest.TestCase):
    def test_quotes_are_typographers_quotes(self):
        self.assertEqual(T.typo("Trump alleges 'fake' figures; users' vaults; it's \"loopholes.\""),
                         "Trump alleges ‘fake’ figures; users’ vaults; it’s “loopholes.”")


class Audit(unittest.TestCase):
    def post(self, **kw):
        p = {"headlines": ["Nvidia halts chip shipments to Southeast Asia"], "topic": "Tech", "company": "Nvidia",
             "logo_names": ["Nvidia"], "body": "The pause covers four countries.", "dek": "",
             "caption": "Nvidia halts chip shipments to Southeast Asia\n\n#tech #news",
             "photo_file": "NVIDIA Headquarters.jpg", "credit_file": "NVIDIA Headquarters.jpg", "credit": "Photo: X"}
        p.update(kw)
        return p

    def test_clean_post_passes(self):
        self.assertEqual(desk.audit(self.post()), [])

    def test_each_failure_class_holds_the_post(self):
        cases = {
            "credit belongs to": self.post(credit_file="Other.jpg"),
            "not its premises": self.post(photo_file="Nvidia SLI GTX280.jpg", credit_file="Nvidia SLI GTX280.jpg"),
            "does not name the company": self.post(photo_file="Graphics Processing Unit.JPG", credit_file="Graphics Processing Unit.JPG"),
            "skipped topic": self.post(body="The strike killed two workers."),
            "not a news format": self.post(headlines=["What will Nvidia's halt mean for Asia?"]),
            "em or en dash": self.post(body="The pause — four countries."),
            "calls the news a": self.post(caption="Nvidia halts chip shipments to Southeast Asia\n\nFollow for every story.\n\n#tech #news"),
            "dek repeats": self.post(dek="Nvidia halts chip shipments to Southeast Asia, it says."),
            "full stop": self.post(headlines=["Nvidia halts chip shipments."]),
            "SOURCE ask": self.post(source_cta=True),
        }
        for want, p in cases.items():
            self.assertTrue(any(want in x for x in desk.audit(p)), (want, desk.audit(p)))


class FinishKeepsAssets(unittest.TestCase):
    def test_final_digest_carries_the_cards_photo_and_credit(self):
        # finish saved "final" before the cards were rendered, so queue looked the photo up again and paired the
        # card with another photo's credit (two posts held for "photo without a credit line" on 2026-11-26)
        from aidaily import __main__ as M, render
        with tempfile.TemporaryDirectory() as d:
            day = Path(d) / "2026-11-26"
            day.mkdir()
            s = {"url": "https://x/1", "title": "Meloni rebukes Ukraine", "summary": "", "source": "FT"}
            (day / "digest.json").write_text(json.dumps({"slots": {"top": [s]}}))
            (day / "chosen.json").write_text(json.dumps([s]))
            (day / "copy.json").write_text(json.dumps([{"id": 0, "headline": "Meloni rebukes Ukraine", "dek": "",
                                                       "linkedin_post": "", "x_post": "", "figure": ""}]))

            def pack(slots, out):
                for st in slots["top"]:
                    st["_assets"] = {"photo": "file:///p.jpg", "credit": "Photo: A", "file": "Meloni.jpg"}
                return []

            class A:
                out, date = d, "2026-11-26"
            with mock.patch.object(render, "pack", side_effect=pack), mock.patch("aidaily.review.write", return_value="r"):
                M.finish(A())
            final = json.loads((day / "digest.json").read_text())["final"]["top"][0]
            self.assertEqual(final["_assets"]["file"], "Meloni.jpg")


if __name__ == "__main__":
    unittest.main()
