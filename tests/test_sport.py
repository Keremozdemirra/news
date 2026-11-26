"""The sport section: its own lane through the desk, website only, never a social channel."""
import json
import os
import re
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ.setdefault("DESK_SITE_OFFLINE", "1")
from aidaily import copy, desk, platforms, rank, reel, site
from test_desk import Tmp, story
from test_platforms import SECRETS

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
SRC = {"bbc1": {"name": "BBC Sport", "publisher": "BBC Sport", "category": "sport"},
       "bbc2": {"name": "BBC Sport", "publisher": "BBC Sport", "category": "sport"},
       "gu": {"name": "The Guardian Sport", "publisher": "The Guardian", "category": "sport"},
       "cnbc": {"name": "CNBC", "category": "business"}}


def it(title, src, hours=1):
    return dict(title=title, source_id=src, url=f"https://x/{abs(hash(title + src))}", published=NOW - timedelta(hours=hours), summary="")


def stamp(**kw):
    return (desk.now() - timedelta(**kw)).isoformat(timespec="seconds")


class Rank(unittest.TestCase):
    def test_two_feeds_of_one_newsroom_count_once_and_the_class_is_sport(self):
        items = [it("Arsenal beat Chelsea 2-1 in the Premier League", "bbc1"), it("Arsenal beat Chelsea 2-1 in the Premier League", "bbc2"),
                 it("Arsenal beat Chelsea 2-1 in the Premier League", "gu")]
        got = rank.rank(items, SRC, now=NOW)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["category"], "sport")
        self.assertEqual(got[0]["outlets"], ["BBC Sport", "The Guardian"])
        self.assertEqual([p for p, _ in got[0]["timeline"]], ["BBC Sport", "The Guardian"])

    def test_a_transfer_is_not_a_funding_round(self):
        got = rank.rank([it("Liverpool buys striker for 80m", "bbc1")], SRC, now=NOW)
        self.assertEqual(got[0]["category"], "sport")

    def test_a_major_competition_outranks_routine_news(self):
        got = rank.rank([it("Club signs a goalkeeper on loan", "bbc1"), it("Champions League final venue confirmed", "gu")], SRC, now=NOW)
        self.assertTrue(got[0]["title"].startswith("Champions League"))


class Select(Tmp):
    def rows(self, n, score=9.0):
        fresh = desk.now().isoformat()
        words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet".split()
        return [{"title": f"{words[i]} club win {words[(i + 3) % 10]} cup tie", "score": score, "published": fresh, "outlets": ["BBC Sport"],
                 "url": f"https://x/{i}", "links": [f"https://x/{i}"]} for i in range(n)]

    def test_per_run_cap(self):
        with mock.patch.dict(desk.CONFIG, {"sport_per_run": 3, "sport_daily_max": 12, "sport_min_score": 7.0}):
            self.assertEqual(len(desk.select(self.rows(8), lane="sport")), 3)

    def test_daily_cap_counts_the_last_24_hours(self):
        with mock.patch.dict(desk.CONFIG, {"sport_per_run": 4, "sport_daily_max": 5, "sport_min_score": 7.0}):
            for i in range(3):
                self.write_post(f"s{i}", status="web", topic="Sport", urls=[f"https://old/{i}"], headlines=[f"old {i}"])
            self.write_post("ancient", status="web", topic="Sport", created=stamp(hours=30), urls=["https://old/9"], headlines=["very old"])
            self.assertEqual(desk.sport_room(), 2)
            self.assertEqual(len(desk.select(self.rows(8), lane="sport")), 2)

    def test_sport_bar_is_its_own_and_biggest_first(self):
        rows = self.rows(2)
        rows[1]["score"] = 12.0
        rows.append({**self.rows(3)[2], "score": 6.0})
        with mock.patch.dict(desk.CONFIG, {"sport_min_score": 7.0, "sport_per_run": 4, "sport_daily_max": 12}):
            got = desk.select(rows, lane="sport")
        self.assertEqual([s["score"] for s in got], [12.0, 9.0])

    def test_betting_copy_and_fragments_do_not_take_a_slot(self):
        rows = self.rows(4)
        rows[0]["title"] = "Week 12 NFL odds, lines, totals, spreads for every game"
        rows[1]["title"] = "Euro Leagues"
        with mock.patch.dict(desk.CONFIG, {"sport_min_score": 7.0, "sport_per_run": 4, "sport_daily_max": 12}):
            self.assertEqual(len(desk.select(rows, lane="sport")), 2)

    def test_shipped_caps_keep_business_the_core(self):
        real = json.loads(((__import__("pathlib").Path(desk.__file__).resolve().parent.parent) / "desk.json").read_text())
        self.assertLessEqual(real["sport_daily_max"], 15)
        self.assertLessEqual(real["sport_per_run"], real["sport_daily_max"])


class Copy(unittest.TestCase):
    def test_sport_prompt_has_its_own_audience_and_fixed_topic(self):
        p = copy.prompt("id: 0", lane="sport")
        self.assertIn("sport section", p)
        self.assertIn('always "Sport"', p)
        self.assertNotIn("consultant, manager or business student", p)
        self.assertIn("consultant, manager or business student", copy.prompt("id: 0"))
        self.assertNotIn("Sport", copy.prompt("id: 0").split("- topic:")[1].split("- headline")[0])

    def test_the_section_comes_from_the_lane_not_from_the_model(self):
        s = {"title": "Arsenal beat Chelsea 2-1", "summary": "Arsenal won 2-1 at home.", "source": "BBC Sport", "lane": "sport"}
        row = {"id": 0, "headline": "Arsenal beat Chelsea 2-1", "dek": "Arsenal won at home.", "topic": "Culture", "company": "Arsenal",
               "backer": "Chelsea", "orgs": ["Chelsea"], "person": "", "figure": "", "x_post": "Arsenal beat Chelsea 2-1", "linkedin_post": "Arsenal won 2-1.\n\nSource: BBC Sport",
               "image_query": "", "company_domain": "arsenal.com"}
        copy.apply([s], [row])
        self.assertEqual(s["topic"], "Sport")
        self.assertEqual(s["backer"], "")
        self.assertEqual(s["orgs"], [])


class Lane(Tmp):
    def day(self, score, topic):
        d = self.root / "out"
        (d / "pack").mkdir(parents=True)
        m, s = story(1)
        m["score"] = s["score"] = score
        s["topic"] = topic
        (d / "pack" / "manifest.json").write_text(json.dumps([m]))
        (d / "digest.json").write_text(json.dumps({"final": {"top": [s]}}))
        return d

    def test_sport_is_web_tier_even_with_instagram_room_and_a_top_score(self):
        (path,) = desk.queue(self.day(20.0, "Sport"), batch="b", render=False)
        post = json.loads(path.read_text())
        self.assertEqual((post["tier"], post["status"], post["topic"]), ("web", "web", "Sport"))
        self.assertNotIn("publish_after", post)

    def test_the_same_story_as_business_takes_the_instagram_room(self):
        (path,) = desk.queue(self.day(20.0, "Business"), batch="b", render=False)
        self.assertEqual(json.loads(path.read_text())["tier"], "instagram")

    def test_audit_holds_a_sport_post_that_reached_a_social_queue(self):
        post = json.loads(self.write_post("x", topic="Sport", tier="instagram", status="queued").read_text())
        post.update(photo_file="", credit="", caption="c", body="b", dek="d", logo_names=[], company="")
        self.assertTrue(any("website-only" in p for p in desk.audit(post)))
        post.update(tier="web", status="web")
        self.assertFalse(any("website-only" in p for p in desk.audit(post)))


class NoSocial(Tmp):
    """The rule: Sport never goes to Instagram, Threads, Bluesky, Telegram or Facebook."""
    def setUp(self):
        super().setUp()
        for p in (mock.patch.dict(os.environ, SECRETS), mock.patch.dict(desk.CONFIG, {"platforms": {n: True for n in platforms.NAMES}})):
            p.start()
            self.addCleanup(p.stop)
        self.sent = []

        class Fake:
            def __init__(self, name, sent):
                self.name, self.sent = name, sent

            def post(self, post):
                self.sent.append((self.name, post["id"]))
                return {"id": "x", "url": ""}

            def digest(self, posts):
                self.sent.append((self.name, "digest"))
                return {"id": "x"}
        self.fact = {n: (lambda n=n: Fake(n, self.sent)) for n in platforms.NAMES}

    def test_topic_is_excluded_in_code(self):
        self.assertIn("Sport", desk.NO_SOCIAL_TOPICS)
        self.assertFalse(desk.social_allowed({"topic": "Sport"}))
        self.assertTrue(desk.social_allowed({"topic": "Markets"}))

    def test_web_social_skips_sport_however_high_it_scores(self):
        self.write_post("a", status="web", tier="web", topic="Sport", score=99, published=stamp(minutes=5), urls=["a"], headlines=["Final"])
        self.assertEqual(desk.web_social(self.fact), 0)
        self.assertEqual(self.sent, [])

    def test_web_social_still_sends_business(self):
        self.write_post("b", status="web", tier="web", topic="Markets", score=99, published=stamp(minutes=5), urls=["b"], headlines=["Rates"])
        self.assertEqual(desk.web_social(self.fact), 1)
        self.assertTrue(self.sent)

    def test_cross_post_sends_nothing_for_sport(self):
        path = self.write_post("c", status="published", topic="Sport", published=stamp(minutes=5))
        desk.cross_post(json.loads(path.read_text()), path, self.fact)
        self.assertEqual(self.sent, [])

    def test_a_queued_sport_post_is_never_published_to_instagram(self):
        self.write_post("d", status="queued", topic="Sport", tier="instagram")
        client = mock.Mock()
        with mock.patch.object(desk, "configured", return_value=True):
            desk.publish(client=client)
        client.assert_not_called()
        self.assertFalse(client.method_calls)

    def test_reel_and_digest_leave_sport_out(self):
        self.write_post("e", status="published", topic="Sport", published=stamp(minutes=5), score=50)
        self.write_post("f", status="published", topic="Markets", published=stamp(minutes=5), score=1)
        with mock.patch.object(reel, "today", return_value=stamp(minutes=5)[:10]):
            self.assertEqual([p["id"] for p in reel.top_posts()], ["f"])


class SiteBuild(Tmp):
    def build(self, sport=3):
        topics = ["Economy", "Markets", "Business", "Tech", "Politics", "World"]
        for i in range(24):
            self.write_post(f"2026-11-26-10{i:02d}-1", status="published", published=stamp(hours=i // 3), headlines=[f"Central bank holds rates {i}"],
                            dek="Dek.", body="Body.", sources=["CNBC"], source_urls=["https://www.cnbc.com/x"], topic=topics[i % 6], score=9)
        for i in range(sport):
            self.write_post(f"2026-11-26-11{i:02d}-1", status="web", tier="web", published=stamp(hours=i), headlines=[f"Arsenal beat Chelsea {i}-0"],
                            dek="Arsenal won at home.", body="Arsenal won at home.", sources=["BBC Sport", "The Guardian"],
                            source_urls=["https://www.bbc.co.uk/sport/football/1", "https://www.theguardian.com/football/2"], topic="Sport", score=9)
        stub = lambda *a: a[-1].write_bytes(b"jpg") or True  # noqa: E731
        with mock.patch.object(site, "og_image", side_effect=stub), mock.patch.object(site, "share_card", side_effect=stub):
            return site.build(self.root / "_site")

    def test_sport_page_nav_front_block_feed_and_sitemap(self):
        out = self.build()
        front = (out / "index.html").read_text()
        self.assertIn(f'href="{site.BASE}/sport/"', front)
        self.assertIn('class="sportblk"', front)
        self.assertGreater(front.index('class="sportblk"'), front.index('class="sects"'))  # below the business sections
        page = (out / "sport" / "index.html").read_text()
        self.assertIn("Arsenal beat Chelsea", page)
        self.assertIn('aria-current="page">Sport</a>', page)
        self.assertEqual(len(ET.parse(out / "sport" / "feed.xml").getroot().findall("channel/item")), 3)
        locs = [u.text for u in ET.parse(out / "sitemap.xml").getroot().iterfind(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertTrue(any(l.endswith("/sport/") for l in locs))
        self.assertTrue(any(l.endswith("/s/2026-11-26-1100-1/") for l in locs))
        self.assertFalse((out / "t" / "sport").exists())

    def test_business_pages_stay_business(self):
        out = self.build()
        for f in ("latest/index.html", "feed.xml", "brief/index.html"):
            self.assertNotIn("Arsenal", (out / f).read_text(), f)
        lead = re.search(r'<h[12] class="lh">(.*?)</h[12]>', (out / "index.html").read_text(), re.S).group(1)
        self.assertNotIn("Arsenal", lead)

    def test_sport_article_page_links_its_section_and_its_sources(self):
        out = self.build()
        h = (out / "s" / "2026-11-26-1100-1" / "index.html").read_text()
        self.assertIn(f'<a class="kick" href="{site.BASE}/sport/">Sport</a>', h)
        self.assertIn('>BBC Sport</a>', h)
        self.assertIn("https://www.bbc.co.uk/sport/football/1", h)
        self.assertNotIn("Central bank", h.split('class="related"')[-1].split("</section>")[0])  # related news stays in sport

    def test_no_sport_posts_leaves_no_block_and_a_page_without_articles(self):
        out = self.build(sport=0)
        self.assertNotIn("sportblk", (out / "index.html").read_text())

    def test_no_ui_text_calls_news_a_story(self):
        out = self.build()
        for f in ("index.html", "sport/index.html"):
            visible = re.sub(r"<[^>]+>", " ", (out / f).read_text())
            self.assertNotRegex(visible, r"\bstor(y|ies)\b", f)


if __name__ == "__main__":
    unittest.main()
