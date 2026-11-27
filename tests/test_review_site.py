"""Findings of the 2026-11-27 review of boardread.news: one importance order on every surface, one time format, honest labels."""
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

    def test_the_404_page_links_are_a_list_of_big_targets(self):
        self.assertIn('class="gl"', self.read("404.html"))

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
