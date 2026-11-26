"""The weekly insights loop: pull per-post numbers from every connected platform, find what works, and feed it back
into ranking and timing within guard rails. Standard library only.

  pull      Instagram (reach, saves, shares, profile visits, follows), Threads (views, likes, replies, reposts,
            quotes, shares), Facebook (reactions, comments, shares, impressions where Meta still serves them),
            Bluesky (likes, reposts, quotes, replies; the public AppView, no login) and Telegram (views read from
            the channel's own public page t.me/s/<channel>, subscribers from the Bot API). Each result lands in
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
from datetime import timedelta

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
        if not post.get("media_id"):
            return None
        got = self.client.media_insights(post["media_id"], metrics=self.METRICS)
        return {k: v for k, v in got.items() if k != "_errors"} or None

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
        self.handle = os.environ.get("BSKY_HANDLE", "").strip().lstrip("@") or "boardread.bsky.social"
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


class Telegram(Source):
    """The Bot API does not return view counts of channel posts, so views are read from the channel's own public web
    preview (https://t.me/s/<channel>), the same numbers anyone sees. Subscribers come from getChatMemberCount."""
    name = "telegram"
    PAGES = 8

    def __init__(self, opener=urllib.request.urlopen):
        super().__init__(opener)
        self.token, self.chat = os.environ.get("TG_BOT_TOKEN", ""), os.environ.get("TG_CHANNEL", "")
        # the public page needs the username: TG_CHANNEL when it is one, else the t.me link in desk.json accounts
        link = next((a["url"] for a in desk.CONFIG.get("accounts", []) if a["name"] == "Telegram" and a.get("url")), "")
        self.username = self.chat[1:] if self.chat.startswith("@") else link.rstrip("/").rsplit("/", 1)[-1]
        if not self.username:
            raise LookupError("a public channel username (TG_CHANNEL=@name or the Telegram url in desk.json)")
        self.views = {}

    def prefetch(self, posts):
        before = ""
        for _ in range(self.PAGES):
            html = self.get(f"https://t.me/s/{self.username}", {"before": before} if before else None, "telegram page").decode("utf-8", "replace")
            found = page_views(html)
            if not found:
                break
            self.views.update(found)
            before = str(min(found))
            if min(found) <= 1:
                break

    def fetch(self, post):
        slot = (post.get("platforms") or {}).get("telegram") or {}
        mid = int(slot["id"]) if str(slot.get("id", "")).isdigit() else None
        return {"views": self.views[mid]} if mid in self.views else None

    def followers(self):
        if not (self.token and self.chat):
            return None
        got = self.get_json(f"https://api.telegram.org/bot{self.token}/getChatMemberCount", {"chat_id": self.chat}, "telegram members")
        return got.get("result")


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
        return act / g("reach") if g("reach") >= 50 else float(act)
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


def lifts(rows):
    """[(post, {platform: lift})]: each value over its platform's median in the window; posts with no usable value drop out."""
    per = {}
    for p in rows:
        for name, m in (p.get("metrics") or {}).items():
            v = value(name, m)
            if v is not None:
                per.setdefault(name, []).append(v)
    med = {k: statistics.median(v) for k, v in per.items() if v and statistics.median(v) > 0}
    out = []
    for p in rows:
        got = {}
        for name, m in (p.get("metrics") or {}).items():
            v = value(name, m)
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


def next_quiet_hours(rows):
    """UTC hours where Threads and Bluesky posts do clearly worse (shrunk lift under QUIET_BELOW, MIN_N posts):
    web-tier posts wait for the next hour. At most MAX_QUIET hours, the worst first."""
    by = {}
    for p, got in lifts(rows):
        v = [got[k] for k in ("threads", "bluesky") if k in got]
        if v:
            by.setdefault(hour(p), []).append(sum(v) / len(v))
    bad = {h: shrunk(sum(v) / len(v), len(v)) for h, v in by.items() if len(v) >= MIN_N}
    bad = {h: x for h, x in bad.items() if x < QUIET_BELOW}
    return sorted(sorted(bad, key=bad.get)[:MAX_QUIET])


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
    v = learned().get(key)
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
        try:
            got[name] = cls()
        except LookupError as e:
            missing[name] = f"not connected ({e})"
    return got, missing


def pull(rows, sources):
    """Read every post on every source; errors are counted per source and never stop the others."""
    errors = {}
    for name, src in sources.items():
        try:
            if hasattr(src, "prefetch"):
                src.prefetch([p for p, _ in rows])
        except Exception as e:  # noqa: BLE001
            errors.setdefault(name, []).append(str(e)[:200])
            continue
        for p, path in rows:
            try:
                m = src.fetch(p)
            except Exception as e:  # noqa: BLE001
                errors.setdefault(name, []).append(str(e)[:200])
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
           "quiet_hours": next_quiet_hours(posts_),
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
    lines += [f"Learned: {json.dumps(report['learned']['after'])}"]
    if report["missing"]:
        lines += ["", "Not connected: " + ", ".join(sorted(report["missing"]))]
    return "\n".join(lines) + "\n"

