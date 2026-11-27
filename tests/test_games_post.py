"""The daily games post: three puzzle numbers and a link, once a day per platform, and never a word that helps."""
import base64, datetime as dt, json, re, unittest
from pathlib import Path
from unittest import mock

from aidaily import desk, games_post

ROOT = Path(__file__).resolve().parent.parent
DAY = dt.date(2026, 11, 28)
SLUGS = ("topfloor", "tickerflip", "face-the-figure")


class Resp:
    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else data.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.data


def puzzles(day=DAY):
    """The committed puzzles, re-dated, with answers no template could hold by accident."""
    out = {}
    for slug in SLUGS:
        p = json.loads((ROOT / "games" / slug / "assets" / "data" / "today.json").read_text())
        p["date"], p["no"] = day.isoformat(), {"topfloor": 3, "tickerflip": 2, "face-the-figure": 2}[slug]
        out[slug] = p
    out["tickerflip"]["a"] = base64.b64encode("ZEBRAS"[::-1].lower().encode()).decode()
    out["tickerflip"]["clue"] = "a striped animal"
    return out


def site_opener(day=DAY, stale=()):
    def opener(req, timeout=None, context=None):
        for slug, p in puzzles(day).items():
            if f"/play/{slug}/" in req.full_url:
                if slug in stale:
                    p["date"] = (day - dt.timedelta(days=1)).isoformat()
                return Resp(json.dumps(p))
        raise AssertionError(req.full_url)
    return opener


CHANNEL = ('<div class="tgme_widget_message" data-post="boardread/40"><div class="tgme_widget_message_text js-message_text" dir="auto">'
           'Fed holds rates<br/>More text</div></div>')
SENT = ('<div class="tgme_widget_message" data-post="boardread/41"><div class="tgme_widget_message_text js-message_text" dir="auto">'
        '<b>Today&#39;s games · 28 Nov</b><br/><br/>Topfloor No. 3</div></div>')
TITLE = "Today's games · 28 Nov"


class Telegram:
    PUBLIC = "https://t.me"

    def __init__(self, page=CHANNEL, fail=False):
        self.env, self.page, self.fail, self.calls = {"TG_BOT_TOKEN": "x", "TG_CHANNEL": "@boardread"}, page, fail, []

    def call(self, method, params):
        self.calls.append((method, params))
        return {"message_id": 42}

    def _open(self, req, label):
        if self.fail:
            raise OSError("no route")
        return self.page.encode()


class Threads:
    def __init__(self, feed=(), fail=False):
        self.env, self.feed, self.fail, self.calls = {"THREADS_USER_ID": "77"}, list(feed), fail, []

    def call(self, method, path, params):
        if method == "GET" and path.endswith("/threads"):
            if self.fail:
                raise OSError("no route")
            return {"data": [{"id": "1", "text": x, "permalink": "https://threads.com/p/1"} for x in self.feed]}
        if method == "GET":
            return {"permalink": "https://threads.com/p/9"}
        self.calls.append((path, params))
        return {"id": "c1"}

    def wait(self, container):
        pass

    def publish(self, container):
        self.calls.append(("publish", container))
        return "m9"


class Facebook:
    host, version = "https://graph.facebook.com", "v27.0"

    def __init__(self, feed=(), fail=False):
        self.env, self.feed, self.fail, self.calls = {"FB_PAGE_ID": "55"}, list(feed), fail, []

    def page_token(self):
        return "page-token"

    def form(self, method, url, params, label):
        if self.fail:
            raise OSError("no route")
        return {"data": [{"id": "55_1", "message": x} for x in self.feed]}

    def call(self, path, params):
        self.calls.append((path, params))
        return {"id": "55_9"}


class Bluesky:
    APPVIEW, MAX_BYTES = "https://public.api.bsky.app", 1_000_000

    def __init__(self, feed=(), fail=False, big=False):
        self.env, self.feed, self.fail, self.big, self.calls = {"BSKY_HANDLE": "boardread.news", "BSKY_APP_PASSWORD": "x"}, list(feed), fail, big, []

    def form(self, method, url, params, label):
        if self.fail:
            raise OSError("no route")
        return {"feed": [{"post": {"uri": "at://did/app.bsky.feed.post/abc", "record": {"text": x}}} for x in self.feed]}

    def fetch(self, url):
        return b"x" * (2_000_000 if self.big else 1000)

    def xrpc(self, name, body, jwt=None, raw=None, mime=None):
        if name.endswith("createSession"):
            return {"accessJwt": "j", "did": "did:plc:1"}
        if name.endswith("uploadBlob"):
            return {"blob": {"ref": "b"}}
        self.calls.append((name, body))
        return {"uri": "at://did:plc:1/app.bsky.feed.post/xyz"}


def clients(**kw):
    return {"threads": kw.get("threads", Threads()), "bluesky": kw.get("bluesky", Bluesky()),
            "telegram": kw.get("telegram", Telegram()), "facebook": kw.get("facebook", Facebook())}


def on(value=True, **config):
    return mock.patch.dict(desk.CONFIG, {"growth": {**desk.CONFIG.get("growth", {}), "games_post": value, "utm": False},
                                         "platforms": {n: True for n in games_post.PLATFORMS}, **config})


def run(cs, **kw):
    with mock.patch.object(desk, "_last_sent", kw.pop("last", lambda name: None)), mock.patch.object(desk, "platform_cooldown", kw.pop("cool", lambda name: None)):
        return games_post.run(send=True, clients=cs, opener=kw.pop("opener", site_opener()), day=DAY, minute=kw.pop("minute", 5), limit=kw.pop("limit", 4))


class Text(unittest.TestCase):
    def test_three_lines_numbers_and_the_link(self):
        with on():
            t = games_post.text(games_post.numbers(puzzles()), DAY)
        self.assertEqual(t.split("\n"), [TITLE, "", "Topfloor No. 3", "Tickerflip No. 2", "Face the Figure No. 2", "", "https://boardread.news/play/"])

    def test_telegram_caption_is_the_same_post_in_html(self):
        with on():
            t = games_post.telegram_html(games_post.numbers(puzzles()), DAY)
        self.assertEqual(t.split("\n"), [f"<b>{TITLE}</b>", "", "Topfloor No. 3", "Tickerflip No. 2", "Face the Figure No. 2", "",
                                         '<a href="https://boardread.news/play/">boardread.news/play/</a>'])
        self.assertLessEqual(len(t), 1024)

    def test_no_answer_and_no_hint_in_any_text(self):
        ps = puzzles()
        nos = games_post.numbers(ps)
        with on():
            every = " ".join([games_post.text(nos, DAY, n) for n in games_post.PLATFORMS] + [games_post.telegram_html(nos, DAY), games_post.body(nos, DAY)]).lower()
        self.assertNotIn("zebras", every)
        self.assertNotIn(ps["tickerflip"]["clue"], every)
        self.assertNotIn(str(ps["tickerflip"]["len"]) + " letters", every)
        for r in ps["face-the-figure"]["rounds"]:
            self.assertNotIn(r["answer"], every)                      # "higher" / "lower"
            for side in ("a", "b"):
                self.assertNotIn(r[side]["subject"].lower(), every)
        for pr in ps["topfloor"]["prompts"]:
            self.assertNotIn(pr["text"].lower(), every)

    def test_the_committed_tickerflip_answer_is_not_in_the_text(self):
        p = json.loads((ROOT / "games" / "tickerflip" / "assets" / "data" / "today.json").read_text())
        word = base64.b64decode(p["a"]).decode()[::-1]
        self.assertNotIn(word, games_post.text({"topfloor": 1, "tickerflip": 1, "face-the-figure": 1}, DAY).lower())

    def test_only_the_number_is_read_from_a_puzzle(self):
        class Only(dict):
            def __getitem__(self, k):
                assert k == "no", k
                return 7
        self.assertEqual(games_post.numbers({"tickerflip": Only()}), {"tickerflip": 7})

    def test_the_link_carries_the_channel_only_with_the_utm_switch(self):
        with on():
            self.assertEqual(games_post.link("threads"), "https://boardread.news/play/")
        with mock.patch.dict(desk.CONFIG, {"growth": {"utm": True}}):
            self.assertEqual(games_post.link("threads"), "https://boardread.news/play/?utm_source=threads&utm_medium=social")

    def test_the_picture_is_a_game_share_image_and_changes_by_day(self):
        nos = {"topfloor": 1, "tickerflip": 1, "face-the-figure": 1}
        pics = {games_post.image(nos, DAY + dt.timedelta(days=i)) for i in range(3)}
        self.assertEqual(pics, {f"https://boardread.news/play/{s}/assets/share.jpg" for s in SLUGS})


class Send(unittest.TestCase):
    def test_sends_once_to_each_of_the_four(self):
        cs = clients()
        with on():
            got = run(cs)
        self.assertEqual(sorted(got), ["bluesky", "facebook", "telegram", "threads"])
        self.assertEqual(got["telegram"], {"id": "42", "url": "https://t.me/boardread/42"})
        (method, params), = cs["telegram"].calls
        self.assertEqual(method, "sendPhoto")
        self.assertTrue(params["disable_notification"])
        self.assertIn("Tickerflip No. 2", params["caption"])
        (path, params), publish = cs["threads"].calls
        self.assertEqual((path, params["media_type"], publish), ("77/threads", "IMAGE", ("publish", "c1")))
        self.assertTrue(params["text"].startswith(TITLE))
        self.assertTrue(params["image_url"].endswith("/assets/share.jpg"))
        (path, params), = cs["facebook"].calls
        self.assertEqual((path, params["link"]), ("55/feed", "https://boardread.news/play/"))
        self.assertTrue(params["message"].startswith(TITLE))
        (name, body), = cs["bluesky"].calls
        rec = body["record"]
        self.assertTrue(rec["text"].startswith(TITLE))
        self.assertEqual(rec["embed"]["external"]["uri"], "https://boardread.news/play/")
        self.assertIn("thumb", rec["embed"]["external"])
        self.assertLessEqual(len(rec["text"]), 300)
        self.assertEqual(got["bluesky"]["url"], "https://bsky.app/profile/boardread.news/post/xyz")

    def test_one_platform_a_run_and_telegram_first(self):
        cs = clients()
        with on(), mock.patch.object(desk, "_last_sent", lambda name: None), mock.patch.object(desk, "platform_cooldown", lambda name: None):
            got = games_post.run(send=True, clients=cs, opener=site_opener(), day=DAY, minute=5)
        self.assertEqual(list(got), ["telegram"])
        self.assertEqual([cs[n].calls for n in ("threads", "bluesky", "facebook")], [[], [], []])
        self.assertEqual(games_post.PLATFORMS[0], "telegram")

    def test_the_next_run_moves_on_to_the_next_platform(self):
        cs = clients(telegram=Telegram(page=CHANNEL + SENT))
        with on():
            self.assertEqual(list(run(cs, limit=1)), ["threads"])

    def test_instagram_is_never_a_target(self):
        self.assertNotIn("instagram", games_post.PLATFORMS)
        self.assertEqual(set(games_post.SEND), set(games_post.PLATFORMS))

    def test_switched_off_sends_nothing(self):
        cs = clients()
        with on(False):
            self.assertEqual(run(cs), {})
        self.assertTrue(all(c.calls == [] for c in cs.values()))

    def test_the_switch_ships_in_desk_json(self):
        self.assertIn("games_post", json.loads((ROOT / "desk.json").read_text())["growth"])

    def test_a_platform_switched_off_in_desk_json_is_left_out(self):
        cs = clients()
        with on(), mock.patch.dict(desk.CONFIG, {"platforms": {"threads": True, "bluesky": False, "telegram": True, "facebook": False}}):
            self.assertEqual(sorted(run(cs)), ["telegram", "threads"])

    def test_already_on_a_platform_sends_nothing_there(self):
        cs = clients(telegram=Telegram(page=CHANNEL + SENT), threads=Threads(feed=[TITLE + "\n\nTopfloor No. 3"]),
                     facebook=Facebook(feed=["A story", TITLE + "\n\nTopfloor No. 3"]), bluesky=Bluesky(feed=[TITLE + "\n\nTopfloor No. 3"]))
        with on():
            self.assertEqual(run(cs), {})
        self.assertTrue(all(c.calls == [] for c in cs.values()))

    def test_yesterdays_post_does_not_count_as_todays(self):
        old = TITLE.replace("28 Nov", "27 Nov")
        cs = clients(telegram=Telegram(page=CHANNEL + SENT.replace("28 Nov", "27 Nov")), threads=Threads(feed=[old]),
                     facebook=Facebook(feed=[old]), bluesky=Bluesky(feed=[old]))
        with on():
            self.assertEqual(len(run(cs)), 4)

    def test_an_unreadable_feed_sends_nothing_there_and_the_others_go_on(self):
        cs = clients(telegram=Telegram(page="<html>Too many requests</html>"), threads=Threads(fail=True), facebook=Facebook(fail=True))
        with on():
            self.assertEqual(sorted(run(cs)), ["bluesky"])
        self.assertEqual(cs["telegram"].calls + cs["threads"].calls + cs["facebook"].calls, [])

    def test_waits_until_all_three_puzzles_are_todays(self):
        cs = clients()
        with on():
            self.assertEqual(run(cs, opener=site_opener(stale=("tickerflip",))), {})
        self.assertTrue(all(c.calls == [] for c in cs.values()))

    def test_spaced_from_the_news_posts(self):
        now = desk.now()
        last = lambda name: now - dt.timedelta(minutes=5) if name == "threads" else now - dt.timedelta(hours=2)  # noqa: E731
        cs = clients()
        with on(social_spacing_minutes=20):
            self.assertEqual(sorted(run(cs, last=last)), ["bluesky", "facebook", "telegram"])
        self.assertEqual(cs["threads"].calls, [])

    def test_a_platform_cooling_down_waits(self):
        cs = clients()
        with on():
            got = run(cs, cool=lambda name: desk.now() + dt.timedelta(hours=3) if name == "facebook" else None)
        self.assertNotIn("facebook", got)
        self.assertEqual(cs["facebook"].calls, [])

    def test_tried_in_the_first_quarter_of_an_hour_only(self):
        cs = clients()
        with on():
            self.assertEqual(run(cs, minute=games_post.TRY_MINUTES), {})
            self.assertEqual(run(cs, minute=40), {})
        self.assertTrue(all(c.calls == [] for c in cs.values()))

    def test_one_platform_failing_does_not_stop_the_rest(self):
        class Broken(Facebook):
            def call(self, path, params):
                raise RuntimeError("refused")
        with on():
            self.assertEqual(sorted(run(clients(facebook=Broken()))), ["bluesky", "telegram", "threads"])

    def test_an_oversize_picture_leaves_the_bluesky_card_without_one(self):
        cs = clients(bluesky=Bluesky(big=True))
        with on():
            run(cs)
        self.assertNotIn("thumb", cs["bluesky"].calls[0][1]["record"]["embed"]["external"])

    def test_dry_run_sends_nothing(self):
        cs = clients()
        with on():
            self.assertEqual(games_post.run(send=False, clients=cs, opener=site_opener(), day=DAY), {})
        self.assertTrue(all(c.calls == [] for c in cs.values()))

    def test_the_workflow_step_holds_no_secret_the_publish_step_does_not(self):
        y = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
        step = y.split("- name: Games post", 1)[1].split("\n      - ", 1)[0]
        publish = y.split("- name: Publish", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("python3 -m aidaily games-post --send", step)
        mine, theirs = set(re.findall(r"secrets\.(\w+)", step)), set(re.findall(r"secrets\.(\w+)", publish))
        self.assertTrue(mine <= theirs, mine - theirs)
        self.assertFalse({s for s in mine if s.startswith(("IG_", "YT_"))})

    def test_platforms_py_is_only_called(self):
        src = (ROOT / "aidaily" / "games_post.py").read_text()
        self.assertNotIn("instagram", src.lower().replace("never the instagram feed", ""))


class Share(unittest.TestCase):
    """The end-screen share of each game: a result with no answer in it, and a link that says where the visit came from."""
    FILES = {"topfloor": "js/topfloor.js", "tickerflip": "js/tickerflip.js", "face-the-figure": "js/ftf.js"}

    def test_every_game_shares_a_tracked_link_by_sheet_or_copy(self):
        for slug, f in self.FILES.items():
            src = (ROOT / "games" / slug / f).read_text()
            self.assertEqual(src.count(f"https://boardread.news/play/{slug}/?utm_source=share"), 1, slug)
            self.assertIn("navigator.share({ text })", src, slug)
            self.assertIn("navigator.clipboard.writeText(text)", src, slug)
            self.assertIn('e.name === "AbortError"', src, slug)
            self.assertIn('id="share"', (ROOT / "games" / slug / "index.html").read_text(), slug)

    def test_the_share_line_is_built_from_scores_only(self):
        for slug, f in self.FILES.items():
            src = (ROOT / "games" / slug / f).read_text()
            line = next(l for l in src.split("\n") if "utm_source=share" in l)
            for leak in ("answer", "word", "subject", "entries", ".value", "clue"):
                self.assertNotIn(leak, line, (slug, leak))


if __name__ == "__main__":
    unittest.main()
