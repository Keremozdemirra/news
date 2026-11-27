import io
import json
import tempfile
import unittest
from pathlib import Path

from aidaily import indexnow

SM = '<urlset><url><loc>https://b.news/</loc></url><url><loc>https://b.news/s/a/</loc></url>{}</urlset>'


class Opener:
    def __init__(self):
        self.reqs = []

    def __call__(self, req, timeout=None):
        self.reqs.append(req)
        r = io.BytesIO(b"")
        r.status = 202
        return r


class IndexNow(unittest.TestCase):
    def test_only_pages_the_live_sitemap_did_not_have(self):
        built = SM.format('<url><loc>https://b.news/s/b/</loc></url>')
        self.assertEqual(indexnow.new_urls(built, SM.format("")), ["https://b.news/s/b/"])
        self.assertEqual(indexnow.new_urls(SM.format(""), SM.format("")), [])

    def test_payload_names_host_key_and_key_file(self):
        o = Opener()
        self.assertEqual(indexnow.ping("https://b.news", ["https://b.news/s/b/"], opener=o), 202)
        body = json.loads(o.reqs[0].data)
        self.assertEqual(body["host"], "b.news")
        self.assertEqual(body["key"], indexnow.KEY)
        self.assertEqual(body["keyLocation"], f"https://b.news/{indexnow.KEY}.txt")
        self.assertEqual(o.reqs[0].full_url, "https://api.indexnow.org/indexnow")

    def test_nothing_new_sends_nothing(self):
        o = Opener()
        self.assertEqual(indexnow.ping("https://b.news", [], opener=o), 0)
        self.assertEqual(o.reqs, [])

    def test_key_file_holds_the_key(self):
        f = Path(__file__).resolve().parent.parent / "assets-site" / f"{indexnow.KEY}.txt"
        self.assertEqual(f.read_text(), indexnow.KEY)

    def test_a_failed_ping_never_fails_the_step(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "sitemap.xml").write_text(SM.format('<url><loc>https://b.news/s/c/</loc></url>'))
            Path(d, "live.xml").write_text(SM.format(""))
            orig = indexnow.ping
            indexnow.ping = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
            try:
                self.assertEqual(indexnow.main(d, str(Path(d, "live.xml")), "https://b.news"), 0)
            finally:
                indexnow.ping = orig


if __name__ == "__main__":
    unittest.main()
