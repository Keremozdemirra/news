"""Scenes fit the article (2026-11-27): a place-named scene only on an article about that place, a scene of one
thing only on an article about it, the sport's own ground, and no search on the headline's other proper names."""
import json
import re
import unittest
from unittest import mock

from aidaily import desk, entities, scenes, templates as T

DATA = scenes.load()


def files(lists):
    return [i["file"] for items in lists for i in items]


class Fit(unittest.TestCase):
    def test_skyline_ballot_and_banknotes_only_where_they_belong(self):
        # the Melbourne skyline once ran on an Indian trust, a Polish ballot box on Guinea-Bissau's election
        tata = files(scenes.entries("Tata Trusts' Vijay Singh seeks probe of legal costs", "Business", DATA))
        self.assertNotIn("AUS Melbourne, Central Business District, Skyline 001.jpg", tata)
        gb = files(scenes.entries("Guinea-Bissau's military rulers delay elections by two years", "Politics", DATA))
        self.assertNotIn("2023 Polish parliamentary election and referendum. October 2023. Ballot box in Tomaszów Mazowiecki, "
                         "Sikorskiego Street 6A.jpg", gb)
        # the Connecticut voting machine (its ballot reads "Morris, Connecticut, 2006") is retired: a generic fallback instead
        self.assertNotIn("Example voting booth.jpg", gb)
        self.assertIn("Alley of flags UNO Geneva.jpg", gb)
        fed = files(scenes.entries("Fed is poised to raise rates despite stock turmoil", "Economy", DATA))
        self.assertIn("US Dollar banknotes I.jpg", fed)
        self.assertNotIn("Pile of Euro Notes (5856649637).jpg", fed)
        self.assertIn("AUS Melbourne, Central Business District, Skyline 001.jpg",
                      files(scenes.entries("Melbourne office market cools", "Business", DATA)))

    def test_a_scene_of_one_thing_needs_that_thing(self):
        heathrow = files(scenes.entries("MPs say ministers failed to make the case for Heathrow third runway", "Politics", DATA))
        self.assertNotIn("Example voting booth.jpg", heathrow)
        self.assertNotIn("Bermuda (UK) image number 282 courtroom.jpg", heathrow)

    def test_the_cow_and_the_padlock_are_retired_and_held(self):
        # a Holstein cow stood for Alberta's oil money
        self.assertNotIn("Holstein at Dusk.jpg", files(scenes.entries("Alberta raises surplus as oil surges", "Economy", DATA)))
        post = {"headlines": ["Alberta raises projected surplus to C$8.5 billion"], "topic": "Economy", "body": "", "dek": "",
                "caption": "x #economy #news", "photo_file": "Holstein at Dusk.jpg", "photo_kind": "scene",
                "credit": "Photo: A, CC BY 4.0, via Wikimedia Commons"}
        self.assertTrue(any("taken off" in p for p in desk.audit(post)))

    def test_audit_holds_a_scene_that_names_another_place(self):
        post = {"headlines": ["Tata Trusts' Vijay Singh seeks probe of legal costs"], "topic": "Business", "body": "", "dek": "",
                "caption": "x #business #news", "photo_file": "AUS Melbourne, Central Business District, Skyline 001.jpg",
                "photo_kind": "scene", "credit": "Photo: A, CC BY 4.0, via Wikimedia Commons"}
        self.assertTrue(any("does not fit" in p for p in desk.audit(post)))

    def test_office_scenes_stay_off_garment_workers(self):
        bd = files(scenes.entries("Bangladesh garment workers clash with police over wages", "World", DATA))
        self.assertNotIn("Coworking space 2026-09-27.jpg", bd)
        self.assertIn("Coworking space 2026-09-27.jpg", files(scenes.entries("SAP explores 10,000 job cuts", "Business", DATA)))


class Sport(unittest.TestCase):
    def test_a_football_club_gets_a_football_ground_never_a_pit_lane(self):
        lists = scenes.entries("Bournemouth beat Celta Vigo 2-1 with 10 men", "Sport", DATA, sport=True)
        got = files(lists)
        # a football pitch or goal, never the one New Jersey stadium that ran on four posts in a batch (retired)
        self.assertIn("Soccer goals in the south field in Brastad 3.jpg", got)
        self.assertNotIn("Hinchliffe Stadium (Paterson, NJ).jpg", got)
        self.assertNotIn("Pit lane at Phillip Island GP Circuit (16232935133).jpg", got)
        self.assertNotIn("Boxing ring, MGM Grand.jpg", got)


class SportAudit(unittest.TestCase):
    def test_a_pit_lane_on_a_football_article_is_held(self):
        post = {"headlines": ["Bournemouth beat Celta Vigo 2-1 with 10 men"], "topic": "Sport", "body": "", "dek": "",
                "caption": "x #news", "photo_file": "Pit lane at Phillip Island GP Circuit (16232935133).jpg", "photo_kind": "scene",
                "credit": "Photo: A, CC BY 4.0, via Wikimedia Commons"}
        self.assertTrue(any("not this article's sport" in p for p in desk.audit(post)))
        post.update(photo_file="Soccer goals in the south field in Brastad 3.jpg")
        self.assertFalse(any("sport" in p for p in desk.audit(post)))


class NoNameSearch(unittest.TestCase):
    def test_the_headlines_other_names_are_not_searched(self):
        # "Ford" found a car museum for Ontario's premier Doug Ford
        s = {"headline": "Ontario's Ford and Unifor urge Ottawa to scrap automaker emissions rules", "topic": "Politics", "summary": ""}
        calls = []
        with mock.patch.object(entities, "fresh_photo", side_effect=lambda subj, *a, **k: calls.append((subj, k)) or (None, "", "")), \
             mock.patch.object(entities, "headline_names", side_effect=AssertionError("searched the headline's names")), \
             mock.patch.object(scenes, "photo", return_value=(None, "", "", "")):
            T.pick_photo(s, s["headline"].lower(), "", fetch=True)
        self.assertFalse(any(k.get("strict") for _, k in calls))


if __name__ == "__main__":
    unittest.main()


class Retired(unittest.TestCase):
    """Photo plan item 1: a retired file is in no list and no path picks it."""
    BAD = ("Example voting booth.jpg", "Hinchliffe Stadium (Paterson, NJ).jpg", "Cranes in the Port of Algeciras and Gibraltar.jpg",
           "Colorful Old Oil Barrels.jpg", "NOIRLab HQ Conference Room ( V8A4834-CC).jpg", "Globe with yellow background 1.jpg",
           "Market stalls at Ljubljana Central Market.jpg", "Old port cranes at Port of Antwerp, pic-054.JPG")

    def lists(self):
        for r in DATA["rules"] + DATA["sport"]:
            yield r["files"]
        yield from DATA["topics"].values()

    def test_no_list_names_a_retired_file(self):
        gone = set(DATA["retired"])
        self.assertTrue(set(self.BAD) <= gone)
        self.assertEqual([i["file"] for items in self.lists() for i in items if i["file"] in gone], [])

    def test_entries_and_the_name_search_skip_retired_files(self):
        data = json.loads(json.dumps(DATA))
        data["topics"]["Politics"].append({"file": "Example voting booth.jpg", "alt": "x"})
        self.assertNotIn("Example voting booth.jpg", files(scenes.entries("Taiwan votes Saturday", "Politics", data)))
        from aidaily import entities
        self.assertIn("Hinchliffe Stadium (Paterson, NJ).jpg", entities.never_use())

    def test_the_fallback_topics_always_have_a_picture(self):
        # no text-only card (Kerem): Business and World, the topics every story falls back on, keep files any story may carry
        for t in scenes.FALLBACK_TOPICS:
            self.assertGreaterEqual(len([i for i in DATA["topics"][t] if not i.get("place") and not i.get("needs")]), 2, t)


# names of places that appear in Commons titles of scene files; a file whose title or alt names one must say where it
# may go (place or needs) or carry generic: true, a person's word that the picture itself shows nowhere in particular
PLACE_WORDS = re.compile(r"\b(Manhattan|New York|Seattle|Halifax|Nova Scotia|Koper|Vancouver|Anacortes|Burnaby|Permian|Caspian|Ostfriesland|Freimann|Mödlareuth|Fraisse|Neufahrn|Leoben|Ardmore|San Antonio|Bemmel|São Paulo|Rostov|Russia|Gibraltar|El Alto|Medicine Hat|Auckland|Kleinmachnow|Trenwith|Cornwall|Katrin|Inglés|Tepia|London|Phillip Island|Adelaide|Canberra|MGM Grand|Tokyo|Inter&Co|OAKA|Geneva|Genève|Brussels|Hague|Haag|Brastad|Washington|Melbourne|Säynätsalo|Polish|Basque|Bermuda|Hakata|Negishi|Fuji|Shahamah|Vasconcelos|Asikkala|Portsmouth|Auditorium Theatre|National Archives|aeropuerto|Antártico|PROANTAR|Galeria|Mega store|Gliwice|Tomaszów|Japan|China|India|France|Germany|Spain|Italy|Brazil|Canada|Australia|Mexico|Korea|Taiwan|Israel|Poland|Finland|Ukraine|Turkey|Iran|Egypt|Nigeria|Kenya|Argentina|Chile|Indonesia|Vietnam|Thailand|Singapore|Malaysia|Philippines|Pakistan|Algeciras|Antwerp|Haifa|Ljubljana|Connecticut|Paris|Berlin|Madrid|Rome|Beijing|Shanghai|Mumbai|Delhi|Seoul|Sydney|Toronto|Moscow|Istanbul|Dubai)\b", re.I)


class SceneTags(unittest.TestCase):
    """Photo plan item 3."""

    def test_a_scene_that_names_a_place_says_where_it_may_go(self):
        bad = []
        for items in [r["files"] for r in DATA["rules"] + DATA["sport"]] + list(DATA["topics"].values()):
            for i in items:
                if PLACE_WORDS.search(i["file"] + " " + i["alt"]) and not (i.get("place") or i.get("needs") or i.get("generic")):
                    bad.append(i["file"])
        self.assertEqual(bad, [])

    def test_the_audited_headlines_get_their_subject_not_a_broad_word(self):
        rules = DATA["rules"]
        pick = lambda t, s="": (scenes.best_rule(rules, t, t + " " + s) or {}).get("id")  # noqa: E731
        self.assertIsNone(pick("AI exports drive Asia growth", "Exports of AI chips lifted growth across Asia."))
        self.assertEqual(pick("Australia clears law requiring LNG exporters to keep 20% for domestic use"), "gas")
        self.assertEqual(pick("Hong Kong home rents hit new highs as competing offers push prices up"), "realestate")
        self.assertIsNone(pick("Tokyo core inflation hits 16-month high", "Core consumer prices rose 2.9%."))
        self.assertEqual(pick("Maltese-flagged tanker capsizes off Ibiza", "A chemical tanker capsized."), "shipping")

    def test_no_scene_twice_in_one_batch(self):
        got = []
        batch = set()
        info = {"width": 2000, "height": 1400, "url": "u", "extmetadata": {}}
        with mock.patch.object(entities, "_commons_info", return_value=info), \
             mock.patch.object(entities, "photo_ok", return_value=(True, "Photo: X, CC0, via Wikimedia Commons")), \
             mock.patch.object(entities, "_get", return_value=b"jpeg"):
            for _ in range(3):
                _, _, f, _ = scenes.photo("Taiwan votes Saturday in local elections", "Politics", set(), batch=batch)
                got.append(f)
                batch.add(f)
        self.assertEqual(len(got), len(set(got)))
