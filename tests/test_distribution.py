"""The Telegram pinned post and the Bluesky custom feed (skeleton file and generator record)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import desk, distribution, platforms


def bs(uri, at):
    return {"platforms": {"bluesky": {"id": uri, "at": at}}}


class Feed(unittest.TestCase):
    def test_skeleton_is_our_bluesky_posts_newest_first(self):
        rows = [bs("at://did:plc:x/app.bsky.feed.post/1", "2026-11-26T10:00:00+00:00"),
                bs("at://did:plc:x/app.bsky.feed.post/2", "2026-11-26T12:00:00+00:00"),
                bs("", "2026-11-26T13:00:00+00:00"), {"platforms": {}},
                bs("at://did:plc:x/app.bsky.feed.like/3", "2026-11-26T14:00:00+00:00")]
        got = distribution.skeleton(rows)["feed"]
        self.assertEqual([x["post"][-1] for x in got], ["2", "1"])

    def test_skeleton_caps_the_list(self):
        rows = [bs(f"at://did:plc:x/app.bsky.feed.post/{i:03d}", f"2026-11-26T10:{i % 60:02d}:00+00:00") for i in range(150)]
        self.assertEqual(len(distribution.skeleton(rows)["feed"]), distribution.MAX_FEED)

    def test_write_skeleton(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(desk, "posts", return_value=[]):
            distribution.write_skeleton(d)
            self.assertEqual(json.loads((Path(d) / "bsky-feed.json").read_text())["feed"], [])

    def test_generator_record_fits_the_lexicon(self):
        r = distribution.generator_record("did:web:feed.boardread.news")
        self.assertEqual(r["$type"], "app.bsky.feed.generator")
        self.assertLessEqual(len(r["displayName"]), 24)
        self.assertLessEqual(len(r["description"]), 300)
        self.assertTrue(r["createdAt"].endswith("Z"))

    def test_publish_is_a_dry_run_unless_sent(self):
        with mock.patch.object(platforms, "Bluesky") as cls:
            distribution.publish_generator("feed.boardread.news")
            cls.assert_not_called()

    def test_send_uses_put_record_with_a_fixed_rkey(self):
        client = mock.Mock()
        client.env = {"BSKY_HANDLE": "boardread.bsky.social", "BSKY_APP_PASSWORD": "p"}
        client.xrpc.side_effect = [{"did": "did:plc:me", "accessJwt": "j"}, {"uri": "at://did:plc:me/app.bsky.feed.generator/boardread"}]
        distribution.publish_generator("feed.boardread.news", send=True, client=client)
        name, body, jwt = client.xrpc.call_args_list[1][0]
        self.assertEqual(name, "com.atproto.repo.putRecord")
        self.assertEqual(body["rkey"], "boardread")
        self.assertEqual(body["record"]["did"], "did:web:feed.boardread.news")

    def test_worker_serves_json_on_the_three_paths(self):
        js = (desk.HERE / "scripts" / "bsky-feed-worker.js").read_text()
        for path in ("/.well-known/did.json", "/xrpc/app.bsky.feed.describeFeedGenerator", "/xrpc/app.bsky.feed.getFeedSkeleton"):
            self.assertIn(path, js)
        self.assertIn('"content-type": "application/json', js)


class Pin(unittest.TestCase):
    def test_pin_text_says_what_it_is_and_links_the_rest(self):
        t = distribution.pin_text()
        self.assertNotRegex(t, r"(?i)written by|ai[- ]generated|automated desk")
        self.assertIn("/standards/", t)
        self.assertIn("#markets", t)
        self.assertIn("Bluesky https://", t)
        self.assertNotIn("Telegram https://", t)
        self.assertLessEqual(len(t), 4096)  # sendMessage text limit

    def test_pin_is_a_dry_run_unless_sent(self):
        with mock.patch.object(platforms, "Telegram") as cls:
            self.assertIsNone(distribution.pin())
            cls.assert_not_called()

    def test_client_pin_sends_silently_then_pins_silently(self):
        calls = []

        def call(method, params):
            calls.append((method, params))
            return {"message_id": 42} if method == "sendMessage" else True

        with mock.patch.dict("os.environ", {"TG_BOT_TOKEN": "t", "TG_CHANNEL": "@boardread"}):
            tg = platforms.Telegram()
        tg.call = call
        self.assertEqual(tg.pin("hello"), {"id": "42"})
        self.assertEqual([m for m, _ in calls], ["sendMessage", "pinChatMessage"])
        self.assertTrue(calls[0][1]["disable_notification"])
        self.assertEqual(calls[1][1], {"chat_id": "@boardread", "message_id": 42, "disable_notification": True})


if __name__ == "__main__":
    unittest.main()
