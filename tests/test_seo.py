"""The SEO audit, the publisher schema and the analytics switch."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from aidaily import desk, seo, site

SITE = "https://boardread.news"
ARTICLE = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": "Fed holds rates",
           "image": ["https://boardread.news/og/a.jpg"], "datePublished": "2026-11-26T10:00:00Z",
           "author": {"@type": "Organization", "name": "Boardread", "url": "https://boardread.news/about/"},
           "publisher": seo.organization(SITE)}


def html(path, ld=None, extra="", canonical=True):
    head = f'<link rel="canonical" href="{SITE}{path}"><meta property="og:url" content="{SITE}{path}">' if canonical else ""
    block = f'<script type="application/ld+json">{json.dumps(ld)}</script>' if ld else ""
    return f"<!doctype html><html><head>{head}{block}</head><body>{extra}</body></html>"


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def put(self, rel, text):
        f = self.root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)

    def found(self, level="error"):
        return [m for lv, _, m in seo.audit(self.root, SITE) if lv == level]

    def test_a_clean_site_has_no_errors(self):
        self.put("index.html", html("/", extra='<a href="/s/a/">a</a><img src="/x.jpg" width="3" height="2">'))
        self.put("x.jpg", "")
        self.put("s/a/index.html", html("/s/a/", ARTICLE))
        self.put("sitemap.xml", f"<urlset><url><loc>{SITE}/</loc></url><url><loc>{SITE}/s/a/</loc></url></urlset>")
        self.put("robots.txt", f"Sitemap: {SITE}/sitemap.xml\n")
        self.assertEqual(self.found(), [])
        self.assertEqual(self.found("warn"), [])

    def test_old_address_and_foreign_canonical_are_errors(self):
        self.put("index.html", html("/", extra='<a href="https://keremozdemir.de/news/s/a/">old</a>'))
        self.put("t/index.html", html("/t/").replace(SITE + "/t/", "https://example.com/t/", 1))
        errs = self.found()
        self.assertTrue(any("old address" in e for e in errs))
        self.assertTrue(any("canonical outside" in e for e in errs))
        self.assertTrue(any("og:url differs" in e for e in errs))

    def test_missing_canonical_and_broken_internal_link(self):
        self.put("index.html", html("/", canonical=False, extra='<a href="/nope/">x</a>'))
        errs = self.found()
        self.assertIn("no canonical link", errs)
        self.assertTrue(any("missing file: /nope/" in e for e in errs))

    def test_article_schema_rules(self):
        bad = dict(ARTICLE, headline="x" * 111, datePublished="2026-11-26T10:00:00", image=["/og/a.jpg"],
                   author={"name": "Boardread"}, publisher={"name": "Boardread"})
        self.put("s/a/index.html", html("/s/a/", bad))
        errs = " | ".join(self.found())
        for want in ("over 110", "without a timezone", "absolute https", "name and a url", "without a logo"):
            self.assertIn(want, errs)
        self.put("s/a/index.html", html("/s/a/").replace("</head>", '<script type="application/ld+json">{oops</script></head>'))
        self.assertTrue(any("does not parse" in e for e in self.found()))

    def test_sitemaps(self):
        self.put("index.html", html("/"))
        self.put("hidden/index.html", html("/hidden/", extra="").replace("<head>", '<head><meta name="robots" content="noindex">'))
        self.put("sitemap.xml", f"<urlset><url><loc>{SITE}/hidden/</loc></url><url><loc>https://other.org/</loc></url></urlset>")
        old = (datetime.now(timezone.utc) - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.put("news-sitemap.xml", f"<urlset><url><loc>{SITE}/</loc><news:publication_date>{old}</news:publication_date></url></urlset>")
        self.put("robots.txt", f"Sitemap: {SITE}/sitemap.xml\n")
        errs, warns = self.found(), self.found("warn")
        self.assertTrue(any("noindex" in e for e in errs))
        self.assertTrue(any("<loc> outside" in e for e in errs))
        self.assertTrue(any("older than two days" in w for w in warns))
        self.assertTrue(any("news-sitemap.xml" in w for w in warns))

    def test_main_exit_code(self):
        self.put("index.html", html("/", canonical=False))
        self.assertEqual(seo.main(self.root, SITE), 1)
        self.put("index.html", html("/"))
        self.assertEqual(seo.main(self.root, SITE), 0)

    def test_base_path_sites_resolve_links_under_the_base(self):
        base = "https://keremozdemir.de/x"
        self.put("index.html", f'<link rel="canonical" href="{base}/"><a href="/x/s/a/">a</a><a href="/impressum/">i</a>')
        errs = [m for lv, _, m in seo.audit(self.root, base) if lv == "error"]
        self.assertTrue(any("/x/s/a/" in e for e in errs))
        self.assertFalse(any("/impressum/" in e for e in errs))  # outside the base: not this site's file


class Schema(unittest.TestCase):
    def test_organization_points_at_the_standards_pages_and_channels(self):
        org = seo.organization(SITE, accounts=[{"name": "Bluesky", "url": "https://bsky.app/profile/x"}, {"name": "X", "url": ""}])
        self.assertEqual(org["@type"], "NewsMediaOrganization")
        self.assertEqual(org["publishingPrinciples"], f"{SITE}/standards/")
        self.assertEqual(org["logo"]["url"], f"{SITE}/logo.png")
        self.assertEqual(org["sameAs"], ["https://bsky.app/profile/x"])

    def test_article_ld_uses_the_organization(self):
        p = {"id": "a", "headlines": ["H"], "dek": "D", "published": "2026-11-26T10:00:00+00:00", "topic": "Markets"}
        ld = site.article_ld(p, None)
        self.assertEqual(ld["publisher"]["@type"], "NewsMediaOrganization")
        out = []
        seo.check_article(ld, "/s/a/", out)
        self.assertEqual(out, [])


class Analytics(unittest.TestCase):
    def test_off_by_default_and_in_the_shipped_config(self):
        self.assertEqual(seo.analytics({}), ("", ""))
        shipped = json.loads((desk.HERE / "desk.json").read_text())
        self.assertEqual(seo.analytics(shipped), ("", ""))
        self.assertIs(shipped["growth"]["utm"], False)

    def test_rejects_anything_but_a_plain_site_code(self):
        self.assertEqual(seo.analytics({"analytics": {"goatcounter": "evil.com/x"}}), ("", ""))

    def test_on_adds_a_scriptless_pixel_and_its_csp_host(self):
        host, tag = seo.analytics({"analytics": {"goatcounter": "boardread"}})
        self.assertEqual(host, "https://boardread.goatcounter.com")
        t = tag("/s/a/")
        self.assertIn('src="https://boardread.goatcounter.com/count?p=/s/a/"', t)
        self.assertIn('referrerpolicy="no-referrer"', t)
        self.assertNotIn("<script", t)

    def test_page_has_no_third_party_host_while_off_and_the_pixel_when_on(self):
        off = site.page("T", "<p>x</p>", path="/")
        self.assertNotIn("goatcounter", off)
        with mock.patch.dict(desk.CONFIG, {"analytics": {"goatcounter": "boardread"}}):
            on = site.page("T", "<p>x</p>", path="/s/a/")
        self.assertIn("img-src 'self' data: https://boardread.goatcounter.com;", on)
        self.assertIn("count?p=" + site.BASE + "/s/a/", on)


if __name__ == "__main__":
    unittest.main()
