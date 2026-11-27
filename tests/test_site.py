import os
import json
import re
import unittest
import xml.etree.ElementTree as ET
from datetime import timedelta
from unittest import mock

os.environ.setdefault("DESK_SITE_OFFLINE", "1")  # building a site in a test never fetches market data or rewrites state/markets.json
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
                            body="Body.", sources=["CNBC"], source_urls=["https://www.cnbc.com/x"], categories=["policy"], photo_kind="person")
            (desk.MEDIA / pid).mkdir(parents=True)
            (desk.MEDIA / pid / "thumb.jpg").write_text("x")
        (desk.MEDIA / "2026-11-26-1300-1" / "photo.jpg").write_text("x")
        # a stand-in for ffmpeg: the real cut is checked by hand, here only that its result is wired in
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        crop = lambda ph, dest, *a, **k: dest.write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub), \
                mock.patch.object(site, "crop_image", side_effect=crop):
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
        self.assertEqual(ld["author"], {"@type": "Organization", "name": "Boardread", "url": site.SITE + "/about/"})  # the page that says who writes it
        self.assertTrue(ld["publisher"]["logo"]["url"].startswith("https://"))
        self.assertTrue(ld["datePublished"].endswith("Z"))
        self.assertIn("Written by AI from the sources listed", h)
        self.assertIn(f'href="{site.BASE}/standards/"', h)  # the corrections policy, which links the contact page
        self.assertNotIn("<b>here", h)  # field text is escaped, never markup
        self.assertIn("&lt;b&gt;here", h)
        # a story with only a thumb has no photo, no picture on the site, and still its own share card
        h2 = (out / "s" / "2026-11-21-1300-1" / "index.html").read_text()
        self.assertIn(site.BASE + "/og/2026-11-21-1300-1.jpg", h2)
        self.assertFalse((out / "img" / "2026-11-21-1300-1-t.jpg").exists())

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


class SitePages(SiteMeta):
    def test_every_page_the_navigation_promises_exists(self):
        out = self.build()
        for f in ("latest/index.html", "archive/index.html", f"archive/{desk.now():%Y-%m-%d}/index.html", "search/index.html",
                  "about/index.html", "standards/index.html", "contact/index.html",
                  "404.html", "robots.txt", "llms.txt", "search.json", "assets/site.css", "assets/site.js", "t/ai/index.html", "week/index.html"):
            self.assertTrue((out / f).exists(), f)

    def test_structured_data_gives_google_three_crops_a_visible_byline_and_list_pages_an_itemlist(self):
        out = self.build()
        h = (out / "s" / "2026-11-26-1300-1" / "index.html").read_text()
        ld = json.loads(LD.search(h).group(1))
        self.assertEqual([u.rsplit("-", 1)[1] for u in ld["image"]], ["16x9.jpg", "4x3.jpg", "1x1.jpg"])
        for u in ld["image"]:
            self.assertTrue((out / u.replace(site.ORIGIN + site.BASE, "").lstrip("/")).exists(), u)
        self.assertIn(f'<span class="by">By <a href="{site.BASE}/about/">Boardread</a></span>', h)  # the byline Google News looks for
        photoless = json.loads(LD.search((out / "s" / "2026-11-21-1300-1" / "index.html").read_text()).group(1))
        self.assertEqual(len(photoless["image"]), 1)  # no photo: the one share card
        home = (out / "index.html").read_text()
        self.assertNotIn("SearchAction", home)  # nothing on the site reads it
        pages = ["latest/index.html"] + [f"t/{d.name}/index.html" for d in sorted((out / "t").iterdir()) if d.is_dir()]
        with_list = 0
        for page in pages:
            colls = [x for x in (json.loads(y) for y in LD.findall((out / page).read_text())) if x["@type"] == "CollectionPage"]
            self.assertEqual(len(colls), 1, page)
            if "mainEntity" in colls[0]:
                with_list += 1
                self.assertEqual(colls[0]["mainEntity"]["@type"], "ItemList")
                self.assertTrue(colls[0]["mainEntity"]["itemListElement"][0]["url"].startswith("https://"))
        self.assertGreaterEqual(with_list, 2)  # Latest and the section the story is in
        self.assertTrue(any(json.loads(x)["@type"] == "CollectionPage" for x in LD.findall((out / "numbers" / "index.html").read_text()))
                        if (out / "numbers" / "index.html").exists() else True)

    def test_llms_txt_names_the_site_its_sections_newest_articles_standards_and_feeds(self):
        out = self.build()
        txt = (out / "llms.txt").read_text()
        lines = txt.splitlines()
        self.assertLess(len(lines), 40)
        self.assertEqual(lines[0], "# Boardread")
        self.assertTrue(lines[2].startswith("> "))
        for head in ("## Sections", "## Latest", "## Standards", "## Feeds"):
            self.assertIn(head, lines)
        self.assertIn(f"{site.SITE}/s/2026-11-26-1300-1/", txt)
        self.assertIn(f"{site.SITE}/news-sitemap.xml", txt)
        self.assertIn(f"{site.SITE}/standards/", txt)

    def test_search_index_has_the_fields_the_script_reads(self):
        out = self.build()
        rows = json.loads((out / "search.json").read_text())
        self.assertEqual(len(rows), 2)
        self.assertEqual(set(rows[0]), {"headline", "dek", "topic", "date", "url", "company", "sources"})
        self.assertTrue(rows[0]["url"].endswith("/s/2026-11-26-1300-1/"))

    def test_story_page_has_sources_share_links_related_and_neighbours(self):
        out = self.build()
        h = (out / "s" / "2026-11-26-1300-1" / "index.html").read_text()
        self.assertIn('href="https://www.cnbc.com/x"', h)
        for host in ("x.com/intent/post", "bsky.app/intent/compose", "linkedin.com/sharing/share-offsite", "wa.me/?text="):
            self.assertIn(host, h)
        self.assertIn("data-copy=", h)
        self.assertNotIn("Related news", h)  # the only other story is the Older link, and shares nothing with this one
        self.assertIn('rel="prev"', h)  # the older story
        self.assertNotIn("Newer", h)  # nothing is newer than the newest

    def test_footer_links_the_own_impressum_and_privacy_pages(self):
        out = self.build()
        h = (out / "index.html").read_text()
        self.assertIn('href="/impressum/"', h)
        self.assertIn('href="/privacy/"', h)
        self.assertNotIn("keremozdemir.de/privacy", h)
        priv = (out / "privacy" / "index.html").read_text()
        for s in ("br:visit", "SOURCE", "BayLDA", "Art. 77", "GitHub Pages", "Anthropic"):
            self.assertIn(s, priv)
        self.assertIn("/privacy/</loc>", (out / "sitemap.xml").read_text())
        imp = (out / "impressum" / "index.html").read_text()
        for s in ("§ 5 DDG", "§ 18 Abs. 2 MStV", "Kerem Özdemir", "80807 München", "§ 36 VSBG"):
            self.assertIn(s, imp)

    def test_newsletter_slot_stays_hidden_until_a_url_exists(self):
        self.assertNotIn("Newsletter", (self.build() / "index.html").read_text())

    def test_no_script_tag_with_inline_code(self):
        h = (self.build() / "index.html").read_text()
        self.assertNotIn("<script>", h)


class SiteAddress(unittest.TestCase):
    def test_site_url_alone_moves_the_whole_site_to_the_domain_root(self):
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, DESK_SITE_URL="https://boardread.news")
            code = "from aidaily import site; print(repr(site.BASE), site.SITE); site.build(%r)" % d
            r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("'' https://boardread.news", r.stdout)
            h = (Path(d) / "index.html").read_text()
            self.assertIn('href="https://boardread.news/"', h)
            self.assertNotIn('href="/news/', h)
            self.assertIn('href="/latest/"', h)

    def test_brand_domain_is_its_own_setting_and_defaults_to_the_site(self):
        with mock.patch.dict(desk.CONFIG, {"brand_domain": "boardread.news"}):
            self.assertEqual(desk.brand_domain(), "boardread.news")
        with mock.patch.dict(desk.CONFIG, {"brand_domain": ""}):
            self.assertEqual(desk.brand_domain(), desk.CONFIG["site_url"].split("://")[-1])


class SiteNewsletter(SiteMeta):
    def test_newsletter_link_appears_when_desk_json_has_a_url(self):
        with mock.patch.dict(desk.CONFIG, {"newsletter_url": "https://news.example/sub"}):
            self.assertIn("https://news.example/sub", (self.build() / "index.html").read_text())


class SiteRedirects(SiteMeta):
    def test_old_address_gets_a_stub_per_story_pointing_at_the_new_one(self):
        self.build()
        out = self.root / "old"
        site.redirects(out)
        h = (out / "news" / "s" / "2026-11-26-1300-1" / "index.html").read_text()
        self.assertIn(f'url={site.SITE}/s/2026-11-26-1300-1/', h)
        self.assertIn('rel="canonical"', h)
        self.assertTrue((out / "news" / "index.html").exists())
