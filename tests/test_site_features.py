import os
import json
import xml.etree.ElementTree as ET
import unittest
from datetime import timedelta
from unittest import mock

os.environ.setdefault("DESK_SITE_OFFLINE", "1")  # building a site in a test never fetches market data or rewrites state/markets.json
from aidaily import desk, outlets, site, sitepages, views
from test_desk import Tmp


class Outlets(unittest.TestCase):
    def test_aggregators_and_social_accounts_are_not_newsrooms(self):
        p = {"sources": ["Techmeme", "CNBC", "cnbc", "@trq212", "Google News", "Hacker News", "Product Hunt", "X"]}
        self.assertEqual(outlets.newsrooms(p), ["CNBC"])

    def test_only_aggregators_left_keeps_them_rather_than_an_empty_list(self):
        self.assertEqual(outlets.newsrooms({"sources": ["Techmeme"]}), ["Techmeme"])
        self.assertEqual(outlets.newsrooms({}), [])

    def test_article_urls_map_to_outlets_by_domain(self):
        self.assertEqual(outlets.outlet_of("https://www.bbc.co.uk/news/x?a=1"), "BBC")
        self.assertEqual(outlets.outlet_of("https://www.ft.com/content/1"), "Financial Times")
        self.assertEqual(outlets.outlet_of("https://small.example.org/a"), "small.example.org")

    def test_source_mix_lists_one_link_per_named_outlet(self):
        p = {"sources": ["CNBC", "Techmeme"], "source_urls": ["https://www.cnbc.com/a", "https://www.cnbc.com/b", "https://techmeme.com/x", "https://www.npr.org/z"]}
        self.assertEqual(outlets.source_mix(p), [("CNBC", "https://www.cnbc.com/a")])


def post(self, pid, hours_ago, **kw):
    d = dict(status="published", published=(desk.now() - timedelta(hours=hours_ago)).isoformat(), headlines=[f"Story {pid}"], dek="Dek.",
             body="First.\nSecond.", sources=["CNBC", "Financial Times"], source_urls=["https://www.cnbc.com/a", "https://www.ft.com/b"], topic="Business", score=5)
    d.update(kw)
    self.write_post(pid, **d)
    (desk.MEDIA / pid).mkdir(parents=True, exist_ok=True)


class Features(Tmp):
    def setUp(self):
        super().setUp()
        post(self, "2026-11-26-0900-1", 1, headlines=["SAP explores at least 10,000 job cuts"], figure="10,000", company="SAP", logo_names=["SAP"],
             sources=["Techmeme", "CNBC", "Financial Times"], dek="The group restructures.")
        post(self, "2026-11-26-0800-1", 2, headlines=["SAP names a new chief"], company="SAP", sources=["CNBC"], topic="Tech")
        post(self, "2026-11-26-0700-1", 3, headlines=["Global stocks rally"], topic="Markets", figure="", sources=["Techmeme"])
        (desk.MEDIA / "2026-11-26-0700-1" / "thumb.jpg").write_text("x")  # the Instagram crop with text: never a picture here
        (desk.MEDIA / "2026-11-26-0900-1" / "logo.svg").write_text("<svg/>")
        for i in range(3, 12):
            post(self, f"2026-11-25-1{i:02d}-1", 5 + i, score=i)
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub):
            self.out = site.build(self.root / "_site")

    def read(self, rel):
        return (self.out / rel).read_text()

    def rows(self):
        return sorted([p for p, _ in desk.posts()], key=lambda p: p["published"], reverse=True)

    def test_coverage_meter_counts_newsrooms_without_the_aggregator(self):
        h = self.read("s/2026-11-26-0900-1/index.html")
        self.assertIn("2 newsrooms", h)
        self.assertIn("Reported by ", h)  # the outlet names, as text, in the byline
        self.assertNotIn('class="mtr"', h)  # no box meters
        self.assertIn("2 newsrooms", self.read("index.html"))

    def test_photoless_story_is_a_text_row_never_a_thumbnail_tile(self):
        h = self.read("index.html")
        self.assertNotIn("2026-11-26-0700-1-t.jpg", h)
        self.assertFalse((self.out / "img" / "2026-11-26-0700-1-t.jpg").exists())

    def test_story_has_what_happened_and_the_number_only_when_stated(self):
        h = self.read("s/2026-11-26-0900-1/index.html")
        self.assertIn("What happened", h)
        self.assertIn("numbox", h)
        self.assertIn('class="big">10,000<', h)
        self.assertNotIn("Why it matters", h)
        self.assertNotIn("numbox", self.read("s/2026-11-26-0800-1/index.html"))

    def test_number_box_needs_the_figure_in_headline_or_dek(self):
        p = {"headlines": ["A headline"], "dek": "The dek says 5%.", "figure": "5%"}
        self.assertIn("The dek says 5%.", site.number_box(p))
        self.assertEqual(site.number_box({**p, "figure": "7%"}), "")
        self.assertEqual(site.number_box({**p, "figure": ""}), "")

    def test_how_made_panel_and_how_it_works_page_carry_live_counts(self):
        h = self.read("s/2026-11-26-0900-1/index.html")
        for s in ("How this article was made", "Checks passed", "Financial Times"):
            self.assertIn(s, h)
        self.assertEqual(site.desk_counts(self.rows())["stories"], 12)
        page = self.read("how-it-works/index.html")
        self.assertIn("Feeds scanned", page)
        self.assertIn("12 articles", page)

    def test_source_mix_links_each_outlet_to_its_article(self):
        h = self.read("s/2026-11-26-0900-1/index.html")
        self.assertIn('href="https://www.cnbc.com/a"', h)
        self.assertIn(">Financial Times</a>", h)

    def test_brief_has_at_most_eight_stories_end_marker_archive_and_nav_link(self):
        h = self.read("brief/index.html")
        self.assertLessEqual(h.count('<article class="bn">'), 8)
        self.assertGreaterEqual(h.count('<article class="bn">'), 5)
        self.assertIn("End of the brief.", h)  # the column ends, with the closing mark
        self.assertIn("&ndash; 30 &ndash;", h)
        self.assertTrue((self.out / "brief" / "2026-11-26" / "index.html").exists())
        self.assertIn(f'href="{site.BASE}/brief/"', self.read("index.html"))
        self.assertNotIn("Earlier briefs", h)  # one day of stories: no empty heading

    def test_quiz_fill_the_number_with_answer_story_and_sources(self):
        h = self.read("quiz/index.html")
        self.assertIn("Fill the number", h)
        self.assertIn("SAP explores at least ___ job cuts", h)
        self.assertEqual(h.count('class="opt"'), 4)
        self.assertRegex(h, r'data-answer="\d"')
        self.assertIn("/s/2026-11-26-0900-1/", h)
        self.assertIn("https://www.cnbc.com/a", h)
        self.assertNotIn("<script>", h)

    def test_quiz_skips_types_without_data_and_says_so_when_nothing_is_left(self):
        self.assertEqual(sitepages.quiz_questions([]), [])
        self.assertIn("no quiz yet", sitepages.quiz_page([]))
        for p in self.rows():  # the quiz reads the figure the page shows
            p["_hires"] = False
        types = {q["type"] for q in sitepages.quiz_questions(self.rows())}
        self.assertEqual(types, {"fill"})  # fewer than four companies, no money figures, no portraits

    def test_company_page_needs_two_stories_and_story_pages_link_to_it(self):
        page = self.read("c/sap/index.html")
        self.assertLess(page.index("SAP explores"), page.index("SAP names a new chief"))  # newest first
        self.assertIn("co-sap.svg", page)
        self.assertIn(f'href="{site.BASE}/c/sap/"', self.read("s/2026-11-26-0900-1/index.html"))
        self.assertEqual(sorted(p.name for p in (self.out / "c").iterdir()), ["sap"])

    def test_feeds_per_topic_and_company_parse_and_are_advertised(self):
        for rel in ("t/tech/feed.xml", "c/sap/feed.xml", "t/business/feed.xml"):
            ET.parse(self.out / rel)
        self.assertEqual(len(ET.parse(self.out / "c/sap/feed.xml").getroot().findall("channel/item")), 2)
        self.assertIn("/c/sap/feed.xml", self.read("c/sap/index.html"))
        self.assertIn('rel="alternate" type="application/rss+xml" title="boardread. Tech"', self.read("t/tech/index.html"))

    def test_most_covered_ranks_companies_by_stories_in_seven_days(self):
        self.assertEqual(site.most_covered(self.rows())[0], ("SAP", "sap", 2))
        self.assertNotIn("Most covered this week", self.read("index.html"))  # a ranking of one company ranks nothing
        self.assertNotIn("Most covered this week", self.read("week/index.html"))
        rows = self.rows()
        extra = [dict(rows[0], id=f"x{i}", company=c, published=rows[0]["published"]) for i, c in enumerate(["Acme", "Acme", "Beta", "Beta", "Gamma", "Gamma"])]
        listing = site.covered_list(rows + extra, {}, 5)
        self.assertIn("Acme", listing)
        self.assertNotIn("1 articles", listing)

    def test_front_page_carries_the_hooks_the_script_uses(self):
        h = self.read("index.html")
        self.assertIn('id="since"', h)
        self.assertIn("data-keys", h)
        js = self.read("assets/site.js")
        for token in ("br:visit", "keydown", "data-quiz", "localStorage"):
            self.assertIn(token, js)
        self.assertNotIn("document.cookie", js)

    def test_channel_marks_are_inline_svg_with_accessible_names(self):
        with mock.patch.object(site, "accounts", return_value=[{"name": "Bluesky", "url": "https://bsky.app/x"}]):
            h = site.page("t", "", "d")
        self.assertRegex(h, r'<a class="chan" href="https://bsky.app/x" rel="me noopener" aria-label="Bluesky"><svg')
        share = site.share_links({"id": "i", "headlines": ["H"]})
        self.assertIn('aria-label="Copy link"', share)
        for name in ("X", "Bluesky", "LinkedIn", "WhatsApp"):
            self.assertIn(f'aria-label="Share on {name}"', share)
        self.assertNotIn("<img", share)

    def test_share_card_page_has_headline_meter_and_address(self):
        h = site.card_html({"headlines": ["Headline here"], "sources": ["CNBC", "FT"], "topic": "Tech"})
        for s in ("Headline here", "2 newsrooms", "boardread.news"):
            self.assertIn(s, h)
        self.assertNotIn("<i class=on>", h)  # coverage is text, not boxes


if __name__ == "__main__":
    unittest.main()


class Chrome(Features):
    """The masthead, navigation and markets of the broadsheet design, with only the numbers page shipped."""

    def setUp(self):
        shipped = mock.patch.object(site, "SHIPPED", {"numbers"})
        shipped.start()
        self.addCleanup(shipped.stop)
        super().setUp()

    def test_nav_lists_only_pages_that_exist_and_names_the_quiz_until_play_ships(self):
        h = self.read("index.html")
        for href in ("/brief/", "/numbers/", "/week/", "/search/"):
            self.assertIn(f'href="{site.BASE}{href}"', h)
        for gone in ("/board/", "/feed/", "/paper/", "/play/", "/quiz/"):  # not shipped: no menu entry, no page
            self.assertNotIn(f'<a href="{site.BASE}{gone}">', h)
            if gone != "/quiz/":  # the old questions page stays at its address, unlinked, until the games replace it
                self.assertFalse((self.out / gone.strip("/") / "index.html").exists(), gone)

    def test_two_faces_self_hosted_and_the_v2_masthead(self):
        h = self.read("index.html")
        self.assertIn('wrap barin', h)  # one bar: menu and search, the wordmark, the toggle and marks
        self.assertIn('class="menu"', h)
        self.assertIn('class="sections"', h)
        self.assertNotIn("Archivo", h)
        for f in ("LibreFranklin-800.woff2", "Newsreader-var.woff2"):
            self.assertTrue((self.out / "fonts" / f).exists(), f)
        self.assertFalse((self.out / "fonts" / "Archivo-var.woff2").exists())
        ofl = (self.out / "fonts" / "OFL.txt").read_text()
        self.assertIn("Newsreader", ofl)
        self.assertNotIn("Archivo", ofl)
        for name in ("site.css", "views.css"):
            css = (self.out / "assets" / name).read_text()
            for banned in ("Archivo", "border-radius", "box-shadow", "gradient"):
                self.assertNotIn(banned, css, (name, banned))

    def test_brand_icons_and_manifest_are_shipped_and_linked(self):
        h = self.read("index.html")
        for part in ("icon.svg", "favicon.ico", "apple-touch-icon.png", "manifest.webmanifest"):
            self.assertIn(part, h)
            self.assertTrue((self.out / part).exists(), part)
        icons = json.loads(self.read("manifest.webmanifest"))["icons"]
        self.assertEqual({i["sizes"] for i in icons}, {"192x192", "512x512"})
        for f in ("icon-192.png", "icon-512.png", "og-default.png"):
            self.assertTrue((self.out / f).exists(), f)

    def test_footer_has_four_groups_and_one_line(self):
        h = self.read("index.html")
        for group in ("<h2>Sections</h2>", "<h2>Boardread</h2>", "<h2>Legal</h2>", "<h2>Follow</h2>"):
            self.assertIn(group, h)
        self.assertIn("Written by AI from the sources listed. Corrections:", h)

    def test_numbers_page_shows_the_figure_and_no_oil_row_without_a_key(self):
        h = self.read("numbers/index.html")
        self.assertIn("10,000", h)
        self.assertNotIn("Brent", h)
        self.assertNotIn("Pending", h)


class Views(Features):
    """Board, Feed and the cover, built with their keys shipped."""

    def setUp(self):
        shipped = mock.patch.object(site, "SHIPPED", {"numbers", "board", "feed", "paper"})
        shipped.start()
        self.addCleanup(shipped.stop)
        super().setUp()

    def test_board_has_flaps_seats_names_and_wire_and_no_empty_seat_rows(self):
        h = self.read("board/index.html")
        for part in ('id="river"', 'id="names"', 'id="wire"', 'class="fl go"'):
            self.assertIn(part, h)
        self.assertNotIn("&mdash;", h)  # a seat nobody holds is not a row
        self.assertNotIn("Not reported", self.read("s/2026-11-26-0900-1/index.html"))
        self.assertIn("SAP", h)  # the most-covered company is on the names tape
        self.assertIn('data-age', h)

    def test_wire_marks_each_article_against_the_newsrooms_that_reported_it(self):
        h = self.read("board/index.html")
        self.assertIn("Financial Times", h)
        self.assertRegex(h, r'<td><span title="CNBC"')

    def test_feed_cards_are_photo_or_text_and_the_cover_links_the_week(self):
        h = self.read("feed/index.html")
        self.assertIn('class="fgrid"', h)
        self.assertIn("fcard", h)
        self.assertRegex(h, r'class="fcard[^"]*textonly"')  # photo-less articles are text cards
        c = self.read("cover/index.html")
        self.assertIn("cv-card", c)
        self.assertRegex(c, r"Week \d\d")

    def test_names_ranks_by_pickups_and_drops_plain_words(self):
        names = {n for n, _, _ in views.names(self.rows_shown())}
        self.assertIn("SAP", names)
        self.assertNotIn("Global", names)

    def rows_shown(self):
        return site.published()

    def test_nav_links_the_shipped_pages(self):
        h = self.read("index.html")
        for href in ("/board/", "/feed/"):
            self.assertIn(f'<a href="{site.BASE}{href}">', h)

    def test_paper_has_an_even_number_of_pages_a_dated_archive_and_no_script_needed_to_read(self):
        h = self.read("paper/index.html")
        self.assertEqual(h.count('class="leaf"') * 2, h.count('<div class="face r">') + h.count('<div class="face bk">'))
        self.assertEqual(h.count('class="pgw"'), h.count('class="leaf"') * 2)  # the phone row holds the same pages
        self.assertIn("data-prev", h)
        self.assertIn("paper.js", h)
        d = [p.name for p in (self.out / "paper").iterdir() if p.is_dir()]
        self.assertEqual(sorted(d), sorted({site.day_of(p["published"]) for p in site.published()}))

    def test_paper_shows_the_last_full_day_not_the_running_one(self):
        rows = site.published()
        today = site.day_of(rows[0]["published"])
        self.assertEqual(views.edition_day(rows, today="2999-01-01"), today)  # the newest day once it has closed
        self.assertEqual(views.edition_day(rows, today=today), today)  # nothing earlier exists: the newest day
        self.assertEqual(views.edition_day(rows + [dict(rows[0], published="2020-01-01T00:00:00+00:00")], today=today), "2020-01-01")
        self.assertIsNone(views.edition_day([], today="2026-11-26"))


def fake(headline, topic, n, score, **kw):
    d = dict(id=headline[:8], headlines=[headline], dek="", topic=topic, sources=[f"Room {i}" for i in range(n)], score=score, published="2026-11-26T12:00:00+00:00", _thumb=True)
    d.update(kw)
    return d


class FrontPage(unittest.TestCase):
    def test_hard_news_outranks_brand_pr_even_with_a_higher_desk_score(self):
        pr = fake("Denny's reshares Nvidia origin story after Jensen Huang's return", "Business", 4, 13.3)
        tariffs = fake("Trump signals he is ready to escalate tariffs on Asian trading partners", "Economy", 4, 12.0)
        tanker = fake("Maltese-flagged tanker capsizes off Ibiza, killing a crew member", "World", 3, 8.3)
        breach = fake("1Password reports a data breach and says user vaults are safe", "Tech", 2, 8.4)
        order = sorted([pr, tariffs, tanker, breach], key=views.front_score, reverse=True)
        self.assertIs(order[0], tariffs)
        self.assertIs(order[-1], pr)
        self.assertLess(views.front_score(pr), views.front_score(breach))

    def test_a_photo_runs_on_the_front_only_when_it_shows_the_named_subject(self):
        self.assertTrue(views.photo_ok(fake("Trump signals tariffs", "Economy", 4, 9, photo_file="Official Presidential Portrait of Donald Trump.jpg")))
        self.assertTrue(views.photo_ok(fake("Norse Atlantic suspends all flights", "Business", 3, 9, photo_file="Norse Atlantic Airways Boeing 787.jpg")))
        self.assertFalse(views.photo_ok(fake("OpenAI corrects GPT-6.2 billing mistake", "AI", 1, 9, photo_file="Virginia Tech - data center.jpg")))
        self.assertFalse(views.photo_ok(fake("FCC clears SpaceX to deploy 1 million satellites", "Tech", 4, 9, photo_file="North America from low orbiting satellite.jpg")))
        self.assertFalse(views.photo_ok(fake("Trump signals tariffs", "Economy", 4, 9, photo_file="", _thumb=False)))


class FrontPhotos(unittest.TestCase):
    def test_the_same_subject_is_recognised_across_articles(self):
        a = fake("Trump signals tariffs", "Economy", 4, 9, photo_file="Official Presidential Portrait of Donald Trump.jpg")
        b = fake("Trump demands probe of GDP revision", "Economy", 2, 8, photo_file="January 2025 Official Presidential Portrait of Donald Trump.jpg")
        self.assertEqual(views.photo_subject(a), views.photo_subject(b))  # the front shows the first and runs the second as text
        self.assertIsNone(views.photo_subject(fake("OpenAI corrects billing", "AI", 1, 9, photo_file="Virginia Tech - data center.jpg")))


class FrontBuilt(Features):
    def test_every_article_appears_once_on_the_front_page(self):
        import re
        h = self.read("index.html")
        main = h[h.index('<main'):h.index("</main>")]
        links = re.findall(r'<(?:h1|h3)[^>]*><a[^>]*href="[^"]*/s/([^/"]+)/"|<a href="[^"]*/s/([^/"]+)/"><div class="mt"', main)
        ids = [a or b for a, b in links]
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_most_covered_stays_out_until_three_companies_have_two_articles(self):
        self.assertNotIn("Most covered", self.read("index.html"))  # only SAP has two articles

    def test_default_theme_is_light_with_a_toggle_and_a_head_script(self):
        h = self.read("index.html")
        self.assertIn('class="themebtn"', h)
        self.assertRegex(h, r'<script src="[^"]*theme\.js[^"]*"></script>')  # blocking, in the head, before first paint
        self.assertNotIn("prefers-color-scheme", (self.out / "assets" / "site.css").read_text())
        js = (self.out / "assets" / "theme.js").read_text()
        self.assertIn("br:theme", js)
        self.assertNotIn("matchMedia", js)

    def test_section_rows_have_no_holes_and_no_empty_rules(self):
        import re
        h = self.read("index.html")
        rows = re.findall(r'<div class="sects" style="--n:(\d+)">', h)
        self.assertEqual(rows, [])  # sections reflow with auto-fit columns: no counts, no empty slots
        self.assertGreaterEqual(h.count('<section class="sect">'), 1)
        for sect in re.findall(r'<section class="sect">(.*?)</section>', h, re.S):
            self.assertIn("<article", sect)  # a section head always has an article under it

    def test_front_has_no_byline_wall_and_no_quiz_link(self):
        h = self.read("index.html")
        self.assertNotIn("By the Boardread desk", h)
        self.assertNotIn('href="/quiz/"', h)
        self.assertIn("Boardread desk, written by AI", self.read("s/2026-11-26-0900-1/index.html"))

    def test_front_rates_block_has_one_source_line_and_no_chart(self):
        h = self.read("index.html")
        for block in h.split('<section class="rates')[1:]:
            self.assertIn('class="attr"', block)  # one source line under the block
