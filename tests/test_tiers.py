import json
import os
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import desk, platforms, site
from test_desk import FakeIG, Tmp, story
from test_platforms import SECRETS

def stamp(**kw):
    return (desk.now() - timedelta(**kw)).isoformat(timespec="seconds")


class Day(Tmp):
    """A day directory of scored stories, as `daily` leaves it for queue()."""
    def day(self, scores, topic="Tech"):
        d = self.root / f"out{len(list(self.root.glob('out*')))}"
        (d / "pack").mkdir(parents=True)
        rows = [story(i) for i in range(1, len(scores) + 1)]
        for (m, s), score in zip(rows, scores):
            m["score"] = s["score"] = score
            s["topic"] = topic
        (d / "pack" / "manifest.json").write_text(json.dumps([m for m, _ in rows]))
        (d / "digest.json").write_text(json.dumps({"final": {"top": [s for _, s in rows]}}))
        return d

    def queued(self, scores, **kw):
        return [json.loads(p.read_text()) for p in desk.queue(self.day(scores, **kw), batch="b", render=False)]

    def cap(self, n):
        desk._save(desk.STATE / "pace.json", {"cap": n, "since": stamp(), "last_block": ""})


class Config(Tmp):
    def test_shipped_thresholds_are_ordered(self):
        # desk.HERE is patched to a temp dir in these tests; the shipped file sits beside the package
        real = json.loads((Path(desk.__file__).resolve().parent.parent / "desk.json").read_text())
        self.assertLessEqual(real["site_min_score"], real["social_min_score"])
        self.assertLessEqual(real["social_min_score"], real["facebook_min_score"])
        self.assertGreater(real["social_spacing_minutes"], 0)

    def test_without_the_new_keys_the_bar_is_min_score(self):
        cfg = {k: v for k, v in desk.CONFIG.items() if k != "site_min_score"}
        with mock.patch.object(desk, "CONFIG", cfg):
            self.assertEqual(desk.site_min_score(), cfg["min_score"])


class Select(Tmp):
    def test_website_bar_not_instagram_bar_picks_stories(self):
        fresh = desk.now().isoformat()
        rows = [{"title": t, "score": sc, "published": fresh, "outlets": ["TechCrunch"], "url": t, "links": [t]}
                for t, sc in (("Anthropic releases coding agent", desk.CONFIG["site_min_score"]),
                              ("Mistral raises funding round", desk.CONFIG["site_min_score"] - 0.1))]
        self.assertEqual([s["title"] for s in desk.select(rows)], ["Anthropic releases coding agent"])

    def test_a_web_post_counts_as_posted_for_repeats(self):
        fresh = desk.now().isoformat()
        self.write_post("w", status="web", published=fresh, urls=["x"], headlines=["Google previews robotics model"])
        row = {"title": "Google previews robotics model", "score": 12, "published": fresh, "outlets": ["TechCrunch"],
               "url": "other", "links": ["other"]}
        self.assertEqual(desk.select([row]), [])


class Tiers(Day):
    def test_most_important_take_instagrams_room_the_rest_go_to_the_web_at_once(self):
        self.cap(2)
        got = {p["urls"][0]: p for p in self.queued([8.1, 9.5, 8.4, 9.0, 8.2])}
        by_score = sorted(got.values(), key=lambda p: -p["score"])
        self.assertEqual([p["tier"] for p in by_score], ["instagram", "instagram", "web", "web", "web"])
        self.assertEqual([p["status"] for p in by_score], ["queued", "queued", "web", "web", "web"])
        for p in by_score[:2]:
            self.assertIn("publish_after", p)
            self.assertNotIn("published", p)
        for p in by_score[2:]:
            self.assertTrue(p["published"])
            self.assertNotIn("publish_after", p)
            self.assertEqual(p["story"], "")
            self.assertEqual(p["cards"], ["card.jpg", "detail.jpg"])  # same rendering, so the site has its images

    def test_room_is_what_is_left_of_the_cap_after_published_and_queued(self):
        self.cap(3)
        self.write_post("pub", status="published", published=desk.now().isoformat(), kind=None)
        self.write_post("q", status="queued", urls=["z"], headlines=["Other news item"])
        got = self.queued([9.0, 8.5, 8.2])
        self.assertEqual(sorted(p["tier"] for p in got), ["instagram", "web", "web"])

    def test_full_cap_sends_everything_to_the_web(self):
        self.cap(1)
        self.write_post("pub", status="published", published=desk.now().isoformat(), urls=["z"], headlines=["Other news item"])
        got = self.queued([9.0, 8.5])
        self.assertEqual({p["status"] for p in got}, {"web"})

    def test_below_instagrams_own_bar_is_web_even_with_room(self):
        with mock.patch.dict(desk.CONFIG, {"min_score": 9.0}):
            got = self.queued([9.5, 8.5])
        self.assertEqual({p["score"]: p["tier"] for p in got}, {9.5: "instagram", 8.5: "web"})

    def test_instagram_takes_only_what_the_schedule_fits_the_rest_goes_to_the_web(self):
        fits = desk.CONFIG["max_hours_ahead"] * 60 // desk.CONFIG["spacing_minutes"] + 1
        scores = [9.0 + i / 10 for i in range(fits + 2)]
        got = self.queued(scores)
        self.assertEqual(len(got), len(scores))  # no story is left behind: each is on Instagram's schedule or the web
        ig = sorted((p["score"] for p in got if p["tier"] == "instagram"), reverse=True)
        self.assertEqual(ig, sorted(scores, reverse=True)[:fits])
        self.assertEqual({p["status"] for p in got if p["tier"] == "web"}, {"web"})
        times = sorted(p["publish_after"] for p in got if p["tier"] == "instagram")
        self.assertEqual(len(set(times)), fits)

    def test_audit_still_holds_a_web_post(self):
        self.cap(0)
        got = self.queued([9.0], topic="")
        self.assertEqual(got[0]["status"], "held")
        self.assertNotIn("published", got[0])
        self.assertEqual(site.published(), [])

    def test_a_repeat_run_never_requeues_a_web_story(self):
        self.cap(0)
        d = self.day([9.0, 8.5])
        self.assertEqual(len(desk.queue(d, batch="b", render=False)), 2)
        self.assertEqual(desk.queue(d, batch="c", render=False), [])


class WebNeverGoesToInstagram(Tmp):
    def test_publish_leaves_web_posts_alone(self):
        p = self.write_post("w", status="web", tier="web", published=stamp(minutes=1))
        ig = FakeIG()
        self.assertEqual(desk.publish(client=ig), 0)
        self.assertEqual(ig.posted, [])
        self.assertEqual(json.loads(p.read_text())["status"], "web")

    def test_stale_instagram_post_becomes_web_and_is_never_posted(self):
        old = stamp(hours=desk.CONFIG["max_publish_age_hours"] + 1)
        stale = self.write_post("stale", created=old, tier="instagram")
        ig = FakeIG()
        desk.publish(client=ig)
        got = json.loads(stale.read_text())
        self.assertEqual((got["status"], got["tier"]), ("web", "web"))
        self.assertTrue(got["published"])
        self.assertEqual(ig.posted, [])
        self.assertEqual([p["id"] for p in site.published()], ["stale"])

    def test_cooldown_does_not_keep_an_expired_post_off_the_web(self):
        desk._save(desk.STATE / "cooldown.json", {"until": (desk.now() + timedelta(hours=5)).isoformat()})
        stale = self.write_post("stale", created=stamp(hours=desk.CONFIG["max_publish_age_hours"] + 1))
        fresh = self.write_post("fresh")
        ig = FakeIG()
        self.assertEqual(desk.publish(client=ig), 0)
        self.assertEqual(json.loads(stale.read_text())["status"], "web")
        self.assertEqual(json.loads(fresh.read_text())["status"], "queued")  # still waits for Instagram
        self.assertEqual(ig.posted, [])

    def test_a_post_with_a_send_marker_is_expired_not_mirrored(self):
        p = self.write_post("m", created=stamp(hours=desk.CONFIG["max_publish_age_hours"] + 1), attempted=stamp(hours=13))
        desk.publish(client=FakeIG())
        self.assertEqual(json.loads(p.read_text())["status"], "expired")
        self.assertEqual(site.published(), [])


class Social(Tmp):
    def setUp(self):
        super().setUp()
        extra = [mock.patch.dict(os.environ, SECRETS), mock.patch.dict(desk.CONFIG, {"platforms": {n: True for n in platforms.NAMES}, "lead_when_ig_blocked": False})]
        for p in extra:
            p.start()
            self.addCleanup(p.stop)
        self.sent = []

        class Fake:
            def __init__(self, name, sent):
                self.name, self.sent = name, sent

            def post(self, post):
                self.sent.append((self.name, post["id"]))
                return {"id": f"{self.name}-{post['id']}", "url": ""}
        self.fact = {n: (lambda n=n: Fake(n, self.sent)) for n in platforms.NAMES}

    def web(self, pid, score, **kw):
        kw.setdefault("published", stamp(minutes=5))
        return self.write_post(pid, status="web", tier="web", score=score, urls=[pid], headlines=[f"Story {pid}"], **kw)

    def run_social(self):
        return desk.web_social(self.fact)

    def test_only_bluesky_and_threads_never_telegram_or_facebook(self):
        self.web("a", desk.CONFIG["social_min_score"])
        self.assertEqual(self.run_social(), 1)
        self.assertEqual(sorted(self.sent), [("bluesky", "a"), ("threads", "a")])

    def test_below_social_min_score_stays_on_the_site_only(self):
        p = self.web("a", desk.CONFIG["social_min_score"] - 0.1)
        self.assertEqual(self.run_social(), 0)
        self.assertEqual(self.sent, [])
        self.assertNotIn("platforms", json.loads(p.read_text()))

    def test_one_post_per_run_highest_score_first_then_spaced(self):
        hi = desk.CONFIG["social_min_score"] + 1
        self.web("low", hi)
        self.web("high", hi + 1)
        self.run_social()
        self.assertEqual({i for _, i in self.sent}, {"high"})
        self.assertEqual(self.run_social(), 0)  # inside social_spacing_minutes
        self.assertEqual({i for _, i in self.sent}, {"high"})
        gap = desk.CONFIG["social_spacing_minutes"] + 1
        sent = desk.QUEUE / "high" / "post.json"
        got = json.loads(sent.read_text())
        for slot in got["platforms"].values():
            slot["at"] = stamp(minutes=gap)
        sent.write_text(json.dumps(got))
        self.assertEqual(self.run_social(), 1)
        self.assertEqual({i for _, i in self.sent}, {"high", "low"})

    def test_a_post_is_never_sent_twice(self):
        self.web("a", 12)
        self.run_social()
        for p in (desk.QUEUE / "a" / "post.json",):
            got = json.loads(p.read_text())
            for slot in got["platforms"].values():
                slot["at"] = stamp(hours=3)
            p.write_text(json.dumps(got))
        self.assertEqual(self.run_social(), 0)
        self.assertEqual(len(self.sent), 2)

    def test_an_attempted_marker_without_a_result_is_not_retried(self):
        p = self.web("a", 12, platforms={"bluesky": {"attempted": stamp(hours=2)}, "threads": {"attempted": stamp(hours=2)}})
        self.assertEqual(self.run_social(), 0)
        self.assertEqual(self.sent, [])
        self.assertIn("attempted", json.loads(p.read_text())["platforms"]["bluesky"])

    def test_a_platform_in_cooldown_is_left_alone_the_other_still_goes(self):
        desk._save(desk.STATE / "cooldown-bluesky.json", {"until": (desk.now() + timedelta(hours=3)).isoformat()})
        p = self.web("a", 12)
        self.run_social()
        self.assertEqual(self.sent, [("threads", "a")])
        self.assertNotIn("bluesky", json.loads(p.read_text())["platforms"])  # still open once the cooldown ends

    def test_both_in_cooldown_means_nothing_is_attempted(self):
        for n in ("bluesky", "threads"):
            desk._save(desk.STATE / f"cooldown-{n}.json", {"until": (desk.now() + timedelta(hours=3)).isoformat()})
        self.web("a", 12)
        self.assertEqual(self.run_social(), 0)

    def test_old_web_posts_are_not_pushed_to_social(self):
        self.web("old", 12, published=stamp(hours=desk.CONFIG["max_publish_age_hours"] + 1))
        self.assertEqual(self.run_social(), 0)

    def test_switched_off_platforms_are_skipped(self):
        self.web("a", 12)
        with mock.patch.dict(desk.CONFIG, {"platforms": {"threads": False, "bluesky": True}}):
            self.run_social()
        self.assertEqual(self.sent, [("bluesky", "a")])

    def test_instagram_published_posts_keep_every_platform(self):
        p = self.write_post("ig", status="published", tier="instagram", published=stamp(minutes=1), score=13, urls=["ig"],
                            headlines=["Big story"], media_id="m", permalink="https://instagram.com/p/x")
        desk.cross_post(json.loads(p.read_text()), p, self.fact)
        self.assertEqual({n for n, _ in self.sent}, {"threads", "facebook", "bluesky", "telegram"})

    def test_publish_runs_the_web_step_after_instagram_and_survives_its_crash(self):
        self.web("a", 12)
        with mock.patch.object(desk, "web_social", side_effect=RuntimeError("boom")):
            self.assertEqual(desk.publish(client=FakeIG()), 0)
        with mock.patch.object(desk, "web_social") as step:
            desk.publish(client=FakeIG())
        step.assert_called_once()


class SiteTier(Tmp):
    def test_web_posts_are_on_the_site_without_claiming_instagram(self):
        for pid, status, extra in (("2026-11-26-1300-1", "published", {"permalink": "https://instagram.com/p/x"}),
                                   ("2026-11-26-1300-2", "web", {}), ("2026-11-26-1300-3", "queued", {})):
            self.write_post(pid, status=status, published=desk.now().isoformat(), headlines=[f"Headline {pid[-1]}"], dek="Dek.",
                            body="Body.", sources=["CNBC"], source_urls=["https://www.cnbc.com/x"], score=9, **extra)
            (desk.MEDIA / pid).mkdir(parents=True)
            (desk.MEDIA / pid / "thumb.jpg").write_text("x")
        out = site.build(self.root / "_site")
        index = (out / "index.html").read_text()
        self.assertIn("Headline 1", index)
        self.assertIn("Headline 2", index)
        self.assertNotIn("Headline 3", index)
        web_page = (out / "s" / "2026-11-26-1300-2" / "index.html").read_text()
        self.assertNotIn("The post on Instagram", web_page)
        ig_page = (out / "s" / "2026-11-26-1300-1" / "index.html").read_text()
        self.assertIn("The post on Instagram", ig_page)
        self.assertIn("2026-11-26-1300-2", (out / "feed.xml").read_text())
        self.assertIn("/s/2026-11-26-1300-2/", (out / "sitemap.xml").read_text())

    def test_the_week_page_ranks_by_score(self):
        for pid, status, score in (("2026-11-26-1300-1", "published", 8.2), ("2026-11-26-1300-2", "web", 11.0)):
            self.write_post(pid, status=status, published=desk.now().isoformat(), headlines=[f"Headline {pid[-1]}"], score=score,
                            source_urls=["https://www.cnbc.com/x"])
            (desk.MEDIA / pid).mkdir(parents=True)
            (desk.MEDIA / pid / "thumb.jpg").write_text("x")
        week = (site.build(self.root / "_site") / "week" / "index.html").read_text()
        self.assertLess(week.index("Headline 2"), week.index("Headline 1"))
