import json
import unittest

from aidaily import feeds

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>OpenAI launches GPT-6 &amp; more</title><link>https://example.com/a</link>
<pubDate>Sun, 27 Sep 2026 10:00:00 +0000</pubDate><description>&lt;p&gt;Body&lt;/p&gt;</description></item>
<item><title></title><link>https://example.com/empty</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Paper</title><link href="https://example.org/p"/><updated>2026-09-27T08:00:00Z</updated></entry>
</feed>"""


class Feeds(unittest.TestCase):
    def test_rss(self):
        out = feeds.parse_xml(RSS, "s")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "OpenAI launches GPT-6 & more")
        self.assertEqual(out[0]["summary"], "Body")
        self.assertEqual(out[0]["published"].hour, 10)

    def test_atom_href_link(self):
        out = feeds.parse_xml(ATOM, "s")
        self.assertEqual(out[0]["url"], "https://example.org/p")

    def test_hn_json(self):
        raw = json.dumps({"hits": [{"title": "Show HN: agent", "url": None, "objectID": "9",
                                    "created_at": "2026-09-27T08:00:00Z", "points": 50, "num_comments": 10}]})
        out = feeds.parse_json(raw.encode(), "hn")
        self.assertEqual(out[0]["url"], "https://news.ycombinator.com/item?id=9")
        self.assertEqual(out[0]["points"], 50)

    def test_reddit_skips_stickied(self):
        raw = json.dumps({"data": {"children": [
            {"data": {"title": "Rules", "stickied": True}},
            {"data": {"title": "Qwen 4 out", "permalink": "/r/x/1", "created_utc": 1790000000, "score": 3}}]}})
        out = feeds.parse_json(raw.encode(), "r")
        self.assertEqual([i["title"] for i in out], ["Qwen 4 out"])

    def test_dead_feed_is_not_fatal(self):
        items, err = feeds.fetch({"id": "x", "url": "http://127.0.0.1:9/none", "type": "rss"})
        self.assertEqual(items, [])
        self.assertTrue(err)


class Gzip(unittest.TestCase):
    def test_unannounced_gzip_is_decoded(self):
        import gzip
        from unittest import mock
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return gzip.compress(RSS)
        with mock.patch("urllib.request.urlopen", return_value=R()):
            items, err = feeds.fetch({"id": "g", "url": "https://x", "type": "rss"})
        self.assertIsNone(err)
        self.assertEqual(len(items), 1)
