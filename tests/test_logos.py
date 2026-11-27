"""Logos: only the company's own, and one chip spec around every logo."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import entities as E
from aidaily import render
from aidaily import templates as T

HAVE_CHROME = Path(render.CHROME).exists() if render.CHROME.startswith("/") else bool(shutil.which(render.CHROME))


def wikidata(hits, entities):
    """A stand-in for entities._get: search hits by query, then entity JSON by id."""
    def get(url, raw=False):
        if "wbsearchentities" in url:
            return {"search": hits}
        qid = re.search(r"EntityData/(Q\d+)\.json", url).group(1)
        return {"entities": {qid: entities[qid]}}
    return get


def ent(label, site=""):
    claims = {"P856": [{"mainsnak": {"datavalue": {"value": site}}}]} if site else {}
    return {"labels": {"en": {"value": label}}, "claims": claims}


class Match(unittest.TestCase):
    def test_openaire_is_not_openai(self):
        """2026-11-27: the OpenAIRE logo went on 'OpenAI countersues Apple' because 'OpenAIRE' starts with 'OpenAI'."""
        hits = [{"id": "Q1", "label": "OpenAIRE", "description": "network of open access repositories and service providers"},
                {"id": "Q2", "label": "OpenAI", "description": "American artificial intelligence research company"}]
        with mock.patch.object(E, "_get", wikidata(hits, {"Q1": ent("OpenAIRE", "https://www.openaire.eu"),
                                                           "Q2": ent("OpenAI", "https://openai.com")})):
            self.assertEqual(E.company_entity("OpenAI")[0], "OpenAI")
        with mock.patch.object(E, "_get", wikidata(hits[:1], {"Q1": ent("OpenAIRE", "https://www.openaire.eu")})):
            with self.assertRaises(LookupError):
                E.company_entity("OpenAI")  # not certain: no logo

    def test_a_longer_label_needs_the_name_as_its_own_website(self):
        hits = [{"id": "Q3", "label": "Disney+", "description": "American video streaming service"},
                {"id": "Q4", "label": "Disney Interactive Studios", "description": "American video game developer"},
                {"id": "Q5", "label": "Meta Platforms", "description": "American technology company"}]
        es = {"Q3": ent("Disney+", "https://www.disneyplus.com"), "Q4": ent("Disney Interactive Studios", "https://disney.com/games"),
              "Q5": ent("Meta Platforms", "https://www.meta.com/")}
        with mock.patch.object(E, "_get", wikidata(hits[:2], es)):
            with self.assertRaises(LookupError):
                E.company_entity("Disney")
        with mock.patch.object(E, "_get", wikidata(hits[2:], es)):
            self.assertEqual(E.company_entity("Meta")[0], "Meta Platforms")

    def test_a_song_or_a_game_series_is_no_company(self):
        hits = [{"id": "Q6", "label": "Fifa", "description": "vocal track by Angelique Kidjo; studio recording"},
                {"id": "Q7", "label": "FIFA", "description": "association football video game series"}]
        with mock.patch.object(E, "_get", wikidata(hits, {"Q6": ent("Fifa"), "Q7": ent("FIFA")})):
            with self.assertRaises(LookupError):
                E.company_entity("Fifa")

    def test_a_domain_from_the_copy_must_be_the_entitys(self):
        hits = [{"id": "Q2", "label": "OpenAI", "description": "American artificial intelligence research company"}]
        with mock.patch.object(E, "_get", wikidata(hits, {"Q2": ent("OpenAI", "https://openai.com")})):
            self.assertEqual(E.company_entity("OpenAI", "openai.com")[0], "OpenAI")
            with self.assertRaises(LookupError):
                E.company_entity("OpenAI", "openaire.eu")


class Chip(unittest.TestCase):
    def logos(self, tmp):
        wide = Path(tmp) / "wide.svg"
        wide.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 270 72"><rect width="270" height="72"/></svg>')
        square = Path(tmp) / "square.svg"
        square.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 98"><rect width="80" height="98"/></svg>')
        return wide.as_uri(), square.as_uri()

    def test_every_chip_has_one_height_and_one_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = (T.logo_chip(u) for u in self.logos(tmp))
        for chip in (a, b):
            self.assertIn(f"height:{T.CHIP_H}px", chip)
            self.assertIn(f"padding:{round(T.CHIP_H * T.CHIP_PAD)}px;", chip)
            self.assertNotIn("border-radius", chip)  # square, like every brand v2 surface
        # optical size: the square symbol is as tall as the box; the long wordmark is shorter, never wider than 5 boxes
        box = T.CHIP_H - 2 * round(T.CHIP_H * T.CHIP_PAD)
        self.assertEqual(T.logo_size(80 / 98, box)[1], box)
        w, h = T.logo_size(270 / 72, box)
        self.assertLess(h, box)
        self.assertLessEqual(w, box * 5)

    @unittest.skipUnless(HAVE_CHROME, "needs Chrome")
    def test_rendered_chips_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            uris = self.logos(tmp)
            page = T.head() + ('<div style="display:flex;gap:18px">' + "".join(T.logo_chip(u) for u in uris) + "</div>"
                               + """<script>window.addEventListener('load',()=>{document.body.setAttribute('data-r',JSON.stringify(
[...document.querySelectorAll('[data-chip]')].map(c=>{const s=getComputedStyle(c);const b=c.getBoundingClientRect();
return [b.height,s.paddingTop,s.paddingLeft,s.paddingBottom,s.paddingRight,s.borderRadius]})))})</script></body></html>""")
            f = Path(tmp) / "c.html"
            f.write_text(page)
            with tempfile.TemporaryDirectory() as profile:
                dom = subprocess.run([render.CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
                                      "--virtual-time-budget=3000", "--dump-dom", f.as_uri()], capture_output=True, text=True,
                                     timeout=60).stdout
        rows = json.loads(re.search(r'data-r="([^"]+)"', dom).group(1).replace("&quot;", '"'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], rows[1])  # same height, the same padding on all sides, the same (square) corners
        self.assertEqual(len(set(rows[0][1:5])), 1)


if __name__ == "__main__":
    unittest.main()
