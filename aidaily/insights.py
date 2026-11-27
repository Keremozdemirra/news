"""The weekly insights loop: pull per-post numbers from every connected platform, find what works, and feed it back
into ranking and timing within guard rails. Standard library only.

  pull      Instagram (reach, saves, shares, profile visits, follows), Threads (views, likes, replies, reposts,
            quotes, shares), Facebook (reactions, comments, shares, impressions where Meta still serves them),
            Bluesky (likes, reposts, quotes, replies; the public AppView, no login) and Telegram (views and
            subscribers read from the channel's own public page t.me/s/<channel>, no bot token). Each result lands in
            post.json under "metrics"/<platform>, with the time it was read. A platform without secrets is skipped.
  analyse   one number per post and platform (the platform's own engagement measure), divided by that platform's
            median over the window, so a Threads post and a Telegram post can be compared: 1.0 is a typical post.
            Grouped by topic, rank category, format, visual (photo or text card), tier and UTC hour.
  feed back state/weights.json (rank category weights read by desk.pick), state/learned.json (Telegram digest hour,
            quiet hours for web-tier social posts, a hold on the Instagram volume ramp), state/followers.json
            (shown on the site), state/insights/<ISO week>.json (everything above, before and after).

Guard rails, each a constant below: nothing changes below MIN_N posts in a group; every lift is shrunk towards 1
by n / (n + SHRINK); weights stay inside WEIGHT_RANGE and move at most WEIGHT_STEP a week; the digest hour stays in
DIGEST_WINDOW and moves one hour a week; quiet hours are capped at MAX_QUIET and never hold a breaking story; the
volume ramp can be held, never cut. A person reads the weekly file; nothing here posts or deletes.
"""
import json
import os
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from . import desk
from .feeds import CTX

WINDOW_DAYS = 30
MIN_N = 5            # posts a group needs before it may change anything
SHRINK = 10          # lift is pulled toward 1 by n / (n + SHRINK)
WEIGHT_RANGE = (0.8, 1.25)
WEIGHT_STEP = 0.1    # most a weight moves in one week
SIGNAL = 0.15        # a shrunk lift this far from 1 is reported as a signal
DIGEST_WINDOW = (17, 21)
MAX_QUIET = 6
QUIET_BELOW = 0.7
HOLD_RATIO = 0.8     # last 7 days' Instagram send rate under 80% of the 8-30 day median holds the ramp
HOLD_MIN_N = 10
REREAD_DAYS = 7      # posts older than this keep the numbers already stored; only never-measured ones are read
COUNT_MIN_HOURS = 48  # count-based numbers (no audience size) are compared only once a post has had two days
LEARNED_DAYS = 14    # learned values older than this are ignored and the shipped defaults apply
QUIET_KEEP_DAYS = 14  # a quiet hour stays at least this long, so the schedule does not flip week to week
COUNT_BASED = ("bluesky", "telegram")
UA = "boardread-desk/1.0 (+https://boardread.news/about/)"


class Source:
    """One platform's reader. fetch(post) -> dict of raw numbers or None; followers() -> int or None."""
    name = ""

    def __init__(self, opener=urllib.request.urlopen):
        self.opener = opener

    def get(self, url, params=None, label=""):
        full = url + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        req = urllib.request.Request(full, headers={"User-Agent": UA})
        try:
            with self.opener(req, timeout=30, context=CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{label or self.name}: HTTP {e.code}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"{label or self.name}: {e.reason}") from None

    def get_json(self, url, params=None, label=""):
        return json.loads(self.get(url, params, label))


def _metric_rows(rows):
    """Meta insights answer either values[0].value or total_value.value per metric."""
    out = {}
    for r in rows or []:
        if r.get("values"):
            out[r["name"]] = r["values"][0].get("value")
        elif "total_value" in r:
            out[r["name"]] = (r["total_value"] or {}).get("value")
    return out


class Instagram(Source):
    name = "instagram"
    METRICS = ("reach", "saved", "shares", "likes", "comments", "views", "profile_visits", "follows")

    def __init__(self, client=None, opener=urllib.request.urlopen):
        super().__init__(opener)
        if client is None:
            if not desk.configured():
                raise LookupError("IG_TOKEN, IG_USER_ID")
            from .instagram import Client
            client = Client()
        self.client = client

    def fetch(self, post):
        """One call with every metric comma-joined; only when Instagram refuses that call (a metric renamed or
        not offered for this media type) does it fall back to one call per metric. A block answer is raised
        untouched, so pull() can hand it to desk.note_block and stop."""
        if not post.get("media_id"):
            return None
        from .instagram import IGError
        try:
            rows = self.client.call("GET", f"{post['media_id']}/insights", {"metric": ",".join(self.METRICS)}).get("data", [])
            got = _metric_rows(rows)
        except IGError as e:
            if desk.BLOCKED.search(str(e)):
                raise
            got = {k: v for k, v in self.client.media_insights(post["media_id"], metrics=self.METRICS).items() if k != "_errors"}
        return got or None

    def followers(self):
        return (self.client.followers() or {}).get("followers_count")


class Threads(Source):
    name = "threads"
    METRICS = "views,likes,replies,reposts,quotes,shares"

    def __init__(self, opener=urllib.request.urlopen):
        super().__init__(opener)
        self.token, self.user = os.environ.get("THREADS_TOKEN", ""), os.environ.get("THREADS_USER_ID", "")
        if not (self.token and self.user):
            raise LookupError("THREADS_TOKEN, THREADS_USER_ID")
        self.host = os.environ.get("THREADS_API_HOST", "https://graph.threads.com/v1.0")

    def fetch(self, post):
        slot = (post.get("platforms") or {}).get("threads") or {}
        if not slot.get("id"):
            return None
        got = self.get_json(f"{self.host}/{slot['id']}/insights", {"metric": self.METRICS, "access_token": self.token})
        return _metric_rows(got.get("data")) or None

    def followers(self):
        got = self.get_json(f"{self.host}/{self.user}/threads_insights", {"metric": "followers_count", "access_token": self.token})
        return _metric_rows(got.get("data")).get("followers_count")


class Facebook(Source):
    name = "facebook"

    def __init__(self, opener=urllib.request.urlopen):
        super().__init__(opener)
        self.token, self.page = os.environ.get("FB_PAGE_TOKEN", ""), os.environ.get("FB_PAGE_ID", "")
        if not (self.token and self.page):
            raise LookupError("FB_PAGE_TOKEN, FB_PAGE_ID")
        self.base = f"{os.environ.get('FB_API_HOST', 'https://graph.facebook.com')}/{os.environ.get('FB_API_VERSION', 'v27.0')}"

    def fetch(self, post):
        slot = (post.get("platforms") or {}).get("facebook") or {}
        if not slot.get("id"):
            return None
        got = self.get_json(f"{self.base}/{slot['id']}", {"fields": "shares,comments.limit(0).summary(true),reactions.limit(0).summary(true)",
                                                          "access_token": self.token})
        out = {"shares": (got.get("shares") or {}).get("count", 0),
               "comments": ((got.get("comments") or {}).get("summary") or {}).get("total_count", 0),
               "reactions": ((got.get("reactions") or {}).get("summary") or {}).get("total_count", 0)}
        try:  # Meta has been retiring Page post metrics; impressions are a bonus, never a requirement
            rows = self.get_json(f"{self.base}/{slot['id']}/insights", {"metric": "post_impressions_unique", "access_token": self.token})
            reach = _metric_rows(rows.get("data")).get("post_impressions_unique")
            if reach is not None:
                out["reach"] = reach
        except RuntimeError:
            pass
        return out

    def followers(self):
        return self.get_json(f"{self.base}/{self.page}", {"fields": "followers_count", "access_token": self.token}).get("followers_count")


class Bluesky(Source):
    """The public AppView answers post counts and profiles without a login (docs.bsky.app, app.bsky.feed.getPosts:
    up to 25 URIs a call)."""
    name = "bluesky"
    HOST = "https://public.api.bsky.app/xrpc"

    def __init__(self, opener=urllib.request.urlopen):
        super().__init__(opener)
        self.handle = os.environ.get("BSKY_HANDLE", "").strip().lstrip("@") or None
        self.cache = {}

    def prefetch(self, posts):
        uris = [((p.get("platforms") or {}).get("bluesky") or {}).get("id") for p in posts]
        uris = [u for u in uris if u and u.startswith("at://")]
        for i in range(0, len(uris), 25):
            got = self.get_json(f"{self.HOST}/app.bsky.feed.getPosts", {"uris": uris[i:i + 25]})
            for p in got.get("posts", []):
                self.cache[p["uri"]] = {"likes": p.get("likeCount", 0), "reposts": p.get("repostCount", 0),
                                        "quotes": p.get("quoteCount", 0), "replies": p.get("replyCount", 0)}

    def fetch(self, post):
        return self.cache.get(((post.get("platforms") or {}).get("bluesky") or {}).get("id"))

    def followers(self):
        if not self.handle:
            return None
        return self.get_json(f"{self.HOST}/app.bsky.actor.getProfile", {"actor": self.handle}).get("followersCount")


POST_ID = re.compile(r'^[^"/]+/(\d+)"')
VIEWS = re.compile(r'tgme_widget_message_views">([\d.,]+[KMk]?)<')


def page_views(html):
    """{message id: views} from one t.me/s page; each message block starts at its data-post attribute, so a block
    without a counter (a service message) never borrows the next block's number."""
    out = {}
    for block in html.split('data-post="')[1:]:
        mid, views = POST_ID.match(block), VIEWS.search(block)
        if mid and views:
            out[int(mid.group(1))] = _count(views.group(1))
    return out


def _count(text):
    text = text.replace(",", "")
    mult = {"K": 1_000, "k": 1_000, "M": 1_000_000}.get(text[-1:], 1)
    return int(float(text.rstrip("KMk")) * mult)


SUBSCRIBERS = re.compile(r'counter_value">([\d.,]+[KMk]?)</span>\s*<span class="counter_type">subscribers')


class Telegram(Source):
    """The Bot API does not return view counts of channel posts, so views and the subscriber count are read from the
    channel's own public web preview (https://t.me/s/<channel>), the same numbers anyone sees. No bot token is used.
    Pages go back until they reach the oldest Telegram post in the window, at most PAGES; if the cap stops them
    first, `short` says so and the report labels the shorter window."""
    name = "telegram"
    PAGES = 40

    def __init__(self, opener=urllib.request.urlopen):
        super().__init__(opener)
        self.chat = os.environ.get("TG_CHANNEL", "")
        # the public page needs the username: TG_CHANNEL when it is one, else the t.me link in desk.json accounts
        link = next((a["url"] for a in desk.CONFIG.get("accounts", []) if a["name"] == "Telegram" and a.get("url")), "")
        self.username = self.chat[1:] if self.chat.startswith("@") else link.rstrip("/").rsplit("/", 1)[-1]
        if not self.username:
            raise LookupError("a public channel username (TG_CHANNEL=@name or the Telegram url in desk.json)")
        self.views, self.subscribers, self.short = {}, None, False

    def prefetch(self, posts):
        ids = [int(s["id"]) for s in (((p.get("platforms") or {}).get("telegram") or {}) for p in posts) if str(s.get("id", "")).isdigit()]
        oldest = min(ids, default=None)
        before = ""
        for _ in range(self.PAGES):
            html = self.get(f"https://t.me/s/{self.username}", {"before": before} if before else None, "telegram page").decode("utf-8", "replace")
            if self.subscribers is None:
                m = SUBSCRIBERS.search(html)
                self.subscribers = _count(m.group(1)) if m else None
            found = page_views(html)
            if not found:
                return
            self.views.update(found)
            before = str(min(found))
            if min(found) <= 1 or oldest is None or min(found) <= oldest:
                return
        self.short = True

    def fetch(self, post):
        slot = (post.get("platforms") or {}).get("telegram") or {}
        mid = int(slot["id"]) if str(slot.get("id", "")).isdigit() else None
        return {"views": self.views[mid]} if mid in self.views else None

    def followers(self):
        if self.subscribers is None:
            html = self.get(f"https://t.me/s/{self.username}", None, "telegram page").decode("utf-8", "replace")
            m = SUBSCRIBERS.search(html)
            self.subscribers = _count(m.group(1)) if m else None
        return self.subscribers


SOURCES = {"instagram": Instagram, "threads": Threads, "facebook": Facebook, "bluesky": Bluesky, "telegram": Telegram}
LABELS = {"instagram": "Instagram", "threads": "Threads", "facebook": "Facebook", "bluesky": "Bluesky", "telegram": "Telegram"}


# ------------------------------------------------------------------ one number per post and platform

def value(platform, m):
    """The platform's own engagement measure, or None when the post is too small to say anything.
    Rates where the platform gives an audience size (sends and saves per reach on Instagram, the research's top
    signal), counts where it does not (Bluesky has no views; Telegram's views are the reach)."""
    if not m:
        return None
    g = lambda k: m.get(k) or 0  # noqa: E731
    if platform == "instagram":
        return (g("shares") + g("saved")) / g("reach") if g("reach") >= 50 else None
    if platform == "threads":
        return (g("replies") + g("reposts") + g("quotes") + g("shares")) / g("views") if g("views") >= 50 else None
    if platform == "facebook":
        act = g("shares") + g("comments") + g("reactions")
        return act / g("reach") if g("reach") >= 50 else float(act)  # a count: see counted()
    if platform == "bluesky":
        return g("likes") + 2 * (g("reposts") + g("quotes")) + g("replies")
    if platform == "telegram":
        return float(g("views")) if g("views") else None
    return None


def visual(p):
    return "photo" if p.get("photo_file") else "text card"


def fmt(p):
    if p.get("kind"):
        return p["kind"]
    shape = (p.get("video") or {}).get("shape")
    if shape:  # the video card A/B: desk.json video.format alternates the two shapes until these rows decide
        return "video reel" if shape == "reel" else "video carousel"
    n = len(p.get("cards") or [])
    return "web only" if p.get("status") == "web" else ("carousel" if n > 1 else "single image")


def hour(p):
    return desk._stamp(p.get("published", "")).hour


DIMENSIONS = {
    "topic": lambda p: p.get("topic") or "unknown",
    "category": lambda p: (p.get("categories") or ["unknown"])[0],
    "format": fmt,
    "visual": visual,
    "tier": lambda p: "instagram" if p.get("status") == "published" else "web",
    "hour_utc": lambda p: f"{hour(p) // 3 * 3:02d}-{hour(p) // 3 * 3 + 3:02d}",
}


def counted(name, m):
    """True when the platform's number is a running count with no audience size, which keeps growing for days."""
    return name in COUNT_BASED or (name == "facebook" and (m.get("reach") or 0) < 50)


def usable(p, name, m):
    """The post's value on a platform, or None. Counts are compared only once the post is COUNT_MIN_HOURS old,
    so a fresh post's half-grown count is never read as a weak one."""
    if not m:
        return None
    if counted(name, m):
        at = desk._stamp(p.get("published", ""))
        if not at or desk.now() - at < timedelta(hours=COUNT_MIN_HOURS):
            return None
    return value(name, m)


def lifts(rows):
    """[(post, {platform: lift})]: each value over its platform's median in the window; posts with no usable value drop out."""
    per = {}
    for p in rows:
        for name, m in (p.get("metrics") or {}).items():
            v = usable(p, name, m)
            if v is not None:
                per.setdefault(name, []).append(v)
    med = {k: statistics.median(v) for k, v in per.items() if v and statistics.median(v) > 0}
    out = []
    for p in rows:
        got = {}
        for name, m in (p.get("metrics") or {}).items():
            v = usable(p, name, m)
            if v is not None and name in med:
                got[name] = v / med[name]
        if got:
            out.append((p, got))
    return out


def shrunk(mean, n):
    return 1 + (mean - 1) * n / (n + SHRINK)


def analyse(rows, only=None):
    """{dimension: {group: {"n", "lift"}}}; lift is the mean per-post lift (platforms averaged), shrunk toward 1."""
    out = {}
    for p, got in lifts(rows):
        sel = {k: v for k, v in got.items() if not only or k in only}
        if not sel:
            continue
        x = sum(sel.values()) / len(sel)
        for dim, key in DIMENSIONS.items():
            try:
                g = key(p)
            except (AttributeError, TypeError, ValueError):
                continue
            out.setdefault(dim, {}).setdefault(g, []).append(x)
    return {d: {g: {"n": len(v), "lift": round(shrunk(sum(v) / len(v), len(v)), 3)} for g, v in sorted(groups.items())}
            for d, groups in out.items()}


def signals(table):
    """Lines a person can read: groups with enough posts whose lift is clearly above or below a typical post."""
    lines = []
    for dim, groups in table.items():
        for g, s in groups.items():
            if s["n"] >= MIN_N and abs(s["lift"] - 1) >= SIGNAL:
                lines.append(f"{dim} {g}: {'+' if s['lift'] > 1 else ''}{round((s['lift'] - 1) * 100)}% vs a typical post (n={s['n']})")
    return sorted(lines)


# ------------------------------------------------------------------ feedback, guarded

def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def next_weights(table, previous):
    """Rank category weights for desk.pick. A category under MIN_N keeps its previous weight; others follow the
    shrunk lift, inside WEIGHT_RANGE, at most WEIGHT_STEP from last week."""
    out = dict(previous)
    for cat, s in (table.get("category") or {}).items():
        if s["n"] < MIN_N:
            continue
        old = previous.get(cat, 1.0)
        out[cat] = round(clamp(clamp(s["lift"], *WEIGHT_RANGE), old - WEIGHT_STEP, old + WEIGHT_STEP), 3)
    return out


def next_digest_hour(rows, current):
    """Telegram views by publishing hour inside DIGEST_WINDOW: move one hour toward the best hour when it beats the
    current one by SIGNAL with MIN_N posts on both sides. Else stay."""
    by = {}
    for p, got in lifts(rows):
        if "telegram" in got:
            by.setdefault(hour(p), []).append(got["telegram"])
    lo, hi = DIGEST_WINDOW
    cand = {h: shrunk(sum(v) / len(v), len(v)) for h, v in by.items() if lo <= h <= hi and len(v) >= MIN_N}
    if not cand or current not in cand:
        return current
    best = max(cand, key=cand.get)
    if best == current or cand[best] - cand[current] < SIGNAL:
        return current
    return current + (1 if best > current else -1)


def next_quiet_hours(rows, previous=None, today=None):
    """UTC hours where Threads and Bluesky posts do clearly worse (shrunk lift under QUIET_BELOW, MIN_N posts):
    web-tier posts wait for the next hour. Breaking posts are left out of the scoring, since they never wait.
    A quiet hour, once set, stays QUIET_KEEP_DAYS. At most MAX_QUIET hours, the worst first.
    previous: {hour (str): date set}. Returns the same shape."""
    today = today or desk.now().date()
    kept = {h: d for h, d in (previous or {}).items()
            if (today - date.fromisoformat(d[:10])).days < QUIET_KEEP_DAYS}
    by = {}
    for p, got in lifts(rows):
        if (p.get("score") or 0) >= desk.CONFIG["breaking_score"]:
            continue
        v = [got[k] for k in ("threads", "bluesky") if k in got]
        if v:
            by.setdefault(hour(p), []).append(sum(v) / len(v))
    bad = {h: shrunk(sum(v) / len(v), len(v)) for h, v in by.items() if len(v) >= MIN_N}
    bad = {h: x for h, x in bad.items() if x < QUIET_BELOW}
    out = dict(kept)
    for h in sorted(bad, key=bad.get):
        if len(out) >= MAX_QUIET:
            break
        out.setdefault(str(h), today.isoformat())
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def ramp_hold(rows, today):
    """True when the last seven days' median Instagram send rate fell under HOLD_RATIO of the 8-30 day median,
    with HOLD_MIN_N posts on each side: more posts are only added while per-post sends hold."""
    recent, before = [], []
    for p in rows:
        v = value("instagram", (p.get("metrics") or {}).get("instagram"))
        if v is None:
            continue
        (recent if today - desk._stamp(p["published"]) <= timedelta(days=7) else before).append(v)
    if len(recent) < HOLD_MIN_N or len(before) < HOLD_MIN_N or statistics.median(before) == 0:
        return False
    return statistics.median(recent) < HOLD_RATIO * statistics.median(before)


def learned():
    return desk._load(desk.STATE / "learned.json", {})


def learned_value(key, default):
    """A learned value, or the default when it is missing or the file is older than LEARNED_DAYS (a weekly run that
    stopped must not leave a stale schedule in force)."""
    got = learned()
    at = desk._stamp(got.get("updated") or "")
    if not at or desk.now() - at > timedelta(days=LEARNED_DAYS):
        return default
    v = got.get(key)
    if key == "quiet_hours" and isinstance(v, dict):
        v = [int(h) for h in v]
    return default if v is None else v


# ------------------------------------------------------------------ the weekly run

def window_posts(days=WINDOW_DAYS):
    cut = desk.now() - timedelta(days=days)
    out = []
    for p, path in desk.posts():
        if p.get("status") not in ("published", "web") or p.get("kind") == "story" or not p.get("published"):
            continue
        if desk._stamp(p["published"]) < cut:
            continue
        out.append((p, path))
    return out


def open_sources(factories=None):
    got, missing = {}, {}
    for name, cls in (factories or SOURCES).items():
        if name == "instagram" and desk.cooldown_until():
            missing[name] = f"cooldown until {desk.cooldown_until():%Y-%m-%d %H:%M} UTC"
            continue
        try:
            got[name] = cls()
        except LookupError as e:
            missing[name] = f"not connected ({e})"
    return got, missing


def due(p, name):
    """Read again: posts up to REREAD_DAYS old, and older ones never measured on this platform."""
    if not ((p.get("metrics") or {}).get(name)):
        return True
    at = desk._stamp(p.get("published", ""))
    return bool(at) and desk.now() - at <= timedelta(days=REREAD_DAYS)


def pull(rows, sources):
    """Read every due post on every source; errors are counted per source and never stop the others. Instagram is
    checked against the desk's cooldown before every call, and a block answer goes to desk.note_block and stops
    Instagram for this run, the same rule the publishing flow follows."""
    errors = {}
    for name, src in sources.items():
        todo = [(p, path) for p, path in rows if due(p, name)]
        try:
            if hasattr(src, "prefetch") and todo:
                src.prefetch([p for p, _ in todo])
        except Exception as e:  # noqa: BLE001
            errors.setdefault(name, []).append(str(e)[:200])
            continue
        for p, path in todo:
            if name == "instagram" and desk.cooldown_until():
                errors.setdefault(name, []).append("stopped: Instagram cooldown")
                break
            try:
                m = src.fetch(p)
            except Exception as e:  # noqa: BLE001
                errors.setdefault(name, []).append(str(e)[:200])
                if name == "instagram" and desk.note_block(e):
                    break
                continue
            if m:
                p.setdefault("metrics", {})[name] = {**m, "at": desk.now().isoformat(timespec="seconds")}
                if name == "instagram":
                    p["insights"] = {k: v for k, v in m.items()}  # the site's "most shared" reads this
                desk._save(path, p)
    return {k: {"count": len(v), "first": v[0]} for k, v in errors.items()}


def run(factories=None):
    rows = window_posts()
    sources, missing = open_sources(factories)
    errors = pull(rows, sources)
    posts_ = [p for p, _ in rows]

    followers = {}
    for name, src in sources.items():
        try:
            n = src.followers()
            if n is not None:
                followers[LABELS[name]] = n
        except Exception as e:  # noqa: BLE001
            errors.setdefault(name, {"count": 0, "first": str(e)[:200]})["count"] += 1

    table = analyse(posts_)
    per_platform = {name: analyse(posts_, only={name}) for name in SOURCES}
    old_weights = desk._load(desk.STATE / "weights.json", {})
    weights = next_weights(table, old_weights)
    old = learned()
    from .desk import DIGEST_HOUR
    new = {"digest_hour": next_digest_hour(posts_, old.get("digest_hour", DIGEST_HOUR)),
           "quiet_hours": next_quiet_hours(posts_, old.get("quiet_hours") if isinstance(old.get("quiet_hours"), dict) else {}),
           "ramp_hold": ramp_hold(posts_, desk.now()),
           "updated": desk.now().isoformat(timespec="seconds")}

    desk._save(desk.STATE / "weights.json", weights)
    desk._save(desk.STATE / "learned.json", new)
    if followers:
        desk._save(desk.STATE / "followers.json", {**desk._load(desk.STATE / "followers.json", {}), **followers})
    week = desk.now().strftime("%G-W%V")
    report = {"week": week, "window_days": WINDOW_DAYS, "posts": len(posts_), "measured": len(lifts(posts_)),
              "account": {"followers_count": followers.get("Instagram")} if followers.get("Instagram") else {},
              "followers": followers, "missing": missing, "errors": errors,
              "notes": (["telegram: views cover a shorter window than 30 days (page cap reached)"]
                        if getattr(sources.get("telegram"), "short", False) else []),
              "signals": signals(table), "all": table, "by_platform": {k: v for k, v in per_platform.items() if v},
              "weights": {"before": old_weights, "after": weights},
              "learned": {"before": {k: old.get(k) for k in ("digest_hour", "quiet_hours", "ramp_hold")}, "after": new},
              "guard_rails": {"min_n": MIN_N, "shrink": SHRINK, "weight_range": WEIGHT_RANGE, "weight_step": WEIGHT_STEP,
                              "digest_window": DIGEST_WINDOW, "max_quiet": MAX_QUIET, "hold_ratio": HOLD_RATIO}}
    desk._save(desk.STATE / "insights" / f"{week}.json", report)
    print(f"insights {week}: {len(posts_)} posts, {report['measured']} measured on {', '.join(sources) or 'no platform'}")
    for line in report["signals"]:
        print("  " + line)
    for k, v in errors.items():
        print(f"  {k}: {v['count']} error(s), first: {v['first']}")
    return report


def summary_md(report):
    """The weekly file as a short Markdown block, for the GitHub step summary."""
    lines = [f"### Insights {report['week']}", "",
             f"{report['posts']} posts in the last {report['window_days']} days, {report['measured']} with numbers.", ""]
    if report["followers"]:
        lines += ["| Platform | Followers |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(report["followers"].items())] + [""]
    lines += ["**Signals**", ""] + ([f"- {x}" for x in report["signals"]] or ["- none yet (too few posts per group)"]) + [""]
    w = report["weights"]
    changed = {k: (w["before"].get(k, 1.0), v) for k, v in w["after"].items() if w["before"].get(k, 1.0) != v}
    lines += ["**Weight changes**", ""] + ([f"- {k}: {a} -> {b}" for k, (a, b) in sorted(changed.items())] or ["- none"]) + [""]
    lines += [f"Learned: {json.dumps(report['learned']['after'])}"] + [f"Note: {n}" for n in report.get("notes", [])]
    if report["missing"]:
        lines += ["", "Not connected: " + ", ".join(sorted(report["missing"]))]
    return "\n".join(lines) + "\n"



# the per-platform daily table (Kerem, 2026-11-27): one row per platform per day, from the read access we already have

VIEW_KEYS = ("views", "reach", "impressions", "post_impressions_unique")
LIKE_KEYS = ("likes", "like_count", "reactions")
COMMENT_KEYS = ("comments", "replies", "comments_count")
SHARE_KEYS = ("shares", "reposts", "quotes")


def _first(m, keys):
    return next((m[k] for k in keys if isinstance(m.get(k), (int, float))), None)


def day_table(rows, followers, day, shorts_state=None):
    """{platform: {posts, views, likes, comments, shares, followers}} for the posts published on `day` (UTC date)."""
    out = {}
    for name in SOURCES:
        sent = []
        for p in rows:
            if name == "instagram":
                ok = p.get("media_id") and (p.get("published") or "").startswith(day)
            else:
                slot = (p.get("platforms") or {}).get(name) or {}
                ok = slot.get("id") and not slot.get("removed") and (slot.get("at") or "").startswith(day)
            if ok:
                sent.append((p.get("metrics") or {}).get(name) or {})
        row = {"posts": len(sent), "followers": followers.get(name)}
        for label, keys in (("views", VIEW_KEYS), ("likes", LIKE_KEYS), ("comments", COMMENT_KEYS), ("shares", SHARE_KEYS)):
            vals = [v for v in (_first(m, keys) for m in sent) if v is not None]
            row[label] = sum(vals) if vals else None
        out[name] = row
    st = shorts_state if shorts_state is not None else desk._load(desk.STATE / "shorts.json", {})
    made = [v for v in (st.get("attempted") or {}).values() if (v.get("at") or "").startswith(day) and v.get("video_id")]
    # the YouTube token is upload-only by design: no views or followers until a read scope is granted
    out["youtube"] = {"posts": len(made), "narrated": sum(1 for v in made if v.get("narrated")), "views": None,
                      "likes": None, "comments": None, "shares": None, "followers": None}
    return out


def daily(factories=None, day=None):
    """Read today's posts on every connected platform and write the day's row to state/metrics.json (90 days kept).
    Site clicks are not counted: the site keeps no analytics by design (its privacy page). Returns the day's table."""
    day = day or f"{desk.now():%Y-%m-%d}"
    rows = window_posts(days=2)
    sources, missing = open_sources(factories)
    errors = pull(rows, sources)
    followers = {}
    for name, src in sources.items():
        try:
            followers[name] = src.followers()
        except Exception as e:  # noqa: BLE001
            errors.setdefault(name, {"count": 0, "first": str(e)[:200]})["count"] += 1
    table = day_table([p for p, _ in rows], followers, day)
    path = desk.STATE / "metrics.json"
    data = desk._load(path, {"days": {}})
    data["days"][day] = {"at": desk.now().isoformat(timespec="seconds"), "platforms": table,
                         **({"missing": missing} if missing else {}), **({"errors": errors} if errors else {})}
    data["days"] = dict(sorted(data["days"].items())[-90:])
    desk._save(path, data)
    return table
