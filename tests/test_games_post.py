"""The daily games post: three puzzle numbers and a link, once a day, and never a word that helps."""
import base64, datetime as dt, json, os, unittest
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


class Client:
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


def on(value=True):
    return mock.patch.dict(desk.CONFIG, {"growth": {**desk.CONFIG.get("growth", {}), "games_post": value}})


class Text(unittest.TestCase):
    def test_three_lines_numbers_and_the_link(self):
        t = games_post.text(games_post.numbers(puzzles()), DAY)
        self.assertEqual(t.split("\n"), ["<b>Today's games · 28 Nov</b>", "", "Topfloor No. 3", "Tickerflip No. 2", "Face the Figure No. 2", "",
                                         '<a href="https://boardread.news/play/">boardread.news/play/</a>'])

    def test_no_answer_and_no_hint_in_the_text(self):
        ps = puzzles()
        t = games_post.text(games_post.numbers(ps), DAY).lower()
        self.assertNotIn("zebras", t)
        self.assertNotIn(ps["tickerflip"]["clue"], t)
        self.assertNotIn(str(ps["tickerflip"]["len"]) + " letters", t)
        for r in ps["face-the-figure"]["rounds"]:
            self.assertNotIn(r["answer"], t)                      # "higher" / "lower"
            for side in ("a", "b"):
                self.assertNotIn(r[side]["subject"].lower(), t)
        for pr in ps["topfloor"]["prompts"]:
            self.assertNotIn(pr["text"].lower(), t)

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


class Send(unittest.TestCase):
    def test_sends_once_when_switched_on(self):
        c = Client()
        with on():
            got = games_post.run(send=True, client=c, opener=site_opener(), day=DAY)
        self.assertEqual(got, {"id": "42", "url": "https://t.me/boardread/42"})
        (method, params), = c.calls
        self.assertEqual(method, "sendMessage")
        self.assertEqual(params["chat_id"], "@boardread")
        self.assertTrue(params["disable_notification"])
        self.assertIn("Tickerflip No. 2", params["text"])

    def test_switched_off_sends_nothing(self):
        c = Client()
        with on(False):
            self.assertIsNone(games_post.run(send=True, client=c, opener=site_opener(), day=DAY))
        self.assertEqual(c.calls, [])

    def test_the_switch_ships_as_committed(self):
        self.assertIn("games_post", json.loads((ROOT / "desk.json").read_text())["growth"])

    def test_already_in_the_channel_sends_nothing(self):
        c = Client(page=CHANNEL + SENT)
        with on():
            self.assertIsNone(games_post.run(send=True, client=c, opener=site_opener(), day=DAY))
        self.assertEqual(c.calls, [])

    def test_yesterdays_post_does_not_count_as_todays(self):
        c = Client(page=CHANNEL + SENT.replace("28 Nov", "27 Nov"))
        with on():
            self.assertIsNotNone(games_post.run(send=True, client=c, opener=site_opener(), day=DAY))

    def test_an_unreadable_channel_sends_nothing(self):
        for c in (Client(fail=True), Client(page="<html>Too many requests</html>")):
            with on():
                self.assertIsNone(games_post.run(send=True, client=c, opener=site_opener(), day=DAY))
            self.assertEqual(c.calls, [])

    def test_waits_until_all_three_puzzles_are_todays(self):
        c = Client()
        with on():
            self.assertIsNone(games_post.run(send=True, client=c, opener=site_opener(stale=("tickerflip",)), day=DAY))
        self.assertEqual(c.calls, [])

    def test_dry_run_sends_nothing(self):
        c = Client()
        with on():
            self.assertIsNone(games_post.run(send=False, client=c, opener=site_opener(), day=DAY))
        self.assertEqual(c.calls, [])

    def test_the_workflow_step_gets_the_telegram_secrets_only(self):
        y = (ROOT / ".github" / "workflows" / "publish.yml").read_text()
        step = y.split("- name: Games post", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("python3 -m aidaily games-post --send", step)
        self.assertEqual(sorted(set(__import__("re").findall(r"secrets\.(\w+)", step))), ["TG_BOT_TOKEN", "TG_CHANNEL"])


if __name__ == "__main__":
    unittest.main()
