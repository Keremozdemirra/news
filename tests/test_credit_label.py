import unittest

from aidaily import entities, scenes, site
from aidaily import templates as T


def info(artist, lic="Public domain"):
    return {"extmetadata": {"Artist": {"value": artist}, "LicenseShortName": {"value": lic}}}


class Label(unittest.TestCase):
    def test_the_author_field_never_doubles_the_label(self):
        for artist in ("Foto: Nebojša Tejić/STA", "foto:Nebojša Tejić/STA", "Photo by: Nebojša Tejić/STA",
                       "Fotografie: Nebojša Tejić/STA", "Photograph: Nebojša Tejić/STA", "<a href='x'>Foto: Nebojša Tejić/STA</a>"):
            ok, credit = entities.photo_ok(info(artist))
            self.assertTrue(ok)
            self.assertEqual(credit, "Photo: Nebojša Tejić/STA, Public domain, via Wikimedia Commons")

    def test_a_name_that_only_starts_like_a_label_is_kept(self):
        self.assertEqual(entities.strip_label("Fotis Papadopoulos"), "Fotis Papadopoulos")
        self.assertEqual(entities.strip_label("Photon Labs"), "Photon Labs")

    def test_stored_credits_are_cleaned_where_they_are_shown(self):
        bad = "Photo: Foto: Nebojša Tejić/STA, Public domain, via Wikimedia Commons"
        good = "Photo: Nebojša Tejić/STA, Public domain, via Wikimedia Commons"
        self.assertEqual(entities.clean_credit(bad), good)
        self.assertEqual(entities.clean_credit(good), good)
        self.assertIn(good, T._credit(bad))
        self.assertNotIn("Foto:", T._credit(bad))
        self.assertEqual(site.credit_line({"credit": bad}), "Archive photo, not from this event. " + good)


class Licence(unittest.TestCase):
    """Photo plan item 6 and the deep review: licence gate, credit, links, archive label on every kind."""

    def info(self, lic, terms="", artist="A"):
        return {"extmetadata": {"LicenseShortName": {"value": lic}, "License": {"value": terms}, "Artist": {"value": artist}}}

    def test_only_cc0_public_domain_and_cc_by(self):
        for lic, ok in (("CC BY 4.0", True), ("CC BY 2.0", True), ("CC0", True), ("Public domain", True),
                        ("CC BY-SA 4.0", False), ("OGL", False), ("CC BY-NC 2.0", False)):
            self.assertEqual(entities.photo_ok(self.info(lic))[0], ok, lic)
        self.assertFalse(entities.photo_ok(self.info("Public domain", "pd-us-expired"))[0])
        self.assertTrue(entities.photo_ok(self.info("Public domain", "pd-usgov"))[0])
        self.assertFalse(entities.photo_ok(self.info("CC BY 4.0", artist="Xinhua"))[0])

    def test_an_address_is_never_the_credited_creator(self):
        self.assertEqual(entities.photo_ok(self.info("CC BY 4.0", artist="http://www.president.gov.ua/,"))[1],
                         "Photo: president.gov.ua, CC BY 4.0, via Wikimedia Commons")
        self.assertEqual(entities.clean_credit("Photo: http://www.president.gov.ua/, CC BY 4.0, via Wikimedia Commons"),
                         "Photo: president.gov.ua, CC BY 4.0, via Wikimedia Commons")

    def test_every_kind_is_labelled_and_the_licence_and_file_are_linked(self):
        p = {"credit": "Photo: Shinuinu, CC BY 4.0, via Wikimedia Commons", "photo_kind": "company", "photo_file": "Macy's store.jpg"}
        self.assertTrue(site.credit_line(p).startswith("Archive photo, not from this event."))
        h = site.credit_html(p)
        self.assertIn('href="https://creativecommons.org/licenses/by/4.0/"', h)
        self.assertIn('href="https://commons.wikimedia.org/wiki/File:Macy%27s_store.jpg"', h)
        story = {"headline": "Macy's postpones parade", "_assets": {"credit": p["credit"], "kind": "company", "photo": "file:///tmp/x.jpg",
                                                                      "file": "x", "logos": [], "logo_names": []}}
        self.assertIn("Archive photo, not from this event.", T._foot(story, T.BRAND))


class GasScene(unittest.TestCase):
    def test_a_gas_story_gets_a_gas_scene_not_oil_drums(self):
        first = scenes.entries("Australia clears law requiring LNG exporters to keep 20% for domestic use", "Politics")[0]
        self.assertTrue(first and all("LNG" in i["file"] for i in first))
        oil = scenes.entries("Oil prices rise as OPEC cuts output", "Markets")[0]
        self.assertFalse(any("LNG" in i["file"] for i in oil))


if __name__ == "__main__":
    unittest.main()
