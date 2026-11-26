import json
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from unittest import mock

from aidaily import desk, site
from test_desk import Tmp

LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
HEAD = ('rel="canonical"', 'og:site_name', 'og:title', 'og:description', 'og:url', 'og:type', 'og:image"',
        'twitter:card" content="summary_large_image"', 'name="description"')
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "n": "http://www.google.com/schemas/sitemap-news/0.9"}


class SiteMeta(Tmp):
    def build(self):
        new, old = desk.now(), desk.now() - timedelta(days=5)
        for pid, when, head in (("2026-11-26-1300-1", new, "A very long headline " * 8), ("2026-11-21-1300-1", old, "Old story")):
            self.write_post(pid, status="published", published=when.isoformat(), headlines=[head], dek="Dek <b>here</b>.",
                            body="Body.", sources=["CNBC"], source_urls=["https://www.cnbc.com/x"], categories=["policy"])
            (desk.MEDIA / pid).mkdir(parents=True)
            (desk.MEDIA / pid / "thumb.jpg").write_text("x")
        (desk.MEDIA / "2026-11-26-1300-1" / "photo.jpg").write_text("x")
        # a stand-in for ffmpeg: the real cut is checked by hand, here only that its result is wired in
        with mock.patch.object(site, "og_image", side_effect=lambda src, dst: dst.write_bytes(b"jpg") or True):
            return site.build(self.root / "_site")

    def test_every_page_carries_preview_tags(self):
        out = self.build()
        for f in ("index.html", "t/tech/index.html", "week/index.html", "s/2026-11-26-1300-1/index.html"):
            h = (out / f).read_text()
            for k in HEAD:
                self.assertIn(k, h, (f, k))
            self.assertRegex(h, r'og:image" content="https://[^"]+\.(jpg|png)"')

    def test_story_page_structured_data_and_footer(self):
        out = self.build()
        h = (out / "s" / "2026-11-26-1300-1" / "index.html").read_text()
        self.assertIn('property="og:type" content="article"', h)
        self.assertIn(f'href="{site.SITE}/s/2026-11-26-1300-1/"', h)
        self.assertIn("/og/2026-11-26-1300-1.jpg", h)
        ld = json.loads(LD.search(h).group(1))
        self.assertEqual(ld["@type"], "NewsArticle")
        self.assertLessEqual(len(ld["headline"]), 110)
        self.assertTrue(ld["isAccessibleForFree"])
        self.assertEqual(ld["author"], {"@type": "Organization", "name": "Boardread", "url": site.SITE + "/"})
        self.assertTrue(ld["publisher"]["logo"]["url"].startswith("https://"))
        self.assertTrue(ld["datePublished"].endswith("Z"))
        self.assertIn("Written by AI from the sources listed", h)
        self.assertIn('href="/contact/"', h)
        self.assertNotIn("<b>", h)  # field text is escaped, never markup
        # a story with only a thumb has no photo: its preview is the shared image, and the page builds
        h2 = (out / "s" / "2026-11-21-1300-1" / "index.html").read_text()
        self.assertIn("/news/og-default.png", h2)

    def test_sitemaps_parse_and_news_sitemap_keeps_48_hours(self):
        out = self.build()
        locs = [u.text for u in ET.parse(out / "sitemap.xml").getroot().iterfind(".//s:loc", NS)]
        for want in ("/s/2026-11-26-1300-1/", "/s/2026-11-21-1300-1/", "/t/tech/", "/week/"):
            self.assertTrue(any(l.endswith(want) for l in locs), want)
        self.assertTrue(all(u.find("s:lastmod", NS) is not None for u in ET.parse(out / "sitemap.xml").getroot()))
        news = ET.parse(out / "news-sitemap.xml").getroot()
        self.assertEqual(len(news), 1)
        self.assertEqual(news.find(".//n:name", NS).text, "Boardread")
        self.assertEqual(news.find(".//n:language", NS).text, "en")
        self.assertTrue(news.find(".//n:publication_date", NS).text.endswith("Z"))

    def test_feed_items_have_category_creator_image_and_permalink_guid(self):
        out = self.build()
        item = ET.parse(out / "feed.xml").getroot().find("channel/item")
        self.assertEqual(item.find("guid").get("isPermaLink"), "true")
        self.assertTrue(item.find("category").text)
        self.assertEqual(item.find("{http://purl.org/dc/elements/1.1/}creator").text, "Boardread")
        enc = item.find("enclosure")
        self.assertEqual((enc.get("type"), enc.get("length")), ("image/jpeg", "3"))
        self.assertTrue(enc.get("url").startswith("https://"))

    def test_clip_cuts_at_a_word(self):
        self.assertEqual(site.clip("short", 110), "short")
        c = site.clip("word " * 40, 110)
        self.assertLessEqual(len(c), 110)
        self.assertTrue(c.endswith("…"))
