"""Findings of the 2026-11-27 review of boardread.news: one importance order on every surface, one time format, honest labels."""
import json
import os
import re
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ.setdefault("DESK_SITE_OFFLINE", "1")
from aidaily import desk, markets, site, sitepages, views
from test_markets import data
from test_site_features import Features, post


def fake(pid, headline, topic="Economy", n=3, score=8, hours=0, **kw):
    t = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc) - timedelta(hours=hours)
    d = dict(id=pid, headlines=[headline], dek="", topic=topic, sources=[f"Room {i}" for i in range(n)], score=score, published=t.isoformat(), _thumb=False)
    d.update(kw)
    return d


class Ranking(unittest.TestCase):
    def test_a_section_block_shows_the_most_important_not_the_newest(self):
        big = fake("big", "Altria explores takeover bid for Imperial Brands", "Business", n=5, score=12, hours=6)
        small = [fake(f"s{i}", f"Small hire {i}", "Business", n=1, score=2, hours=i * 0.1) for i in range(5)]
        html = views.front([*small, big], {}, None)
        self.assertIn("Altria explores", html)

    def test_the_front_has_a_top_five_list_after_the_lead_with_ages_and_no_pictures(self):
        rows = [fake(f"r{i}", f"Story number {i} of the day", "Economy", n=3, score=9, hours=i * 0.3) for i in range(8)]
        html = views.front(rows, {}, None)
        block = re.search(r'<section class="top5".*?</section>', html, re.S).group(0)
        self.assertEqual(block.count("<li>"), 5)
        self.assertEqual(block.count("data-age"), 5)
        self.assertNotIn("<img", block)
        self.assertLess(html.index('class="lead"'), html.index('class="top5"'))
        self.assertIn(".front .lead .rates", (site.ASSETS / "views.css").read_text())

    def test_todays_puzzles_link_every_live_game_in_the_rail_and_under_the_top_stories(self):
        rows = [fake(f"r{i}", f"Story number {i} of the day", "Economy", n=3, score=9, hours=i * 0.3) for i in range(8)]
        from aidaily import play
        with mock.patch.object(site, "SHIPPED", {"play"}):
            html = views.front(rows, {}, None)
        self.assertEqual(html.count('class="puzzles inrail"'), 1)
        self.assertEqual(html.count('class="puzzles inlead"'), 1)
        for slug, title, _, _ in play.live():
            self.assertEqual(html.count(f'href="/play/{slug}/"'), 2)
        self.assertLess(html.index('class="top5"'), html.index('class="puzzles inlead"'))
        with mock.patch.object(site, "SHIPPED", set()):
            self.assertNotIn("puzzles", views.front(rows, {}, None))

    def test_section_rows_pads_a_quiet_section_with_older_articles(self):
        rows = [fake("a", "New one", "Tech", hours=1), fake("b", "Old one", "Tech", hours=40)]
        got = views.section_rows(rows, site.dt(rows[0]["published"]))
        self.assertEqual([p["id"] for p in got], ["a", "b"])

    def test_sport_block_is_ranked_too(self):
        big = fake("big", "Final goes to extra time", "Sport", n=5, hours=5)
        small = [fake(f"s{i}", f"Training update {i}", "Sport", n=1, score=1, hours=i * 0.1) for i in range(5)]
        html = views.sport_block(views.section_rows([*small, big], site.dt(small[0]["published"])), lambda p: False)
        self.assertIn("Final goes to extra time", html)

    def test_the_feed_and_the_front_page_lead_with_the_same_article(self):
        old_tariff = fake("t", "Trump signals tariffs on Asian trading partners", "Economy", n=4, score=12, hours=20)
        fresh = [fake(f"f{i}", f"France inflation slows to {i}%", "Economy", n=3, score=9, hours=i * 0.2) for i in range(1, 7)]
        rows = sorted([old_tariff, *fresh], key=lambda p: p["published"], reverse=True)
        lead = views.front_rank(site.window(rows))[0]
        first_card = re.search(r'<article class="fcard first[^"]*"><a href="[^"]*/s/([^/]+)/"', views.feed(rows)).group(1)
        self.assertEqual(first_card, lead["id"])

    def test_the_brief_ranks_like_the_front_page(self):
        rows = [fake(f"p{i}", f"Politics story {i}", "Politics", n=1, score=15, hours=i) for i in range(6)]
        rows.append(fake("fr", "France's inflation slows to 2.9%", "Economy", n=4, score=8, hours=0.5))
        got = sitepages.brief_rows(rows, "2026-11-27")
        self.assertEqual([p["id"] for p in got], [p["id"] for p in views.front_rank(rows)][:sitepages.BRIEF_N])

    def test_the_paper_picks_its_front_by_the_same_rank(self):
        rows = [fake(f"p{i}", f"Culture note {i}", "Culture", n=1, score=20, hours=i) for i in range(5)]
        rows.append(fake("fr", "Court halts the merger", "Politics", n=5, score=6, hours=2))
        front, _ = views.edition_split(rows)
        self.assertEqual(front[0]["id"], "fr")


class Times(unittest.TestCase):
    def test_a_time_carries_its_date_unless_it_is_today(self):
        self.assertEqual(site.stamp("2026-11-27T10:42:00+00:00", ref="2026-11-27"), "10:42 UTC")
        self.assertEqual(site.stamp("2026-11-26T15:16:00+00:00", ref="2026-11-27"), "26 Nov, 15:16 UTC")
        self.assertEqual(site.stamp("2026-11-26T15:16:00+00:00", utc=False, ref="2026-11-27"), "26 Nov, 15:16")


class Names(unittest.TestCase):
    def test_possessives_titles_and_common_nouns_do_not_make_names(self):
        rows = [fake("a", "Nvidia's chips sell out", dek="Officials say President Donald Trump's team met Nvidia.", n=2),
                fake("b", "Nvidia raises its forecast", dek="President Donald Trump's tariffs weigh on Nvidia.", n=2)]
        names = {n for n, _, _ in views.names(rows)}
        self.assertIn("Nvidia", names)
        self.assertNotIn("Nvidia's", names)
        self.assertNotIn("Officials", names)
        self.assertFalse([n for n in names if n.startswith("President") or n.endswith("'s")])
        self.assertIn("Donald Trump", names)


class Numbers(unittest.TestCase):
    def test_a_figure_comes_with_the_sentence_that_states_it(self):
        p = fake("m", "Amazon and Meta talk about lifting the block on Meta's Muse", dek="The talks reopen. Amazon's ad business generates $68.6 billion a year.", figure="$68.6 billion")
        self.assertEqual(views.figure_sentence("$68.6 billion", p), "Amazon's ad business generates $68.6 billion a year.")
        html = views.numbers_page([p], None)
        self.assertIn("generates $68.6 billion a year", html)
        self.assertIn("Muse", html)

    def test_a_figure_in_the_headline_needs_no_second_caption(self):
        p = fake("m", "42 state AGs sue", dek="Attorneys general file.", figure="42")
        self.assertEqual(views.figure_sentence("42", p), "")

    def test_numbers_page_puts_daily_crypto_above_the_monthly_metals(self):
        m = data(True)
        m["series"]["gold"] = [["2026-09-01", 4319.0], ["2026-10-01", 4105.0]]
        m["crypto"] = {"coins": [{"name": "Bitcoin", "sym": "BTC", "price": 90000.0, "pct": 1.0}], "at": "2026-11-27T12:00:00Z"}
        html = views.numbers_page([fake("x", "Story")], m)
        self.assertLess(html.index(">Crypto<"), html.index(">Metals<"))
        self.assertLess(html.index(">Markets<"), html.index(">Crypto<"))

    def test_metal_cards_say_against_which_month_and_weekly_cards_say_weekly(self):
        m = data(True)
        m["series"]["gold"] = [["2026-09-01", 4319.0], ["2026-10-01", 4105.0]]
        self.assertIn("vs Sep", markets.cards(m, ("gold",)))
        self.assertIn("weekly observations", markets.cards(m, ("gasoline",)))
        self.assertIn("daily observations", markets.cards(m, ("brent",)))


class Companies(unittest.TestCase):
    def test_a_headline_naming_a_tagged_company_joins_its_page(self):
        tagged = [fake("a", "Nvidia lifts its forecast", company="Nvidia"), fake("b", "Nvidia chips ship", company="Nvidia")]
        loose = fake("c", "Nvidia halts shipments to China")
        other = fake("d", "Shares rise on Tuesday")
        self.assertEqual(site.infer_companies([*tagged, loose, other]), 1)
        self.assertEqual(site.co_of(loose), "Nvidia")
        self.assertEqual(site.co_of(other), "")
        self.assertIn("nvidia", site.companies([*tagged, loose]))
        self.assertEqual(len(site.companies([*tagged, loose])["nvidia"][1]), 3)

    def test_a_plain_word_is_not_a_company(self):
        tagged = [fake("a", "Block cuts jobs", company="Block"), fake("b", "Block shares fall", company="Block")]
        loose = fake("c", "Road block ends")
        site.infer_companies([*tagged, loose])
        self.assertEqual(site.co_of(loose), "")


class Strip(unittest.TestCase):
    def setUp(self):
        self.m = data(True)
        self.m["crypto"] = {"coins": [{"name": "Bitcoin", "sym": "BTC", "price": 90000.0, "pct": 1.0}, {"name": "Ether", "sym": "ETH", "price": 3000.0, "pct": -1.0}], "at": "2026-11-27T12:00:00Z"}

    def test_a_price_older_than_yesterday_carries_its_date(self):
        from datetime import date
        html = markets.strip(self.m, "", today=date(2026, 11, 28))  # data ends 25-26 Nov
        self.assertIn('<small class="sd">25 Nov</small>', html)  # the 10-year, 25 Nov
        fresh = markets.strip(self.m, "", today=date(2026, 11, 26))
        self.assertNotIn('class="sd"', fresh)

    def test_items_link_to_their_series_and_the_coins_stay_after_the_third(self):
        html = markets.strip(self.m, "")
        self.assertIn('href="/numbers/#brent"', html)
        self.assertIn('href="/numbers/#crypto"', html)
        order = [html.index(x) for x in ("EUR/USD", "Brent", "US 10-year", "BTC", "ETH")]
        self.assertEqual(order, sorted(order))  # the top coins right after EUR/USD, Brent and the 10-year
        self.assertEqual(html.count('aria-hidden="true" class="dup"'), html.count('class="si"') // 2)
        self.assertEqual(html.count('<a tabindex="-1" class="si"'), html.count('aria-hidden="true" class="dup"'))

    def test_numbers_page_has_the_anchors(self):
        page = views.numbers_page([fake("x", "Story")], self.m)
        for anchor in ('id="brent"', 'id="eurusd"', 'id="crypto"'):
            self.assertIn(anchor, page)


class Gate(unittest.TestCase):
    def test_what_fails(self):
        ok = fake("a", "Fine headline", body="Text.", dek="Dek.")
        self.assertEqual(site.content_problems(ok), [])
        self.assertEqual(site.content_problems(dict(ok, body=" \n")), ["empty body"])
        self.assertEqual(site.content_problems(dict(ok, dek="")), ["empty dek"])
        self.assertEqual(site.content_problems(dict(ok, body="Hello {headline}")), ["template leak"])
        self.assertEqual(site.content_problems(dict(ok, dek="{{ dek }}")), ["template leak"])
        self.assertEqual(site.content_problems(dict(ok, body="None of the banks said so.")), [])

    def test_one_bad_article_is_held_and_the_rest_go(self):
        rows = [fake(f"g{i}", f"Good {i}", body="Text.", dek="Dek.") for i in range(5)] + [fake("bad", "Bad one", body="", dek="Dek.")]
        ok, held = site.quarantine(rows)
        self.assertEqual(len(ok), 5)
        self.assertEqual(held, [{"id": "bad", "reasons": ["empty body"]}])

    def test_the_build_stops_only_when_nothing_or_half_passes(self):
        bad = lambda i: fake(f"b{i}", f"Bad {i}", body="", dek="Dek.")  # noqa: E731
        good = lambda i: fake(f"g{i}", f"Good {i}", body="Text.", dek="Dek.")  # noqa: E731
        with self.assertRaises(site.BuildBlocked):
            site.quarantine([bad(1), bad(2)])
        with self.assertRaises(site.BuildBlocked):
            site.quarantine([bad(i) for i in range(3)] + [good(i) for i in range(3)])
        site.quarantine([bad(1), good(1), good(2)])  # under six articles, one bad: only that one is held


class Context(unittest.TestCase):
    def box(self, headline, dek=""):
        m = data(True)
        m["series"]["henryhub"] = [["2026-11-24", 3.3], ["2026-11-25", 3.4]]
        return markets.context_for({"headlines": [headline], "dek": dek}, m)

    def test_every_rule_resolves_to_a_daily_or_weekly_series(self):
        for pattern, keys in markets.CONTEXT_RULES:
            for k in keys:
                self.assertIn(k, markets.SERIES)
                self.assertNotEqual(markets.SERIES[k][3], "wb", k)  # a monthly average is not today's price
                self.assertNotIn(k, markets.METALS)

    def test_rules_match_the_headline_or_the_dek(self):
        self.assertIn("USD/JPY", self.box("Yen slides as the BOJ holds"))
        self.assertIn("USD/JPY", self.box("Tokyo inflation hits a high", "Japan's core prices rose."))
        self.assertIn("GBP/USD", self.box("Sterling falls after the Bank of England vote"))
        self.assertIn("USD/CNY", self.box("China's exports slow", ""))
        self.assertIn("Natural gas", self.box("Natural gas jumps on cold forecasts"))
        self.assertIn("US gasoline", self.box("Pump prices ease as gasoline stocks build"))

    def test_a_country_alone_is_not_enough(self):
        self.assertEqual(self.box("Japan's Senate narrowly rejects censure motion"), "")
        self.assertEqual(self.box("UK Department for Work and Pensions takes systems offline"), "")
        self.assertEqual(self.box("Gold hits a record"), "")  # no metal cell, ever

    def test_two_cells_at_most(self):
        html = self.box("ECB holds rates as oil jumps and the yen slides")
        self.assertLessEqual(html.count('class="rt"'), 2)
        self.assertIn("Source: ECB statistics.", html)


class Related(unittest.TestCase):
    def test_related_needs_something_in_common_and_skips_the_neighbours(self):
        a = fake("a", "Rosebank oil field approved by UK ministers", "Politics", hours=1)
        near = fake("b", "UK ministers weigh Rosebank oil approval", "Politics", hours=2)
        far = fake("c", "UK ministers approve Rosebank oil licence", "Politics", hours=3)
        other = fake("d", "India Parliament passes budget", "Politics", hours=1.5)
        rows = [a, other, near, far]
        got = site.related(a, rows, exclude=[near])
        self.assertEqual([o["id"] for o in got], ["c"])
        self.assertEqual(site.related(other, rows), [])

    def test_more_on_needs_the_name_in_the_text_and_two_other_articles(self):
        p = fake("a", "Hong Kong rents rise", body="Habitat Property reported.", company="Habitat Property")
        others = [fake(f"o{i}", "Habitat Property sells", company="Habitat Property") for i in range(2)]
        self.assertTrue(site.more_on(p, "Habitat Property", [p, *others]))
        self.assertFalse(site.more_on(p, "Habitat Property", [p, others[0]]))
        self.assertFalse(site.more_on(dict(p, body="Nothing here."), "Habitat Property", [p, *others]))


class Touch(unittest.TestCase):
    css = (site.ASSETS / "views.css").read_text()
    js = (site.ASSETS / "site.js").read_text()

    def test_the_header_gives_up_its_box_on_a_phone_so_the_bar_can_stick(self):
        mobile = self.css[self.css.index("@media(max-width:900px){\n  /* a sticky bar"):]
        mobile = mobile[:mobile.index("\n}")]
        self.assertIn(".mh{display:contents}", mobile)
        self.assertIn(".mh .bar{position:sticky;top:0", mobile)

    def test_the_strip_has_a_pause_button_that_reduced_motion_hides(self):
        html = markets.strip(data(True))
        self.assertRegex(html, r'<button type="button" class="mpause" aria-pressed="false"')
        self.assertIn(".mstrip.paused ul{animation-play-state:paused}", self.css)
        self.assertRegex(self.css, r"prefers-reduced-motion:reduce\)\{[^@]*\.mstrip \.mpause\{display:none\}")
        self.assertIn('"aria-pressed"', self.js)
        self.assertIn("track.tabIndex = 0", self.js)

    def test_the_shortcuts_button_is_for_a_keyboard(self):
        self.assertIn("(hover: hover) and (pointer: fine)", self.js)
        self.assertIn(".kbd-hint{display:none}", self.css)

    def test_standalone_links_get_a_44px_target_on_touch(self):
        self.assertRegex(self.css, r"\.kick,\.more[^{]*\{display:inline-block;padding:14px 0;margin:-14px 0\}")
        self.assertIn("min-height:44px", self.css[self.css.index(".gl a"):][:80])

    def test_lists_and_pagers_get_the_same_target(self):
        for sel in (".pager a", ".mx th a", ".arch li a", ".mlist h3 a"):
            self.assertIn(sel, self.css[self.css.index("pointer:coarse"):])

    def test_no_gradient_anywhere(self):
        self.assertNotIn("gradient", self.css)


class Held(Features):
    """A real build with one article whose body is empty: it is on no page, sitemap, feed or search, and the status page lists it."""

    def setUp(self):
        self._p = mock.patch.object(site, "SHIPPED", {"numbers", "board", "feed", "paper"})
        self._p.start()
        self.addCleanup(self._p.stop)
        super().setUp()

    def test_a_held_article_is_nowhere(self):
        import shutil
        shutil.rmtree(self.out)
        post(self, "2026-11-26-1000-1", 1, headlines=["Empty one"], body="")
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub):
            out = site.build(self.root / "_site2")
        self.assertFalse((out / "s" / "2026-11-26-1000-1").exists())
        for f in ("sitemap.xml", "news-sitemap.xml", "feed.xml", "search.json", "latest/index.html"):
            self.assertNotIn("2026-11-26-1000-1", (out / f).read_text(), f)
        self.assertEqual(site.QUARANTINE, [{"id": "2026-11-26-1000-1", "reasons": ["empty body"]}])
        from aidaily import status
        self.assertEqual(status.snapshot()["quarantined"], site.QUARANTINE)


class Corrected(Features):
    def build_with(self, rows):
        import shutil
        shutil.rmtree(self.out)
        (desk.HERE / "corrections.json").write_text(json.dumps(rows))
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub):
            self.out = site.build(self.root / "_site3")

    def test_without_corrections_the_page_says_so_and_articles_carry_a_report_link(self):
        self.assertIn("No corrections yet.", self.read("corrections/index.html"))
        h = self.read("s/2026-11-26-0900-1/index.html")
        self.assertIn("github.com/Keremozdemirra/news/issues/new?title=Error%3A", h)
        self.assertIn("Article%3A%20https%3A%2F%2Fboardread.news%2Fs%2F2026-11-26-0900-1%2F", h)
        self.assertNotIn('class="corr"', h)
        self.assertIn("/corrections/</loc>", self.read("sitemap.xml"))

    def test_a_correction_is_dated_on_the_article_in_the_ld_and_on_the_page(self):
        self.build_with([{"id": "2026-11-26-0900-1", "time": "2026-11-27T09:30:00+00:00", "wrong": "10,000 jobs.", "right": "At least 10,000 jobs."}])
        h = self.read("s/2026-11-26-0900-1/index.html")
        self.assertIn('<aside class="corr" role="note"><b>Corrected</b>', h)
        self.assertIn("Was: 10,000 jobs. Now: At least 10,000 jobs.", h)
        ld = json.loads(re.findall(r'<script type="application/ld\+json">(.*?)</script>', h)[0])
        self.assertEqual(ld["dateModified"], "2026-11-27T09:30:00Z")
        self.assertEqual(ld["correction"][0]["@type"], "CorrectionComment")
        page = self.read("corrections/index.html")
        self.assertIn("2026-11-26-0900-1", page)
        self.assertNotIn("No corrections yet", page)

    def test_a_withdrawn_article_is_a_noindex_tombstone_and_in_no_list(self):
        self.build_with([{"id": "2026-11-26-0900-1", "time": "2026-11-27T09:30:00+00:00", "right": "The figure was wrong.", "withdrawn": True}])
        h = self.read("s/2026-11-26-0900-1/index.html")
        self.assertIn("This article was withdrawn", h)
        self.assertIn('content="noindex"', h)
        self.assertNotIn("SAP explores at least 10,000 job cuts", h)
        for f in ("sitemap.xml", "news-sitemap.xml", "feed.xml", "search.json", "latest/index.html", "index.html"):
            self.assertNotIn("SAP explores at least 10,000 job cuts" if f != "sitemap.xml" and f != "news-sitemap.xml" else "/s/2026-11-26-0900-1/", self.read(f), f)

    def test_a_broken_file_is_no_corrections(self):
        (desk.HERE / "corrections.json").write_text("{not json")
        self.assertEqual(site.load_corrections(), {})
        (desk.HERE / "corrections.json").write_text(json.dumps([{"id": "x"}, {"id": "y", "time": "nonsense"}, "str"]))
        self.assertEqual(site.load_corrections(), {})


class Built(Features):
    """A real build: the pages and feeds the review found wrong."""

    def setUp(self):
        shipped = mock.patch.object(site, "SHIPPED", {"numbers", "board", "feed", "paper"})
        shipped.start()
        self.addCleanup(shipped.stop)
        super().setUp()

    def test_weekly_feed_has_an_item_and_points_at_itself(self):
        x = self.read("weekly.xml")
        self.assertIn('rel="self"', x)
        self.assertIn("/weekly.xml", re.search(r'<atom:link href="([^"]+)"', x).group(1))
        self.assertGreaterEqual(len(ET.fromstring(x).findall(".//item")), 1)

    def test_search_results_are_not_indexed(self):
        self.assertIn('content="noindex"', self.read("search/index.html"))

    def test_paper_is_canonical_to_its_dated_edition_and_not_in_the_sitemap(self):
        h = self.read("paper/index.html")
        day = re.search(r'rel="canonical" href="[^"]*/paper/(\d{4}-\d\d-\d\d)/"', h).group(1)
        self.assertTrue((self.out / "paper" / day / "index.html").exists())
        sm = self.read("sitemap.xml")
        self.assertNotRegex(sm, r"/paper/</loc>")
        self.assertIn(f"/paper/{day}/</loc>", sm)

    def test_a_dated_edition_is_never_titled_yesterdays_paper(self):
        for d in (self.out / "paper").iterdir():
            if d.is_dir():
                h = (d / "index.html").read_text()
                self.assertNotIn("Yesterday&#x27;s paper, ", h)
                self.assertNotIn("Yesterday&#x27;s<br>paper", h)
                self.assertRegex(re.search(r"<title>(.*?)</title>", h).group(1), r"^The paper, \d+ \w+ \d{4}")

    def test_front_and_latest_say_when_they_were_built(self):
        for page in ("index.html", "latest/index.html"):
            self.assertRegex(self.read(page), r'<p class="upd" data-built="\d{4}-\d\d-\d\dT[\d:]+Z">Updated (\d+ \w+, )?\d\d:\d\d UTC(<span id="since" role="status" hidden></span>)?</p>')
        self.assertEqual(self.read("index.html").count('id="since"'), 1)  # one status line: the time, then the reader's own count
        self.assertNotIn('class="since"', self.read("index.html"))
        self.assertIn("3 * 36e5", (site.ASSETS / "site.js").read_text())

    def test_sources_sit_under_the_date_line_one_newsroom_is_called_single_source_and_ld_cites_them(self):
        h = self.read("s/2026-11-26-0900-1/index.html")  # CNBC and the Financial Times (Techmeme is an aggregator)
        self.assertRegex(h, r'<p class="srcs"><b>Sources:</b> <span><a href="https://www.cnbc.com/a"[^>]*>CNBC</a> and <a href="https://www.ft.com/b"[^>]*>Financial Times</a></span></p>')
        self.assertNotIn("Single source", h)
        self.assertLess(h.index('class="mt art-meta"'), h.index('class="srcs"'))  # the date line, then the sources
        self.assertNotIn('class="byline"', h)
        self.assertEqual(h.count("written by AI") + h.count("Written by AI"), 2, "said once in the end note, once in the footer")
        ld = json.loads(re.findall(r'<script type="application/ld\+json">(.*?)</script>', h)[0])
        self.assertEqual([c["name"] for c in ld["citation"]], ["CNBC", "Financial Times"])
        self.assertEqual(ld["citation"][0]["url"], "https://www.cnbc.com/a")
        one = self.read("s/2026-11-26-0800-1/index.html")  # SAP names a new chief: CNBC only
        self.assertIn('<span class="tag">Single source</span>', one)

    def test_the_404_page_says_it_in_one_line_and_offers_search_and_the_newest_stories(self):
        h = self.read("404.html")
        self.assertIn("<h1>Page not found</h1>", h)
        self.assertIn("Try search or the latest news.", h)
        self.assertIn('class="sbox"', h)
        self.assertIn('name="q"', h)
        self.assertEqual(len(re.findall(r'<li><a href="[^"]*/s/[^"]+"><time', h)), 5)  # the five newest, in the Latest row markup
        self.assertIn('<meta name="robots" content="noindex">', h)
        self.assertNotIn('class="prose"', h)  # no bullets

    def test_the_paper_has_a_text_edition_for_phones(self):
        self.assertIn('class="mlist"', self.read("paper/index.html"))

    def test_counts_use_one_definition_and_say_what_latest_is(self):
        self.assertIn("Business", self.read("latest/index.html"))
        self.assertNotIn("Every article", self.read("latest/index.html"))

    def test_main_feed_says_what_it_leaves_out(self):
        self.assertIn("no Sport", self.read("about/index.html"))
        self.assertIn("/sport/feed.xml", self.read("about/index.html"))


if __name__ == "__main__":
    unittest.main()
