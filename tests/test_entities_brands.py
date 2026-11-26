import unittest

from aidaily import entities


class ForeignBrand(unittest.TestCase):
    def test_other_companys_chip_is_caught(self):
        # the case that reached Instagram: an AMD chip photo on an Nvidia story
        self.assertEqual(entities.foreign_brand("AMD Radeon GPU die close-up.jpg",
                                                "Nvidia halts chip shipments to four Southeast Asian countries"), "AMD")

    def test_brand_the_story_names_passes(self):
        self.assertEqual(entities.foreign_brand("Nvidia GeForce board.jpg", "Nvidia earnings beat GeForce demand"), "")

    def test_unbranded_photo_passes(self):
        self.assertEqual(entities.foreign_brand("Printed circuit board macro.jpg", "Nvidia halts chip shipments"), "")

    def test_word_inside_another_word_is_not_a_brand(self):
        self.assertEqual(entities.foreign_brand("Starlight over the harbour.jpg", "Ports reopen"), "")


    def test_own_aircraft_with_maker_name_passes(self):
        self.assertEqual(entities.foreign_brand("Norse Atlantic Airways Boeing 787 LN-FND Oslo Gardermoen.jpg",
                                                "Norse Atlantic suspends all flights", own="Norse Atlantic"), "")

    def test_place_the_story_does_not_name_is_caught(self):
        self.assertEqual(entities.foreign_brand("Engine House Allihies Copper Mine County Cork.jpg",
                                                "Latin America's copper and energy could benefit from AI demand"), "Cork")

    def test_place_the_story_names_passes(self):
        self.assertEqual(entities.foreign_brand("Kuwait City skyline.jpg", "Iranian drone attack in Kuwait kills two"), "")


class PhotoFilters(unittest.TestCase):
    def test_parrot_is_not_amazon(self):
        self.assertTrue(entities.NATURE.search("Turquoise-fronted amazon (Amazona aestiva) head.JPG"))

    def test_ai_generated_image_is_not_a_photo(self):
        self.assertTrue(entities.NOT_PHOTO.search("AI generated image of Loab character.jpg"))

    def test_air_defence_system_is_a_scene_not_a_topic_photo(self):
        self.assertTrue(entities.PEOPLE.search("Antelope Air Defense System in CCK Air Force Base.jpg"))


    def test_museum_textile_is_not_anthropic(self):
        self.assertTrue(entities.ART.search("Fragment of an Egyptian Textile, depicting the anthropic figure of Anthousa.jpg"))

    def test_fan_in_branded_shirt_is_not_the_company(self):
        self.assertTrue(entities.CROWD.search("Biggest Rockstar Games fan ever - Flickr.jpg"))


if __name__ == "__main__":
    unittest.main()
