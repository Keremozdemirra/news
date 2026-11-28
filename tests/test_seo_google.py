"""Google Search, News and Discover readiness: the index gate, the sitemaps' dates, thin hubs, image size, Preferred sources.
No network: every page and file is built in a temp directory."""
import struct
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from aidaily import seo, site

SITE_URL = site.SITE
NOW = datetime(2026, 11, 28, 8, 0, tzinfo=timezone.utc)


def art(i="a", sources=("Reuters", "BBC"), published="2026-11-28T06:00:00+00:00"):
    return {"id": i, "headlines": [f"Headline {i}"], "dek": "Dek.", "published": published, "sources": list(sources), "topic": "Markets"}


def png(w, h):
    """A valid PNG header and IHDR, which is all the audit reads."""
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


class IndexGate(unittest.TestCase):
    def test_an_article_from_one_newsroom_is_not_indexable(self):
        self.assertFalse(site.indexable(art(sources=["Reuters"])))
        self.assertFalse(site.indexable(art(sources=["Reuters", "reuters "])))  # the same newsroom twice is one
        self.assertTrue(site.indexable(art()))

    def test_the_page_says_noindex_and_loses_max_image_preview(self):
        h = site.page("T", "<p>x</p>", path="/s/a/", noindex=True)
        self.assertIn('<meta name="robots" content="noindex">', h)
        self.assertNotIn("max-image-preview", h)
        self.assertIn("max-image-preview:large", site.page("T", "<p>x</p>", path="/s/a/"))

    def test_a_single_source_story_is_in_neither_sitemap(self):
        rows = [art("one", ["Reuters"]), art("two")]
        news = site.news_sitemap(rows, NOW)
        self.assertNotIn("/s/one/", news)
        self.assertIn("/s/two/", news)

    def test_the_story_page_of_a_single_source_is_noindex(self):
        one, two = art("one", ["Reuters"]), art("two")
        with mock.patch.object(site, "CORRECTIONS", {}):
            self.assertIn('content="noindex"', site.story(one, [one, two], cos={}, counts={}))
            self.assertNotIn('content="noindex"', site.story(two, [one, two], cos={}, counts={}))


class NewsSitemap(unittest.TestCase):
    def test_google_news_format(self):
        # https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap
        xml = site.news_sitemap([art("a", published="2026-11-28T06:00:00+00:00")], NOW)
        for tag in ("news:name", "news:language", "news:publication_date", "news:title"):
            self.assertRegex(xml, f"<{tag}>[^<]+</{tag}>")
        self.assertIn("<news:publication_date>2026-11-28T06:00:00Z</news:publication_date>", xml)
        self.assertNotIn("Boardread</news:title>", xml)  # no publication name in the title

    def test_only_the_last_two_days(self):
        old = art("old", published=(NOW - timedelta(hours=49)).isoformat())
        new = art("new", published=(NOW - timedelta(hours=47)).isoformat())
        xml = site.news_sitemap([new, old], NOW)
        self.assertIn("/s/new/", xml)
        self.assertNotIn("/s/old/", xml)


class Lastmod(unittest.TestCase):
    def test_an_entry_without_a_date_has_no_lastmod_tag(self):
        xml = site.urlset([(f"{SITE_URL}/about/", ""), (f"{SITE_URL}/s/a/", "2026-11-28T06:00:00Z")])
        self.assertEqual(xml.count("<lastmod>"), 1)
        self.assertIn("/about/</loc></url>", xml)

    def test_a_correction_moves_the_article_lastmod_and_datemodified(self):
        p = art()
        fix = {"id": "a", "time": "2026-11-28T07:30:00+00:00", "text": "Fixed."}
        with mock.patch.object(site, "CORRECTIONS", {"a": [fix]}):
            self.assertEqual(site.iso(site.modified(p)), "2026-11-28T07:30:00Z")
            self.assertEqual(site.article_ld(p, None)["dateModified"], "2026-11-28T07:30:00Z")
        with mock.patch.object(site, "CORRECTIONS", {}):
            self.assertEqual(site.article_ld(p, None)["dateModified"], site.article_ld(p, None)["datePublished"])


class Discover(unittest.TestCase):
    def test_the_ld_images_are_three_shapes_all_1200_wide(self):
        self.assertEqual([(n, w) for n, w, h in site.LD_CROPS], [("16x9", 1200), ("4x3", 1200), ("1x1", 1200)])
        self.assertEqual([round(w / h, 2) for _, w, h in site.LD_CROPS], [1.78, 1.33, 1.0])
        p = dict(art(), _crops=["16x9", "4x3", "1x1"])
        self.assertEqual(len(site.article_ld(p, None)["image"]), 3)
        self.assertEqual((site.OG_W, site.OG_H), (1200, 630))

    def test_the_audit_fails_a_narrow_image(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "og").mkdir()
            (root / "og" / "a.png").write_bytes(png(800, 450))
            (root / "og" / "b.png").write_bytes(png(1200, 630))
            for name, bad in (("a", True), ("b", False)):
                out = []
                seo.check_image(root, SITE_URL, f"{SITE_URL}/og/{name}.png", "/s/x/", out)
                self.assertEqual(bool(out), bad, out)

    def test_image_size_reads_png_and_jpeg_headers(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "x.png"
            f.write_bytes(png(1200, 675))
            self.assertEqual(seo.image_size(f), (1200, 675))
            j = Path(t) / "x.jpg"
            j.write_bytes(b"\xff\xd8" + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 630, 1200) + b"\0" * 20)
            self.assertEqual(seo.image_size(j), (1200, 630))
            self.assertIsNone(seo.image_size(Path(t) / "none.jpg"))


class AuditExtras(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def errors(self):
        return [m for lv, _, m in seo.audit(self.root, SITE_URL, now=NOW) if lv == "error"]

    def test_search_console_verification_file_is_not_a_page(self):
        (self.root / "google1234.html").write_text("google-site-verification: google1234.html")
        self.assertEqual([e for e in self.errors() if "canonical" in e], [])

    def test_bad_lastmod_and_incomplete_news_entries(self):
        (self.root / "sitemap.xml").write_text(f"<urlset><url><loc>{SITE_URL}/</loc><lastmod>yesterday</lastmod></url></urlset>")
        (self.root / "news-sitemap.xml").write_text(
            f"<urlset><url><loc>{SITE_URL}/s/a/</loc><news:news><news:publication><news:name>B</news:name></news:publication>"
            f"<news:title>T</news:title></news:news></url></urlset>")
        errs = " | ".join(self.errors())
        self.assertIn("lastmod not ISO", errs)
        self.assertIn("without news:language", errs)
        self.assertIn("without news:publication_date", errs)
        (self.root / "sitemap.xml").write_text(f"<urlset><url><loc>{SITE_URL}/</loc><lastmod>2030-01-01T00:00:00Z</lastmod></url></urlset>")
        self.assertIn("lastmod in the future", " | ".join(self.errors()))


class ThinHubs(unittest.TestCase):
    def build_paged(self, n):
        rows = [art(str(i), published=f"2026-11-28T0{i}:00:00+00:00") for i in range(n)]
        sm = []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(site, "CORRECTIONS", {}):
            site.paged(Path(t), "/t/markets/", rows, "Markets", "d", "", "markets", sitemap=sm)
            html = (Path(t) / "t/markets/index.html").read_text()
        return html, sm

    def test_a_hub_under_the_minimum_is_noindex_and_not_in_the_sitemap(self):
        html, sm = self.build_paged(site.MIN_HUB - 1)
        self.assertIn('content="noindex"', html)
        self.assertEqual(sm, [])

    def test_a_hub_at_the_minimum_is_indexed(self):
        html, sm = self.build_paged(site.MIN_HUB)
        self.assertNotIn('content="noindex"', html)
        self.assertEqual(len(sm), 1)

    def test_later_pages_keep_their_own_canonical(self):
        rows = [art(str(i), published=f"2026-11-{10 + i // 2:02d}T0{i % 2}:00:00+00:00") for i in range(site.PER + 3)]
        with tempfile.TemporaryDirectory() as t, mock.patch.object(site, "CORRECTIONS", {}):
            site.paged(Path(t), "/latest/", rows, "Latest", "d", "", "latest")
            two = (Path(t) / "latest/page/2/index.html").read_text()
        self.assertIn(f'<link rel="canonical" href="{SITE_URL}/latest/page/2/">', two)
        self.assertNotIn('content="noindex"', two)


class PreferredSources(unittest.TestCase):
    def test_about_links_google_preferences_with_the_domain(self):
        # https://developers.google.com/search/docs/appearance/preferred-sources: a domain-level site links this URL
        with mock.patch.object(site, "BASE", ""):
            html = site.about_page()
        host = SITE_URL.split("//")[1].split("/")[0]
        self.assertIn(f"https://www.google.com/preferences/source?q={host}", html)
        self.assertNotIn("news.google.com/swg", html)  # the script would be a third-party request the CSP forbids

    def test_a_site_under_a_path_gets_no_link(self):
        with mock.patch.object(site, "BASE", "/news"):
            self.assertNotIn("preferences/source", site.about_page())


if __name__ == "__main__":
    unittest.main()
