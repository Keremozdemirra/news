"""Secret scrubbing, duplicate checks on every platform, auth pauses, the comment-count shortcut, the status page
and the health issue."""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from aidaily import __main__ as cli, desk, platforms, redact, status

TOKEN = "EAAGm0PX4ZCpsBAKZCZBexampleexampleexample123"


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [mock.patch.object(desk, "QUEUE", root / "queue"), mock.patch.object(desk, "STATE", root / "state"),
                        mock.patch.object(desk, "PAUSED", root / "PAUSED"), mock.patch.object(desk, "HERE", root),
                        mock.patch.dict(os.environ, {"GITHUB_TOKEN": "", "DESK_PAUSED": "", "DESK_MEDIA_BASE": "https://raw.example/m",
                                                     "THREADS_TOKEN": "threads-token-value", "THREADS_USER_ID": "me",
                                                     "FB_PAGE_TOKEN": TOKEN, "FB_PAGE_ID": "111", "BSKY_HANDLE": "desk.bsky.social",
                                                     "BSKY_APP_PASSWORD": "abcd-efgh-ijkl-mnop", "TG_BOT_TOKEN": "tg-token-value",
                                                     "TG_CHANNEL": "@chan"}),
                        mock.patch.dict(desk.CONFIG, {"platforms": {n: True for n in platforms.NAMES}, "token_expiry": {}})]
        for p in self.patches:
            p.start()
        self.root = root

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def post(self, pid="p1", **kw):
        p = {"id": pid, "created": desk.now().isoformat(), "status": "published", "cards": ["card.jpg"], "score": 12,
             "headlines": ["Lab ships a model"], "dek": "It is faster.", "body": "It is faster than the last one.",
             "caption": "Lab ships a model", "published": desk.now().isoformat(), "topic": "AI"}
        p.update(kw)
        path = desk.QUEUE / pid / "post.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(p))
        return p, path


class Redact(Tmp):
    def test_short_identifiers_are_left_alone(self):
        # THREADS_USER_ID is "me": replacing it turned "message" into "<secret>ssage"
        with mock.patch.dict(os.environ, {"THREADS_TOKEN": "me"}):
            self.assertEqual(redact.scrub('{"message": "time"}'), '{"message": "time"}')

    def test_token_shapes_and_values(self):
        text = f"GET x?access_token={TOKEN}&a=1 Bearer abcdefghijklmnop 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
        out = redact.scrub(text)
        self.assertNotIn(TOKEN, out)
        self.assertNotIn("abcdefghijklmnop", out)
        self.assertNotIn("AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", out)
        self.assertIn("a=1", out)

    def test_save_scrubs_errors_and_secret_values_but_keeps_story_urls(self):
        url = "https://example.com/news-2026-tech-deal-done?token=abc"
        desk._save(self.root / "x.json", {"error": f"HTTP 400 access_token={TOKEN}", "urls": [url], "note": f"x {TOKEN} y"})
        text = (self.root / "x.json").read_text()
        self.assertNotIn(TOKEN, text)
        self.assertIn(url, text)  # a token-shaped pattern never rewrites a story's own link

    def test_stdout_is_scrubbed(self):
        buf = io.StringIO()
        redact.Stream(buf).write(f"failed with {TOKEN}\n")
        self.assertNotIn(TOKEN, buf.getvalue())

    def test_platform_errors_keep_their_words(self):
        c = platforms.Threads()
        self.assertEqual(c._scrub('{"message": "Session has expired"} threads-token-value'),
                         '{"message": "Session has expired"} <secret>')


class Find:
    """A platform client whose account already carries (or lacks) the post."""
    def __init__(self, live=None, error=None):
        self.live, self.error, self.sent = live, error, 0

    def find(self, post):
        if self.error:
            raise platforms.PlatformError(self.error)
        return self.live

    def post(self, post):
        self.sent += 1
        return {"id": "new", "url": "https://x/new"}


class CrossPostGuards(Tmp):
    def run_one(self, name, client):
        p, path = self.post()
        with mock.patch.dict(desk.CONFIG, {"platforms": {name: True}}):
            desk.cross_post(p, path, {name: lambda: client})
        return json.loads(path.read_text()).get("platforms", {}).get(name)

    def test_live_copy_is_recorded_not_sent_again(self):
        c = Find(live={"id": "old", "url": "https://bsky.app/x/post/old"})
        slot = self.run_one("bluesky", c)
        self.assertEqual((c.sent, slot["id"], slot["found_live"]), (0, "old", True))

    def test_unanswered_check_is_recorded_without_a_send_marker_and_retried(self):
        c = Find(error="bluesky getAuthorFeed: HTTP 502: bad gateway")
        slot = self.run_one("bluesky", c)
        self.assertEqual(c.sent, 0)
        self.assertNotIn("attempted", slot)
        self.assertIn("check_error", slot)
        self.assertIn("duplicate check failed", status.snapshot()["errors"][0]["summary"])
        # the next publish run offers the Instagram post to that platform again
        ok = Find()
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}):
            self.assertEqual(desk.retry_unchecked({"bluesky": lambda: ok}), 1)
        self.assertEqual(ok.sent, 1)
        got = json.loads((desk.QUEUE / "p1" / "post.json").read_text())["platforms"]["bluesky"]
        self.assertEqual(got["id"], "new")
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}):
            self.assertEqual(desk.retry_unchecked({"bluesky": lambda: ok}), 0)  # done means done

    def test_check_gives_up_after_its_tries(self):
        p, path = self.post()
        bad = Find(error="HTTP 502")
        with mock.patch.dict(desk.CONFIG, {"platforms": {"bluesky": True}}):
            for _ in range(desk.CHECK_TRIES):
                desk.cross_post(json.loads(path.read_text()), path, {"bluesky": lambda: bad})
        slot = json.loads(path.read_text())["platforms"]["bluesky"]
        self.assertIn("skipped", slot)
        self.assertEqual(bad.sent, 0)

    def test_facebook_find_reads_the_page_posts_with_the_page_token(self):
        p, _ = self.post()
        page = desk.story_url(p["id"])
        seen = []

        def opener(req, timeout=None, context=None):
            seen.append(req.full_url)
            if "/me/accounts" in req.full_url:
                return _Resp({"data": [{"id": "111", "name": "Boardread", "access_token": "page-token-value-123"}]})
            return _Resp({"data": [{"id": "111_9", "message": f"Lab ships a model\n\nSources: {page}",
                                    "permalink_url": "https://www.facebook.com/111/posts/9"}]})
        fb = platforms.Facebook(opener=opener)
        self.assertEqual(fb.find(p), {"id": "111_9", "url": "https://www.facebook.com/111/posts/9"})
        self.assertIn("/111/posts?", seen[-1])
        self.assertIn("access_token=page-token-value-123", seen[-1])
        self.assertIsNone(fb.find({**p, "id": "other"}))
        self.assertNotIn("page-token-value-123", redact.scrub("x page-token-value-123 y"))  # registered derived secret

    def test_rejected_credential_pauses_until_a_new_secret(self):
        class Expired(Find):
            def post(self, post):
                raise platforms.PlatformError('threads POST threads: HTTP 400: {"error":{"code":190}}')
        self.run_one("threads", Expired())
        self.assertTrue(desk.platform_cooldown("threads"))
        saved = json.loads((desk.STATE / "cooldown-threads.json").read_text())
        self.assertTrue(saved["auth"])
        self.assertNotIn("threads-token-value", json.dumps(saved))
        with mock.patch.dict(os.environ, {"THREADS_TOKEN": "a-brand-new-token"}):
            self.assertIsNone(desk.platform_cooldown("threads"))  # renewed: tried at once

    def test_bluesky_find_reads_the_link_card(self):
        p, _ = self.post()
        page = desk.story_url(p["id"])
        feed = {"feed": [{"post": {"uri": "at://did/app.bsky.feed.post/3k", "record": {"embed": {"external": {"uri": page}}}}}]}
        b = platforms.Bluesky(opener=lambda req, timeout=None, context=None: _Resp(feed))
        self.assertEqual(b.find(p)["url"], "https://bsky.app/profile/desk.bsky.social/post/3k")
        self.assertIsNone(b.find({**p, "id": "other"}))

    def test_threads_find_matches_the_first_line_and_skips_older_posts(self):
        p, _ = self.post()
        line = platforms.threads_text(p).split("\n")[0]
        old = (desk.now() - timedelta(days=2)).isoformat()
        rows = {"data": [{"id": "1", "text": line + "\n\nmore", "timestamp": old},
                         {"id": "2", "text": line + "\n\nmore", "timestamp": desk.now().isoformat(), "permalink": "https://t/2"}]}
        t = platforms.Threads(opener=lambda req, timeout=None, context=None: _Resp(rows))
        self.assertEqual(t.find(p), {"id": "2", "url": "https://t/2"})


class _Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data).encode())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class EngageCounts(Tmp):
    def client(self, count):
        class IG:
            read = 0

            def own_username(self):
                return "desk"

            def recent_media(self, limit=25):
                return [{"id": "m1", "comments_count": count}]

            def comments(self, media):
                IG.read += 1
                return []

            def reply(self, *a):
                pass
        return IG()

    def test_unchanged_count_is_not_read_again(self):
        self.post(media_id="m1")
        first = self.client(2)
        desk.engage(client=first, ask=lambda p: "")
        self.assertEqual(first.read, 1)
        same = self.client(2)
        desk.engage(client=same, ask=lambda p: "")
        self.assertEqual(same.read, 0)
        more = self.client(3)
        desk.engage(client=more, ask=lambda p: "")
        self.assertEqual(more.read, 1)

    def test_a_failed_list_reads_every_post(self):
        self.post(media_id="m1")
        ig = self.client(2)
        ig.recent_media = mock.Mock(side_effect=RuntimeError("HTTP 500"))
        desk.engage(client=ig, ask=lambda p: "")
        self.assertEqual(ig.read, 1)


class FakeGH:
    def __init__(self):
        self.issues, self.comments, self.patches, self.closed = [], [], [], []

    def enabled(self):
        return True

    def _call(self, method, path, body=None):
        if method == "GET" and path.startswith("issues?"):
            return [{"number": i["number"], "title": i["title"], "user": {"login": status.BOT}}
                    for i in self.issues if i["number"] not in self.closed]
        if method == "PATCH":
            self.patches.append(body)
        if method == "POST" and path.endswith("/comments"):
            self.comments.append(body["body"])
        return {}

    def open_issue(self, title, body, labels=()):
        n = len(self.issues) + 1
        self.issues.append({"number": n, "title": title, "body": body})
        return n

    def comment(self, number, text, close=False):
        self.comments.append(text)
        if close:
            self.closed.append(number)

    def close(self, number):
        self.closed.append(number)


class Health(Tmp):
    def at(self, minutes):
        return mock.patch.object(status, "now", lambda: desk.now() + timedelta(minutes=minutes))

    def broken_threads(self):
        self.post(platforms={"threads": {"attempted": desk.now().isoformat(),
                                         "error": 'threads: HTTP 400: {"error":{"message":"Error validating access token","code":190}}'}})

    def test_renewed_token_clears_the_alarm_at_once(self):
        self.broken_threads()
        self.assertEqual([k for k, _ in status.problems(status.snapshot())], ["auth-threads"])
        self.post("p2", platforms={"threads": {"id": "t1", "url": "https://t/1", "at": (desk.now() + timedelta(minutes=1)).isoformat()}})
        self.assertEqual(status.problems(status.snapshot()), [])

    def test_numbers_in_a_body_are_not_auth_errors(self):
        self.assertNotIn("credential", status.classify('HTTP 500: {"id": "1401", "n": 4012}'))
        self.assertNotIn("rate limit", status.classify('HTTP 500: {"id": "14290"}'))
        self.assertIn("credential", status.classify("telegram: HTTP 401: Unauthorized"))

    def test_classify_never_quotes_the_message(self):
        text = 'HTTP 400: {"error":{"message":"secret words here","code":190,"error_subcode":0}}'
        self.assertEqual(status.classify(text), "HTTP 400 · code 190 · credential expired or revoked")

    def test_issue_waits_then_opens_once_then_closes_when_clear(self):
        gh = FakeGH()
        self.broken_threads()
        status.health(status.snapshot(), gh=gh)
        self.assertEqual(gh.issues, [])  # not yet: a problem must last HOLD_MINUTES
        with self.at(status.HOLD_MINUTES + 1):
            status.health(status.snapshot(), gh=gh)
            status.health(status.snapshot(), gh=gh)
        self.assertEqual(len(gh.issues), 1)
        self.assertIn("THREADS_TOKEN", gh.issues[0]["body"])
        self.assertEqual(gh.comments, [])  # nothing changed, so nothing mailed
        for p in desk.QUEUE.glob("*/post.json"):
            p.unlink()
        with self.at(status.HOLD_MINUTES + 2):
            status.health(status.snapshot(), gh=gh)
        self.assertEqual(gh.closed, [])  # clear has to last too
        with self.at(status.HOLD_MINUTES + status.CLEAR_MINUTES + 5):
            status.health(status.snapshot(), gh=gh)
        self.assertEqual(gh.closed, [1])

    def test_a_new_problem_is_one_comment(self):
        gh = FakeGH()
        self.broken_threads()
        status.health(status.snapshot(), gh=gh)
        with self.at(status.HOLD_MINUTES + 1):
            status.health(status.snapshot(), gh=gh)
            self.post("p2", status="queued", publish_after=(desk.now() - timedelta(hours=5)).isoformat(),
                      created=(desk.now() - timedelta(hours=5)).isoformat())
            status.health(status.snapshot(), gh=gh)  # the stuck post is first seen now
        with self.at(2 * status.HOLD_MINUTES + 5):
            status.health(status.snapshot(), gh=gh)
        self.assertEqual(len(gh.issues), 1)
        self.assertEqual(len(gh.comments), 1)
        self.assertIn("due", gh.comments[0])

    def test_cooldown_and_pause_are_not_problems(self):
        desk._save(desk.STATE / "cooldown.json", {"until": (desk.now() + timedelta(hours=5)).isoformat(), "error": "x"})
        self.post("q", status="queued", publish_after=(desk.now() - timedelta(hours=5)).isoformat())
        self.assertEqual(status.problems(status.snapshot()), [])
        self.broken_threads()
        desk.PAUSED.write_text("")
        self.assertEqual(status.problems(status.snapshot()), [])

    def test_failing_workflows_and_a_dead_clock(self):
        runs = {"publish": [{"status": "completed", "conclusion": "failure", "created": desk.now().isoformat(), "url": "https://g/1"}] * 3,
                "tick": [{"status": "completed", "conclusion": "success", "created": desk.now().isoformat(), "url": "https://g/2"}]}
        keys = [k for k, _ in status.problems(status.snapshot(runs))]
        self.assertEqual(sorted(keys), ["clock", "wf-publish"])

    def test_stale_site(self):
        old = {"generated": (desk.now() - timedelta(hours=5)).isoformat()}
        self.assertEqual([k for k, _ in status.problems(status.snapshot(), old)], ["site"])

    def test_page_and_json_carry_no_secret(self):
        self.broken_threads()
        out = self.root / "status"
        status.write(out, runs={})
        for f in ("status.json", "index.html"):
            text = (out / f).read_text()
            self.assertNotIn("threads-token-value", text)
            self.assertNotIn("Error validating", text)
        self.assertIn("credential expired or revoked", (out / "index.html").read_text())

    def test_weekly_closes_last_weeks_report(self):
        gh = FakeGH()
        gh.issues.append({"number": 1, "title": "Weekly health 2026-W47", "body": ""})
        self.post()
        runs = {"publish": [{"status": "completed", "conclusion": "failure", "created": desk.now().isoformat(), "url": "https://g/1"}]}
        body = status.weekly(gh=gh, runs=runs)
        self.assertIn("| publish | failure", body)
        self.assertRegex(body, r"\| publish \|.*\| 1 \|")
        self.assertEqual(gh.closed, [1])
        self.assertTrue(gh.issues[-1]["title"].startswith("Weekly health"))


class DeleteCommand(Tmp):
    def test_a_refused_delete_does_not_stop_the_others(self):
        self.post("a", media_id="m1")
        self.post("b", media_id="m2")

        class C:
            def __init__(self, *a, **k):
                pass

            def delete(self, mid):
                if mid == "m1":
                    raise RuntimeError("HTTP 400 code 10")
                return True
        with mock.patch("aidaily.instagram.Client", C), mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            rc = cli.main(["delete", "a", "b"])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads((desk.QUEUE / "b" / "post.json").read_text())["status"], "deleted")
        self.assertEqual(json.loads((desk.QUEUE / "a" / "post.json").read_text())["status"], "published")


if __name__ == "__main__":
    unittest.main()
