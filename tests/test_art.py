import re
import unittest

from aidaily import art


class Art(unittest.TestCase):
    """The abstract plates are built but switched off (site.ART_ON) until the art direction is final; they stay tested."""

    def test_the_same_article_always_draws_the_same_plate(self):
        a = art.plate("Markets", "2026-11-26-1446-5", 3, 14)
        self.assertEqual(a, art.plate("Markets", "2026-11-26-1446-5", 3, 14))
        self.assertNotEqual(a, art.plate("Markets", "2026-11-26-1446-6", 3, 14))

    def test_newsrooms_set_the_strokes_and_the_hour_the_rotation(self):
        for topic in ("Markets", "Economy", "Business", "Politics", "World", "Tech", "AI", "Culture"):
            self.assertIn(topic, art.FAMILY)
            self.assertNotEqual(art.plate(topic, "k", 1, 0), art.plate(topic, "k", 6, 0), topic)
        self.assertNotEqual(art.plate("Markets", "k", 3, 1), art.plate("Markets", "k", 3, 7))

    def test_plates_are_flat_ink_without_colour_gradients_or_text(self):
        for topic in art.FAMILY:
            s = art.plate(topic, "x1", 4, 10)
            self.assertNotRegex(s, r"#[0-9a-fA-F]{3,6}|rgb\(|gradient|filter|<text|<image")
            self.assertIn('fill="currentColor"', s)
            self.assertIn('aria-hidden="true"', s)

    def test_barcode_has_one_bar_per_article(self):
        self.assertEqual(len(re.findall(r"<rect", art.barcode([1, 3, 6, 2]))), 4)
        self.assertEqual(art.barcode([]), "")
