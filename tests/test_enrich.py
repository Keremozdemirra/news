"""Primary-source enrichment (desk.json growth.enrich): fixtures only, no network, no model.

The fixtures in tests/fixtures/enrich are real responses (Eurostat, ECB, BLS, FRED, ONS, the Commission's and the CMA's
feeds and pages) trimmed for size, except the SEC data files: data.sec.gov refuses a client with no declared contact, so
those follow its documented schema with synthetic values for a fictional registrant.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("DESK_SITE_OFFLINE", "1")
from aidaily import copy, desk, enrich, feeds, site
from test_desk import Tmp
from test_site_features import post

FX = Path(__file__).parent / "fixtures" / "enrich"
ROUTES = (("MRR_FR", "ecb_mrr.json"), ("KR.DFR", "ecb_dfr.json"), ("prc_hicp_manr", "eurostat_hicp_fr.json"), ("CUUR0000SA0", "bls_cpi.json"),
          ("DCOILBRENTEU", "fred_brent.csv"), ("DCOILWTICO", "fred_wti.csv"), ("d7g7", "ons_cpi.json"),
          ("company_tickers", "sec_tickers.json"), ("CIK0001999001/us-gaap/Revenues", "sec_concept_revenues.json"),
          ("CIK0001999001/us-gaap/NetIncomeLoss", "sec_concept_netincome.json"), ("submissions/CIK0001999001", "sec_submissions.json"),
          ("competition-and-markets-authority", "cma.atom"), ("cma-study-reveals", "cma_release.html"),
          ("presscorner/api/rss", "ec_rss.xml"), ("presscorner/api/documents", "ec_speech.json"), ("pressreleases.rss", "sec_pressreleases.rss"))
NOW = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)


def getter(calls=None):
    def get(url, ua=""):
        if calls is not None:
            calls.append((url, ua))
        for key, name in ROUTES:
            if key in url:
                return (FX / name).read_bytes()
        raise AssertionError(f"a test reached the network: {url}")
    return get


def ctx(reply="[]", contact="", now=NOW, calls=None):
    asked = []
    c = enrich.Ctx(get=getter(calls), ask=lambda prompt: asked.append(prompt) or reply, now=now, contact=contact)
    c.asked = asked
    return c


def story(title, summary="", **kw):
    d = {"title": title, "summary": summary, "source": "BBC", "score": 9.0, "published": "2026-11-26T09:00:00+00:00", "reports": []}
    d.update(kw)
    return d


class NoNetwork(unittest.TestCase):
    def setUp(self):
        for target in ("aidaily.enrich._fetch", "aidaily.feeds.http_get"):
            p = mock.patch(target, side_effect=AssertionError("a test reached the network"))
            p.start()
            self.addCleanup(p.stop)


class NumberGate(NoNetwork):
    def test_a_number_the_evidence_states_passes(self):
        self.assertEqual(enrich.number_problems("The rate was 3.88% in October 2026.", "FRED FEDFUNDS: 2026-09-01 3.75; 2026-10-01 3.88"), [])

    def test_a_scaled_number_passes_only_when_rounding_gives_it(self):
        ev = "SEC Revenues val 4210000000 end 2026-09-26"
        self.assertEqual(enrich.number_problems("Revenue was $4.21 billion.", ev), [])
        self.assertEqual(enrich.number_problems("Revenue was $4.3 billion.", ev), ["4.3"])
        self.assertEqual(enrich.number_problems("Revenue was $4.2 million.", ev), ["4.2"])

    def test_an_invented_number_is_returned(self):
        self.assertEqual(enrich.number_problems("The rate was 4.5%.", "rate 3.88"), ["4.5"])


class MacroSources(NoNetwork):
    def test_eurostat_inflation_for_a_country_story(self):
        s = story("France's inflation slows to 2.9% in November as energy prices fall")
        facts = enrich.macro(s, ctx(now=datetime(2026, 1, 20, tzinfo=timezone.utc)))
        self.assertEqual(len(facts), 1)
        f = facts[0]
        self.assertEqual((f["label"], f["kind"]), ("Eurostat", "stat"))
        self.assertIn("France at 0.7% for December 2025, against 0.8% in November 2025", f["text"])
        self.assertTrue(f["data_url"].startswith("https://ec.europa.eu/eurostat/api/") and "geo=FR" in f["data_url"])
        self.assertEqual(enrich.fact_problems(s, f), [])

    def test_a_stale_print_is_not_called_latest(self):
        c = ctx(now=NOW)  # the fixture's newest month is December 2025
        self.assertEqual(enrich.macro(story("France's inflation slows in November"), c), [])
        self.assertTrue(any("no fresh print" in n for n in c.notes))

    def test_ecb_key_rates(self):
        s = story("Spain's Pablo Hernandez de Cos set to lead European Central Bank")
        facts = enrich.macro(s, ctx())
        self.assertEqual([f["label"] for f in facts], ["European Central Bank"] * 2)
        self.assertIn("main refinancing rate has stood at 2.65% since Sep 16, 2026, up from 2.4% on Jun 17, 2026", facts[0]["text"])
        self.assertTrue(all(enrich.fact_problems(s, f) == [] for f in facts))

    def test_bls_consumer_prices_derive_the_change_from_two_printed_values(self):
        s = story("Inflation is squeezing Americans as grocery bills rise before Black Friday", "U.S. shoppers cut back.")
        month, year = enrich.macro(s, ctx())[:2]
        self.assertEqual(month["label"], "U.S. Bureau of Labor Statistics")
        self.assertIn("stood at 337.511 in October 2026, 0.2% above the September 2026 level of 336.940", month["text"])
        # BLS collected no CPI for October 2025: a year-on-year rate is never worked out across the gap, the newest month with a year-ago value stands
        self.assertRegex(year["text"], r"% above its level a year earlier in September 2026, at 336\.940 against \d+\.\d+")
        for f in (month, year):
            self.assertEqual(enrich.number_problems(f["text"], f["evidence"]), [])
            self.assertEqual(enrich.fact_problems(s, f), [])

    def test_fred_oil_prices_are_named_for_the_agency_behind_them(self):
        s = story("Oil Futures Settle Lower Ahead of OPEC+ Policy Meeting")
        facts = enrich.macro(s, ctx())
        self.assertEqual({f["label"] for f in facts}, {"U.S. Energy Information Administration via FRED"})
        self.assertIn("Brent crude spot price was $91.80 a barrel on Nov 24, 2026, against $91.20 a barrel on Nov 23, 2026", facts[0]["text"])

    def test_ons_inflation_for_a_british_story(self):
        facts = enrich.macro(story("UK inflation rises as Bank of England weighs its next rate move"), ctx())
        self.assertEqual(facts[0]["label"], "UK Office for National Statistics")
        self.assertIn("3.6% for October 2026, against 3.5% in September 2026", facts[0]["text"])

    def test_a_story_about_no_indicator_gets_nothing_and_asks_nothing(self):
        calls = []
        self.assertEqual(enrich.macro(story("Princess Kate's cancer documentary: 3 takeaways"), ctx(calls=calls)), [])
        self.assertEqual(calls, [])

    def test_one_dead_api_never_stops_the_others(self):
        c = ctx()
        real = c.get
        c.get = lambda url, ua="": (_ for _ in ()).throw(OSError("down")) if "DCOILBRENTEU" in url else real(url, ua)
        facts = enrich.macro(story("Oil settles as OPEC+ meets"), c)
        self.assertEqual(len(facts), 1)
        self.assertTrue(any("OSError" in n for n in c.notes))


class SecFilings(NoNetwork):
    S = story("Acme Robotics swings to a quarterly loss as revenue climbs", "The robot maker reported results on Thursday.", published="2026-10-30T21:00:00+00:00")

    def test_without_a_declared_contact_nothing_is_requested(self):
        calls = []
        c = ctx(calls=calls)
        self.assertEqual(enrich.sec_company(self.S, c), [])
        self.assertEqual(calls, [])
        self.assertTrue(any("no generic contact" in n for n in c.notes))

    def test_facts_from_xbrl_and_the_8k_with_the_declared_contact(self):
        calls = []
        facts = enrich.sec_company(self.S, ctx(contact="desk@example.test", calls=calls))
        self.assertTrue(all(ua == "Boardread news desk desk@example.test" for _, ua in calls))
        texts = [f["text"] for f in facts]
        self.assertIn("Acme Robotics reported revenue of $4.21 billion for the quarter ended Sep 26, 2026, in its 10-Q filed Oct 30, 2026, "
                      "against $3.87 billion a year earlier.", texts)
        self.assertTrue(any("net loss of $125.0 million" in t and "against $310.0 million a year earlier" in t for t in texts))
        self.assertTrue(any("8-K on Oct 30, 2026 under item 2.02: results of operations" in t for t in texts))
        for f in facts:
            self.assertEqual(f["label"], "U.S. Securities and Exchange Commission (EDGAR)")
            self.assertRegex(f["url"], r"^https://www\.sec\.gov/Archives/edgar/data/1999001/\d{18}/0001999001-26-0000\d\d-index\.htm$")
            self.assertEqual(enrich.fact_problems(self.S, f), [])

    def test_a_word_that_is_also_a_company_is_not_matched(self):
        tickers = json.loads((FX / "sec_tickers.json").read_text())
        self.assertIsNone(enrich.match_registrant(story("Retailers aim at holiday shoppers with a new target date"), tickers))
        self.assertEqual(enrich.match_registrant(story("Oakwood Holdings buys a rival"), tickers)["ticker"], "OAK")
        # a ticker in brackets is a certain match
        self.assertEqual(enrich.match_registrant(story("A robot maker reports", "Acme (NASDAQ: ACME) said"), tickers)["ticker"], "ACME")


class TextSources(NoNetwork):
    CMA = story("UK watchdog finds private dentistry market is not working well for patients",
                "The Competition and Markets Authority published interim findings of its market study on Thursday.", published="2026-11-26T12:00:00+00:00")
    REPLY = json.dumps([
        {"fact": "The CMA says roughly 60% of UK patients buy at least part of their dental treatment privately.",
         "quote": "around 60% of patients now paying privately for at least some dental care"},
        {"fact": "The interim findings cover a private dental market the regulator values at £8 billion.",
         "quote": "market study into the UK’s £8 billion private dentistry market"},
        {"fact": "The General Dental Council surveyed patients, and over a third of them said a lack of NHS options is why they pay privately.",
         "quote": "More than a third of patients surveyed by the General Dental Council say they pay for private dental services because of a lack of NHS options"}])

    def test_the_regulators_own_release_is_found_and_read(self):
        c = ctx(self.REPLY)
        facts = enrich.regulator(self.CMA, c)
        self.assertEqual(len(facts), 3)
        self.assertTrue(all(f["label"] == "UK Competition and Markets Authority" and f["kind"] == "release" for f in facts))
        self.assertTrue(all(f["url"] == "https://www.gov.uk/government/news/cma-study-reveals-catalogue-of-concerns-in-private-dentistry-market" for f in facts))
        self.assertIn("DOCUMENT (UK Competition and Markets Authority)", c.asked[0])
        kept, dropped = enrich.gate_facts(self.CMA, facts)
        self.assertEqual((len(kept), dropped), (3, []))

    def test_the_commissions_press_corner_is_read_through_its_document_api(self):
        doc, name = enrich.release_text(ctx(), "https://ec.europa.eu/commission/presscorner/detail/en/speech_26_2613")
        self.assertEqual(name, "European Commission")
        self.assertIn("Good morning, everyone", doc)

    def test_sec_pages_need_the_declared_contact(self):
        c = ctx()
        self.assertEqual(enrich.release_text(c, "https://www.sec.gov/newsroom/press-releases/2026-116-x"), ("", ""))
        self.assertTrue(any("no generic contact" in n for n in c.notes))

    def test_a_fact_without_a_matching_primary_text_is_dropped(self):
        bad = json.dumps([
            {"fact": "The CMA found that 45% of patients pay privately.", "quote": "around 45% of patients now paying privately"},         # quote is not in the document
            {"fact": "The CMA says 70% of patients pay privately.", "quote": "around 60% of patients now paying privately for at least some dental care"},  # number not in its quote
            {"fact": "The CMA has published interim findings into the private dentistry market for patients across the UK.",
             "quote": "The CMA has published interim findings into the private dentistry market"},                                      # six or more words copied
            {"fact": "The CMA study draws on statutory powers including financial information.", "quote": "information acquired through statutory powers including internal financial information"}])
        facts = enrich.regulator(self.CMA, ctx(bad))
        # the quote that is not in the document and the six-word copy never leave the extractor; the number the quote lacks stops at the gate
        self.assertEqual(len(facts), 2)
        kept, dropped = enrich.gate_facts(self.CMA, facts)
        self.assertEqual([f["text"] for f in kept], ["The CMA study draws on statutory powers including financial information."])
        self.assertEqual(dropped[0]["why"], ["numbers not in the primary text ['70']"])

    def test_a_release_the_story_does_not_match_is_not_used(self):
        other = story("Oil settles as OPEC+ meets", "The Competition and Markets Authority has nothing to do with it.")
        self.assertEqual(enrich.regulator(other, ctx(self.REPLY)), [])

    def test_a_company_release_is_followed_only_from_a_link_in_the_item(self):
        self.assertEqual(enrich.primary_links(["https://www.businesswire.com/news/home/2026/x", "https://investor.acme.test/news/q3",
                                               "https://www.nytimes.com/2026/11/26/business/x.html", "https://acme.test/blog/post",
                                               "https://www.sec.gov/Archives/edgar/data/1/2/x.htm"]),
                         ["https://www.businesswire.com/news/home/2026/x", "https://investor.acme.test/news/q3", "https://www.sec.gov/Archives/edgar/data/1/2/x.htm"])
        self.assertEqual(enrich.press_release(story("Acme reports"), ctx()), [])  # no link, no request

    def test_a_feed_item_keeps_the_links_of_its_html(self):
        rss = (b'<rss><channel><item><title>Acme reports</title><link>https://news.example/a</link><description>'
               b'&lt;p&gt;Read the &lt;a href="https://investor.acme.test/news/q3"&gt;release&lt;/a&gt;.&lt;/p&gt;</description></item></channel></rss>')
        item = feeds.parse_xml(rss, "x")[0]
        self.assertEqual(item["hrefs"], ["https://investor.acme.test/news/q3"])
        self.assertIn("Read the release", item["summary"])


class NoCopying(NoNetwork):
    RSS = story("Oil Futures Settle Lower Ahead of OPEC+ Policy Meeting",
                "Brent crude was $91.80 a barrel on Tuesday, down from $92.90 on Monday as traders waited for the producers' meeting later this week.")

    def test_a_fact_that_repeats_six_words_of_the_summary_is_dropped(self):
        f = enrich._fact("Brent crude was $91.80 a barrel on Tuesday, down from $92.90 on Monday, FRED shows.", "FRED", "https://fred.stlouisfed.org/series/X",
                         "FRED X: 2026-11-23 92.90; 2026-11-24 91.80", "stat")
        why = enrich.fact_problems(self.RSS, f)
        self.assertTrue(any(w.startswith("copies the newsroom") for w in why), why)

    def test_a_fact_that_only_restates_the_summary_is_dropped(self):
        f = enrich._fact("Brent crude was a barrel on Tuesday as traders waited for the producers' meeting this week.", "FRED", "https://fred.stlouisfed.org/series/X",
                         "FRED X: 2026-11-24 91.80", "stat")
        self.assertIn("says only what the newsroom said", enrich.fact_problems(self.RSS, f))

    def test_no_fact_built_from_a_fixture_shares_a_six_word_run_with_its_story(self):
        stories = [(story("France's inflation slows to 2.9% in November", "France's annual inflation rate slowed to 2.9% in November from 3.1% in October, as energy prices fell."),
                    datetime(2026, 1, 20, tzinfo=timezone.utc)),
                   (story("Oil settles as OPEC+ meets", "Oil fell for a second day before the producers' meeting."), NOW), (story("UK inflation rises to 3.6%", "UK consumer price inflation rose to 3.6% in October from 3.5% in September."), NOW)]
        n = 0
        for s, now in stories:
            for f in enrich.macro(s, ctx(now=now)):
                n += 1
                self.assertEqual(enrich.shared_run(f["text"], copy.source_text(s)), "", f["text"])
        self.assertGreaterEqual(n, 3)

    def test_a_writer_sentence_copied_from_the_summary_is_dropped(self):
        s = dict(self.RSS, headline="Oil falls", dek="", linkedin_post="", enrich={"facts": self.facts()})
        out = enrich.check_context(s, ["Brent crude was $91.80 a barrel on Tuesday, down from $92.90 on Monday as traders waited."])
        # the copied sentence is dropped; the facts' own sentences stand in
        self.assertEqual([r["text"] for r in out], [f["text"] for f in self.facts()])

    def facts(self):
        return [enrich._fact("The Brent crude spot price was $91.80 a barrel on Nov 24, 2026, against $91.20 a barrel on Nov 23, 2026.", "U.S. Energy Information Administration via FRED",
                             "https://fred.stlouisfed.org/series/DCOILBRENTEU", "FRED DCOILBRENTEU: 2026-11-23 91.20; 2026-11-24 91.80", "stat"),
                enrich._fact("The WTI crude spot price was $87.70 a barrel on Nov 24, 2026, against $87.10 a barrel on Nov 23, 2026.", "U.S. Energy Information Administration via FRED",
                             "https://fred.stlouisfed.org/series/DCOILWTICO", "FRED DCOILWTICO: 2026-11-23 87.10; 2026-11-24 87.70", "stat")]


class WriterSection(NoNetwork):
    def setUp(self):
        super().setUp()
        self.s = story("Oil Futures Settle Lower Ahead of OPEC+ Policy Meeting", "Oil fell before the producers' meeting.", headline="Oil settles lower before the OPEC+ meeting",
                       dek="Oil fell before the producers' meeting.", linkedin_post="Oil settled lower.\n\nSource: WSJ")
        self.s["enrich"] = {"facts": NoCopying.facts(self)}

    def test_the_writers_sentences_stand_when_they_use_only_the_facts(self):
        rows = ["Brent crude spot was $91.80 a barrel on Nov 24, 2026, up from $91.20 a barrel the day before.", "WTI crude spot closed at $87.70 a barrel, against $87.10 a barrel on Nov 23, 2026."]
        out = enrich.check_context(self.s, rows)
        self.assertEqual([r["text"] for r in out], rows)
        self.assertEqual(out[0]["url"], "https://fred.stlouisfed.org/series/DCOILBRENTEU")
        self.assertEqual(out[1]["url"], "https://fred.stlouisfed.org/series/DCOILWTICO")
        self.assertEqual(enrich.audit(out), [])

    def test_a_sentence_with_a_number_no_fact_holds_is_dropped_and_the_facts_stand_in(self):
        out = enrich.check_context(self.s, ["Brent crude fell to $85.00 a barrel on Nov 24, 2026.", "WTI spot closed at $87.70 a barrel on Nov 24, 2026."])
        self.assertEqual([r["text"] for r in out], [f["text"] for f in self.s["enrich"]["facts"]])

    def test_commentary_and_a_stock_phrase_are_dropped(self):
        rows = ["Brent crude spot at $91.80 a barrel signals that traders are nervous about the meeting.", "Oil prices amid the meeting stood at $91.80 a barrel on Nov 24, 2026."]
        out = enrich.check_context(self.s, rows)
        self.assertEqual([r["text"] for r in out], [f["text"] for f in self.s["enrich"]["facts"]])

    def test_one_fact_is_not_a_section(self):
        self.s["enrich"]["facts"] = self.s["enrich"]["facts"][:1]
        self.assertEqual(enrich.check_context(self.s, ["Brent crude spot was $91.80 a barrel on Nov 24, 2026, up from $91.20 a barrel the day before."]), [])

    def test_audit_catches_a_number_the_evidence_lacks_and_a_missing_link(self):
        rows = [{"text": "Brent was $99.00 a barrel.", "label": "EIA", "url": "https://x.test/a", "evidence": "FRED 91.80"},
                {"text": "WTI was $87.70.", "label": "", "url": "http://x.test", "evidence": "FRED 87.70"}]
        problems = enrich.audit(rows)
        self.assertEqual(len(problems), 2)
        self.assertIn("numbers not in the primary text", problems[0])

    def test_the_prompt_and_the_block_carry_the_facts_only_while_the_switch_is_on(self):
        self.s["url"] = "https://x.test/a"
        with mock.patch.object(copy, "switch", lambda n: n == "enrich"):
            blk = copy.block([self.s])
            self.assertIn("primary facts:\n- F1:", blk)
            self.assertIn("- context:", copy.prompt(blk))
            self.assertNotIn("- context:", copy.prompt("id: 0\ntitle: t"))   # no story with facts: the field is not asked for
        with mock.patch.object(copy, "switch", lambda n: False):
            self.assertNotIn("primary facts", copy.block([self.s]))
            self.assertNotIn("- context:", copy.prompt(copy.block([self.s])))

    def test_apply_keeps_the_context_beside_the_checked_copy(self):
        s = story("Oil settles lower ahead of OPEC+ meeting", "Oil fell on Tuesday before the producers meet this week.")
        s["enrich"] = {"facts": NoCopying.facts(self)}
        row = {"id": 0, "headline": "Oil settles lower before the OPEC+ meeting", "dek": "Oil fell on Tuesday before the producers meet this week.",
               "linkedin_post": "Traders waited for the meeting of the producers.\nThe session ended lower.\n\nSource: BBC", "x_post": "Oil settles lower",
               "context": ["Brent crude spot was $91.80 a barrel on Nov 24, 2026, up from $91.20 a barrel the day before.", "Brent crude spot was $70.00 a barrel."]}
        with mock.patch.object(copy, "switch", lambda n: n == "enrich"):
            copy.apply([s], [row])
        self.assertEqual(s["copy_status"], "ok")
        self.assertEqual([r["text"] for r in s["context"]], [f["text"] for f in s["enrich"]["facts"]])  # one valid sentence is not a section: the facts stand in
        with mock.patch.object(copy, "switch", lambda n: False):
            s2 = story("Oil settles lower ahead of OPEC+ meeting", "Oil fell on Tuesday before the producers meet this week.")
            s2["enrich"] = {"facts": NoCopying.facts(self)}
            copy.apply([s2], [row])
        self.assertEqual(s2["context"], [])


class Run(NoNetwork):
    def stories(self, n=5):
        return [story(f"Oil Futures Settle Lower Ahead of OPEC+ Policy Meeting {i}", score=10 - i, url=f"https://x.test/{i}") for i in range(n)]

    def test_at_most_a_few_stories_an_hour_and_the_top_ones_first(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(enrich, "STATE", Path(d) / "enrich.json"):
            ss = self.stories()
            done = enrich.run(ss, ctx(), limit=2)
            self.assertEqual([t[-1] for t, _ in done], ["0", "1"])
            self.assertEqual([bool(s.get("enrich")) for s in ss], [True, True, False, False, False])
            # the log counts the hour: a second run within it has nothing left
            self.assertEqual(enrich.run(ss, ctx(), limit=2), [])
            # an hour later the budget is back
            self.assertEqual(len(enrich.run(ss, ctx(now=NOW + timedelta(minutes=61)), limit=2)), 2)

    def test_a_story_with_fewer_than_two_solid_facts_stays_as_it_is(self):
        s = story("Oil settles as OPEC+ meets", score=9)
        c = ctx()
        real = c.get
        c.get = lambda url, ua="": (_ for _ in ()).throw(OSError("down")) if "WTI" in url or "WTICO" in url else real(url, ua)
        enrich.run([s], c, log=False)
        self.assertNotIn("enrich", s)

    def test_a_story_nothing_fits_costs_no_request_and_no_share_of_the_hour(self):
        calls = []
        done = enrich.run([story("Princess Kate documentary: 3 takeaways")], ctx(calls=calls), log=False)
        self.assertEqual((done, calls), ([], []))


class Site(Tmp):
    def setUp(self):
        super().setUp()
        clock = mock.patch.object(desk, "now", return_value=datetime(2026, 11, 26, 23, 0, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        on = mock.patch.dict(desk.CONFIG["growth"], {"enrich": True})
        on.start()
        self.addCleanup(on.stop)
        rows = [{"text": "Brent crude spot was $91.80 a barrel on Nov 24, 2026, up from $91.20 the day before.", "label": "U.S. Energy Information Administration via FRED",
                 "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU", "evidence": "FRED DCOILBRENTEU: 2026-11-23 91.20; 2026-11-24 91.80", "kind": "stat"}]
        post(self, "2026-11-26-0900-1", 1, headlines=["Oil settles lower"], context=rows)
        post(self, "2026-11-26-0800-1", 2, headlines=["Oil rises"])
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub):
            self.out = site.build(self.root / "_site")

    def test_the_article_shows_the_section_and_links_the_primary_source_by_its_agency(self):
        h = (self.out / "s/2026-11-26-0900-1/index.html").read_text()
        self.assertIn('<h2 id="bn">By the numbers</h2>', h)
        self.assertIn('<b>Primary sources:</b>', h)
        self.assertIn('<a href="https://fred.stlouisfed.org/series/DCOILBRENTEU" rel="noopener" target="_blank">U.S. Energy Information Administration via FRED</a>', h)
        self.assertIn("plus the primary sources listed under Primary sources", h)

    def test_an_article_without_context_is_unchanged(self):
        h = (self.out / "s/2026-11-26-0800-1/index.html").read_text()
        for gone in ("bynum", "Primary sources", "By the numbers"):
            self.assertNotIn(gone, h)


class Shipping(unittest.TestCase):
    def test_the_switch_ships_off_or_on_by_the_rollout_decision(self):
        cfg = json.loads((desk.HERE / "desk.json").read_text())["growth"]
        self.assertIn("enrich", cfg)
        self.assertIsInstance(cfg["enrich"], bool)

    def test_the_post_carries_no_context_while_the_switch_is_off(self):
        with mock.patch.dict(desk.CONFIG["growth"], {"enrich": False}):
            self.assertFalse(desk.growth("enrich"))


if __name__ == "__main__":
    unittest.main()
