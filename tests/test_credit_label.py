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
        self.assertEqual(site.credit_line({"credit": bad}), good)


class GasScene(unittest.TestCase):
    def test_a_gas_story_gets_a_gas_scene_not_oil_drums(self):
        first = scenes.entries("Australia clears law requiring LNG exporters to keep 20% for domestic use", "Politics")[0]
        self.assertTrue(first and all("LNG" in i["file"] for i in first))
        oil = scenes.entries("Oil prices rise as OPEC cuts output", "Markets")[0]
        self.assertFalse(any("LNG" in i["file"] for i in oil))


if __name__ == "__main__":
    unittest.main()
