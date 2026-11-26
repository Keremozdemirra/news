import xml.etree.ElementTree as ET
import unittest
from datetime import timedelta
from unittest import mock

from aidaily import desk, outlets, site, sitepages
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
        self.assertIn("Reported by 2 newsrooms", h)
        self.assertNotIn("Techmeme", h)
        self.assertIn("Reported by 2 newsrooms", self.read("index.html"))

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
        self.assertIn("<b>Financial Times</b>", h)

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
        self.assertIn("Most covered this week", self.read("index.html"))
        self.assertIn("Most covered this week", self.read("week/index.html"))

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
        for s in ("Headline here", "Reported by 2 newsrooms", "boardread.news"):
            self.assertIn(s, h)
        self.assertEqual(h.count("<i class=on>"), 2)


if __name__ == "__main__":
    unittest.main()


class Chrome(Features):
    """The masthead, navigation and markets of the broadsheet design."""

    def test_nav_lists_only_pages_that_exist_and_names_the_quiz_until_play_ships(self):
        h = self.read("index.html")
        for href in ("/brief/", "/numbers/", "/week/", "/search/", "/quiz/"):
            self.assertIn(f'href="{site.BASE}{href}"', h)
        for gone in ("/board/", "/feed/", "/paper/", "/play/"):  # not shipped: no menu entry, no page
            self.assertNotIn(f'class="cap" href="{site.BASE}{gone}"', h)
            self.assertFalse((self.out / gone.strip("/") / "index.html").exists(), gone)

    def test_masthead_counts_and_archivo_headlines_are_self_hosted(self):
        h = self.read("index.html")
        self.assertIn("Articles today", h)
        self.assertIn("Archivo-var.woff2", h)
        self.assertTrue((self.out / "fonts" / "Archivo-var.woff2").exists())
        self.assertIn("Archivo", (self.out / "fonts" / "OFL.txt").read_text())

    def test_numbers_page_shows_the_figure_and_no_oil_row_without_a_key(self):
        h = self.read("numbers/index.html")
        self.assertIn("10,000", h)
        self.assertNotIn("Brent", h)
        self.assertNotIn("Pending", h)
