"""The feed layout family: which layout a story gets, that no two posts in a row share one, and that every rendered
layout keeps its text inside the 4:5 safe area."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import desk, render
from aidaily import feedlayouts as FL
from aidaily import templates as T

HAVE = shutil.which("ffmpeg") and (Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME))
CREDIT = "Photo: A. Author, CC BY 4.0, via Wikimedia Commons"
FACTORY = "Industrial production line operating in a large modern factory.jpg"  # a vetted generic scene (scenes.json)


def shot(uri, f="A.jpg"):
    return {"uri": uri, "credit": CREDIT, "file": f}


def story(headline, photo="", kind="scene", extras=None, **kw):
    s = {"title": headline, "headline": headline, "topic": "World", "category": "news", "source": "Reuters",
         "outlets": ["Reuters"], "timeline": [0], "published": "2026-11-27T10:00:00+00:00",
         "_assets": {"photo": photo, "credit": CREDIT if photo else "", "file": "Own.jpg" if photo else "", "kind": kind,
                     "logo": "", "backer": "", "logos": [], "logo_names": [], "alt": "", "ticker": None},
         "_extras": extras or {"portrait": None, "scene": None, "pair": []}}
    s.update(kw)
    return s


class Names(unittest.TestCase):
    def test_a_thing_named_after_a_person_is_not_the_person(self):
        self.assertEqual(FL.people_named({"headline": "Trump Tower planned for Hanoi, sources say"}), [])

    def test_spellings_and_order(self):
        got = FL.people_named({"headline": "Trump says he asked Putin to pull back", "person": "Donald Trump"})
        self.assertEqual([n for n, _ in got], ["Donald Trump", "Vladimir Putin"])
        got = FL.people_named({"headline": "Zelenskyy compares Trump to an appeaser", "person": "Volodymyr Zelenskyy"})
        self.assertEqual([n for n, _ in got], ["Volodymyr Zelenskyy", "Donald Trump"])  # not Zelensky a second time

    def test_a_shared_surname_needs_the_full_name_unless_it_is_the_story_person(self):
        self.assertEqual(FL.people_named({"headline": "Duterte's ICC trial set to start"}), [])
        self.assertEqual(FL.people_named({"headline": "Duterte's ICC trial set to start", "person": "Rodrigo Duterte"})[0][0],
                         "Rodrigo Duterte")


class Choice(unittest.TestCase):
    def test_fits_follow_what_the_photos_support(self):
        # a generic archive scene does not fit the story: photo-free cards only
        generic = story("Fed holds rates", "file:///x.jpg", "scene")
        generic["_assets"]["file"] = FACTORY
        self.assertEqual(FL.fits(generic, fetch=False), ["type", "brief"])
        self.assertEqual(FL.fits(story("Nvidia opens a plant", "file:///x.jpg", "company"), fetch=False), ["photo", "type"])
        pair = [("Donald Trump", shot("file:///a.jpg", "A.jpg")), ("Vladimir Putin", shot("file:///b.jpg", "B.jpg"))]
        s = story("Trump says he asked Putin to pull back", "file:///x.jpg", extras={"portrait": None, "scene": None, "pair": pair})
        self.assertEqual(FL.fits(s, fetch=False)[0], "split")
        place = {"portrait": shot("file:///p.jpg", "P.jpg"), "scene": shot("file:///s.jpg", "S.jpg"), "pair": []}
        self.assertEqual(FL.fits(story("Musk pledges shares", "file:///x.jpg", "company", place), fetch=False)[0], "place")

    def test_a_photo_that_does_not_fit_never_reaches_the_card(self):
        """2026-11-27: a factory floor ran small on 'Canada's Supreme Court largely upholds Quebec's religious symbols
        ban'. A topic-picked archive scene is 'low' and the card shows no photo and credits none."""
        s = story("Canada's Supreme Court largely upholds Quebec's religious symbols ban", "file:///x.jpg", "scene",
                  dek="The court said the province may keep the law.", topic="Politics")
        s["_assets"]["file"] = FACTORY
        self.assertEqual(FL.photo_fit(s), "low")
        for name in ("type", "brief"):
            self.assertNotIn("file:///x.jpg", FL.html(s, name))
            self.assertEqual(FL.credits(s, name), [])
        self.assertNotIn("photo", FL.fits(s, fetch=False))
        s["_assets"]["kind"] = "person"
        self.assertEqual(FL.photo_fit(s), "high")

    def test_type_fills_the_card(self):
        short, long = "Fed holds rates", "Canada's Supreme Court largely upholds Quebec's religious symbols ban after a long fight"
        self.assertGreater(FL.fill_size(short, 936, 700), FL.fill_size(long, 936, 700))
        self.assertGreaterEqual(FL.fill_size(long, 936, 700), 90)

    def test_number_only_with_a_checkable_money_or_share_figure(self):
        s = story("France enters recession after GDP falls 0.2% in third quarter", "file:///x.jpg", figure="0.2%")
        self.assertIn("number", FL.fits(s, fetch=False))
        s = story("Calvert-Lewin signs new Leeds contract until 2029", "file:///x.jpg", figure="2029")
        self.assertNotIn("number", FL.fits(s, fetch=False))  # a year at 300 px says nothing

    def test_never_the_same_layout_twice_in_a_row(self):
        stories = [story("Fed holds rates", "file:///x.jpg", "scene"),
                   story("Nvidia opens a plant", "file:///x.jpg", "company"),
                   story("France enters recession after GDP falls 0.2%", "file:///x.jpg", figure="0.2%"),
                   story("Nvidia opens a second plant", "file:///x.jpg", "company")] * 3
        prev, seen = "", []
        for s in stories:
            prev = FL.choose(s, prev, fetch=False)
            seen.append(prev)
        self.assertTrue(all(a != b for a, b in zip(seen, seen[1:])), seen)
        self.assertGreaterEqual(len(set(seen)), 3)

    def test_the_queue_carries_the_last_layout_forward_per_tier(self):
        rows = [({"tier": "instagram", "status": "published", "layout": "split", "publish_after": "2026-11-27T10:00:00+00:00"}, None),
                ({"tier": "instagram", "status": "queued", "layout": "type", "publish_after": "2026-11-27T12:00:00+00:00"}, None),
                ({"tier": "instagram", "kind": "story", "status": "queued", "publish_after": "2026-11-27T13:00:00+00:00"}, None),
                ({"tier": "web", "status": "web", "created": "2026-11-27T11:00:00+00:00"}, None)]
        with mock.patch.object(desk, "posts", return_value=rows):
            self.assertEqual(desk._last_layout("instagram"), "type")
            self.assertEqual(desk._last_layout("web"), "photo")  # before the layouts: the full-photo card

    def test_the_audit_holds_a_card_photo_without_credit_or_of_someone_unnamed(self):
        post = {"id": "a", "headlines": ["Trump says he asked Putin to pull back"], "layout": "split",
                "photos": [{"file": "A.jpg", "credit": CREDIT, "name": "Donald Trump"},
                           {"file": "B.jpg", "credit": "", "name": "Kim Jong Un"}]}
        problems = " | ".join(desk.audit(post))
        self.assertIn("'B.jpg' without a credit line", problems)
        self.assertIn("card shows Kim Jong Un", problems)
        self.assertNotIn("card shows Donald Trump", problems)


SAFE = """<script>window.addEventListener('load',()=>setTimeout(()=>{const r=[...document.querySelectorAll(
'[data-text],[data-credit],h1,[data-portrait]')].map(e=>{const b=e.getBoundingClientRect();return [e.tagName,b.left,b.top,b.right,b.bottom]});
document.body.setAttribute('data-rects',JSON.stringify(r))},300))</script></body>"""


@unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
class SafeArea(unittest.TestCase):
    def rects(self, page, tmp):
        f = Path(tmp) / "p.html"
        f.write_text(page.replace("</body>", SAFE, 1))
        with tempfile.TemporaryDirectory() as profile:
            dom = subprocess.run([render.CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                                  "--window-size=1080,1350", "--virtual-time-budget=4000", "--dump-dom", f.as_uri()],
                                 capture_output=True, text=True, timeout=60).stdout
        m = re.search(r'data-rects="([^"]+)"', dom)
        self.assertIsNotNone(m, "page did not report its text boxes")
        return json.loads(m.group(1).replace("&quot;", '"'))

    def test_every_layout_keeps_text_inside_the_safe_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            uris = []
            for i, size in enumerate(("1600x1200", "900x1200")):
                p = Path(tmp) / f"{i}.jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={size}", "-frames:v", "1",
                                str(p)], check=True)
                uris.append(p.as_uri())
            long = "Trump says he asked Putin to pull back all military aggression against Europe after talks"
            pair = [("Donald Trump", shot(uris[1], "A.jpg")), ("Vladimir Putin", shot(uris[1], "B.jpg"))]
            extras = {"portrait": shot(uris[1], "P.jpg"), "scene": shot(uris[0], "S.jpg"), "pair": pair}
            s = story(long, uris[0], "person", extras, person="Donald Trump", figure="$387M",
                      dek="The retailers booked $387 million in refunds.")
            with mock.patch.object(T, "domain", return_value="boardread.news"):
                for name in FL.NAMES:
                    s["_assets"]["kind"] = "company"
                    for box in self.rects(FL.html(s, name), tmp):
                        tag, x1, y1, x2, y2 = box
                        with self.subTest(layout=name, element=tag):
                            self.assertGreaterEqual(x1, FL.FEED_SAFE - 1)
                            self.assertLessEqual(x2, 1080 - FL.FEED_SAFE + 1)
                            self.assertGreaterEqual(y1, FL.FEED_SAFE_Y - 1)
                            self.assertLessEqual(y2, 1350 - FL.FEED_SAFE_Y + 1)


if __name__ == "__main__":
    unittest.main()
