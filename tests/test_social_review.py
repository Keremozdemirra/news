"""Fixes from the 2026-11-27 review of social output: Telegram duplicates, the ticker on Bluesky video posts."""
import json
from datetime import timedelta
from unittest import mock

from aidaily import desk, platforms
from test_platforms import Env, Fake, post

HEAD = "Denny's reshares Nvidia origin story after Jensen Huang's return"


def page(*msgs):
    """A t.me/s/<name> page: (id, first line, ISO time, link) per message."""
    out = ['<html><body><section class="tgme_channel_history">']
    for mid, text, when, link in msgs:
        out.append(f'<div class="tgme_widget_message" data-post="chan/{mid}" data-view="x">'
                   f'<div class="tgme_widget_message_text js-message_text" dir="auto"><b>{text}</b><br/><br/>'
                   f'Detail.<br/><br/><a href="{link}">Sources</a></div>'
                   f'<time datetime="{when}" class="time">12:00</time></div>')
    return ("".join(out) + "</section></body></html>").encode()


class TelegramFind(Env):
    def test_finds_the_story_by_headline_or_link(self):
        now = desk.now().isoformat()
        f = Fake({"t.me/s/chan": page(("7", "Something else entirely", now, "https://x/s/other/"),
                                      ("9", HEAD, now, "https://elsewhere/"))})
        self.assertEqual(platforms.Telegram(opener=f).find(post()), {"id": "9", "url": "https://t.me/chan/9"})
        f = Fake({"t.me/s/chan": page(("4", "A different first line", now, desk.story_url(post()["id"]) + "?utm_source=telegram"))})
        self.assertEqual(platforms.Telegram(opener=f).find(post())["id"], "4")

    def test_an_older_post_or_none_is_not_this_story(self):
        old = (desk.now() - timedelta(days=3)).isoformat()
        f = Fake({"t.me/s/chan": page(("3", HEAD, old, "https://x/"))})
        self.assertIsNone(platforms.Telegram(opener=f).find(post()))

    def test_a_numeric_channel_id_is_resolved_to_its_public_name(self):
        with mock.patch.dict("os.environ", {"TG_CHANNEL": "-100123"}):
            f = Fake({"getChat": {"ok": True, "result": {"username": "chan"}}, "t.me/s/chan": page()})
            self.assertIsNone(platforms.Telegram(opener=f).find(post()))

    def test_cross_post_records_an_earlier_send_instead_of_posting_again(self):
        p = post()
        path = self.stored(p)
        f = Fake({"t.me/s/chan": page(("23", HEAD, desk.now().isoformat(), "https://x/"))})
        desk.cross_post(p, path, factories={"telegram": lambda: platforms.Telegram(opener=f)}, names=["telegram"])
        slot = json.loads(path.read_text())["platforms"]["telegram"]
        self.assertEqual((slot["id"], slot.get("found_live")), ("23", True))
        self.assertFalse(any("sendPhoto" in r.full_url or "sendMediaGroup" in r.full_url for r in f.seen))


class Ticker(Env):
    def test_bluesky_video_text_carries_the_ticker_and_a_correct_facet(self):
        p = post(company="Meituan", ticker={"exchange": "HKEX", "symbol": "3690"},
                 headlines=["Meituan posts earnings beat as price war cools"])
        text, facets = platforms.bluesky_video_text(p)
        self.assertIn("Meituan (HKEX: 3690)", text)
        self.assertEqual(text.split("\n")[0], platforms.bluesky_text(p).split("\n")[0])
        idx = facets[0]["index"]
        self.assertEqual(text.encode()[idx["byteStart"]:idx["byteEnd"]].decode(), facets[0]["features"][0]["uri"])
