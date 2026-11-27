"""The daily games post: one short Telegram message with today's three puzzle numbers and the /play/ link.

Switch: desk.json growth.games_post. Telegram only. Sent once per UTC day, after the day's puzzles are on the site:
the numbers come from the live /play/<game>/assets/data/today.json, and nothing is sent until all three carry
today's date. The channel itself is the record of what was sent (the Bot API cannot read a channel, its public
preview page can): a post that already opens with today's title line means the day is done. When that page cannot
be read, nothing is sent.

The text is built from the game names and puzzle numbers alone. No field of a puzzle that holds a word, a figure,
a subject or an answer is read here, so the post cannot give one away.
"""
import datetime as dt
import html
import json
import re
import ssl
import urllib.request

from . import desk, play

try:      # python.org builds on macOS ship without a CA bundle; the system one is at this path
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except Exception:  # noqa: BLE001
    CTX = ssl.create_default_context()

LINES = {"topfloor": "Topfloor", "tickerflip": "Tickerflip", "face-the-figure": "Face the Figure"}


def today_utc():
    return dt.datetime.now(dt.timezone.utc).date()


def title(day):
    return f"Today's games · {day.day} {day.strftime('%b')}"


def site():
    return desk.CONFIG["site_url"].rstrip("/")


def numbers(puzzles):
    """slug -> puzzle number, from whole puzzle files. Only "no" is taken from a puzzle."""
    return {slug: int(p["no"]) for slug, p in puzzles.items()}


def text(nos, day):
    """The message, Telegram HTML. One line per game, no hints."""
    lines = [f"<b>{html.escape(title(day), quote=False)}</b>", ""]
    lines += [f"{LINES[slug]} No. {nos[slug]}" for slug in LINES if slug in nos]
    link = site() + "/play/"
    lines += ["", f'<a href="{html.escape(link)}">{html.escape(link.split("://")[-1])}</a>']
    return "\n".join(lines)


def live_puzzles(day, opener=urllib.request.urlopen):
    """Today's puzzles as the site serves them, or None while any of the live games still shows another day."""
    out = {}
    for slug, _, _, _ in play.live():
        if slug not in LINES:
            continue
        req = urllib.request.Request(f"{site()}/play/{slug}/assets/data/today.json",
                                     headers={"User-Agent": "BoardreadGamesPost/1", "Cache-Control": "no-cache"})
        with opener(req, timeout=20, context=CTX) as f:
            p = json.loads(f.read().decode("utf-8"))
        if p.get("date") != day.isoformat():
            return None
        out[slug] = p
    return out or None


def already_sent(client, day):
    """The channel's post that opens with today's title line, as {"id", "url"}; None when there is none."""
    chat = client.env["TG_CHANNEL"]
    name = chat.lstrip("@") if chat.startswith("@") else (client.call("getChat", {"chat_id": chat}).get("username") or "")
    if not name:
        raise RuntimeError("a private channel cannot be checked for an earlier games post")
    page = client._open(urllib.request.Request(f"{client.PUBLIC}/s/{name}", headers={"User-Agent": "Mozilla/5.0"}),
                        "telegram channel page").decode("utf-8", "replace")
    if "tgme_" not in page:          # an error page or a redirect: not proof that nothing was sent
        raise RuntimeError("the channel page did not load")
    want = title(day)
    for block in page.split('data-post="')[1:]:
        mid = block.split('"', 1)[0].rsplit("/", 1)[-1]
        body = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        first = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", body.group(1)))) if body else ""
        if first.strip().split("\n", 1)[0].strip() == want:
            return {"id": mid, "url": f"https://t.me/{name}/{mid}"}
    return None


def run(send=False, client=None, opener=urllib.request.urlopen, day=None):
    """Prints what it did. Returns the sent message ({"id", "url"}) or None."""
    day = day or today_utc()
    try:
        puzzles = live_puzzles(day, opener)
    except Exception as e:  # noqa: BLE001  the next run tries again
        print(f"games post: the live puzzles could not be read ({type(e).__name__})")
        return None
    if not puzzles:
        print("games post: today's puzzles are not on the site yet")
        return None
    msg = text(numbers(puzzles), day)
    if not send:
        print(msg)
        print("\ndry run: nothing sent. Add --send to post it.")
        return None
    if not desk.growth("games_post"):
        print("games post: switched off (desk.json growth.games_post)")
        return None
    if client is None:
        from . import platforms
        client = platforms.Telegram()
    try:
        seen = already_sent(client, day)
    except Exception as e:  # noqa: BLE001  a day without the post is better than the post twice
        print(f"games post: not sent, the channel could not be checked ({str(e)[:120]})")
        return None
    if seen:
        print(f"games post: already in the channel, {seen['url']}")
        return None
    got = client.call("sendMessage", {"chat_id": client.env["TG_CHANNEL"], "text": msg, "parse_mode": "HTML",
                                      "disable_notification": True, "disable_web_page_preview": True,
                                      "link_preview_options": {"is_disabled": True}})
    chat = client.env["TG_CHANNEL"]
    out = {"id": str(got["message_id"]), "url": f"https://t.me/{chat.lstrip('@')}/{got['message_id']}" if chat.startswith("@") else ""}
    print(f"games post: sent, message {out['id']} {out['url']}".rstrip())
    return out
