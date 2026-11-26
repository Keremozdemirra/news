import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import desk, entities, platforms, site
from test_desk import Tmp
from test_platforms import post as platform_post

NASDAQ, NYSE, LSE, HKEX = "Q82059", "Q13677", "Q171240", "Q496672"


def listing(exchange, symbol, rank="normal", refs=True, **qualifiers):
    q = {"P249": [{"datavalue": {"value": symbol}}]} if symbol else {}
    q.update(qualifiers)
    return {"mainsnak": {"datavalue": {"value": {"id": exchange}}}, "rank": rank, "qualifiers": q,
            "references": [{"snaks": {}}] if refs else []}


def wikidata(label, *listings, delisted=False):
    """A fake Wikidata (one search hit, one entity) and a fake Nasdaq Trader directory that lists the
    company's US symbols under its label, unless `delisted`."""
    def get(url, raw=False):
        if "nasdaqtrader" in url:
            ex = "nasdaqlisted" if "nasdaqlisted" in url else "otherlisted"
            rows = [] if delisted else [f"{sym}|{label} - Common Stock|{'N' if ex == 'otherlisted' else 'Q'}|{sym}"
                                        for l in listings for sym in [l["qualifiers"].get("P249", [{}])[0].get("datavalue", {}).get("value")]
                                        if sym and l["mainsnak"]["datavalue"]["value"]["id"] == (NYSE if ex == "otherlisted" else NASDAQ)]
            return ("Symbol|Security Name|x|y\n" + "\n".join(rows) + "\nFile Creation Time: 1126202600:00|||\n").encode()
        if "wbsearchentities" in url:
            return {"search": [{"id": "Q1"}]}
        return {"entities": {"Q1": {"labels": {"en": {"value": label}}, "claims": {"P414": list(listings)}}}}
    return get


class Ticker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.object(entities, "CACHE", Path(self.tmp.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def lookup(self, name, label, *listings, **kw):
        for f in Path(self.tmp.name).glob("listing-*"):  # each lookup gets the day's directory afresh
            f.unlink()
        with mock.patch.object(entities, "_get", wikidata(label, *listings, **kw)):
            return entities.ticker(name)

    def test_single_listing(self):
        self.assertEqual(self.lookup("Nvidia", "Nvidia", listing(NASDAQ, "NVDA")), {"exchange": "NASDAQ", "symbol": "NVDA"})

    def test_legal_form_in_the_label_is_the_same_company(self):
        self.assertEqual(self.lookup("Apple", "Apple Inc.", listing(NASDAQ, "AAPL"))["symbol"], "AAPL")

    def test_two_listings_with_a_preferred_one_takes_it(self):
        t = self.lookup("Shell", "Shell", listing(LSE, "SHEL", "preferred"), listing(NYSE, "SHEL"))
        self.assertEqual(t, {"exchange": "LSE", "symbol": "SHEL"})

    def test_two_listings_without_a_preferred_one_is_nothing(self):
        self.assertIsNone(self.lookup("Alibaba", "Alibaba Group", listing(NYSE, "BABA"), listing(HKEX, "9988")))

    def test_two_preferred_listings_is_nothing(self):
        self.assertIsNone(self.lookup("X", "X", listing(NYSE, "X", "preferred"), listing(NASDAQ, "X", "preferred")))

    def test_ended_and_deprecated_listings_do_not_count(self):
        ended = {"P582": [{"datavalue": {"value": {"time": "+2020-01-01"}}}]}
        t = self.lookup("Siemens", "Siemens", listing("Q151139", "SIE"), listing(NYSE, "SI", **ended), listing(LSE, "SIE", "deprecated"))
        self.assertEqual(t, {"exchange": "Xetra", "symbol": "SIE"})

    def test_frankfurt_and_xetra_with_one_symbol_are_one_listing(self):
        self.assertEqual(self.lookup("Tesla", "Tesla", listing("Q151139", "TL0"), listing("Q819468", "TL0"))["exchange"], "Xetra")

    def test_us_listing_the_exchange_no_longer_has_is_nothing(self):
        # Wikidata still gave Denny's NASDAQ: DENN after the January 2026 delisting
        self.assertIsNone(self.lookup("Denny's", "Denny's", listing(NASDAQ, "DENN"), delisted=True))

    def test_us_listing_needs_no_wikidata_reference_when_the_exchange_lists_it(self):
        self.assertEqual(self.lookup("Anthropic", "Anthropic", listing(NASDAQ, "ANT", refs=False))["symbol"], "ANT")

    def test_foreign_listing_without_a_reference_is_ignored(self):
        self.assertIsNone(self.lookup("Foreign", "Foreign", listing(HKEX, "9999", refs=False)))
        self.assertEqual(self.lookup("Tencent", "Tencent", listing(HKEX, "0700"))["exchange"], "HKEX")

    def test_a_cached_us_ticker_is_dropped_when_the_exchange_delists_it(self):
        self.lookup("Denny's", "Denny's", listing(NASDAQ, "DENN"))
        listed = wikidata("Denny's", listing(NASDAQ, "DENN"), delisted=True)
        with mock.patch.object(entities, "_get", listed):
            for f in Path(self.tmp.name).glob("listing-*"):
                f.unlink()
            self.assertIsNone(entities.ticker("Denny's"))

    def test_directory_outage_gives_nothing_and_is_not_cached(self):
        def down(url, raw=False):
            if "nasdaqtrader" in url:
                raise OSError("down")
            return wikidata("Nvidia", listing(NASDAQ, "NVDA"))(url, raw)
        with mock.patch.object(entities, "_get", down):
            self.assertIsNone(entities.ticker("Nvidia"))
        self.assertEqual(self.lookup("Nvidia", "Nvidia", listing(NASDAQ, "NVDA"))["symbol"], "NVDA")

    def test_listing_that_has_not_started_is_ignored(self):
        later = {"P580": [{"datavalue": {"value": {"time": "+2999-01-01T00:00:00Z"}}}]}
        earlier = {"P580": [{"datavalue": {"value": {"time": "+1999-01-00T00:00:00Z"}}}]}
        self.assertIsNone(self.lookup("Futureco", "Futureco", listing(NASDAQ, "FUT", **later)))
        self.assertEqual(self.lookup("Pastco", "Pastco", listing(NASDAQ, "PST", **earlier))["symbol"], "PST")

    def test_exchange_outside_the_major_set_is_ignored(self):
        self.assertIsNone(self.lookup("Nagoya Co", "Nagoya Co", listing("Q1188840", "7203")))

    def test_listing_without_a_symbol_is_nothing(self):
        self.assertIsNone(self.lookup("Nvidia", "Nvidia", listing(NASDAQ, None)))

    def test_private_company_is_nothing(self):
        self.assertIsNone(self.lookup("OpenAI", "OpenAI"))

    def test_label_mismatch_is_nothing(self):
        self.assertIsNone(self.lookup("Apple", "Apple Music", listing(NASDAQ, "AAPL")))
        self.assertIsNone(self.lookup("S&P", "S&P 500", listing(NYSE, "SPX")))
        self.assertIsNone(self.lookup("Meta", "Metallica Inc", listing(NASDAQ, "METL")))

    def test_answers_are_cached_and_a_miss_is_remembered(self):
        with mock.patch.object(entities, "_get", wikidata("Nvidia", listing(NASDAQ, "NVDA"))):
            entities.ticker("Nvidia")
        with mock.patch.object(entities, "_get", side_effect=AssertionError("no second lookup")):
            self.assertEqual(entities.ticker("Nvidia")["symbol"], "NVDA")
        self.assertIsNone(self.lookup("OpenAI", "OpenAI"))
        with mock.patch.object(entities, "_get", side_effect=AssertionError("no second lookup")):
            self.assertIsNone(entities.ticker("OpenAI"))

    def test_an_outage_is_not_cached_as_a_miss(self):
        with mock.patch.object(entities, "_get", side_effect=OSError("down")):
            self.assertIsNone(entities.ticker("Nvidia"))
        self.assertEqual(self.lookup("Nvidia", "Nvidia", listing(NASDAQ, "NVDA"))["symbol"], "NVDA")

    def test_google_link_maps_the_exchange_and_refuses_the_unknown(self):
        self.assertEqual(entities.google_finance_url({"exchange": "NASDAQ", "symbol": "NVDA"}), "https://www.google.com/finance/quote/NVDA:NASDAQ")
        self.assertEqual(entities.google_finance_url({"exchange": "LSE", "symbol": "SHEL"}), "https://www.google.com/finance/quote/SHEL:LON")
        self.assertEqual(entities.google_finance_url({"exchange": "Mars Exchange", "symbol": "NVDA"}), "")


class Caption(unittest.TestCase):
    TK = {"exchange": "NASDAQ", "symbol": "NVDA"}

    def test_keyword_line_names_the_ticker_even_when_the_headline_names_the_company(self):
        s = {"topic": "Tech", "company": "Nvidia", "_assets": {"ticker": self.TK}}
        self.assertEqual(desk.keyword_line("Nvidia halts chip shipments", "lead", s), "Nvidia (NASDAQ: NVDA) · Tech")

    def test_no_cashtag_and_no_price(self):
        s = {"topic": "Tech", "company": "Nvidia", "_assets": {"ticker": self.TK}}
        self.assertNotIn("$", desk.keyword_line("Nvidia halts chip shipments", "lead", s))

    def test_without_a_ticker_nothing_changes(self):
        s = {"topic": "Tech", "company": "Nvidia"}
        self.assertEqual(desk.keyword_line("Nvidia halts chip shipments", "lead", s), "")

    def test_line_stays_inside_125_and_falls_back_to_the_bare_name(self):
        s = {"topic": "Tech", "company": "Nvidia", "_assets": {"ticker": self.TK}}
        head = "H" * 100 + " Chip"
        line = desk.keyword_line(head, "lead", s)
        self.assertLessEqual(len(head) + 2 + len(line), desk.KEY_WINDOW)
        self.assertNotIn("(", line)


class PlatformTexts(unittest.TestCase):
    P = dict(company="Nvidia", ticker={"exchange": "NASDAQ", "symbol": "NVDA"})

    def test_ticker_follows_the_first_mention(self):
        t = platforms.bluesky_text(platform_post(**self.P))
        self.assertTrue(t.startswith("Denny's reshares Nvidia (NASDAQ: NVDA) origin story"))
        self.assertEqual(t.count("NVDA"), 1)

    def test_skipped_when_it_would_pass_the_limit(self):
        p = platform_post(**self.P, headlines=["Nvidia " + "x" * 293], dek="")
        t = platforms.bluesky_text(p)
        self.assertNotIn("NVDA", t)
        self.assertLessEqual(len(t), 300)

    def test_no_ticker_no_change(self):
        self.assertNotIn("(", platforms.threads_text(platform_post(company="Nvidia"))[:60])

    def test_a_partial_name_never_gets_the_ticker(self):
        p = platform_post(company="Norse Atlantic", ticker={"exchange": "OSE", "symbol": "NORSE"}, headlines=["Norse suspends flights"])
        self.assertNotIn("NORSE", platforms.telegram_caption(p))

    def test_every_platform_stays_in_its_limit(self):
        p = platform_post(**self.P)
        self.assertLessEqual(len(platforms.telegram_caption(p)), 1024)
        self.assertLessEqual(len(platforms.facebook_text(p)), 2000)
        self.assertLessEqual(len(platforms.threads_text(p).encode()), 500)
        self.assertIn("(NASDAQ: NVDA)", platforms.facebook_text(p))


class Audit(unittest.TestCase):
    def test_ticker_needs_its_company_in_the_headline(self):
        base = dict(headlines=["Nvidia halts chip shipments"], topic="Tech", company="Nvidia", caption="c")
        tk = {"exchange": "NASDAQ", "symbol": "NVDA"}
        self.assertEqual([p for p in desk.audit({**base, "ticker": tk}) if "ticker" in p], [])
        bad = desk.audit({**base, "headlines": ["Chip shipments halted"], "ticker": tk})
        self.assertTrue(any("ticker NVDA" in p for p in bad))
        self.assertTrue(any("ticker" in p for p in desk.audit({**base, "company": "", "ticker": tk})))


class SitePages(Tmp):
    def setUp(self):
        super().setUp()
        for i, tk in enumerate(({"exchange": "NASDAQ", "symbol": "NVDA"}, {"exchange": "NASDAQ", "symbol": "NVDA"},
                                {"exchange": "Mars", "symbol": "ZZZ"})):
            pid = f"2026-11-26-0{i}00-1"
            company = "Nvidia" if i < 2 else "Marsco"
            d = dict(status="published", published=(desk.now() - timedelta(hours=i + 1)).isoformat(), headlines=[f"{company} story {i}"], dek="Dek.",
                     body="First.", sources=["CNBC", "Financial Times"], source_urls=["https://www.cnbc.com/a", "https://www.ft.com/b"],
                     topic="Tech", score=5, company=company, logo_names=[company], ticker=tk)
            self.write_post(pid, **d)
            (desk.MEDIA / pid).mkdir(parents=True, exist_ok=True)
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub):
            self.out = site.build(self.root / "_site")

    def test_story_links_the_ticker_to_google_finance(self):
        h = (self.out / "s/2026-11-26-0000-1/index.html").read_text()
        self.assertIn('<a class="tk" href="https://www.google.com/finance/quote/NVDA:NASDAQ" rel="nofollow noopener">NASDAQ: NVDA</a>', h)
        self.assertNotIn('target="_blank" rel="nofollow noopener">NASDAQ', h)

    def test_unknown_exchange_shows_the_ticker_without_a_link(self):
        h = (self.out / "s/2026-11-26-0200-1/index.html").read_text()
        self.assertIn('<span class="tk">Mars: ZZZ</span>', h)
        self.assertNotIn("finance/quote/ZZZ", h)

    def test_company_page_shows_it_too(self):
        self.assertIn("finance/quote/NVDA:NASDAQ", (self.out / "c/nvidia/index.html").read_text())


if __name__ == "__main__":
    unittest.main()
