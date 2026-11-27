"""The daily games post: today's three puzzle numbers and the /play/ link, once a day on Threads, Bluesky, Telegram
and Facebook (never the Instagram feed).

Switch: desk.json growth.games_post, and a platform only when desk.json platforms has it on. Sent once per UTC day
per platform, after the day's puzzles are on the site: the numbers come from the live
/play/<game>/assets/data/today.json, and nothing is sent until all three carry today's date.

Each platform's own feed is the record of what was sent: a post that already opens with today's title line means
that platform is done for the day. When the feed cannot be read, nothing is sent there. A platform that took a news
post less than social_spacing_minutes ago, or is cooling down, waits for a later run.

The text is built from the game names and puzzle numbers alone. No field of a puzzle that holds a word, a figure,
a subject or an answer is read here, so the post cannot give one away. The picture is one game's share image
(its start screen), a different game each day.

Only the platform clients' own calls are used; platforms.py is not changed by this module.
"""
import datetime as dt
import html
import json
import re
import ssl
import urllib.request
from datetime import timedelta, timezone

from . import desk, play

try:      # python.org builds on macOS ship without a CA bundle; the system one is at this path
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except Exception:  # noqa: BLE001
    CTX = ssl.create_default_context()

LINES = {"topfloor": "Topfloor", "tickerflip": "Tickerflip", "face-the-figure": "Face the Figure"}
PLATFORMS = ("threads", "bluesky", "telegram", "facebook")


def today_utc():
    return dt.datetime.now(dt.timezone.utc).date()


def title(day):
    return f"Today's games · {day.day} {day.strftime('%b')}"


def site():
    return desk.CONFIG["site_url"].rstrip("/")


def link(channel=""):
    """The games page. With growth.utm on it carries the channel's label, like a story link (desk.story_page)."""
    url = site() + "/play/"
    return url + f"?utm_source={channel}&utm_medium=social" if channel and desk.growth("utm") else url


def numbers(puzzles):
    """slug -> puzzle number, from whole puzzle files. Only "no" is taken from a puzzle."""
    return {slug: int(p["no"]) for slug, p in puzzles.items()}


def body(nos, day):
    """Title line, blank, one line per game. Plain text, no hints."""
    return "\n".join([title(day), ""] + [f"{LINES[slug]} No. {nos[slug]}" for slug in LINES if slug in nos])


def text(nos, day, channel=""):
    """The whole post as plain text: the body and the link."""
    return body(nos, day) + "\n\n" + link(channel)


def telegram_html(nos, day):
    lines = body(nos, day).split("\n")
    url = link("telegram")
    return "\n".join([f"<b>{html.escape(lines[0], quote=False)}</b>"] + [html.escape(x, quote=False) for x in lines[1:]]
                     + ["", f'<a href="{html.escape(url)}">{html.escape(site().split("://")[-1] + "/play/")}</a>'])


def image(nos, day):
    """One game's share image, another game each day; None when the game ships none."""
    slugs = [s for s in LINES if s in nos]
    slug = slugs[day.toordinal() % len(slugs)]
    return f"{site()}/play/{slug}/assets/share.jpg" if (play.GAMES_DIR / slug / "assets" / "share.jpg").exists() else None


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


def _opens_with(text_, day):
    return (text_ or "").strip().split("\n", 1)[0].strip() == title(day)


# ---------------------------------------------------------------- already sent today? (reads, never writes)
def seen_telegram(c, day):
    chat = c.env["TG_CHANNEL"]
    name = chat.lstrip("@") if chat.startswith("@") else (c.call("getChat", {"chat_id": chat}).get("username") or "")
    if not name:
        raise RuntimeError("a private channel cannot be checked for an earlier games post")
    page = c._open(urllib.request.Request(f"{c.PUBLIC}/s/{name}", headers={"User-Agent": "Mozilla/5.0"}),
                   "telegram channel page").decode("utf-8", "replace")
    if "tgme_" not in page:          # an error page or a redirect: not proof that nothing was sent
        raise RuntimeError("the channel page did not load")
    for block in page.split('data-post="')[1:]:
        mid = block.split('"', 1)[0].rsplit("/", 1)[-1]
        got = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        first = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", got.group(1)))) if got else ""
        if _opens_with(first, day):
            return {"id": mid, "url": f"https://t.me/{name}/{mid}"}
    return None


def seen_threads(c, day):
    got = c.call("GET", f"{c.env['THREADS_USER_ID']}/threads", {"fields": "id,text,permalink,timestamp", "limit": 25})
    for t in got["data"]:
        if _opens_with(t.get("text"), day):
            return {"id": t["id"], "url": t.get("permalink", "")}
    return None


def seen_facebook(c, day):
    token = c.page_token()
    got = c.form("GET", f"{c.host}/{c.version}/{c.env['FB_PAGE_ID']}/posts",
                 {"fields": "id,message,permalink_url,created_time", "limit": 25, "access_token": token}, "facebook GET posts")
    for m in got["data"]:
        if _opens_with(m.get("message"), day):
            return {"id": m["id"], "url": m.get("permalink_url") or f"https://www.facebook.com/{m['id']}"}
    return None


def seen_bluesky(c, day):
    got = c.form("GET", f"{c.APPVIEW}/xrpc/app.bsky.feed.getAuthorFeed",
                 {"actor": c.env["BSKY_HANDLE"], "limit": 30, "filter": "posts_no_replies"}, "bluesky getAuthorFeed")
    for item in got["feed"]:
        p = item.get("post") or {}
        if _opens_with((p.get("record") or {}).get("text"), day):
            return {"id": p.get("uri", ""), "url": f"https://bsky.app/profile/{c.env['BSKY_HANDLE']}/post/{p.get('uri', '').rsplit('/', 1)[-1]}"}
    return None


# ---------------------------------------------------------------- send
def send_telegram(c, nos, day):
    chat, pic = c.env["TG_CHANNEL"], image(nos, day)
    quiet = {"chat_id": chat, "parse_mode": "HTML", "disable_notification": True}
    if pic:
        got = c.call("sendPhoto", {**quiet, "photo": pic, "caption": telegram_html(nos, day)})
    else:
        got = c.call("sendMessage", {**quiet, "text": telegram_html(nos, day), "disable_web_page_preview": True,
                                     "link_preview_options": {"is_disabled": True}})
    return {"id": str(got["message_id"]), "url": f"https://t.me/{chat.lstrip('@')}/{got['message_id']}" if chat.startswith("@") else ""}


def send_threads(c, nos, day):
    uid, pic, words = c.env["THREADS_USER_ID"], image(nos, day), text(nos, day, "threads")
    params = {"media_type": "IMAGE", "image_url": pic, "text": words} if pic else {"media_type": "TEXT", "text": words}
    container = c.call("POST", f"{uid}/threads", params)["id"]
    c.wait(container)
    media = c.publish(container)
    try:
        url = c.call("GET", media, {"fields": "permalink"}).get("permalink", "")
    except Exception:  # noqa: BLE001  the post is live
        url = ""
    return {"id": media, "url": url}


def send_facebook(c, nos, day):
    """A link post: Facebook draws the card from the games page's own preview tags."""
    c.page_token()
    pid = c.call(f"{c.env['FB_PAGE_ID']}/feed", {"message": text(nos, day, "facebook"), "link": link("facebook")})["id"]
    return {"id": pid, "url": f"https://www.facebook.com/{pid}"}


def send_bluesky(c, nos, day):
    """The body as the post, the link as its card, the share image as the card's picture when it is small enough."""
    sess = c.xrpc("com.atproto.server.createSession", {"identifier": c.env["BSKY_HANDLE"], "password": c.env["BSKY_APP_PASSWORD"]})
    jwt, did = sess["accessJwt"], sess["did"]
    card = {"uri": link("bluesky"), "title": "Boardread games", "description": "Topfloor, Tickerflip, Face the Figure. New every day."}
    pic = image(nos, day)
    if pic:
        try:
            data = c.fetch(pic)
            if len(data) <= c.MAX_BYTES:
                card["thumb"] = c.xrpc("com.atproto.repo.uploadBlob", None, jwt, raw=data, mime="image/jpeg")["blob"]
        except Exception:  # noqa: BLE001  a card without a picture still works
            pass
    record = {"$type": "app.bsky.feed.post", "text": body(nos, day), "langs": ["en"],
              "createdAt": dt.datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
              "embed": {"$type": "app.bsky.embed.external", "external": card}}
    got = c.xrpc("com.atproto.repo.createRecord", {"repo": did, "collection": "app.bsky.feed.post", "record": record}, jwt)
    return {"id": got["uri"], "url": f"https://bsky.app/profile/{c.env['BSKY_HANDLE']}/post/{got['uri'].rsplit('/', 1)[-1]}"}


SEEN = {"telegram": seen_telegram, "threads": seen_threads, "facebook": seen_facebook, "bluesky": seen_bluesky}
SEND = {"telegram": send_telegram, "threads": send_threads, "facebook": send_facebook, "bluesky": send_bluesky}


def waits(name):
    """Why this platform takes no games post right now, or None."""
    if desk.platform_cooldown(name):
        return "cooling down"
    last = desk._last_sent(name)
    gap = timedelta(minutes=desk.CONFIG.get("social_spacing_minutes", 0))
    if last and desk.now() - last < gap:
        return f"a news post went out at {last:%H:%M} UTC, next after {last + gap:%H:%M}"
    return None


TRY_MINUTES = 15     # of each hour: a platform that refuses is asked again 24 times a day at most, not every run


def run(send=False, clients=None, opener=urllib.request.urlopen, day=None, minute=None):
    """Prints what it did. Returns {platform: {"id", "url"}} for the posts sent in this run."""
    day = day or today_utc()
    minute = desk.now().minute if minute is None else minute
    if send and minute >= TRY_MINUTES:
        return {}
    try:
        puzzles = live_puzzles(day, opener)
    except Exception as e:  # noqa: BLE001  the next run tries again
        print(f"games post: the live puzzles could not be read ({type(e).__name__})")
        return {}
    if not puzzles:
        print("games post: today's puzzles are not on the site yet")
        return {}
    nos = numbers(puzzles)
    names = [n for n in PLATFORMS if desk.CONFIG.get("platforms", {}).get(n)]
    if not send:
        print(text(nos, day))
        print(f"\npicture: {image(nos, day) or 'none'}")
        print(f"dry run: nothing sent. With --send it goes to: {', '.join(names) or 'no platform'}.")
        return {}
    if not desk.growth("games_post"):
        print("games post: switched off (desk.json growth.games_post)")
        return {}
    sent = {}
    for name in names:
        try:
            if clients is not None:
                client = clients.get(name)
                if client is None:
                    continue
            else:
                from . import platforms
                client = platforms.CLIENTS[name]()
        except Exception as e:  # noqa: BLE001  secrets not set for this platform
            print(f"games post: {name} skipped ({type(e).__name__})")
            continue
        why = waits(name)
        if why:
            print(f"games post: {name} waits, {why}")
            continue
        try:
            seen = SEEN[name](client, day)
        except Exception as e:  # noqa: BLE001  a day without the post is better than the post twice
            print(f"games post: {name} not sent, its feed could not be checked ({str(e)[:120]})")
            continue
        if seen:
            print(f"games post: {name} already has it, {seen['url']}")
            continue
        try:
            sent[name] = SEND[name](client, nos, day)
            print(f"games post: {name} sent, {sent[name]['url'] or sent[name]['id']}")
        except Exception as e:  # noqa: BLE001  one platform's failure never stops the others
            print(f"games post: {name} failed ({str(e)[:200]})")
    return sent
