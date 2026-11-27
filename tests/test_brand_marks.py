import re
import unittest
import xml.etree.ElementTree as ET

from aidaily import site

PLATFORMS = ("Instagram", "Threads", "Bluesky", "Telegram", "Facebook")


class BrandMarks(unittest.TestCase):
    def test_each_platform_renders_its_own_glyph_as_a_filled_24_unit_svg(self):
        for name in PLATFORMS:
            svg = ET.fromstring(site.mark(name))
            self.assertEqual(svg.get("viewBox"), "0 0 24 24", name)
            self.assertEqual(svg.get("fill"), "currentColor", name)
            self.assertEqual(svg.get("aria-label"), name)
            path = svg[0].get("d")
            self.assertEqual(path, site.BRANDS[name.lower()])
            self.assertGreater(len(path), 200, name)
            self.assertTrue(re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s-]+", path), name)

    def test_the_five_glyphs_are_distinct_and_never_transformed(self):
        paths = {site.BRANDS[n.lower()] for n in PLATFORMS}
        self.assertEqual(len(paths), 5)
        for name in PLATFORMS:
            self.assertNotIn("transform", site.mark(name))

    def test_a_channel_link_keeps_its_url_and_names_the_platform(self):
        html = site.chan("Bluesky", "https://bsky.app/profile/x.test")
        self.assertIn('href="https://bsky.app/profile/x.test"', html)
        self.assertIn('aria-label="Bluesky"', html)
        self.assertIn(site.BRANDS["bluesky"], html)

    def test_generic_marks_are_unchanged(self):
        for name in ("x", "linkedin", "copy", "rss", "whatsapp", "check"):
            self.assertIn('stroke="currentColor"', site.mark(name))


if __name__ == "__main__":
    unittest.main()
