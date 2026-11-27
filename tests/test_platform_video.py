import json
import os
import urllib.error
import urllib.parse
from unittest import mock

from aidaily import desk, platforms
from test_platforms import Env, Fake, http_error, post

CREDIT = "Photo: A, CC BY 4.0, via Wikimedia Commons"
VIDEO_ON = {"on": True, "per_day": 2, "platforms": {n: True for n in platforms.NAMES}}
VIDEO_URL = "https://cdn.jsdelivr.net/gh/o/r@abc/2026-11-26-1446-1/video.mp4"


def vpost(**kw):
    p = post(**kw)
    p.setdefault("video", {"shape": "card", "file": "video.mp4", "cover": "cover.jpg", "spec": [], "headline": p["headlines"][0],
                           "photo_file": p["photo_file"], "credit": p["credit"]})
    return p


def body(req):
    raw = req.data or b""
    try:
        return json.loads(raw)
    except ValueError:
        return dict(urllib.parse.parse_qsl(raw.decode()))


class VideoEnv(Env):
    def setUp(self):
        super().setUp()
        for p in (mock.patch.dict(desk.CONFIG, {"video": VIDEO_ON}),
                  mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "o/r", "DESK_MEDIA_REF": "abc", "DESK_VIDEO_BASE": ""})):
            p.start()
            self.patches.append(p)


class ThreadsVideo(VideoEnv):
    def opener(self, status="FINISHED"):
        def route(req):
            url = req.full_url
            if url.endswith("/threads") and req.data:
                return {"id": "c-video" if b"VIDEO" in req.data else "c-image"}
            if "fields=status" in url:
                return {"status": status if "c-video" in url else "FINISHED"}
            if "threads_publish" in url:
                return {"id": "m1"}
            return {"permalink": "https://threads.net/p/1"}
        return Fake({"graph.threads.com": route})

    def test_a_video_container_from_jsdelivr(self):
        f = self.opener()
        got = platforms.Threads(opener=f, sleep=lambda s: None).post(vpost())
        create = body(f.seen[0])
        self.assertEqual(create["media_type"], "VIDEO")
        self.assertEqual(create["video_url"], VIDEO_URL)
        self.assertTrue(got["video"])
        self.assertEqual(got["id"], "m1")

    def test_a_failed_video_falls_back_to_the_card_in_the_same_send(self):
        f = self.opener(status="ERROR")
        got = platforms.Threads(opener=f, sleep=lambda s: None).post(vpost())
        self.assertIn("ERROR", got["video_error"])
        self.assertNotIn("video", got)
        published = [r for r in f.seen if "threads_publish" in r.full_url]
        self.assertEqual(len(published), 2)  # the image post and its sources reply; the video was never published
        self.assertIn(b"c-image", published[0].data)

    def test_switched_off_or_held_means_stills(self):
        f = self.opener()
        with mock.patch.dict(desk.CONFIG, {"video": {**VIDEO_ON, "platforms": {"threads": False}}}):
            platforms.Threads(opener=f, sleep=lambda s: None).post(vpost())
        self.assertEqual(body(f.seen[0])["media_type"], "IMAGE")
        f = self.opener()
        sa = "Photo: A, CC BY-SA 4.0, via Wikimedia Commons"
        platforms.Threads(opener=f, sleep=lambda s: None).post(vpost(credit=sa))
        self.assertEqual(body(f.seen[0])["media_type"], "IMAGE")


class FacebookVideo(VideoEnv):
    def routes(self, video):
        return Fake({"me/accounts": http_error(400, "{}"), "/me?": {"id": "111", "name": "Boardread", "category": "Media"},
                     "graph-video.facebook.com": video, "/feed": {"id": "111_2"}})

    def test_page_video_from_file_url(self):
        f = self.routes({"id": "v9"})
        got = platforms.Facebook(opener=f).post(vpost())
        req = next(r for r in f.seen if "graph-video" in r.full_url)
        self.assertIn("/111/videos", req.full_url)
        b = body(req)
        self.assertEqual(b["file_url"], VIDEO_URL)
        self.assertIn(desk.story_url("2026-11-26-1446-1"), b["description"])
        self.assertEqual(got["url"], "https://www.facebook.com/111/videos/v9")

    def test_refused_video_becomes_the_link_post(self):
        got = platforms.Facebook(opener=self.routes(http_error(400, '{"error": {"message": "bad video"}}'))).post(vpost())
        self.assertEqual(got["id"], "111_2")
        self.assertIn("bad video", got["video_error"])

    def test_a_network_error_is_not_a_refusal(self):
        with self.assertRaises(platforms.PlatformError):
            platforms.Facebook(opener=self.routes(urllib.error.URLError("timed out"))).post(vpost())


class TelegramVideo(VideoEnv):
    def test_send_video_by_url_with_the_caption(self):
        f = Fake({"sendVideo": {"ok": True, "result": {"message_id": 5, "chat": {"username": "chan"}}}})
        got = platforms.Telegram(opener=f).post(vpost())
        b = body(f.seen[0])
        self.assertEqual(b["video"], VIDEO_URL)
        self.assertTrue(b["cover"].endswith("/cover.jpg"))
        self.assertTrue(b["supports_streaming"])
        self.assertIn("<b>", b["caption"])
        self.assertEqual(got["url"], "https://t.me/chan/5")

    def test_refused_video_sends_the_photo(self):
        f = Fake({"sendVideo": http_error(400, '{"ok": false, "description": "failed to get HTTP URL content"}'),
                  "sendPhoto": {"ok": True, "result": {"message_id": 6, "chat": {"username": "chan"}}}})
        got = platforms.Telegram(opener=f).post(vpost())
        self.assertEqual(got["id"], "6")
        self.assertIn("HTTP URL content", got["video_error"])


class BlueskyVideo(VideoEnv):
    def opener(self, job_state="JOB_STATE_COMPLETED"):
        blob = {"$type": "blob", "ref": {"$link": "bafy"}, "mimeType": "video/mp4", "size": 10}
        return Fake({
            "createSession": {"accessJwt": "jwt", "did": "did:plc:me", "handle": "me.bsky.social",
                              "didDoc": {"service": [{"id": "#atproto_pds", "serviceEndpoint": "https://pds.example.host"}]}},
            "getServiceAuth": {"token": "svc"},
            VIDEO_URL: b"mp4bytes",
            "uploadVideo": {"jobId": "j1", "state": "JOB_STATE_RUNNING"},
            "getJobStatus": {"jobStatus": {"jobId": "j1", "state": job_state,
                                           **({"blob": blob} if job_state == "JOB_STATE_COMPLETED" else {"error": "bad"})}},
            "/og/": b"jpg", "uploadBlob": {"blob": {"ref": "thumb"}},
            "createRecord": {"uri": "at://did:plc:me/app.bsky.feed.post/r1"}})

    def test_video_service_then_a_post_with_a_link_facet(self):
        f = self.opener()
        got = platforms.Bluesky(opener=f, sleep=lambda s: None).post(vpost())
        auth = next(r for r in f.seen if "getServiceAuth" in r.full_url)
        self.assertIn("aud=did%3Aweb%3Apds.example.host", auth.full_url)
        up = next(r for r in f.seen if "uploadVideo" in r.full_url)
        self.assertEqual(up.headers["Authorization"], "Bearer svc")
        rec = body(f.seen[-1])["record"]
        self.assertEqual(rec["embed"]["$type"], "app.bsky.embed.video")
        self.assertEqual(rec["embed"]["aspectRatio"], {"width": 1080, "height": 1350})
        url = desk.story_url("2026-11-26-1446-1", "bluesky")
        idx = rec["facets"][0]["index"]
        self.assertEqual(rec["text"].encode()[idx["byteStart"]:idx["byteEnd"]].decode(), url)
        self.assertLessEqual(len(rec["text"]), 300)
        self.assertTrue(got["video"])

    def test_failed_job_posts_the_link_card(self):
        f = self.opener("JOB_STATE_FAILED")
        got = platforms.Bluesky(opener=f, sleep=lambda s: None).post(vpost())
        self.assertEqual(body(f.seen[-1])["record"]["embed"]["$type"], "app.bsky.embed.external")
        self.assertIn("bad", got["video_error"])

    def test_find_sees_a_video_post_by_its_link(self):
        url = desk.story_url("2026-11-26-1446-1")
        feed = {"feed": [{"post": {"uri": "at://x/app.bsky.feed.post/r9", "record": {
            "text": "x", "facets": [{"features": [{"$type": "app.bsky.richtext.facet#link", "uri": url + "?utm_source=bluesky"}]}],
            "embed": {"$type": "app.bsky.embed.video"}}}}]}
        live = platforms.Bluesky(opener=Fake({"getAuthorFeed": feed})).find(vpost())
        self.assertTrue(live["url"].endswith("/post/r9"))


class Render(VideoEnv):
    def test_videos_render_during_a_block_only_for_the_lead_path(self):
        with mock.patch.object(desk, "lead_active", return_value=True):
            self.assertTrue(desk.video_elsewhere())
            with mock.patch.dict(desk.CONFIG, {"video": {**VIDEO_ON, "platforms": {}}}):
                self.assertFalse(desk.video_elsewhere())
        with mock.patch.object(desk, "lead_active", return_value=False):
            self.assertFalse(desk.video_elsewhere())
