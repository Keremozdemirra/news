"""Cross-posting clients: Threads, Facebook Page, Bluesky and Telegram. Standard library only.

Every client has post(post) -> {"id", "url"} and raises Missing when its secrets are not set, which the
desk treats as "not connected yet" and skips without a word. Secrets come from environment variables
(GitHub Actions secrets) and nowhere else; every error string is scrubbed of them before it can reach a
log, because the repository and its Action logs are public. Which platforms run at all is decided by
desk.json "platforms", every one off until the owner switches it on.

Text and images are built here from the same post.json Instagram uses: headline, one-line dek, the story
page on the site and the existing card/detail JPEGs. The SOURCE-comment line is Instagram-only.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import desk, entities, redact
from .feeds import CTX

NAMES = ("threads", "facebook", "bluesky", "telegram")

# a rate limit or block, whichever platform words it: HTTP 429, Meta codes 4/17/32/613, Bluesky RateLimitExceeded,
# Telegram flood control (retry_after)
BLOCKED = re.compile(r"HTTP 429|rate.?limit|RateLimitExceeded|retry_after|\"code\":\s*(4|17|32|613)\b|"
                     r"temporarily blocked|Action is blocked|Too Many Requests", re.I)


# the platform no longer accepts the credential: Meta OAuth code 190 (expired or revoked token), Bluesky's
# AuthenticationRequired / ExpiredToken, Telegram's 401. Retrying cannot fix it; the owner has to store a new secret.
AUTH = re.compile(r"\"code\":\s*190\b|Error validating access token|Session has expired|InvalidToken|ExpiredToken|"
                  r"AuthenticationRequired|Invalid identifier or password|\bHTTP 401\b|\"error_code\":\s*401\b|\bUnauthorized\b", re.I)

# the secret whose change ends an auth cooldown: a renewed token is tried at once, not a day later
CREDENTIAL = {"threads": "THREADS_TOKEN", "facebook": "FB_PAGE_TOKEN", "bluesky": "BSKY_APP_PASSWORD", "telegram": "TG_BOT_TOKEN"}


def fingerprint(name):
    """Eight hex characters of the SHA-256 of the platform's credential: enough to notice a new secret, nothing
    that helps anyone guess it."""
    import hashlib
    v = os.environ.get(CREDENTIAL.get(name, ""), "")
    return hashlib.sha256(v.encode()).hexdigest()[:8] if v else ""


def _same_line(a, b):
    return " ".join((a or "").split()).casefold() == " ".join((b or "").split()).casefold()


# secrets that name an account rather than unlock it; kept readable in errors
PUBLIC_IDS = ("THREADS_USER_ID", "FB_PAGE_ID", "BSKY_HANDLE", "TG_CHANNEL")


class Missing(RuntimeError):
    """The platform's secrets are not set."""


class PlatformError(RuntimeError):
    pass


# text

def _fit(head, detail, tail, limit, measure=len):
    """headline, detail, then tail, within limit. The detail gives way first, then the headline; the tail never does."""
    def build(h, d):
        return "\n\n".join(x for x in (h, d, tail) if x)

    def clip(text, room):
        if measure(text) <= room:
            return text
        words = text.split()
        while words and measure(" ".join(words) + "…") > room:
            words.pop()
        return (" ".join(words) + "…") if words else ""

    text = build(head, detail)
    if measure(text) <= limit:
        return text
    room = limit - measure(build(head, "")) - 2
    if detail and room > 20:
        text = build(head, clip(detail, room))
        if measure(text) <= limit:
            return text
    return build(clip(head, limit - measure(tail) - 2), "")


def _with_ticker(post, text, limit, measure=len):
    """Adds "(NASDAQ: NVDA)" right after the first mention of the story's company when the text still fits the
    platform's limit; otherwise the text is returned as it was. Only the company's full name is matched, so a
    headline that names "Norse" alone never gets the ticker of "Norse Atlantic"."""
    tk, co = post.get("ticker"), (post.get("company") or "").strip()
    if not tk or not co:
        return text
    m = re.search(r"(?<!\w)" + re.escape(co) + r"(?!\w)", text, re.I)
    if not m or text[m.end():m.end() + 2] == " (":
        return text
    longer = f"{text[:m.end()]} ({entities.ticker_text(tk)}){text[m.end():]}"
    return longer if measure(longer) <= limit else text


def story_page(post, channel=None):
    return desk.story_url(post["id"], channel)


def _tail(post, link):
    return f"Sources: {link}"


def _head(post):
    return post["headlines"][0]


def _utf8(text):
    return len(text.encode("utf-8"))


def _sentences(text):
    return [x for x in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if x]


def _words(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def why_it_matters(post, count=3):
    """Up to `count` sentences from the existing dek and body, without a model call. A sentence that mostly
    repeats the headline or an earlier pick is dropped: the body usually opens by restating the headline."""
    head, picked = _words(_head(post)), []
    for s in _sentences(post.get("dek")) + _sentences(post.get("body")):
        w = _words(s)
        if not w or any(len(w & other) / len(w) >= 0.6 for other in [head] + [_words(x) for x in picked]):
            continue
        picked.append(s)
        if len(picked) == count:
            break
    return picked


def threads_text(post):
    """Headline, a short why-it-matters, no disclosure line. No link: Threads shows links poorly in the main post,
    so the story page goes in a reply. 500 characters, emoji counted by UTF-8 bytes; the topic goes in
    topic_tag, not as a hashtag in the text."""
    head, tail = _head(post), ""
    sentences = why_it_matters(post) or _sentences(post.get("dek"))[:1]
    while sentences:  # whole sentences give way before any word is cut
        text = "\n\n".join(x for x in (head, " ".join(sentences), tail) if x)
        if _utf8(text) <= 500:
            return _with_ticker(post, text, 500, _utf8)
        sentences = sentences[:-1]
    return _with_ticker(post, _fit(head, "", tail, 500, measure=_utf8), 500, _utf8)


def threads_reply_text(post):
    return f"Sources: {story_page(post, 'threads')}"


def threads_tag(post):
    """One topic tag (Threads uses a single one): 1-50 characters, no periods or ampersands. desk.json
    threads_topic_tags may name a Threads community tag per topic (it can hold spaces); else the hashtag word."""
    topic = post.get("topic") or ""
    tag = (desk.CONFIG.get("threads_topic_tags") or {}).get(topic) or desk.CONFIG["topic_tags"].get(topic, "").lstrip("#")
    return re.sub(r"[.&]", "", tag)[:50]


def bluesky_text(post):
    """Headline and dek within 300 graphemes. No link and no facets: the link card carries the URL.
    len() counts code points, which is never fewer than graphemes, so the cap holds."""
    return _with_ticker(post, _fit(_head(post), post.get("dek", ""), "", 300), 300)


def bluesky_description(post):
    return post.get("dek") or post.get("body") or ""


def _long_text(post, limit, channel=None):
    return _with_ticker(post, _fit(_head(post), post.get("body") or post.get("dek", ""), _tail(post, story_page(post, channel)), limit), limit)


def is_breaking(post):
    return (post.get("score") or 0) >= desk.CONFIG["breaking_score"]


def digest_text(posts):
    lines = ["Today on Boardread", ""]
    for i, p in enumerate(posts, 1):
        lines += [f"{i}. {_head(p)}", story_page(p, "telegram"), ""]
    return "\n".join(lines + cross_links("telegram")).rstrip()


def cross_links(here):
    """One closing line naming the brand's other places, for digests: the site and the channels that have an address."""
    others = [a for a in desk.CONFIG.get("accounts", []) if a.get("url") and a["name"].lower() != here]
    if not others:
        return []
    return [f"Every story: {desk.CONFIG['site_url']}", "Also on " + ", ".join(f"{a['name']} {a['url']}" for a in others)]


def telegram_tag(post):
    """The topic as one hashtag: Telegram's post search finds channel posts by hashtag."""
    return desk.CONFIG["topic_tags"].get(post.get("topic") or "", "")


def facebook_skip(post):
    """Why a post stays off the Facebook Page, or "": only the day's most important stories go there."""
    if (post.get("score") or 0) < desk.facebook_min_score_now():
        return "below facebook_min_score"
    if desk.platform_sent_last_24h("facebook") >= desk.CONFIG["facebook_daily_max"]:
        return "above facebook_daily_max"
    return ""


def telegram_caption(post):
    tag = telegram_tag(post)
    if not tag:
        return _long_text(post, 1024, "telegram")  # sendPhoto and InputMediaPhoto: 0-1024 characters
    return _long_text(post, 1024 - len(tag) - 2, "telegram") + "\n\n" + tag


def facebook_text(post):
    return _long_text(post, 2000, "facebook")  # no documented cap; kept to a short report like the other platforms


def _images(post):
    return [desk.media_url(post["id"], c) for c in post["cards"]]


# http

class Client:
    secrets = ()  # env var names; the values are scrubbed from every error

    def __init__(self, opener=urllib.request.urlopen, sleep=time.sleep):
        self.opener = opener
        self.sleep = sleep
        self.env = {k: os.environ.get(k, "") for k in self.secrets}
        if not all(self.env.values()):
            raise Missing(", ".join(self.secrets))
        if self.env.get("BSKY_HANDLE"):
            self.env["BSKY_HANDLE"] = self.env["BSKY_HANDLE"].strip().lstrip("@")

    def _scrub(self, text):
        # identifiers (THREADS_USER_ID is "me") are not credentials: replacing them garbled every error message
        creds = [v for k, v in self.env.items() if v and k not in PUBLIC_IDS and len(v) >= 4]
        for v in sorted(creds, key=len, reverse=True):
            text = text.replace(v, "<secret>").replace(urllib.parse.quote(v, safe=""), "<secret>")
        return redact.scrub(text)

    def _open(self, req, label):
        try:
            with self.opener(req, timeout=60, context=CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise PlatformError(self._scrub(f"{label}: HTTP {e.code}: {body[:400]}")) from None
        except urllib.error.URLError as e:
            raise PlatformError(self._scrub(f"{label}: {e.reason}")) from None

    def form(self, method, url, params, label):
        if method == "GET":
            req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), method="GET")
        else:
            req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method=method)
        return json.loads(self._open(req, label))

    def json(self, url, body, label, headers=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
        return json.loads(self._open(req, label))

    def fetch(self, url):
        return self._open(urllib.request.Request(url), "fetch image")


# Threads
# Docs read 2026-11-26: developers.facebook.com/docs/threads/posts (container + threads_publish, text 500
# characters by UTF-8 bytes, JPEG/PNG up to 8 MB, topic_tag, is_made_with_ai), .../retrieve-and-manage-replies/
# create-replies (TEXT container with reply_to_id, then threads_publish; needs threads_manage_replies),
# developers.facebook.com/docs/threads/troubleshooting (container status),
# developers.facebook.com/docs/threads/threads-media (permalink field; token as access_token parameter).

class Threads(Client):
    secrets = ("THREADS_TOKEN", "THREADS_USER_ID")
    host = os.environ.get("THREADS_API_HOST", "https://graph.threads.com/v1.0")

    def call(self, method, path, params):
        return self.form(method, f"{self.host}/{path}", {**params, "access_token": self.env["THREADS_TOKEN"]},
                         f"threads {method} {path.split('/')[-1]}")

    def wait(self, container, tries=6, pause=30):
        # the docs advise polling once a minute for five minutes at most; images finish sooner
        for _ in range(tries):
            got = self.call("GET", container, {"fields": "status,error_message"})
            if got.get("status") in ("FINISHED", "PUBLISHED"):
                return
            if got.get("status") in ("ERROR", "EXPIRED"):
                raise PlatformError(f"threads container {container}: {got.get('status')} {got.get('error_message', '')}")
            self.sleep(pause)
        raise PlatformError(f"threads container {container}: not ready after {tries * pause}s")

    def find(self, post):
        """This story already on the profile: a post whose first line is the headline as threads_text writes it,
        not older than the queue entry. Run before every send, so a lost status commit never means a second post."""
        head = threads_text(post).split("\n", 1)[0]
        born = desk._stamp(post.get("created", ""))
        got = self.call("GET", f"{self.env['THREADS_USER_ID']}/threads", {"fields": "id,text,permalink,timestamp", "limit": 25})
        for t in got.get("data", []):
            seen = desk._stamp(t.get("timestamp", ""))
            if born and seen and seen < born - timedelta(minutes=5):
                continue
            if _same_line((t.get("text") or "").split("\n", 1)[0], head):
                return {"id": t["id"], "url": t.get("permalink", "")}
        return None

    def check(self):
        """Reads the profile the token belongs to and posts nothing."""
        me = self.call("GET", self.env["THREADS_USER_ID"], {"fields": "id,username"})
        return f"token reaches @{me.get('username')}"

    def post(self, post):
        uid = self.env["THREADS_USER_ID"]
        # text first, one image only: the card. No is_made_with_ai label: it marks the media as AI-made, and the
        # photos are real.
        params = {"media_type": "IMAGE", "image_url": _images(post)[0], "text": threads_text(post)}
        if threads_tag(post):
            params["topic_tag"] = threads_tag(post)
        container = self.call("POST", f"{uid}/threads", params)["id"]
        self.wait(container)
        media = self.call("POST", f"{uid}/threads_publish", {"creation_id": container})["id"]
        try:
            link = self.call("GET", media, {"fields": "permalink"}).get("permalink", "")
        except PlatformError:
            link = ""  # the post is live; losing its id here would make the desk post it again
        got = {"id": media, "url": link}
        # the reply never undoes the post: its outcome is stored beside it, and it is not retried
        try:
            got["reply"] = self.reply(media, threads_reply_text(post))
        except Exception as e:  # noqa: BLE001
            got["reply_error"] = self._scrub(str(e))[:300]
        return got

    def reply(self, to_id, text):
        """A reply is a TEXT container with reply_to_id, published like any post (needs threads_manage_replies)."""
        uid = self.env["THREADS_USER_ID"]
        container = self.call("POST", f"{uid}/threads", {"media_type": "TEXT", "text": text, "reply_to_id": to_id})["id"]
        self.wait(container)
        return {"id": self.call("POST", f"{uid}/threads_publish", {"creation_id": container})["id"]}


# Facebook Page
# Docs read 2026-11-26: developers.facebook.com/docs/graph-api/reference/page/photos/ (POST /{page-id}/photos with
# url and published=false, then POST /{page-id}/feed with message and attached_media[n]={"media_fbid": id};
# Page access token, permissions pages_manage_posts, pages_read_engagement, pages_show_list).

class Facebook(Client):
    secrets = ("FB_PAGE_TOKEN", "FB_PAGE_ID")
    host = os.environ.get("FB_API_HOST", "https://graph.facebook.com")
    version = os.environ.get("FB_API_VERSION", "v27.0")

    _page_token = None

    def page_token(self):
        """The Boardread Page's own token, never a person's.

        The stored token may be the Page token itself or a user token that manages the Page; with a user token
        the Page token is read from /me/accounts (a Page token got through a long-lived user token does not
        expire: developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived). Posting
        with a user token would put the news on someone's personal profile, so that is refused."""
        if self._page_token is not None:
            return self._page_token
        base, tok = f"{self.host}/{self.version}", self.env["FB_PAGE_TOKEN"]
        try:
            pages = self.form("GET", f"{base}/me/accounts", {"fields": "id,name,access_token", "access_token": tok},
                              "facebook GET accounts").get("data", [])
        except PlatformError:
            pages = None  # a Page token has no /me/accounts
        want = self.env["FB_PAGE_ID"].strip()
        if pages is not None:
            pick = [p for p in pages if p.get("id") == want] or [p for p in pages if "boardread" in p.get("name", "").lower()]
            if len(pick) != 1 or not pick[0].get("access_token"):
                raise PlatformError(f"facebook: the token manages {len(pages)} Page(s) and none is clearly Boardread")
            self._page_token, self.page_name = pick[0]["access_token"], pick[0].get("name", "")
            self.env["FB_PAGE_ID"] = str(pick[0]["id"])
        else:
            me = self.form("GET", f"{base}/me", {"fields": "id,name,category", "access_token": tok}, "facebook GET me")
            if not me.get("category"):
                raise PlatformError("facebook: the stored token is neither a Page token nor a user token that manages a Page")
            self._page_token, self.page_name = tok, me.get("name", "")
            self.env["FB_PAGE_ID"] = str(me["id"])
        self.env["_page_token"] = self._page_token  # scrubbed from this client's errors like the stored secrets
        redact.register(self._page_token)  # and from every saved file and log line of the run
        return self._page_token

    def call(self, path, params):
        return self.form("POST", f"{self.host}/{self.version}/{path}", {**params, "access_token": self.page_token()},
                         f"facebook POST {path.split('/')[-1]}")

    def check(self):
        """Reads the Page and posts nothing."""
        self.page_token()
        return f"page {self.page_name!r} reachable" + (" (stored token is the Page token)" if self._page_token == self.env["FB_PAGE_TOKEN"] else " (Page token read through the user token)")

    def find(self, post):
        """This story already on the Page: a post whose text carries the story's own page address."""
        page, url = self.env["FB_PAGE_ID"], story_page(post)
        got = self.form("GET", f"{self.host}/{self.version}/{page}/posts",
                        {"fields": "id,message,permalink_url,created_time", "limit": 25, "access_token": self.page_token()},
                        "facebook GET posts")
        for m in got.get("data", []):
            if url in (m.get("message") or ""):
                return {"id": m["id"], "url": m.get("permalink_url") or f"https://www.facebook.com/{m['id']}"}
        return None

    def token_expiry(self):
        """When the stored token stops working, from Meta's debug_token (a token may inspect itself): 
        expires_at and data_access_expires_at, as {"expires", "data_access"} datetimes (None: no end reported). Posts nothing."""
        tok = self.env["FB_PAGE_TOKEN"]
        got = self.form("GET", f"{self.host}/{self.version}/debug_token", {"input_token": tok, "access_token": tok},
                        "facebook GET debug_token").get("data", {})
        # expires_at 0 means the token itself never expires; data_access_expires_at is the separate 90-day window
        # after which Meta stops returning user data until someone re-authorises the app. Both are reported, apart.
        at = lambda k: datetime.fromtimestamp(got[k], timezone.utc) if got.get(k) else None  # noqa: E731
        return {"expires": at("expires_at"), "data_access": at("data_access_expires_at")}

    def post(self, post):
        self.page_token()
        page = self.env["FB_PAGE_ID"]
        photos = [self.call(f"{page}/photos", {"url": u, "published": "false"})["id"] for u in _images(post)[:10]]
        params = {"message": facebook_text(post)}
        for i, p in enumerate(photos):
            params[f"attached_media[{i}]"] = json.dumps({"media_fbid": p})
        pid = self.call(f"{page}/feed", params)["id"]
        return {"id": pid, "url": f"https://www.facebook.com/{pid}"}


# Bluesky
# Docs read 2026-11-26: docs.bsky.app/docs/advanced-guides/posts and docs.bsky.app/docs/tutorials/creating-a-post
# (app.bsky.feed.post, app.bsky.embed.external with uri, title, description and an optional thumb blob, uploadBlob),
# atproto lexicon com.atproto.server.createSession (identifier + app password -> accessJwt, did).
# The two pages disagree on the per-image cap (1,000,000 bytes and 2 MB); the stricter one is used for the thumb.

class Bluesky(Client):
    secrets = ("BSKY_HANDLE", "BSKY_APP_PASSWORD")
    host = os.environ.get("BSKY_PDS", "https://bsky.social")
    MAX_BYTES = 1_000_000

    def xrpc(self, name, body, jwt=None, raw=None, mime=None):
        headers = {"Authorization": f"Bearer {jwt}"} if jwt else {}
        if raw is not None:
            req = urllib.request.Request(f"{self.host}/xrpc/{name}", data=raw, method="POST",
                                         headers={**headers, "Content-Type": mime})
            return json.loads(self._open(req, f"bluesky {name}"))
        return self.json(f"{self.host}/xrpc/{name}", body, f"bluesky {name}", headers)

    def check(self):
        """Logs in and posts nothing: proves the handle and app password before the platform is switched on."""
        sess = self.xrpc("com.atproto.server.createSession",
                         {"identifier": self.env["BSKY_HANDLE"], "password": self.env["BSKY_APP_PASSWORD"]})
        return f"logged in as @{sess.get('handle')}"

    APPVIEW = os.environ.get("BSKY_APPVIEW", "https://public.api.bsky.app")

    def find(self, post):
        """This story already on the profile: a recent post whose link card points at the story page. The public
        AppView answers without logging in, so the check costs no session."""
        url = story_page(post)
        got = self.form("GET", f"{self.APPVIEW}/xrpc/app.bsky.feed.getAuthorFeed",
                        {"actor": self.env["BSKY_HANDLE"], "limit": 30, "filter": "posts_no_replies"}, "bluesky getAuthorFeed")
        for item in got.get("feed", []):
            p = item.get("post") or {}
            ext = ((p.get("record") or {}).get("embed") or {}).get("external") or {}
            if ext.get("uri") == url:
                rkey = p.get("uri", "").rsplit("/", 1)[-1]
                return {"id": p.get("uri", ""), "url": f"https://bsky.app/profile/{self.env['BSKY_HANDLE']}/post/{rkey}"}
        return None

    def post(self, post):
        sess = self.xrpc("com.atproto.server.createSession",
                         {"identifier": self.env["BSKY_HANDLE"], "password": self.env["BSKY_APP_PASSWORD"]})
        jwt, did = sess["accessJwt"], sess["did"]
        card = {"uri": story_page(post, "bluesky"), "title": _head(post), "description": bluesky_description(post)}
        data = self.fetch(_images(post)[0])
        # a link card without a thumbnail still works, so an oversize card is skipped rather than failing the post
        if len(data) <= self.MAX_BYTES:
            card["thumb"] = self.xrpc("com.atproto.repo.uploadBlob", None, jwt, raw=data, mime="image/jpeg")["blob"]
        record = {"$type": "app.bsky.feed.post", "text": bluesky_text(post), "langs": ["en"],
                  "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                  "embed": {"$type": "app.bsky.embed.external", "external": card}}
        got = self.xrpc("com.atproto.repo.createRecord",
                        {"repo": did, "collection": "app.bsky.feed.post", "record": record}, jwt)
        # the web URL of an at:// URI is bsky.app/profile/<handle>/post/<rkey>
        rkey = got["uri"].rsplit("/", 1)[-1]
        return {"id": got["uri"], "url": f"https://bsky.app/profile/{self.env['BSKY_HANDLE']}/post/{rkey}"}


# Telegram channel
# Docs read 2026-11-26: core.telegram.org/bots/api (sendPhoto, sendMediaGroup with 2-10 InputMediaPhoto, sendMessage, disable_notification,
# link_preview_options (disable_web_page_preview is no longer listed; both are sent),
# caption 0-1024 characters, photo by HTTP URL up to 5 MB per "Sending files", ResponseParameters.retry_after).
# The bot must be an administrator of the channel with permission to post.

class Telegram(Client):
    secrets = ("TG_BOT_TOKEN", "TG_CHANNEL")
    host = os.environ.get("TG_API_HOST", "https://api.telegram.org")

    def call(self, method, params):
        got = self.json(f"{self.host}/bot{self.env['TG_BOT_TOKEN']}/{method}", params, f"telegram {method}")
        if not got.get("ok"):
            raise PlatformError(self._scrub(f"telegram {method}: {json.dumps(got)[:300]}"))
        return got["result"]

    def check(self):
        """Reads the bot and the channel and posts nothing; fails if the bot cannot post there."""
        bot = self.call("getMe", {})
        chat = self.call("getChat", {"chat_id": self.env["TG_CHANNEL"]})
        member = self.call("getChatMember", {"chat_id": self.env["TG_CHANNEL"], "user_id": bot["id"]})
        if member.get("status") != "creator" and not member.get("can_post_messages"):
            raise PlatformError(f"telegram: @{bot.get('username')} is not allowed to post in {chat.get('title')}")
        return f"bot @{bot.get('username')} can post in {chat.get('title')} (@{chat.get('username') or 'private'})"

    def post(self, post):
        urls = _images(post)[:10]
        chat, caption = self.env["TG_CHANNEL"], telegram_caption(post)
        # routine posts are silent; only a breaking story (score at the desk's breaking bar) notifies subscribers
        silent = {"disable_notification": not is_breaking(post)}
        if len(urls) == 1:
            first = self.call("sendPhoto", {"chat_id": chat, "photo": urls[0], "caption": caption, **silent})
        else:
            media = [{"type": "photo", "media": u} for u in urls]
            media[0]["caption"] = caption  # an album shows the caption of its first photo
            first = self.call("sendMediaGroup", {"chat_id": chat, "media": media, **silent})[0]
        username = (first.get("chat") or {}).get("username") or (chat.lstrip("@") if chat.startswith("@") else "")
        return {"id": str(first["message_id"]), "url": f"https://t.me/{username}/{first['message_id']}" if username else ""}

    def pin(self, text):
        """Send one silent message and pin it. Channels never notify on a pin (core.telegram.org/bots/api#pinchatmessage);
        the bot needs can_pin_messages, or can_edit_messages in a channel."""
        chat = self.env["TG_CHANNEL"]
        got = self.call("sendMessage", {"chat_id": chat, "text": text, "disable_notification": True,
                                        "link_preview_options": {"is_disabled": True}, "disable_web_page_preview": True})
        self.call("pinChatMessage", {"chat_id": chat, "message_id": got["message_id"], "disable_notification": True})
        return {"id": str(got["message_id"])}

    def digest(self, posts):
        """The evening digest: one silent text message, links not expanded."""
        got = self.call("sendMessage", {"chat_id": self.env["TG_CHANNEL"], "text": digest_text(posts),
                                        "disable_notification": True, "disable_web_page_preview": True,
                                        "link_preview_options": {"is_disabled": True}})
        return {"id": str(got["message_id"])}


CLIENTS = {"threads": Threads, "facebook": Facebook, "bluesky": Bluesky, "telegram": Telegram}
