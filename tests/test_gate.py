"""The visual gate on known-bad pages: each fails for its own reason, and a good card passes."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import gate, render
from aidaily import templates as T

HAVE = shutil.which("ffmpeg") and (Path(render.CHROME).exists() if render.CHROME.startswith("/") else shutil.which(render.CHROME))


def page(body, w=1080, h=1350, bg="#fff"):
    return (T.head() + f'<div style="position:relative;width:{w}px;height:{h}px;overflow:hidden;background:{bg};'
            f"font-family:'Libre Franklin',sans-serif\">{body}</div></body></html>")


FILLED = ''.join(f'<div style="position:absolute;left:72px;top:{72 + i * 100}px;font-size:60px">Line {i} of the report</div>' for i in range(12))


@unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def shot(self, html, fmt="feed"):
        png = self.dir / "p.png"
        w, h = gate.size(fmt)
        render.shoot(html, png, w, h)
        return png

    def test_a_good_card_passes(self):
        html = page(FILLED)
        self.assertEqual(gate.check(html, "feed", self.shot(html)), [])

    def test_text_in_the_slide_counter_zone(self):
        """The OpenAI detail slide put its logo under Instagram's 2/2 pill (2026-11-27)."""
        html = page(FILLED + '<div style="position:absolute;right:20px;top:30px;font-size:30px">2026</div>')
        self.assertTrue(any("zone" in p for p in gate.check(html, "feed")))

    def test_text_off_the_canvas_and_overlapping(self):
        html = page('<h1 style="position:absolute;left:72px;top:400px;margin:0;font-size:150px;white-space:nowrap">Johannesburg listing</h1>'
                    '<div style="position:absolute;left:72px;top:420px;font-size:80px">Over it</div>')
        problems = gate.check(html, "feed")
        self.assertTrue(any("off the canvas" in p for p in problems))
        self.assertTrue(any("overlaps" in p for p in problems))

    def test_a_squeezed_or_rounded_logo_chip(self):
        """The square tile with a wordmark squeezed in, and a chip off the spec, both fail; the shared chip passes."""
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 270 72"><rect width="270" height="72"/></svg>')
        uri = Path(f.name).as_uri()
        bad = page(FILLED + f'<div data-chip style="position:absolute;left:72px;top:1240px;height:80px;padding:4px 30px;'
                            f'border-radius:12px;background:#eee"><img src="{uri}" style="height:20px"></div>')
        problems = gate.check(bad, "feed")
        self.assertTrue(any("padding" in p for p in problems))
        self.assertTrue(any("corner radius" in p for p in problems))
        good = page(FILLED + f'<div style="position:absolute;left:600px;top:1240px">{T.logo_chip(uri)}</div>')
        self.assertFalse([p for p in gate.check(good, "feed") if "chip" in p])

    def test_a_small_credit(self):
        html = page(FILLED + '<div data-credit style="position:absolute;left:72px;top:1300px;font-size:16px">Photo: A, CC0</div>')
        self.assertTrue(any("credit at 16 px" in p for p in gate.check(html, "feed")))

    def test_an_empty_band(self):
        html = page('<h1 style="position:absolute;left:72px;top:72px;margin:0;font-size:80px">Half a card</h1>'
                    '<div style="position:absolute;left:72px;top:1250px;font-size:30px">boardread.</div>')
        self.assertTrue(any("empty band" in p for p in gate.check(html, "feed", self.shot(html))))

    def test_the_openaire_card_and_a_repeated_layout(self):
        """A logo of an organisation the headline does not name (OpenAIRE on 'OpenAI countersues Apple'), and the same
        layout twice in a row."""
        story = {"headline": "OpenAI countersues Apple for stealing trade secrets",
                 "_assets": {"logo_names": ["OpenAIRE", "Apple"], "photo": "", "kind": "scene"}}
        problems = gate.check(page(FILLED), "feed", None, story, "type", "type")
        self.assertTrue(any("OpenAIRE" in p for p in problems))
        self.assertTrue(any("same layout" in p for p in problems))

    def test_story_and_reel_zones(self):
        story = page('<div style="position:absolute;left:72px;top:1800px;font-size:40px">Under the reply bar</div>', 1080, 1920)
        self.assertTrue(any("zone" in p for p in gate.check(story, "story")))
        reel = page('<div style="position:absolute;left:940px;top:900px;font-size:40px">Like</div>', 1080, 1920)
        self.assertTrue(any("zone" in p for p in gate.check(reel, "reel")))

    def test_text_over_a_face(self):
        html = page(FILLED)
        self.assertTrue(any("face" in p for p in gate.check(html, "feed", face=(60, 60, 600, 600))))


@unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
class ExtraSlides(unittest.TestCase):
    """The number and sources slides pass the gate before carousel_extended may be switched on: each left a third to
    two thirds of the slide empty (2026-11-27)."""

    def story(self):
        return {"title": "Verizon is in talks to buy broadband operator Fidium for about $6 billion",
                "headline": "Verizon is in talks to buy broadband operator Fidium for about $6 billion", "figure": "$6B",
                "topic": "Business", "category": "business", "source": "Bloomberg", "published": "2026-11-27T18:56:00+00:00",
                "outlets": ["Financial Times", "Bloomberg", "Mint"], "timeline": [0, 0, 0], "dek": "",
                "_assets": {"photo": "", "logo": "", "logos": [], "logo_names": [], "credit": "", "file": "", "kind": ""}}

    def test_number_and_sources_slides_pass(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(T, "domain", return_value="boardread.news"):
            for name, html in (("number", T.number_slide(self.story())),
                               ("sources-3", T.sources_slide(self.story(), ["Financial Times", "Bloomberg", "Mint"])),
                               ("sources-1", T.sources_slide(self.story(), ["Fortune"])),
                               ("sources-8", T.sources_slide(self.story(), [f"Newsroom {i}" for i in range(1, 11)], cta=True))):
                png = Path(tmp) / f"{name}.png"
                render.shoot(html, png, 1080, 1350)
                with self.subTest(slide=name):
                    self.assertEqual(gate.check(html, "feed", png), [])


@unittest.skipUnless(HAVE, "needs ffmpeg and Chrome")
class DetailFits(unittest.TestCase):
    def test_a_long_report_with_its_meaning_keeps_the_foot_on_the_slide(self):
        """2026-11-28: the follow and site foot was pushed off the detail slide and the gate held the post. The report
        text now shrinks to fit; the foot is the follow ask only on the last slide."""
        s = ExtraSlides().story()
        body = " ".join(["Verizon said the deal would extend its fibre network to millions of homes in New England."] * 6)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(T, "domain", return_value="boardread.news"):
            for end in (True, False):
                html = T.detail(s, body, ["Financial Times", "Bloomberg"], so_what="It is Verizon's biggest fibre purchase "
                                "since it bought Frontier, and it lifts its reach in the north-east.", end=end)
                png = Path(tmp) / "d.png"
                render.shoot(html, png, 1080, 1350)
                with self.subTest(end=end):
                    self.assertEqual([x for x in gate.check(html, "feed") if "off the canvas" in x or "clipped" in x], [])
                    self.assertEqual("Follow @boardread" in html, end)


class Queue(unittest.TestCase):
    def test_a_failed_gate_holds_the_post(self):
        from aidaily import desk
        post = {"id": "a", "headlines": ["Lab ships a model"], "topic": "Tech", "gate": ["text off the canvas: 'x'"]}
        self.assertIn("visual gate: text off the canvas: 'x'", desk.audit(post))

    def test_a_sentence_with_a_missing_word_holds_the_post(self):
        """Live on 2026-11-28 (2026-11-27-0736-1): "Analysts describe the scale of the walkovers as ." on a detail slide."""
        from aidaily import desk
        post = {"id": "a", "headlines": ["Sarawak's GPS wins a record 29 state seats unopposed"], "topic": "Politics",
                "body": "Major parties are sitting out the polls. Analysts describe the scale of the walkovers as . A majority takes 42 seats."}
        self.assertTrue(any("gap where a word is missing" in p for p in desk.audit(post)))
        post["body"] = "Major parties are sitting out the polls. A simple majority takes 42 seats, about 2.5% of the vote."
        self.assertFalse(any("gap where a word is missing" in p for p in desk.audit(post)))

    def test_the_fallback_card_drops_the_photo(self):
        from aidaily import feedlayouts as FL
        s = {"headline": "Nvidia opens a plant", "_assets": {"photo": "file:///x.jpg", "file": "X.jpg", "kind": "company"}}
        self.assertEqual(FL.photo_fit(s), "high")
        s["_safe"] = True
        self.assertEqual(FL.photo_fit(s), "low")


if __name__ == "__main__":
    unittest.main()
