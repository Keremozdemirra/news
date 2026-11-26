import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import desk, platforms

SECRETS = {"THREADS_TOKEN": "tt-secret", "THREADS_USER_ID": "u1", "FB_PAGE_TOKEN": "fb-secret", "FB_PAGE_ID": "111",
           "BSKY_HANDLE": "me.bsky.social", "BSKY_APP_PASSWORD": "app-pass-secret", "TG_BOT_TOKEN": "tg-secret", "TG_CHANNEL": "@chan"}


class Resp:
    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.data


class Fake:
    """An opener that answers by URL substring and records every request."""
    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def __call__(self, req, timeout=None, context=None):
        self.seen.append(req)
        for key, out in self.routes.items():
            if key in req.full_url:
                if isinstance(out, Exception):
                    raise out
                return Resp(out(req) if callable(out) else out)
        raise AssertionError(f"unexpected {req.full_url}")


def post(**kw):
    p = {"id": "2026-11-26-1446-1", "created": desk.now().isoformat(), "status": "published", "cards": ["card.jpg", "detail.jpg"],
         "headlines": ["Denny's reshares Nvidia origin story after Jensen Huang's return"], "topic": "Business",
         "dek": "The chain says it reinstalled a plaque at the booth where Nvidia's three founders first met.",
         "body": "Denny's used Jensen Huang's return to Nvidia to reshare its role in the company's origin story.",
         "caption": "x\n\nReported by CNBC. Written by AI.\n\nWant the sources? Comment SOURCE"}
    p.update(kw)
    return p


def http_error(code, body):
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(body.encode()))


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [mock.patch.object(desk, "QUEUE", root / "queue"), mock.patch.object(desk, "STATE", root / "state"),
                        mock.patch.dict(os.environ, {**SECRETS, "DESK_MEDIA_BASE": "https://raw.example/r/media"}),
                        mock.patch.dict(desk.CONFIG, {"platforms": {n: True for n in platforms.NAMES}})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def stored(self, p):
        path = desk.QUEUE / p["id"] / "post.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(p))
        return path


class Text(Env):
    def test_threads_within_500_bytes_with_story_link_and_ai_note(self):
        t = platforms.threads_text(post(dek="word " * 200))
        self.assertLessEqual(len(t.encode()), 500)
        self.assertTrue(t.endswith("Written by AI. Sources: https://keremozdemir.de/news/s/2026-11-26-1446-1/"))
        self.assertNotIn("SOURCE ", t)
        self.assertNotIn("#", t)

    def test_threads_counts_emoji_by_bytes(self):
        t = platforms.threads_text(post(dek="\U0001F600" * 200))
        self.assertLessEqual(len(t.encode()), 500)

    def test_ai_note_only_where_instagram_has_it(self):
        self.assertNotIn("Written by AI", platforms.threads_text(post(caption="plain")))

    def test_threads_one_tag_clean(self):
        self.assertEqual(platforms.threads_tag(post(topic="Markets")), "markets")

    def test_bluesky_300_and_link_facet_points_at_the_link(self):
        text, facets = platforms.bluesky_text(post(dek="word " * 200))
        self.assertLessEqual(len(text), 300)
        i = facets[0]["index"]
        self.assertEqual(text.encode()[i["byteStart"]:i["byteEnd"]].decode(), "keremozdemir.de/news/s/2026-11-26-1446-1/")
        self.assertEqual(facets[0]["features"][0]["uri"], "https://keremozdemir.de/news/s/2026-11-26-1446-1/")

    def test_bluesky_offsets_are_bytes_after_non_ascii(self):
        text, facets = platforms.bluesky_text(post(headlines=["Zürich éè \U0001F600 bank"]))
        i = facets[0]["index"]
        self.assertTrue(text.encode()[i["byteStart"]:i["byteEnd"]].decode().startswith("keremozdemir.de"))

    def test_telegram_caption_1024(self):
        self.assertLessEqual(len(platforms.telegram_caption(post(body="word " * 500))), 1024)

    def test_overlong_headline_is_cut_but_link_stays(self):
        t = platforms.threads_text(post(headlines=["long " * 200]))
        self.assertLessEqual(len(t.encode()), 500)
        self.assertIn("/news/s/", t)


class Clients(Env):
    def test_missing_secrets_raise_missing(self):
        with mock.patch.dict(os.environ, {"BSKY_APP_PASSWORD": ""}):
            with self.assertRaises(platforms.Missing):
                platforms.Bluesky()

    def test_threads_carousel_flow(self):
        calls = []

        def out(req):
            calls.append(req.full_url.split("/v1.0/")[1].split("?")[0])
            if "threads_publish" in req.full_url:
                return {"id": "m9"}
            if req.get_method() == "GET":
                return {"status": "FINISHED", "permalink": "https://www.threads.com/@x/post/abc"} if "m9" in req.full_url \
                    else {"status": "FINISHED"}
            return {"id": f"c{len(calls)}"}
        fake = Fake({"/v1.0/": out})
        got = platforms.Threads(opener=fake, sleep=lambda s: None).post(post())
        self.assertEqual(got, {"id": "m9", "url": "https://www.threads.com/@x/post/abc"})
        parent = [r for r in fake.seen if b"CAROUSEL" in (r.data or b"")][0].data.decode()
        self.assertIn("children=c1%2Cc2", parent)
        self.assertIn("topic_tag=business", parent)
        self.assertNotIn("is_made_with_ai", parent)

    def test_facebook_attaches_unpublished_photos(self):
        n = []

        def out(req):
            n.append(req.data.decode())
            return {"id": "ph1"} if "/photos" in req.full_url else {"id": "111_99"}
        fake = Fake({"me/accounts": {"data": [{"id": "111", "name": "Boardread", "access_token": "page-tok"}]}, "/111/": out})
        got = platforms.Facebook(opener=fake).post(post())
        self.assertEqual(got["url"], "https://www.facebook.com/111_99")
        # the stored system-user token only reads the Page; the posts go out with the Page's own token
        self.assertIn("access_token=page-tok", n[0])
        self.assertIn("published=false", n[0])
        self.assertIn("attached_media%5B1%5D", n[2])

    def test_facebook_placeholder_page_id_is_read_from_the_token(self):
        import os
        old = os.environ.get("FB_PAGE_ID")
        os.environ["FB_PAGE_ID"] = "BURAYA_ID"
        try:
            fake = Fake({"me/accounts": {"data": [{"id": "777", "name": "Boardread", "access_token": "pt"}]},
                         "/777/": lambda r: {"id": "ph"} if "/photos" in r.full_url else {"id": "777_1"}})
            got = platforms.Facebook(opener=fake).post(post())
            self.assertEqual(got["id"], "777_1")
        finally:
            os.environ["FB_PAGE_ID"] = old

    def test_facebook_never_posts_with_a_personal_token(self):
        # a user token that manages no Page must not post to the person's own profile
        fake = Fake({"me/accounts": {"data": []}})
        with self.assertRaises(platforms.PlatformError):
            platforms.Facebook(opener=fake).post(post())
        self.assertFalse([r for r in fake.seen if "/feed" in r.full_url or "/photos" in r.full_url])

    def test_facebook_page_token_used_as_is_only_for_a_page(self):
        fake = Fake({"me/accounts": http_error(400, "nonexisting edge accounts"),
                     "/me?": {"id": "111", "name": "Boardread", "category": "News & media website"},
                     "/111/": lambda r: {"id": "ph"} if "/photos" in r.full_url else {"id": "111_5"}})
        self.assertEqual(platforms.Facebook(opener=fake).post(post())["id"], "111_5")
        person = Fake({"me/accounts": http_error(400, "x"), "/me?": {"id": "9", "name": "Someone"}})
        with self.assertRaises(platforms.PlatformError):
            platforms.Facebook(opener=person).post(post())

    def test_bluesky_flow_and_oversize_second_image_dropped(self):
        small, big = b"j" * 1000, b"j" * 1_000_001
        images = iter([small, big])
        fake = Fake({
            "createSession": {"accessJwt": "jwt", "did": "did:plc:z"},
            "raw.example": lambda r: next(images),
            "uploadBlob": {"blob": {"$type": "blob", "ref": {"$link": "b"}, "mimeType": "image/jpeg", "size": 1000}},
            "createRecord": {"uri": "at://did:plc:z/app.bsky.feed.post/3kabc", "cid": "c"}})
        got = platforms.Bluesky(opener=fake).post(post())
        self.assertEqual(got["url"], "https://bsky.app/profile/me.bsky.social/post/3kabc")
        rec = json.loads([r for r in fake.seen if "createRecord" in r.full_url][0].data)["record"]
        self.assertEqual(len(rec["embed"]["images"]), 1)
        self.assertLessEqual(len(rec["text"]), 300)

    def test_bluesky_oversize_card_fails_without_posting(self):
        fake = Fake({"createSession": {"accessJwt": "j", "did": "d"}, "raw.example": b"j" * 1_000_001})
        with self.assertRaises(platforms.PlatformError):
            platforms.Bluesky(opener=fake).post(post())
        self.assertFalse([r for r in fake.seen if "createRecord" in r.full_url])

    def test_telegram_album_caption_on_first_photo(self):
        fake = Fake({"sendMediaGroup": {"ok": True, "result": [{"message_id": 7, "chat": {"username": "chan"}}, {"message_id": 8}]}})
        got = platforms.Telegram(opener=fake).post(post())
        self.assertEqual(got, {"id": "7", "url": "https://t.me/chan/7"})
        media = json.loads(fake.seen[0].data)["media"]
        self.assertIn("caption", media[0])
        self.assertNotIn("caption", media[1])

    def test_errors_never_carry_secrets(self):
        fake = Fake({"me/accounts": {"data": [{"id": "111", "name": "Boardread", "access_token": "page-secret"}]},
                     "/photos": http_error(400, "bad token fb-secret here and page-secret")})
        with self.assertRaises(platforms.PlatformError) as cm:
            platforms.Facebook(opener=fake).post(post())
        self.assertNotIn("fb-secret", str(cm.exception))
        self.assertNotIn("page-secret", str(cm.exception))
        fake = Fake({"sendMediaGroup": {"ok": False, "description": "tg-secret"}})
        with self.assertRaises(platforms.PlatformError) as cm:
            platforms.Telegram(opener=fake).post(post())
        self.assertNotIn("tg-secret", str(cm.exception))


class Boom:
    def __init__(self, msg):
        self.msg = msg

    def post(self, p):
        raise platforms.PlatformError(self.msg)


class Good:
    def __init__(self, name):
        self.name = name
        self.sent = 0

    def post(self, p):
        self.sent += 1
        return {"id": f"{self.name}1", "url": f"https://{self.name}/1"}


class CrossPost(Env):
    def run_cross(self, p, **factories):
        path = self.stored(p)
        fs = {n: (lambda n=n: Good(n)) for n in platforms.NAMES}
        fs.update(factories)
        desk.cross_post(p, path, fs)
        return json.loads(path.read_text())

    def test_desk_json_names_every_platform_with_a_switch(self):
        # each platform is switched on by hand once its account is connected, so only the shape is fixed here
        shipped = json.loads((Path(desk.__file__).parent.parent / "desk.json").read_text())["platforms"]
        self.assertEqual(set(shipped), set(platforms.NAMES))
        self.assertTrue(all(isinstance(v, bool) for v in shipped.values()))

    def test_disabled_platform_is_not_called(self):
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}):
            got = self.run_cross(post(), threads=lambda: self.fail("called"))
        self.assertEqual(list(got["platforms"]), ["bluesky"])

    def test_results_stored_and_never_posted_twice(self):
        p = post()
        got = self.run_cross(p)
        self.assertEqual(set(got["platforms"]), set(platforms.NAMES))
        self.assertEqual(got["platforms"]["bluesky"]["url"], "https://bluesky/1")
        self.assertIn("at", got["platforms"]["bluesky"])
        again = Good("bluesky")
        self.run_cross(got, bluesky=lambda: again)
        self.assertEqual(again.sent, 0)

    def test_missing_secrets_skip_silently(self):
        def missing():
            raise platforms.Missing("X")
        got = self.run_cross(post(), threads=missing)
        self.assertNotIn("threads", got["platforms"])
        self.assertIn("bluesky", got["platforms"])

    def test_error_in_one_platform_does_not_stop_the_rest_and_is_not_retried(self):
        got = self.run_cross(post(), facebook=lambda: Boom("HTTP 500: oops"))
        self.assertNotIn("id", got["platforms"]["facebook"])
        self.assertIn("attempted", got["platforms"]["facebook"])
        self.assertIn("id", got["platforms"]["telegram"])
        retry = Good("facebook")
        self.run_cross(got, facebook=lambda: retry)
        self.assertEqual(retry.sent, 0)

    def test_marker_saved_before_the_call(self):
        p = post()
        path = self.stored(p)
        seen = {}

        class Peek:
            def post(self_, q):
                seen.update(json.loads(path.read_text())["platforms"]["bluesky"])
                return {"id": "1", "url": ""}
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}):
            desk.cross_post(p, path, {"bluesky": Peek})
        self.assertIn("attempted", seen)

    def test_block_sets_24h_cooldown_for_that_platform_only(self):
        got = self.run_cross(post(), threads=lambda: Boom('HTTP 429: {"error":{"code":4}}'))
        self.assertTrue(desk.platform_cooldown("threads"))
        self.assertIsNone(desk.platform_cooldown("bluesky"))
        self.assertLess(desk.platform_cooldown("threads") - desk.now(), timedelta(hours=24, seconds=5))
        called = Good("threads")
        self.run_cross(post(id="next"), threads=lambda: called)
        self.assertEqual(called.sent, 0)

    def test_cooldown_expires(self):
        desk._save(desk.STATE / "cooldown-threads.json", {"until": (desk.now() - timedelta(minutes=1)).isoformat()})
        self.assertIsNone(desk.platform_cooldown("threads"))


class Isolation(Env):
    def test_cross_post_crash_never_reaches_instagram(self):
        p = post()
        path = self.stored(p)
        with mock.patch.object(desk, "cross_post", side_effect=RuntimeError("boom")):
            desk._cross_post(p, path)  # must not raise

    def test_publish_cross_posts_after_instagram_and_keeps_it_published(self):
        p = post(status="queued", publish_after=(desk.now() - timedelta(minutes=1)).isoformat())
        path = self.stored(p)

        class IG:
            def recent_media(self, limit=25):
                return []

            def post_carousel(self, urls, caption):
                return "m1", "https://instagram.com/p/x"
        bsky = Good("bluesky")
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}), \
             mock.patch.dict(platforms.CLIENTS, {"bluesky": lambda: bsky}), \
             mock.patch.object(desk, "PAUSED", Path(self.tmp.name) / "PAUSED"):
            self.assertEqual(desk.publish(client=IG()), 1)
        got = json.loads(path.read_text())
        self.assertEqual(got["status"], "published")
        self.assertEqual(got["platforms"]["bluesky"]["id"], "bluesky1")
        self.assertEqual(bsky.sent, 1)


if __name__ == "__main__":
    unittest.main()
