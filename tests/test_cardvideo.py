import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import cardvideo as CV
from aidaily import desk, instagram, render
from test_desk import FakeIG, Tmp


class Recorder(instagram.Client):
    """Answers every Graph call from a script and records it; nothing leaves the machine."""

    def __init__(self, status="FINISHED", refuse=None):
        super().__init__(token="t", user_id="me")
        self.calls, self.status, self.refuse, self.n = [], status, refuse, 0

    def call(self, method, path, params=None, versioned=True):
        self.calls.append((method, path, dict(params or {})))
        if self.refuse and self.refuse(path, params or {}):
            raise instagram.IGError(f"{method} {path}: HTTP 400: refused")
        if path.endswith("/media") and method == "POST":
            self.n += 1
            return {"id": f"c{self.n}"}
        if method == "GET" and (params or {}).get("fields") == "status_code":
            kind = "video" if path in self.videos() else "image"
            return {"status_code": self.status if kind == "video" else "FINISHED"}
        if path.endswith("media_publish"):
            return {"id": "m1"}
        return {"permalink": "https://instagram.com/p/x"}

    def videos(self):
        out, n = set(), 0
        for m, p, prm in self.calls:
            if p.endswith("/media") and m == "POST":
                n += 1
                if prm.get("media_type") in ("VIDEO", "REELS"):
                    out.add(f"c{n}")
        return out

    def published(self):
        return any(p.endswith("media_publish") for _, p, _ in self.calls)


class Client(unittest.TestCase):
    def test_carousel_with_a_video_first_child(self):
        c = Recorder()
        media, link = c.post_carousel(["https://x/card.jpg", "https://x/detail.jpg"], "cap", sleep=lambda s: None,
                                      video_first="https://cdn/x/video.mp4", thumb_offset=1600)
        self.assertEqual(media, "m1")
        creates = [prm for m, p, prm in c.calls if p == "me/media" and m == "POST"]
        self.assertEqual(creates[0], {"media_type": "VIDEO", "video_url": "https://cdn/x/video.mp4",
                                      "is_carousel_item": "true", "thumb_offset": "1600"})
        self.assertEqual(creates[1]["image_url"], "https://x/detail.jpg")  # the still card is replaced, never doubled
        self.assertEqual(creates[2]["media_type"], "CAROUSEL")
        self.assertEqual(creates[2]["children"], "c1,c2")

    def test_failed_video_raises_before_any_publish(self):
        c = Recorder(status="ERROR")
        with self.assertRaises(instagram.VideoRejected):
            c.post_carousel(["https://x/card.jpg", "https://x/detail.jpg"], "cap", sleep=lambda s: None, video_first="https://cdn/v.mp4")
        self.assertFalse(c.published())

    def test_reel_sends_cover_and_falls_back_from_trial(self):
        c = Recorder(refuse=lambda path, prm: "trial_params" in prm)
        c.reel("https://cdn/v.mp4", "cap", trial="SS_PERFORMANCE", sleep=lambda s: None, cover_url="https://x/cover.jpg")
        creates = [prm for m, p, prm in c.calls if p == "me/media" and m == "POST"]
        self.assertIn("trial_params", creates[0])
        self.assertNotIn("trial_params", creates[1])
        self.assertEqual(creates[1]["cover_url"], "https://x/cover.jpg")
        self.assertTrue(c.published())

    def test_reel_creation_refused_is_a_video_rejection(self):
        c = Recorder(refuse=lambda path, prm: prm.get("media_type") == "REELS")
        with self.assertRaises(instagram.VideoRejected):
            c.reel("https://cdn/v.mp4", "cap", sleep=lambda s: None)
        self.assertFalse(c.published())


CREDIT = "Photo: Jane Roe, CC BY 4.0, via Wikimedia Commons"


def video(**kw):
    v = {"shape": "card", "file": "video.mp4", "cover": "cover.jpg", "spec": [], "headline": "Lab ships a model",
         "photo_file": "Roe.jpg", "credit": CREDIT}
    v.update(kw)
    return v


class VideoIG(FakeIG):
    def __init__(self, reject=False):
        super().__init__()
        self.calls, self.reject = [], reject

    def post_carousel(self, urls, caption, video_first=None, thumb_offset=None, **kw):
        self.calls.append(("carousel", urls, video_first))
        if video_first and self.reject:
            raise instagram.VideoRejected("container c1: ERROR")
        return super().post_carousel(urls, caption)

    def reel(self, url, caption, share_to_feed=True, trial="", cover_url=None, **kw):
        self.calls.append(("reel", url, cover_url))
        if self.reject:
            raise instagram.VideoRejected("container c1: ERROR")
        return "r1", "https://instagram.com/reel/x"


class Publish(Tmp):
    def post(self, **v):
        return self.write_post("a", photo_file="Roe.jpg", credit=CREDIT, video=video(**v))

    def test_video_card_goes_first_from_jsdelivr(self):
        p = self.post()
        ig = VideoIG()
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "o/r", "DESK_MEDIA_REF": "abc"}):
            self.assertEqual(desk.publish(client=ig), 1)
        kind, urls, first = ig.calls[0]
        self.assertEqual(first, "https://cdn.jsdelivr.net/gh/o/r@abc/a/video.mp4")
        self.assertEqual(len(urls), 2)
        self.assertEqual(json.loads(p.read_text())["status"], "published")

    def test_reel_shape_posts_a_reel_with_its_cover(self):
        self.post(shape="reel")
        ig = VideoIG()
        self.assertEqual(desk.publish(client=ig), 1)
        self.assertEqual(ig.calls[0][0], "reel")
        self.assertTrue(ig.calls[0][2].endswith("/a/cover.jpg"))

    def test_refused_video_publishes_the_stills_in_the_same_run(self):
        p = self.post(shape="reel")
        ig = VideoIG(reject=True)
        self.assertEqual(desk.publish(client=ig), 1)
        self.assertEqual([c[0] for c in ig.calls], ["reel", "carousel"])
        self.assertIsNone(ig.calls[1][2])
        got = json.loads(p.read_text())
        self.assertEqual(got["status"], "published")
        self.assertNotIn("video", got)
        self.assertIn("ERROR", got["video_error"])

    def test_share_alike_photo_never_moves(self):
        p = self.write_post("a", photo_file="Roe.jpg", credit="Photo: Jane Roe, CC BY-SA 4.0, via Wikimedia Commons",
                            video=video(credit="Photo: Jane Roe, CC BY-SA 4.0, via Wikimedia Commons"))
        ig = VideoIG()
        # a ShareAlike photo is held by audit() before any video decision: neither the video nor the stills go out
        self.assertEqual(desk.publish(client=ig), 0)
        self.assertEqual(ig.calls, [])
        self.assertEqual(json.loads(p.read_text())["status"], "held")


class Checks(unittest.TestCase):
    def base(self, **v):
        return {"id": "a", "headlines": ["Lab ships a model"], "photo_file": "Roe.jpg", "credit": CREDIT, "video": video(**v)}

    def test_good_video_passes(self):
        self.assertEqual(desk.video_problems(self.base()), [])

    def test_spec_subject_and_record(self):
        self.assertTrue(desk.video_problems(self.base(spec=["size 1080x1080, not 1080x1350"])))
        self.assertTrue(desk.video_problems(self.base(spec=None)))
        self.assertTrue(desk.video_problems(self.base(headline="Another story")))
        self.assertTrue(desk.video_problems(self.base(photo_file="Other.jpg")))
        self.assertTrue(desk.video_problems(self.base(shape="square")))

    def test_audit_holds_a_video_that_skipped_its_check(self):
        post = self.base(spec=["frame rate 25/1"])
        post.update(topic="Tech", caption="cap")
        self.assertTrue(any(p.startswith("video:") for p in desk.audit(post)))
        desk.check_video(post)
        self.assertNotIn("video", post)
        self.assertFalse(any(p.startswith("video:") for p in desk.audit(post)))


class Shape(Tmp):
    def test_alternate_takes_the_shape_used_less(self):
        with mock.patch.dict(desk.CONFIG, {"video": {"format": "alternate"}}):
            self.assertEqual(desk.video_shape(), "card")
            self.write_post("a", video=video(shape="card"))
            self.assertEqual(desk.video_shape(), "reel")
            self.write_post("b", video=video(shape="reel"))
            self.assertEqual(desk.video_shape(), "card")
        with mock.patch.dict(desk.CONFIG, {"video": {"format": "reel"}}):
            self.assertEqual(desk.video_shape(), "reel")

    def test_daily_cap_counts_queued_and_recent(self):
        self.write_post("a", video=video())
        self.write_post("b", video=video(), status="published", published=desk.now().isoformat())
        self.write_post("c", video=video(), status="published", published="2020-01-01T00:00:00+00:00")
        self.assertEqual(desk.videos_last_24h(), 2)


def story(photo, credit=CREDIT, **kw):
    s = {"headline": "Lab ships a model", "title": "Lab ships a model", "topic": "Tech", "published": "2026-11-27T08:00:00+00:00",
         "outlets": ["Outlet A", "Outlet B"], "source": "Outlet A", "person": "",
         "_assets": {"photo": Path(photo).resolve().as_uri() if photo else "", "credit": credit, "logos": [], "logo_names": [],
                     "logo": "", "backer": "", "kind": "photo", "file": "Roe.jpg"}}
    s.update(kw)
    return s


class Card(unittest.TestCase):
    def test_eligible_needs_photo_file_and_open_licence(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            self.assertEqual(CV.eligible(story(f.name)), "")
            self.assertIn("licence", CV.eligible(story(f.name, credit="Photo: X, CC BY-SA 4.0")))
            self.assertIn("licence", CV.eligible(story(f.name, credit="Photo: X, CC BY-NC 2.0")))
        self.assertIn("missing", CV.eligible(story("/nonexistent/x.jpg")))

    def test_focus_prefers_the_face_agents_point(self):
        self.assertEqual(CV.focus({"focus": [0.3, 0.2]}), (0.3, 0.2))
        self.assertEqual(CV.focus({"_assets": {"focus": {"x": 0.7, "y": 0.4}}}), (0.7, 0.4))
        self.assertEqual(CV.focus({"person": "Jane Roe"}), (0.5, 0.25))
        self.assertEqual(CV.focus({"focus": [3, 9]}), (0.5, 0.5))

    def test_motion_layer_keeps_text_and_drops_photo(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            s = story(f.name)
            html_ = CV.layer_html(s, "card", "head")
            self.assertNotIn(Path(f.name).resolve().as_uri(), html_)
            self.assertIn("Lab ships a model", html_)
            self.assertIn(".c-grad", html_)
            self.assertIn("CC BY 4.0, via Wikimedia Commons. Edited", CV.layer_html(s, "card", "base"))
            self.assertIn("height:1920px", CV.layer_html(s, "reel", "base"))
            # the still card is unchanged: its photo is still in it
            self.assertIn(Path(f.name).resolve().as_uri(), render.T.card(s))

    @unittest.skipUnless(shutil.which("ffmpeg") and Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME),
                         "needs ffmpeg and Chrome")
    def test_render_passes_instagrams_spec_in_both_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "p.jpg"
            # a test pattern stands in for a photo
            render.subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1600x1200",
                                   "-frames:v", "1", str(photo)], check=True)
            for shape in ("card", "reel"):
                out = CV.build(story(photo), Path(tmp) / f"{shape}.mp4", shape, seconds=3.0)
                self.assertEqual(CV.audit_file(out, shape), [])
            self.assertTrue(CV.audit_file(Path(tmp) / "card.mp4", "reel"))  # wrong shape is caught


if __name__ == "__main__":
    unittest.main()
