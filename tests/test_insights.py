"""The weekly insights loop: readers, the per-platform measure, the analysis and every guard rail on the feedback."""
import io
import json
import os
import unittest
import urllib.parse
from datetime import timedelta
from unittest import mock

from aidaily import desk, insights, platforms
from test_desk import Tmp


def post(pid, hours_ago=5, **kw):
    p = {"id": pid, "status": "published", "published": (desk.now() - timedelta(hours=hours_ago)).isoformat(timespec="seconds"),
         "headlines": ["H"], "topic": "Markets", "categories": ["markets"], "cards": ["card.jpg", "detail.jpg"],
         "photo_file": "x.jpg", "score": 9.0}
    p.update(kw)
    return p


def ig(reach, shares=0, saved=0):
    return {"metrics": {"instagram": {"reach": reach, "shares": shares, "saved": saved}}}


class Value(unittest.TestCase):
    def test_instagram_is_sends_and_saves_per_reach_and_needs_reach(self):
        self.assertAlmostEqual(insights.value("instagram", {"reach": 100, "shares": 3, "saved": 2}), 0.05)
        self.assertIsNone(insights.value("instagram", {"reach": 49, "shares": 3}))

    def test_threads_is_conversation_per_view(self):
        self.assertAlmostEqual(insights.value("threads", {"views": 200, "replies": 2, "reposts": 1, "quotes": 1, "shares": 0}), 0.02)
        self.assertIsNone(insights.value("threads", {"views": 10, "replies": 5}))

    def test_bluesky_counts_reposts_double_and_telegram_uses_views(self):
        self.assertEqual(insights.value("bluesky", {"likes": 3, "reposts": 1, "quotes": 1, "replies": 2}), 9)
        self.assertEqual(insights.value("telegram", {"views": 40}), 40.0)
        self.assertIsNone(insights.value("telegram", {"views": 0}))

    def test_facebook_rate_when_reach_known_else_count(self):
        self.assertAlmostEqual(insights.value("facebook", {"reach": 100, "shares": 1, "comments": 1, "reactions": 3}), 0.05)
        self.assertEqual(insights.value("facebook", {"shares": 1, "comments": 0, "reactions": 2}), 3.0)

    def test_meta_rows_in_both_shapes(self):
        rows = [{"name": "views", "values": [{"value": 12}]}, {"name": "followers_count", "total_value": {"value": 7}}]
        self.assertEqual(insights._metric_rows(rows), {"views": 12, "followers_count": 7})


class Analysis(unittest.TestCase):
    def rows(self):
        # five Markets posts at twice the typical send rate, five Tech posts at the typical rate
        out = [post(f"m{i}", topic="Markets", categories=["markets"], **ig(1000, 20)) for i in range(5)]
        out += [post(f"t{i}", topic="Tech", categories=["tech"], **ig(1000, 10)) for i in range(5)]
        return out

    def test_lift_is_relative_to_the_platform_median_and_shrunk(self):
        t = insights.analyse(self.rows())
        # median of [20]*5+[10]*5 per 1000 is 0.015: Markets 1.333, Tech 0.667; shrunk by 5/15
        self.assertAlmostEqual(t["topic"]["Markets"]["lift"], round(1 + (0.02 / 0.015 - 1) * 5 / 15, 3))
        self.assertEqual(t["topic"]["Markets"]["n"], 5)
        self.assertLess(t["topic"]["Tech"]["lift"], 1)

    def test_groups_cover_format_visual_tier_and_hour(self):
        t = insights.analyse(self.rows() + [post("w", hours_ago=72, status="web", photo_file="", metrics={"telegram": {"views": 10}})])
        for dim in ("format", "visual", "tier", "hour_utc", "category"):
            self.assertIn(dim, t)
        self.assertIn("text card", t["visual"])
        self.assertIn("web only", t["format"])

    def test_signals_need_min_n(self):
        rows = [post(f"m{i}", topic="Markets", **ig(1000, 50)) for i in range(4)] + [post(f"t{i}", topic="Tech", **ig(1000, 5)) for i in range(4)]
        self.assertFalse(any(s.startswith("topic") for s in insights.signals(insights.analyse(rows))))


class Feedback(unittest.TestCase):
    def test_weights_need_min_n_stay_in_range_and_move_one_step(self):
        table = {"category": {"markets": {"n": 30, "lift": 1.9}, "tech": {"n": 30, "lift": 0.2}, "rare": {"n": 2, "lift": 3.0}}}
        w = insights.next_weights(table, {"rare": 1.1})
        self.assertEqual(w["markets"], 1.1)   # wanted 1.25, one step of 0.1 from 1.0
        self.assertEqual(w["tech"], 0.9)
        self.assertEqual(w["rare"], 1.1)      # too few posts: unchanged
        w2 = insights.next_weights(table, w)
        self.assertEqual(w2["markets"], 1.2)
        self.assertEqual(insights.next_weights(table, {"markets": 1.2})["markets"], 1.25)  # the ceiling

    def tg_rows(self, good_hour, other_hour):
        rows, day = [], desk.now() - timedelta(days=3)
        for i in range(6):
            rows.append(post(f"g{i}", metrics={"telegram": {"views": 100}}))
            rows[-1]["published"] = day.replace(hour=good_hour).isoformat(timespec="seconds")
            rows.append(post(f"o{i}", metrics={"telegram": {"views": 20}}))
            rows[-1]["published"] = day.replace(hour=other_hour).isoformat(timespec="seconds")
        return rows

    def test_digest_hour_moves_one_hour_toward_the_best_and_stays_in_window(self):
        self.assertEqual(insights.next_digest_hour(self.tg_rows(21, 19), 19), 20)
        self.assertEqual(insights.next_digest_hour(self.tg_rows(17, 19), 19), 18)
        self.assertEqual(insights.next_digest_hour(self.tg_rows(9, 19), 19), 19)  # 9 UTC is outside the window

    def test_digest_hour_stays_without_data_for_the_current_hour(self):
        self.assertEqual(insights.next_digest_hour(self.tg_rows(21, 20), 19), 19)

    def quiet_rows(self, bad_from=16, score=9.0):
        rows = []
        for h in range(24):
            for i in range(6):
                v = 200 if h < bad_from else 1
                p = post(f"{h}-{i}", status="web", score=score, metrics={"bluesky": {"likes": v}})
                p["published"] = (desk.now() - timedelta(days=3)).replace(hour=h).isoformat(timespec="seconds")
                rows.append(p)
        return rows

    def test_quiet_hours_need_min_n_and_are_capped(self):
        quiet = insights.next_quiet_hours(self.quiet_rows())
        self.assertEqual(len(quiet), insights.MAX_QUIET)
        self.assertTrue(all(int(h) >= 16 for h in quiet))
        self.assertEqual(insights.next_quiet_hours(self.quiet_rows()[:4]), {})

    def test_breaking_posts_are_left_out_of_the_scoring(self):
        self.assertEqual(insights.next_quiet_hours(self.quiet_rows(score=desk.CONFIG["breaking_score"])), {})

    def test_a_quiet_hour_stays_two_weeks(self):
        today = desk.now().date()
        recent = (today - timedelta(days=insights.QUIET_KEEP_DAYS - 1)).isoformat()
        old = (today - timedelta(days=insights.QUIET_KEEP_DAYS)).isoformat()
        got = insights.next_quiet_hours([], {"3": recent, "4": old}, today)
        self.assertEqual(got, {"3": recent})

    def test_counts_wait_48_hours(self):
        fresh = [post(f"f{i}", hours_ago=10, metrics={"telegram": {"views": 5}}) for i in range(3)]
        aged = [post(f"a{i}", hours_ago=60, metrics={"telegram": {"views": 5}}) for i in range(3)]
        self.assertEqual({p["id"] for p, _ in insights.lifts(fresh + aged)}, {"a0", "a1", "a2"})
        rate = [post("r", hours_ago=2, **ig(1000, 10))]  # rates have their audience size: read at once
        self.assertEqual(len(insights.lifts(rate)), 1)

    def test_ramp_hold_when_recent_sends_fall(self):
        recent = [post(f"r{i}", hours_ago=24, **ig(1000, 5)) for i in range(10)]
        before = [post(f"b{i}", hours_ago=24 * 12, **ig(1000, 10)) for i in range(10)]
        self.assertTrue(insights.ramp_hold(recent + before, desk.now()))
        self.assertFalse(insights.ramp_hold(recent[:9] + before, desk.now()))  # too few recent posts
        steady = [post(f"s{i}", hours_ago=24, **ig(1000, 9)) for i in range(10)]
        self.assertFalse(insights.ramp_hold(steady + before, desk.now()))


class FakeSource:
    def __init__(self, name, numbers, followers=None, fail=False):
        self.name, self.numbers, self._followers, self.fail = name, numbers, followers, fail

    def fetch(self, p):
        if self.fail:
            raise RuntimeError("HTTP 500")
        return self.numbers.get(p["id"])

    def followers(self):
        return self._followers


class Run(Tmp):
    def test_run_writes_metrics_weights_learned_followers_and_report(self):
        for i in range(6):
            self.write_post(f"p{i}", status="published", published=(desk.now() - timedelta(hours=3)).isoformat(timespec="seconds"),
                            categories=["markets" if i < 3 else "tech"], media_id=str(i))
        self.write_post("old", status="published", published=(desk.now() - timedelta(days=40)).isoformat(timespec="seconds"))
        self.write_post("st", status="published", kind="story", published=desk.now().isoformat(timespec="seconds"))
        numbers = {f"p{i}": {"reach": 1000, "shares": 30 if i < 3 else 5, "saved": 0} for i in range(6)}
        factories = {"instagram": lambda: FakeSource("instagram", numbers, 321),
                     "threads": lambda: FakeSource("threads", {}, fail=True),
                     "telegram": mock.Mock(side_effect=LookupError("TG_CHANNEL"))}
        report = insights.run(factories)
        self.assertEqual(report["posts"], 6)
        self.assertEqual(report["measured"], 6)
        self.assertIn("telegram", report["missing"])
        self.assertEqual(report["errors"]["threads"]["count"], 6)
        p0 = json.loads((desk.QUEUE / "p0" / "post.json").read_text())
        self.assertEqual(p0["metrics"]["instagram"]["shares"], 30)
        self.assertEqual(p0["insights"]["shares"], 30)  # the site's "most shared" still reads this
        self.assertEqual(json.loads((desk.STATE / "followers.json").read_text())["Instagram"], 321)
        learned = json.loads((desk.STATE / "learned.json").read_text())
        self.assertEqual(set(learned) - {"updated"}, {"digest_hour", "quiet_hours", "ramp_hold"})
        week = desk.now().strftime("%G-W%V")
        saved = json.loads((desk.STATE / "insights" / f"{week}.json").read_text())
        self.assertEqual(saved["account"]["followers_count"], 321)  # site.stats() reads this key
        self.assertIn("guard_rails", saved)
        self.assertIn("Insights", insights.summary_md(report))

    def test_nothing_connected_is_a_quiet_report(self):
        report = insights.run({"threads": mock.Mock(side_effect=LookupError("x"))})
        self.assertEqual(report["posts"], 0)
        self.assertEqual(report["signals"], [])


class FakeIG:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def call(self, method, path, params=None, versioned=True):
        from aidaily.instagram import IGError
        self.calls.append(params["metric"])
        if self.fail:
            raise IGError(self.fail)
        return {"data": [{"name": m, "values": [{"value": 3}]} for m in params["metric"].split(",")]}

    def media_insights(self, media_id, metrics):
        self.calls.append("per-metric")
        return {"reach": 100}

    def followers(self):
        return {"followers_count": 1}


class InstagramReader(Tmp):
    def test_one_comma_joined_call_per_post(self):
        c = FakeIG()
        got = insights.Instagram(client=c).fetch({"media_id": "1"})
        self.assertEqual(len(c.calls), 1)
        self.assertEqual(c.calls[0], ",".join(insights.Instagram.METRICS))
        self.assertEqual(got["reach"], 3)

    def test_falls_back_per_metric_only_on_a_refusal(self):
        c = FakeIG(fail='GET 1/insights: HTTP 400: {"error":{"code":100}}')
        self.assertEqual(insights.Instagram(client=c).fetch({"media_id": "1"}), {"reach": 100})
        self.assertEqual(c.calls[-1], "per-metric")

    def test_a_block_goes_to_note_block_and_stops_instagram(self):
        for i in range(3):
            self.write_post(f"p{i}", status="published", media_id=str(i), published=desk.now().isoformat(timespec="seconds"))
        c = FakeIG(fail='GET x/insights: HTTP 400: {"error":{"code":4}}')
        report = insights.run({"instagram": lambda: insights.Instagram(client=c)})
        self.assertEqual(len(c.calls), 1)  # the first block ends the run's Instagram reads
        self.assertTrue(desk.cooldown_until())
        self.assertEqual(report["errors"]["instagram"]["count"], 1)

    def test_no_instagram_call_during_a_cooldown(self):
        desk.STATE.mkdir(parents=True, exist_ok=True)
        (desk.STATE / "cooldown.json").write_text(json.dumps({"until": (desk.now() + timedelta(hours=3)).isoformat()}))
        self.write_post("p", status="published", media_id="1", published=desk.now().isoformat(timespec="seconds"))
        factory = mock.Mock()
        report = insights.run({"instagram": factory})
        factory.assert_not_called()
        self.assertIn("cooldown", report["missing"]["instagram"])

    def test_old_posts_keep_their_numbers_and_new_ones_are_read(self):
        self.assertTrue(insights.due(post("x", hours_ago=24 * 20), "instagram"))  # never measured
        old = post("x", hours_ago=24 * 20, **ig(1000, 5))
        self.assertFalse(insights.due(old, "instagram"))
        self.assertTrue(insights.due(post("x", hours_ago=24 * 3, **ig(1000, 5)), "instagram"))


class Readers(unittest.TestCase):
    def test_telegram_subscribers_and_window_cover(self):
        page = ('<span class="counter_value">1.5K</span> <span class="counter_type">subscribers</span>'
                '<div data-post="boardread/50"><span class="tgme_widget_message_views">9</span></div>')
        with mock.patch.dict(os.environ, {"TG_CHANNEL": "@boardread"}):
            t = insights.Telegram(opener=lambda req, timeout, context: io.BytesIO(page.encode()))
        t.PAGES = 3
        t.prefetch([{"platforms": {"telegram": {"id": "10"}}}])
        self.assertEqual(t.followers(), 1500)
        self.assertTrue(t.short)  # every page stops at 50, never reaching message 10
        with mock.patch.dict(os.environ, {"TG_CHANNEL": "@boardread"}):
            t2 = insights.Telegram(opener=lambda req, timeout, context: io.BytesIO(page.encode()))
        t2.prefetch([{"platforms": {"telegram": {"id": "60"}}}])
        self.assertFalse(t2.short)

    def test_bluesky_without_a_handle_reads_no_profile(self):
        with mock.patch.dict(os.environ, {"BSKY_HANDLE": ""}):
            self.assertIsNone(insights.Bluesky(opener=mock.Mock(side_effect=AssertionError)).followers())

    def test_telegram_page_views_pairs_each_block_with_its_own_counter(self):
        html = ('<div data-post="boardread/5"><span class="tgme_widget_message_views">1.2K</span></div>'
                '<div data-post="boardread/6">service message</div>'
                '<div data-post="boardread/7"><span class="tgme_widget_message_views">34</span></div>')
        self.assertEqual(insights.page_views(html), {5: 1200, 7: 34})

    def test_telegram_reads_username_from_accounts_when_channel_is_numeric(self):
        with mock.patch.dict(os.environ, {"TG_CHANNEL": "-100123", "TG_BOT_TOKEN": "t"}):
            self.assertEqual(insights.Telegram().username, "boardread")

    def test_bluesky_batches_25_uris_per_call(self):
        calls = []

        def opener(req, timeout, context):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            calls.append(len(q["uris"]))
            return io.BytesIO(json.dumps({"posts": [{"uri": u, "likeCount": 1} for u in q["uris"]]}).encode())

        rows = [{"platforms": {"bluesky": {"id": f"at://did:plc:x/app.bsky.feed.post/{i}"}}} for i in range(30)]
        b = insights.Bluesky(opener=opener)
        b.prefetch(rows)
        self.assertEqual(calls, [25, 5])
        self.assertEqual(b.fetch(rows[29])["likes"], 1)

    def test_errors_carry_no_url_so_no_token_reaches_a_log(self):
        import urllib.error

        def opener(req, timeout, context):
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"{}"))

        with mock.patch.dict(os.environ, {"THREADS_TOKEN": "SECRET123", "THREADS_USER_ID": "1"}):
            t = insights.Threads(opener=opener)
            with self.assertRaises(RuntimeError) as e:
                t.fetch({"platforms": {"threads": {"id": "9"}}})
        self.assertNotIn("SECRET123", str(e.exception))


class DeskUsesLearned(Tmp):
    def learned(self, **kw):
        desk.STATE.mkdir(parents=True, exist_ok=True)
        kw.setdefault("updated", desk.now().isoformat(timespec="seconds"))
        (desk.STATE / "learned.json").write_text(json.dumps(kw))

    def test_learned_values_expire_after_two_weeks(self):
        self.learned(digest_hour=21, updated=(desk.now() - timedelta(days=insights.LEARNED_DAYS + 1)).isoformat(timespec="seconds"))
        self.assertEqual(insights.learned_value("digest_hour", 19), 19)
        self.learned(digest_hour=21)
        self.assertEqual(insights.learned_value("digest_hour", 19), 21)

    def test_quiet_hours_read_from_the_dict_shape(self):
        self.learned(quiet_hours={"3": "2026-11-20", "4": "2026-11-20"})
        self.assertEqual(insights.learned_value("quiet_hours", []), [3, 4])

    def test_cap_held_is_logged_once_a_day(self):
        desk.STATE.mkdir(parents=True, exist_ok=True)
        since = (desk.now() - timedelta(days=30)).isoformat(timespec="seconds")
        (desk.STATE / "pace.json").write_text(json.dumps({"cap": 12, "since": since, "last_block": ""}))
        self.learned(ramp_hold=True)
        with mock.patch("builtins.print") as pr:
            desk.ramp()
            desk.ramp()
        self.assertEqual(sum("held" in str(c) for c in pr.call_args_list), 1)

    def test_ramp_is_held_never_cut(self):
        desk.STATE.mkdir(parents=True, exist_ok=True)
        since = (desk.now() - timedelta(days=30)).isoformat(timespec="seconds")
        (desk.STATE / "pace.json").write_text(json.dumps({"cap": 12, "since": since, "last_block": ""}))
        self.learned(ramp_hold=True)
        desk.ramp()
        self.assertEqual(desk.pace()["cap"], 12)
        self.learned(ramp_hold=False)
        desk.ramp()
        self.assertEqual(desk.pace()["cap"], 12 + desk.CONFIG["daily_posts_step"])

    def test_story_url_carries_utm_only_with_the_switch(self):
        self.assertNotIn("utm_", desk.story_url("a", "threads"))
        with mock.patch.dict(desk.CONFIG["growth"], {"utm": True}):
            self.assertTrue(desk.story_url("a", "threads").endswith("/s/a/?utm_source=threads&utm_medium=social"))
            self.assertNotIn("utm_", desk.story_url("a"))

    def test_web_social_waits_in_quiet_hours_except_breaking(self):
        self.learned(quiet_hours={str(desk.now().hour): desk.now().date().isoformat()})
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}):
            self.write_post("w1", status="web", score=desk.CONFIG["social_min_score"], published=desk.now().isoformat(timespec="seconds"))
            with mock.patch.object(desk, "cross_post") as cp:
                self.assertEqual(desk.web_social(), 0)
                cp.assert_not_called()
            self.write_post("w2", status="web", score=desk.CONFIG["breaking_score"], published=desk.now().isoformat(timespec="seconds"))
            with mock.patch.object(desk, "cross_post") as cp:
                self.assertEqual(desk.web_social(), 1)
                self.assertEqual(cp.call_args[0][0]["id"], "w2")

    def test_digest_follows_the_learned_hour(self):
        at = desk.now().replace(hour=21, minute=5)
        for i in range(3):
            self.write_post(f"d{i}", status="published", score=9, published=(at - timedelta(hours=1)).isoformat(timespec="seconds"))
        client = mock.Mock()
        client.digest.return_value = {"id": "1"}
        factories = {"telegram": mock.Mock(return_value=client)}
        with mock.patch.object(desk, "now", return_value=at), mock.patch.dict(desk.CONFIG, {"platforms": {"telegram": True}}):
            self.learned(digest_hour=22)
            desk.evening_digest(factories)
            client.digest.assert_not_called()
            self.learned(digest_hour=20)
            desk.evening_digest(factories)
            client.digest.assert_called_once()


class ChannelText(unittest.TestCase):
    def p(self, **kw):
        base = {"id": "a", "headlines": ["Fed holds rates"], "dek": "The bank kept rates.", "body": "word " * 400,
                "topic": "Markets", "cards": ["card.jpg"], "caption": ""}
        base.update(kw)
        return base

    def test_telegram_caption_ends_with_the_topic_hashtag_within_1024(self):
        c = platforms.telegram_caption(self.p())
        self.assertTrue(c.endswith(" · #markets"))
        self.assertLessEqual(platforms._visible(c), 1024)

    def test_digest_closes_with_cross_links(self):
        t = platforms.digest_text([self.p()])
        self.assertIn("Every story: ", t)
        self.assertIn("Bluesky https://bsky.app/profile/boardread.bsky.social", t)
        self.assertNotIn("Telegram https://t.me", t)

    def test_threads_topic_tag_override(self):
        with mock.patch.dict(desk.CONFIG, {"threads_topic_tags": {"Markets": "Stock Market"}}):
            self.assertEqual(platforms.threads_tag(self.p()), "Stock Market")
        self.assertEqual(platforms.threads_tag(self.p()), "markets")


if __name__ == "__main__":
    unittest.main()
