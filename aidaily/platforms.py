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
    """The sources address, then the AI line when it is on: the tail never gives way to the text (_fit)."""
    return "\n".join(x for x in (f"Sources: {link}", desk.ai_line()) if x)


def _head(post):
    return post["headlines"][0]


def _utf8(text):
    return len(text.encode("utf-8"))


# a full stop after these is not the end of a sentence: "21 million U.S. users" was cut at "U.S." on Bluesky
ABBREV = re.compile(r"(?:^|[\s(])(?:[A-Z](?:\.[A-Z])*|Mr|Mrs|Ms|Dr|Prof|Inc|Corp|Co|Ltd|St|No|Jr|Sr|vs|Gov|Sen|Rep|Gen|"
                    r"Lt|Col|Capt|Sgt|Jan|Feb|Mar|Apr|Aug|Sept?|Oct|Nov|Dec)\.$")


def _sentences(text):
    parts = [x for x in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if x]
    out = []
    for x in parts:
        if out and (ABBREV.search(out[-1]) or x[:1].islower()):
            out[-1] += " " + x
        else:
            out.append(x)
    return out


# a sentence that leans on one the post does not carry: "She also discusses...", "...following those findings."
DANGLING = re.compile(r"^(?:she|he|it|its|they|their|his|her|this|these|that|such|also|meanwhile|however|but|and|so|"
                      r"both|the report|the statement|the move|the decision)\b|\bthose\b", re.I)
CONTENT_STOP = set("""about after also among and are been being but can could for from had has have her his into its more
most new not now one our out over said says she than that the their them then there these they this those two was
were what when where which while who will with would year years week weeks you""".split())


def _standalone(sentence):
    return len(sentence.split()) >= 6 and not DANGLING.search(sentence.strip())


def _stems(text):
    return {w[:5] for w in re.findall(r"[a-z0-9]+", text.casefold()) if len(w) >= 3 and w not in CONTENT_STOP}  # ECB, IMF, Fed count


def _words(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def why_it_matters(post, count=3):
    """Up to `count` sentences from the existing dek and body, without a model call. A sentence that mostly
    repeats the headline or an earlier pick is dropped (the body usually opens by restating the headline), and so is
    one that points at something the post does not say or, from the body, shares no word with the headline."""
    head, picked = _words(_head(post)), []
    topic = _stems(_head(post))
    dek = _sentences(post.get("dek"))
    for s in dek + _sentences(post.get("body")):
        w = _words(s)
        if not w or any(len(w & other) / len(w) >= 0.6 for other in [head] + [_words(x) for x in picked]):
            continue
        # the same fact in other words ("1Password says it was hacked in a recent data breach" under a headline and dek
        # that hold the breach): the content stems of the headline, dek and earlier picks together give it away
        mine = _stems(s)
        if mine and s not in dek and len(mine & _stems(" ".join([_head(post), post.get("dek") or "", *picked]))) / len(mine) >= 0.8:
            continue
        # a sentence must stand on its own, and a body sentence must share a word with the headline: an unrelated
        # line about Latvian fighter jets once went out under a headline about Zelenskyy
        if not _standalone(s) or (s not in dek and not (_stems(s) & topic)):
            continue
        picked.append(s)
        if len(picked) == count:
            break
    return picked


def threads_text(post):
    """Headline, a short why-it-matters, then the AI line when it is on. No link: Threads shows links poorly in the main post,
    so the story page goes in a reply. 500 characters, emoji counted by UTF-8 bytes; the topic goes in
    topic_tag, not as a hashtag in the text."""
    head, tail = _head(post), desk.ai_line()
    sentences = why_it_matters(post) or [x for x in _sentences(post.get("dek"))[:1] if _standalone(x)]
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


def bluesky_tag(post):
    """One tag, CamelCase so screen readers say it as words (desk.json bluesky_topic_tags), else the topic itself."""
    topic = post.get("topic") or ""
    return re.sub(r"[^A-Za-z0-9_]", "", (desk.CONFIG.get("bluesky_topic_tags") or {}).get(topic) or topic)


def _tag_facet(text, tag):
    """app.bsky.richtext.facet#tag over "#tag" at the end of text (byte offsets, tag without the #)."""
    end = len(text.encode("utf-8"))
    return {"index": {"byteStart": end - len(tag.encode("utf-8")) - 1, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}]}


def _plus_tag(text, tag, limit=300):
    """text with one closing "#tag" line when it fits, and its facet list."""
    if tag and len(f"{text}\n\n#{tag}") <= limit:
        text = f"{text}\n\n#{tag}"
        return text, [_tag_facet(text, tag)]
    return text, []


def bluesky_text(post):
    """(text, facets) for a link-card post. The card under the post shows the headline as its title and the dek as
    its description, so the text says neither: it gives the next fact, then one topic tag (roadmap 2026-11-27:
    the headline twice, in the text and the card, read as filler). With no such sentence the headline stands
    alone. 300 graphemes; len() counts code points, never fewer. Alt text: app.bsky.embed.external has no alt
    field, so the card's title and description are the text alternative."""
    dek = post.get("dek") or ""
    extra = [x for x in why_it_matters(post) if not _same_line(x, dek) and not _same_line(x, _head(post))][:1]
    text = extra[0] if extra and len(extra[0]) <= 280 else _head(post)[:300]
    return _plus_tag(_with_ticker(post, text, 290), bluesky_tag(post))


def bluesky_video_text(post):
    """(text, facets) for a video post: there is no link card, so the story address goes in the text as a link
    facet (docs.bsky.app/docs/advanced-guides/post-richtext: byteStart and byteEnd count UTF-8 bytes). 300
    graphemes, the headline kept whole before the sentence."""
    url = story_page(post, "bluesky")
    tail = f"Sources: {url}"
    dek = post.get("dek") or ""
    extra = (why_it_matters(post) or [x for x in _sentences(dek) if _standalone(x)])[:1]
    text = _fit(_head(post), " ".join(extra), tail, 300)
    if not text.endswith(tail):
        text = _fit(_head(post), "", tail, 300)
    text = _with_ticker(post, text, 300)  # no card here, so the headline leads; the facet is placed after it
    start = len(text.encode("utf-8")) - len(url.encode("utf-8"))
    facets = [{"index": {"byteStart": start, "byteEnd": start + len(url.encode("utf-8"))},
               "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}] if text.endswith(url) else []
    text, tag = _plus_tag(text, bluesky_tag(post))
    return text, facets + tag


def bluesky_description(post):
    return post.get("dek") or post.get("body") or ""


def _long_text(post, limit, channel=None):
    return _with_ticker(post, _fit(_head(post), post.get("body") or post.get("dek", ""), _tail(post, story_page(post, channel)), limit), limit)


def is_breaking(post):
    return (post.get("score") or 0) >= desk.CONFIG["breaking_score"]


def _h(text):
    import html
    return html.escape(text or "", quote=True)


def digest_text(posts):
    """The evening digest for Telegram (parse_mode HTML): a bold title, then one numbered line per article with the
    headline as the link, so a list of ten reads as ten lines, not twenty."""
    lines = ["<b>Today on Boardread</b>", ""]
    for i, p in enumerate(posts, 1):
        lines.append(f'{i}. <a href="{_h(story_page(p, "telegram"))}">{_h(_head(p))}</a>')
    return "\n".join(lines + [""] + [_h(x) for x in cross_links("telegram")]).rstrip()


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


def _visible(text):
    """Length as Telegram counts a caption: after the HTML entities are parsed."""
    import html
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def telegram_caption(post):
    """A channel post in the house style of news channels (parse_mode HTML): the headline in bold, two sentences
    at most, then one quiet line with the sources link and the topic hashtag (Telegram's post search
    finds channel posts by hashtag). 1024 characters as Telegram counts them, after the markup."""
    link = f'<a href="{_h(story_page(post, "telegram"))}">Sources</a>'
    tag = telegram_tag(post)
    foot = " · ".join(x for x in (link, tag) if x)
    if desk.ai_line():
        foot += f"\n{_h(desk.ai_line())}"
    head = _with_ticker(post, _head(post), 300)
    sentences = why_it_matters(post, 2) or [x for x in _sentences(post.get("dek"))[:1] if _standalone(x)]
    while True:
        text = "\n\n".join(x for x in (f"<b>{_h(head)}</b>", _h(" ".join(sentences)), foot) if x)
        if _visible(text) <= 1024 or not sentences:
            break
        sentences = sentences[:-1]
    if _visible(text) > 1024:  # a headline no newsroom would write; cut it rather than lose the foot
        room = 1024 - _visible(foot) - 4
        text = f"<b>{_h(head[:room - 1].rsplit(' ', 1)[0])}…</b>\n\n{foot}"
    return text


def facebook_text(post):
    """A short Page post above the link preview: the headline, one or two sentences, then the
    sources address. No hashtags: they do nothing on a Page. The preview (title, image) comes from the article
    page's Open Graph tags, so the text does not repeat the dek the preview shows."""
    dek = post.get("dek") or ""
    extra = [x for x in why_it_matters(post, 2) if not _same_line(x, dek)] or [x for x in _sentences(dek)[:1] if _standalone(x)]
    return _with_ticker(post, _fit(_head(post), " ".join(extra), _tail(post, story_page(post, "facebook")), 700), 700)


def facebook_link_text(post):
    """The message above a link preview: the preview shows the headline, so the text gives one or two facts the dek
    does not, then the address (find() looks for it). The headline only when there is nothing else to say."""
    dek = post.get("dek") or ""
    extra = [x for x in why_it_matters(post, 2) if not _same_line(x, dek)]
    body = " ".join(extra) if extra else _head(post)
    return _with_ticker(post, _fit(body, "", _tail(post, story_page(post, "facebook")), 700), 700)


def _images(post):
    return [desk.media_url(post["id"], c) for c in post["cards"]]


def video_for(post, name):
    """The post's video card for this platform, or None (the stills go). The same record and checks Instagram uses
    (desk.video_problems): the post's own licensed photo, the file that passed the spec when it was rendered."""
    v = post.get("video")
    if not v or not desk.video_cfg("on") or not (desk.video_cfg("platforms") or {}).get(name) or desk.video_problems(post):
        return None
    return {"url": desk.video_url(post["id"], v["file"]), "cover": desk.media_url(post["id"], v["cover"]),
            "height": CV_HEIGHT.get(v.get("shape"), 1350)}


CV_HEIGHT = {"card": 1350, "reel": 1920}


class VideoFailed(PlatformError):
    """The video was refused before anything was published: the stills go out in the same send."""


def refused(e):
    """An HTTP 4xx answer is a refusal: nothing went out. A network error or a 5xx may have reached the platform,
    so it is never treated as safe to send again."""
    return bool(re.search(r"HTTP 4\d\d", str(e)))


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

    name = ""

    def post(self, post):
        """The video card when the post has one and this platform takes video (desk.json video.platforms), else the
        stills. A video refused before publishing falls back to the stills in the same send, never a second post."""
        # the platform's own mix (desk.platform_wants_video): after a video, something else, unless the day is short
        v = video_for(post, self.name) if desk.platform_wants_video(self.name) else None
        if not v:
            return {"format": "photo", **self.post_stills(post)}
        try:
            return {**self.post_video(post, v), "video": True, "format": "video"}
        except VideoFailed as e:
            got = self.post_stills(post)
            got["video_error"] = self._scrub(str(e))[:300]
            return got


# Threads
# Docs read 2026-11-26: developers.facebook.com/docs/threads/posts (container + threads_publish, text 500
# characters by UTF-8 bytes, JPEG/PNG up to 8 MB, topic_tag, is_made_with_ai), .../retrieve-and-manage-replies/
# create-replies (TEXT container with reply_to_id, then threads_publish; needs threads_manage_replies),
# developers.facebook.com/docs/threads/troubleshooting (container status),
# developers.facebook.com/docs/threads/threads-media (permalink field; token as access_token parameter).

class Threads(Client):
    name = "threads"
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

    def publish(self, container, pause=30):
        # a container can read FINISHED a moment before threads_publish can see it: the call then fails with
        # subcode 4279009 ("media cannot be found") and nothing is posted (seen 2026-11-27 06:10), so one late try is safe
        uid = self.env["THREADS_USER_ID"]
        try:
            return self.call("POST", f"{uid}/threads_publish", {"creation_id": container})["id"]
        except PlatformError as e:
            if "4279009" not in str(e):
                raise
            self.sleep(pause)
            return self.call("POST", f"{uid}/threads_publish", {"creation_id": container})["id"]

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

    def post_stills(self, post):
        uid = self.env["THREADS_USER_ID"]
        # text first, one image only: the card. No is_made_with_ai label: it marks the media as AI-made, and the
        # photos are real. After a photo post comes a text-only one, Threads' native format, so the profile is not
        # a wall of identical cards.
        text_only = (desk.platform_formats("threads") or ["text"])[-1] == "photo"
        params = ({"media_type": "TEXT", "text": threads_text(post)} if text_only else
                  {"media_type": "IMAGE", "image_url": _images(post)[0], "text": threads_text(post)})
        if threads_tag(post):
            params["topic_tag"] = threads_tag(post)
        container = self.call("POST", f"{uid}/threads", params)["id"]
        self.wait(container)
        return {**self._published(post, self.publish(container)), "format": "text" if text_only else "photo"}

    def post_video(self, post, v):
        """A VIDEO container with video_url (docs read 2026-11-27: developers.facebook.com/docs/threads/posts; video
        spec: MP4, no edit lists, moov first, H.264 closed GOP 4:2:0, AAC 48 kHz, 23-60 fps, up to 1920 columns,
        5 minutes, 1 GB; ours is the Instagram-spec file). A refused or failed container publishes nothing."""
        uid = self.env["THREADS_USER_ID"]
        params = {"media_type": "VIDEO", "video_url": v["url"], "text": threads_text(post)}
        if threads_tag(post):
            params["topic_tag"] = threads_tag(post)
        try:
            container = self.call("POST", f"{uid}/threads", params)["id"]
            self.wait(container, tries=10)  # video processing takes longer than an image
        except PlatformError as e:
            raise VideoFailed(f"threads video: {e}") from None
        return self._published(post, self.publish(container))

    def _published(self, post, media):
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
        return {"id": self.publish(container)}


# Facebook Page
# Docs read 2026-11-26: developers.facebook.com/docs/graph-api/reference/page/photos/ (POST /{page-id}/photos with
# url and published=false, then POST /{page-id}/feed with message and attached_media[n]={"media_fbid": id};
# Page access token, permissions pages_manage_posts, pages_read_engagement, pages_show_list).

class Facebook(Client):
    name = "facebook"
    secrets = ("FB_PAGE_TOKEN", "FB_PAGE_ID")
    video_host = os.environ.get("FB_VIDEO_HOST", "https://graph-video.facebook.com")
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

    def post_video(self, post, v):
        """A Page video from a public URL: POST graph-video.facebook.com/{page-id}/videos with file_url and
        description (docs read 2026-11-27: developers.facebook.com/docs/graph-api/reference/page/videos/, file_url
        "Accessible URL of a video file", published defaults to true; Page token with pages_manage_posts). The text
        is the link post's message, so the story address is in it and find() still sees the post."""
        self.page_token()
        page = self.env["FB_PAGE_ID"]
        try:
            got = self.form("POST", f"{self.video_host}/{self.version}/{page}/videos",
                            {"file_url": v["url"], "description": facebook_text(post), "title": _head(post)[:255],
                             "access_token": self.page_token()}, "facebook POST videos")
        except PlatformError as e:
            if refused(e):
                raise VideoFailed(str(e)) from None
            raise
        vid = got["id"]
        return {"id": vid, "url": f"https://www.facebook.com/{page}/videos/{vid}"}

    def post_stills(self, post):
        """A link post or a photo post, in turn. Link post: POST /{page-id}/feed with message and link; Facebook builds
        the preview from the page's Open Graph tags (developers.facebook.com/docs/pages-api/posts), so the message
        leaves the headline to the preview. Photo post: POST /{page-id}/photos with url and caption
        (developers.facebook.com/docs/graph-api/reference/page/photos/), the card with the headline and the address
        in the text. Alternating halves the link posts: Meta has been testing a monthly cap on them for Pages
        since December 2025 (TechCrunch 2025-12-17; publisher Pages excluded then)."""
        self.page_token()
        page = self.env["FB_PAGE_ID"]
        if (desk.platform_formats("facebook") or ["photo"])[-1] == "link":
            got = self.call(f"{page}/photos", {"url": _images(post)[0], "caption": facebook_text(post)})
            pid = got.get("post_id") or got["id"]
            return {"id": pid, "url": f"https://www.facebook.com/{pid}", "format": "photo"}
        pid = self.call(f"{page}/feed", {"message": facebook_link_text(post), "link": story_page(post, "facebook")})["id"]
        return {"id": pid, "url": f"https://www.facebook.com/{pid}", "format": "link"}

    def last_story_at(self):
        """When the Page's newest story went up (GET /{page-id}/stories, creation_time, same docs), or None. The
        Page is the record: two publish runs started from one commit sent the same frame twice on 2026-11-27."""
        self.page_token()
        got = self.form("GET", f"{self.host}/{self.version}/{self.env['FB_PAGE_ID']}/stories",
                        {"fields": "creation_time,status", "limit": 5, "access_token": self.page_token()}, "facebook GET stories")
        stamps = [int(x["creation_time"]) for x in got.get("data", []) if str(x.get("creation_time", "")).isdigit()]
        return datetime.fromtimestamp(max(stamps), timezone.utc) if stamps else None

    def post_story(self, image_url):
        """A photo story on the Page (docs read 2026-11-27: developers.facebook.com/docs/page-stories-api/). The photo
        is uploaded unpublished with POST /{page-id}/photos (url, published=false), then POST /{page-id}/photo_stories
        with photo_id makes it the story. Same Page token and pages_manage_posts as a feed post. A story takes no
        caption, sticker or link through this API, and a photo already used in a published post cannot be reused."""
        self.page_token()  # resolves FB_PAGE_ID to the Page the token manages
        page = self.env["FB_PAGE_ID"]
        photo = self.call(f"{page}/photos", {"url": image_url, "published": "false"})["id"]
        got = self.call(f"{page}/photo_stories", {"photo_id": photo})
        if not got.get("success") or not got.get("post_id"):
            raise PlatformError(f"facebook: photo_stories did not confirm the story: {str(got)[:200]}")
        pid = str(got["post_id"])
        return {"id": pid, "url": f"https://www.facebook.com/{pid}", "photo_id": photo}


# Bluesky
# Docs read 2026-11-26: docs.bsky.app/docs/advanced-guides/posts and docs.bsky.app/docs/tutorials/creating-a-post
# (app.bsky.feed.post, app.bsky.embed.external with uri, title, description and an optional thumb blob, uploadBlob),
# atproto lexicon com.atproto.server.createSession (identifier + app password -> accessJwt, did).
# The two pages disagree on the per-image cap (1,000,000 bytes and 2 MB); the stricter one is used for the thumb.

class Bluesky(Client):
    name = "bluesky"
    secrets = ("BSKY_HANDLE", "BSKY_APP_PASSWORD")
    VIDEO = os.environ.get("BSKY_VIDEO", "https://video.bsky.app")
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

    def ensure_bot_label(self):
        """The account's own "bot" self-label on its profile record (atproto.com/guides/bot-tutorial, read 2026-11-27):
        Bluesky's disclosure for automated accounts, in place of a line in every post. The profile is read first and
        written back whole, with swapRecord, so the name, bio and avatar stay and a concurrent edit is never lost.
        Returns "set" or "already"."""
        sess = self.xrpc("com.atproto.server.createSession",
                         {"identifier": self.env["BSKY_HANDLE"], "password": self.env["BSKY_APP_PASSWORD"]})
        jwt, did = sess["accessJwt"], sess["did"]
        req = urllib.request.Request(f"{self.host}/xrpc/com.atproto.repo.getRecord?" + urllib.parse.urlencode(
            {"repo": did, "collection": "app.bsky.actor.profile", "rkey": "self"}), headers={"Authorization": f"Bearer {jwt}"})
        got = json.loads(self._open(req, "bluesky getRecord"))
        record = got.get("value") or {"$type": "app.bsky.actor.profile"}
        labels = record.get("labels") or {"$type": "com.atproto.label.defs#selfLabels", "values": []}
        if any(v.get("val") == "bot" for v in labels.get("values", [])):
            return "already"
        labels["values"] = list(labels.get("values", [])) + [{"val": "bot"}]
        record["labels"] = labels
        body = {"repo": did, "collection": "app.bsky.actor.profile", "rkey": "self", "record": record}
        if got.get("cid"):
            body["swapRecord"] = got["cid"]
        self.xrpc("com.atproto.repo.putRecord", body, jwt=jwt)
        return "set"

    APPVIEW = os.environ.get("BSKY_APPVIEW", "https://public.api.bsky.app")

    def find(self, post):
        """This story already on the profile: a recent post whose link card points at the story page. The public
        AppView answers without logging in, so the check costs no session."""
        url = story_page(post)
        got = self.form("GET", f"{self.APPVIEW}/xrpc/app.bsky.feed.getAuthorFeed",
                        {"actor": self.env["BSKY_HANDLE"], "limit": 30, "filter": "posts_no_replies"}, "bluesky getAuthorFeed")
        for item in got.get("feed", []):
            p = item.get("post") or {}
            rec = p.get("record") or {}
            ext = (rec.get("embed") or {}).get("external") or {}
            # a video post has no link card: its story address is a link facet in the text
            links = [f.get("uri", "") for fc in rec.get("facets") or [] for f in fc.get("features") or []]
            if ext.get("uri") == url or any(u.split("?")[0] == url for u in links):
                rkey = p.get("uri", "").rsplit("/", 1)[-1]
                return {"id": p.get("uri", ""), "url": f"https://bsky.app/profile/{self.env['BSKY_HANDLE']}/post/{rkey}"}
        return None

    def post_video(self, post, v):
        """app.bsky.embed.video through the video service, the method the docs recommend so the post never shows
        before its video is ready (docs read 2026-11-27: docs.bsky.app/docs/tutorials/video: a service token from
        com.atproto.server.getServiceAuth, audience the PDS's did:web, lxm com.atproto.repo.uploadBlob, 30 minutes;
        POST video.bsky.app app.bsky.video.uploadVideo; poll app.bsky.video.getJobStatus for the blob; lexicon
        app.bsky.embed.video: video/mp4 up to 300 MB, with alt and aspectRatio). Bluesky-hosted accounts need a
        verified email and have a daily video allowance; a refusal anywhere before createRecord posts nothing."""
        sess = self.xrpc("com.atproto.server.createSession",
                         {"identifier": self.env["BSKY_HANDLE"], "password": self.env["BSKY_APP_PASSWORD"]})
        jwt, did = sess["accessJwt"], sess["did"]
        try:
            pds = next(s["serviceEndpoint"] for s in (sess.get("didDoc") or {}).get("service", [])
                       if s.get("id", "").endswith("#atproto_pds"))
            aud = "did:web:" + urllib.parse.urlparse(pds).hostname
            exp = int(time.time()) + 1800
            tok = self._service_auth(jwt, aud, exp)
            data = self.fetch(v["url"])
            q = urllib.parse.urlencode({"did": did, "name": f"{post['id']}.mp4"})
            req = urllib.request.Request(f"{self.VIDEO}/xrpc/app.bsky.video.uploadVideo?{q}", data=data, method="POST",
                                         headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"})
            job = json.loads(self._open(req, "bluesky uploadVideo"))
            job = job.get("jobStatus", job)
            blob = job.get("blob")
            for _ in range(90):
                if blob:
                    break
                if job.get("state") == "JOB_STATE_FAILED":
                    raise PlatformError(f"bluesky video job failed: {job.get('error') or job.get('message', '')}")
                self.sleep(2)
                job = self.form("GET", f"{self.VIDEO}/xrpc/app.bsky.video.getJobStatus", {"jobId": job["jobId"]},
                                "bluesky getJobStatus").get("jobStatus", {})
                blob = job.get("blob")
            if not blob:
                raise PlatformError("bluesky video not processed after 3 minutes")
        except (PlatformError, KeyError, StopIteration, TypeError) as e:
            raise VideoFailed(f"bluesky video: {e}") from None
        text, facets = bluesky_video_text(post)
        record = {"$type": "app.bsky.feed.post", "text": text, "facets": facets, "langs": ["en"],
                  "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                  "embed": {"$type": "app.bsky.embed.video", "video": blob, "alt": _head(post),
                            "aspectRatio": {"width": 1080, "height": v["height"]}}}
        got = self.xrpc("com.atproto.repo.createRecord",
                        {"repo": did, "collection": "app.bsky.feed.post", "record": record}, jwt)
        rkey = got["uri"].rsplit("/", 1)[-1]
        return {"id": got["uri"], "url": f"https://bsky.app/profile/{self.env['BSKY_HANDLE']}/post/{rkey}"}

    def _service_auth(self, jwt, aud, exp):
        q = urllib.parse.urlencode({"aud": aud, "lxm": "com.atproto.repo.uploadBlob", "exp": exp})
        req = urllib.request.Request(f"{self.host}/xrpc/com.atproto.server.getServiceAuth?{q}",
                                     headers={"Authorization": f"Bearer {jwt}"})
        tok = json.loads(self._open(req, "bluesky getServiceAuth"))["token"]
        self.env["_service_token"] = tok  # scrubbed from this client's errors
        return tok

    def post_stills(self, post):
        sess = self.xrpc("com.atproto.server.createSession",
                         {"identifier": self.env["BSKY_HANDLE"], "password": self.env["BSKY_APP_PASSWORD"]})
        jwt, did = sess["accessJwt"], sess["did"]
        card = {"uri": story_page(post, "bluesky"), "title": _head(post), "description": bluesky_description(post)}
        # Bluesky crops a link-card thumb to about 1.91:1, which cut the 4:5 card through its headline. The article's
        # own 1200x630 share image (the og:image every other link preview shows) fits; until the site has built it,
        # the card is the fallback.
        try:
            data = self.fetch(f"{desk.CONFIG['site_url']}/og/{post['id']}.jpg")
        except PlatformError:
            data = self.fetch(_images(post)[0])
        # a link card without a thumbnail still works, so an oversize card is skipped rather than failing the post
        if len(data) <= self.MAX_BYTES:
            card["thumb"] = self.xrpc("com.atproto.repo.uploadBlob", None, jwt, raw=data, mime="image/jpeg")["blob"]
        text, facets = bluesky_text(post)
        record = {"$type": "app.bsky.feed.post", "text": text, "langs": ["en"],
                  "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                  "embed": {"$type": "app.bsky.embed.external", "external": card}}
        if facets:
            record["facets"] = facets
        got = self.xrpc("com.atproto.repo.createRecord",
                        {"repo": did, "collection": "app.bsky.feed.post", "record": record}, jwt)
        # the web URL of an at:// URI is bsky.app/profile/<handle>/post/<rkey>
        rkey = got["uri"].rsplit("/", 1)[-1]
        return {"id": got["uri"], "url": f"https://bsky.app/profile/{self.env['BSKY_HANDLE']}/post/{rkey}", "format": "link"}


# Telegram channel
# Docs read 2026-11-26: core.telegram.org/bots/api (sendPhoto, sendMediaGroup with 2-10 InputMediaPhoto, sendMessage, disable_notification,
# link_preview_options (disable_web_page_preview is no longer listed; both are sent),
# caption 0-1024 characters, photo by HTTP URL up to 5 MB per "Sending files", ResponseParameters.retry_after).
# The bot must be an administrator of the channel with permission to post.

class Telegram(Client):
    name = "telegram"
    secrets = ("TG_BOT_TOKEN", "TG_CHANNEL")
    host = os.environ.get("TG_API_HOST", "https://api.telegram.org")

    def call(self, method, params):
        got = self.json(f"{self.host}/bot{self.env['TG_BOT_TOKEN']}/{method}", params, f"telegram {method}")
        if not got.get("ok"):
            raise PlatformError(self._scrub(f"telegram {method}: {json.dumps(got)[:300]}"))
        return got["result"]

    PUBLIC = os.environ.get("TG_PUBLIC_HOST", "https://t.me")

    def find(self, post):
        """This story already in the channel. The Bot API cannot read a channel's history, but a public channel's
        web preview (t.me/s/<name>) lists its recent posts without a login: a post that links the story page, or
        whose first line is the headline, and is not older than the queue entry, is this story. Run before every
        send, like the other platforms: a send whose status commit was lost posted the same story twice on
        2026-11-26 (t.me/boardread/23 and /25)."""
        import html as html_
        chat = self.env["TG_CHANNEL"]
        # the secret may hold the numeric chat id: the channel's public name comes from getChat then
        name = chat.lstrip("@") if chat.startswith("@") else (self.call("getChat", {"chat_id": chat}).get("username") or "")
        if not name:
            raise PlatformError("telegram: a private channel cannot be checked for an earlier send")
        page = self._open(urllib.request.Request(f"{self.PUBLIC}/s/{name}", headers={"User-Agent": "Mozilla/5.0"}),
                          "telegram channel page").decode("utf-8", "replace")
        url, head = story_page(post), _head(post)
        born = desk._stamp(post.get("created", ""))
        for block in page.split('data-post="')[1:]:
            mid = block.split('"', 1)[0].rsplit("/", 1)[-1]
            when = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            seen = desk._stamp(when.group(1)) if when else None
            if born and seen and seen < born - timedelta(minutes=5):
                continue
            text = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
            first = html_.unescape(re.sub(r"<br\s*/?>", "\n", text.group(1)) if text else "")
            first = re.sub(r"<[^>]+>", "", first).strip().split("\n", 1)[0]
            if url in block or _same_line(first, head) or _same_line(first, _with_ticker(post, head, 300)):
                return {"id": mid, "url": f"https://t.me/{name}/{mid}"}
        return None

    def find_digest(self, since):
        """Today's evening digest already in the channel (its first line is the digest title), or None. Read from the
        public web preview, like find(): two runs that both read the state before either recorded a send each posted
        the digest on 2026-11-27 (t.me/boardread/36 and /37)."""
        import html as html_
        chat = self.env["TG_CHANNEL"]
        name = chat.lstrip("@") if chat.startswith("@") else (self.call("getChat", {"chat_id": chat}).get("username") or "")
        if not name:
            raise PlatformError("telegram: a private channel cannot be checked for an earlier digest")
        page = self._open(urllib.request.Request(f"{self.PUBLIC}/s/{name}", headers={"User-Agent": "Mozilla/5.0"}),
                          "telegram channel page").decode("utf-8", "replace")
        title = re.sub(r"<[^>]+>", "", digest_text([]).split("\n", 1)[0])
        for block in page.split('data-post="')[1:]:
            mid = block.split('"', 1)[0].rsplit("/", 1)[-1]
            when = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            seen = desk._stamp(when.group(1)) if when else None
            text = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
            first = html_.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", text.group(1)) if text else "")).strip()
            if seen and seen >= since and first.split("\n", 1)[0].strip() == title:
                return {"id": mid, "url": f"https://t.me/{name}/{mid}"}
        return None

    def check(self):
        """Reads the bot and the channel and posts nothing; fails if the bot cannot post there."""
        bot = self.call("getMe", {})
        chat = self.call("getChat", {"chat_id": self.env["TG_CHANNEL"]})
        member = self.call("getChatMember", {"chat_id": self.env["TG_CHANNEL"], "user_id": bot["id"]})
        if member.get("status") != "creator" and not member.get("can_post_messages"):
            raise PlatformError(f"telegram: @{bot.get('username')} is not allowed to post in {chat.get('title')}")
        return f"bot @{bot.get('username')} can post in {chat.get('title')} (@{chat.get('username') or 'private'})"

    def post_video(self, post, v):
        """sendVideo by HTTP URL (docs read 2026-11-27: core.telegram.org/bots/api#sendvideo, MPEG4, caption 0-1024
        after entities, cover by URL, supports_streaming; "Sending files": by URL up to 20 MB for non-photo files and
        the file must carry the right MIME type, which jsDelivr serves as video/mp4). A refusal sends nothing."""
        chat = self.env["TG_CHANNEL"]
        try:
            first = self.call("sendVideo", {"chat_id": chat, "video": v["url"], "cover": v["cover"],
                                            "caption": telegram_caption(post), "parse_mode": "HTML",
                                            "supports_streaming": True, "width": 1080, "height": v["height"],
                                            "disable_notification": not is_breaking(post)})
        except PlatformError as e:
            if refused(e) or '"ok": false' in str(e):  # an answer that says no; a network error may have sent
                raise VideoFailed(str(e)) from None
            raise
        username = (first.get("chat") or {}).get("username") or (chat.lstrip("@") if chat.startswith("@") else "")
        return {"id": str(first["message_id"]), "url": f"https://t.me/{username}/{first['message_id']}" if username else ""}

    def post_stills(self, post):
        # one photo, as news channels post: the detail slides repeat what the caption already says
        urls = _images(post)[:1]
        chat, caption = self.env["TG_CHANNEL"], telegram_caption(post)
        # routine posts are silent; only a breaking story (score at the desk's breaking bar) notifies subscribers
        silent = {"disable_notification": not is_breaking(post)}
        if len(urls) == 1:
            first = self.call("sendPhoto", {"chat_id": chat, "photo": urls[0], "caption": caption, "parse_mode": "HTML", **silent})
        else:
            media = [{"type": "photo", "media": u} for u in urls]
            media[0].update(caption=caption, parse_mode="HTML")  # an album shows the caption of its first photo
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
        got = self.call("sendMessage", {"chat_id": self.env["TG_CHANNEL"], "text": digest_text(posts), "parse_mode": "HTML",
                                        "disable_notification": True, "disable_web_page_preview": True,
                                        "link_preview_options": {"is_disabled": True}})
        return {"id": str(got["message_id"])}


CLIENTS = {"threads": Threads, "facebook": Facebook, "bluesky": Bluesky, "telegram": Telegram}
