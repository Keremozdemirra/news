"""Boardread's news site, built from the committed posts after every run.

Static files only. Scripts are two small vanilla files (copy link, search); no third-party requests: photos are
copied in from the media branch and fonts are self-hosted, so a reader's browser talks to one origin.
Every post that reached a channel appears: published on Instagram, or web tier (status "web").

Where it is served comes from desk.json "site_url". A bare origin (https://boardread.news) puts everything at /;
an origin with a path (https://keremozdemir.de/news) puts everything under that path. One value, no other switch.

  /                      front page: lead, latest, most important, one block per topic, this week, follow
  /latest/               every article, newest first, paged        /latest/page/<n>/
  /t/<topic>/            one topic, paged
  /s/<id>/               one article: photo, report, sources, share, related, previous and next
  /week/                 the last seven days, ranked            /week/<YYYY-Www>/  one finished ISO week
  /archive/              one page per day                       /archive/<YYYY-MM-DD>/
  /search/               client-side search over /search.json
  /play/                 the games hub; /play/<slug>/ one game, copied from games/<slug>/ (see aidaily/play.py)
  /about/ /standards/ /contact/ /404.html   (Impressum and Privacy are keremozdemir.de's, same operator)
  /feed.xml /weekly.xml /sitemap.xml /news-sitemap.xml /robots.txt
  /og/<id>.jpg           the 1200x630 link-preview image of a article, cut from its photo at build time
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import desk, focus, markets, outlets, seo

E = lambda s: html.escape(s or "", quote=True)  # noqa: E731
# DESK_SITE_URL builds the same pages for another address (a local preview, a staging host) without touching desk.json
SITE = (os.environ.get("DESK_SITE_URL") or desk.CONFIG["site_url"]).rstrip("/")
BASE = "/" + SITE.split("/", 3)[3] if SITE.count("/") >= 3 else ""
ORIGIN = "/".join(SITE.split("/")[:3])
NAME = "Boardread"
TAGLINE = "The news that moves business"
ASSETS = Path(__file__).resolve().parent.parent / "assets-site"
OG_W, OG_H = 1200, 630
PER = 20  # articles on one listing page
# Order of the section bar and of the blocks on the front page.
TOPICS = {
    "Markets": "Equities, rates, currencies and commodities, and what moved them.",
    "Economy": "Growth, inflation, jobs and central banks.",
    "Business": "Companies, deals, earnings and strategy.",
    "Politics": "Policy, regulation and elections where they reach business.",
    "World": "Trade, conflict and geopolitics that end up on a balance sheet.",
    "Tech": "The technology industry and the products behind it.",
    "AI": "Models, chips, products and the money around artificial intelligence.",
    "Culture": "Media, entertainment and consumer trends that move business.",
    "Sport": "Football, Formula 1, the NBA and NFL, tennis, golf, cricket, boxing and the Olympics.",
}
SPORT = "Sport"
TOPIC_ORDER = list(TOPICS)  # the section bar and the footer
NEWS_ORDER = [t for t in TOPIC_ORDER if t != SPORT]  # the business sections: the front page blocks come from these, Sport follows them


def is_sport(p):
    return p.get("topic") == SPORT


def topic_path(t):
    """Where a section lives: Sport at /sport/, every other topic at /t/<topic>/."""
    return f"/{t.lower()}/" if t == SPORT else f"/t/{t.lower()}/"
# Same operator as keremozdemir.de, whose Impressum and Privacy pages are the legal notice of this site too.
LEGAL = {"impressum": "https://keremozdemir.de/impressum/", "privacy": "https://keremozdemir.de/privacy/"}
CONTACT_ISSUES = "https://github.com/Keremozdemirra/news/issues"


def published():
    """Posts live on the site: published on Instagram or published to the web tier. Nothing on a page may say
    which one it was, except the Instagram link a post carries only when it has a permalink."""
    rows = [p for p, _ in desk.posts() if p.get("status") in ("published", "web") and p.get("published") and p.get("kind") != "story"]
    # a queued post sent to the other platforms while Instagram was blocked already links to its page
    rows += [dict(p, published=p["lead_published"]) for p, _ in desk.posts()
             if p.get("status") == "queued" and p.get("lead_published") and p.get("kind") != "story"]
    return sorted(rows, key=lambda p: p["published"], reverse=True)


def dt(iso):
    d = datetime.fromisoformat(iso)
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def when(iso):
    return dt(iso).strftime("%-d %b %Y, %H:%M UTC")


def clock(iso):
    return dt(iso).strftime("%-d %b, %H:%M")


def hhmm(iso):
    return dt(iso).strftime("%H:%M")


def day_of(iso):
    return dt(iso).strftime("%Y-%m-%d")


def today():
    return desk.now().strftime("%Y-%m-%d")


def stamp(iso, utc=True, ref=None):
    """The one way a time is written in a list: "11:17 UTC" for an article of the day being built, "26 Nov, 11:17 UTC" for any other
    day, so yesterday and today never read alike. utc=False for the narrow places where the footer's "All times UTC" says it."""
    d = dt(iso)
    text = d.strftime("%H:%M") + (" UTC" if utc else "")
    return text if day_of(iso) == (ref or today()) else d.strftime("%-d %b, ") + text


def day_label(day):
    return datetime.strptime(day, "%Y-%m-%d").strftime("%-d %B %Y")


def week_of(iso):
    return dt(iso).strftime("%G-W%V")


def iso(s):
    return dt(s).strftime("%Y-%m-%dT%H:%M:%SZ")


def shared(p):
    i = p.get("insights") or {}
    # shares and saves say a reader found it worth keeping; before the weekly numbers arrive, the news value the front page uses decides
    return ((i.get("shares") or 0) + (i.get("saved") or 0), views.front_score(p))


def topic(p):
    t = p.get("topic")
    return t if t in TOPICS else "Business"


def href(p):
    return f"{BASE}/s/{p['id']}/"


def short(url):
    return url.split("/")[2].removeprefix("www.") if url.count("/") >= 2 else url


def stats():
    """Followers per platform from the latest weekly file, and what the desk itself keeps."""
    latest = sorted((desk.STATE / "insights").glob("*.json"))
    acct = desk._load(latest[-1], {}).get("account", {}) if latest else {}
    followers = {"Instagram": acct.get("followers_count")} if acct.get("followers_count") else {}
    followers.update(desk._load(desk.STATE / "followers.json", {}))
    return followers


ASSET_FILES = ("theme.js", "site.css", "views.css", "paper.css", "play.css", "site.js", "paper.js", "play.js")
ASSET_V = hashlib.sha1(b"".join((ASSETS / f).read_bytes() for f in ASSET_FILES if (ASSETS / f).exists())).hexdigest()[:8]
FACES = (
    "@font-face{font-family:'Libre Franklin';font-weight:400;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-400.woff2') format('woff2')}"
    "@font-face{font-family:'Libre Franklin';font-weight:500;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-500.woff2') format('woff2')}"
    "@font-face{font-family:'Libre Franklin';font-weight:600;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-600.woff2') format('woff2')}"
    "@font-face{font-family:'Libre Franklin';font-weight:800;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-800.woff2') format('woff2')}"
    # Newsreader (headlines and article text): one variable file, weights 400 to 700; Source Serif 4 and Georgia stand in
    "@font-face{font-family:'Newsreader';font-weight:400 700;font-style:normal;font-display:swap;src:url('{b}/fonts/Newsreader-var.woff2') format('woff2')}"
    # stand-in sized to the web font, so the swap moves nothing
    "@font-face{font-family:'Franklin Fallback';src:local('Arial');size-adjust:103%;ascent-override:92%;descent-override:22%;line-gap-override:0%}"
).replace("{b}", BASE)


def ld_json(data):
    # "<" escaped so no text inside a field can close the script element
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def clip(text, n):
    """At most n characters, cut at a word and marked, for fields a consumer truncates or rejects (JSON-LD headline: 110)."""
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


DEFAULT_OG = f"{BASE}/og-default.png"


# Marks drawn here in one monoline weight (1.25 stroke, round caps, 16-unit grid, currentColor), as keremozdemir.de does:
# a trademark redrawn from memory comes out subtly wrong, so the five platform logos below are the brands' own
# glyphs (BRANDS) and these are generic shapes. x, linkedin and copy are that site's drawings (src/components/icon.tsx), path data unchanged.
SQ = '<rect x="1.6" y="1.6" width="12.8" height="12.8" rx="2.4"/>'
MARKS = {
    "x": SQ + '<path d="M5.2 5.2 10.8 10.8M10.8 5.2 5.2 10.8"/>',
    "linkedin": SQ + '<path d="M5 6.6v4.2M5 4.5v.1"/><path d="M8.2 10.8V6.6M8.2 8.2c0-1 .8-1.6 1.6-1.6s1.4.6 1.4 1.7v2.5"/>',
    "copy": '<rect x="5.6" y="5.6" width="8.8" height="8.8" rx="1.3"/><path d="M10.9 3.2a1.4 1.4 0 0 0-1.3-1.1H3a1.4 1.4 0 0 0-1.4 1.4v6.6c0 .6.4 1.2 1.1 1.3"/>',
    "check": '<path d="m3 8.4 3.4 3.4L13 5.2"/>',
    "rss": '<circle cx="3.6" cy="12.4" r=".9"/><path d="M2.6 7.6a5.8 5.8 0 0 1 5.8 5.8M2.6 2.8a10.6 10.6 0 0 1 10.6 10.6"/>',
    "whatsapp": '<path d="M8 1.9a6.1 6.1 0 0 0-5.2 9.2l-.8 3 3.1-.8A6.1 6.1 0 1 0 8 1.9z"/><path d="m5.6 6 .9 3.8 1.5-2.5 1.5 2.5.9-3.8"/>',
}


# The six platform logos are the brands' own glyphs, not redrawings: path data from Simple Icons (CC0 1.0 for the
# files; the logos stay trademarks of their owners), fetched 2026-11-27 from github.com/simple-icons/simple-icons
# icons/<name>.svg on develop, 24x24, monochrome, drawn filled in currentColor. Used as supplied: no rotation, no
# distortion, no altered shapes (the Meta, Bluesky and Telegram guidelines forbid all three); they are only scaled evenly.
# Guidelines: about.meta.com/brand/resources/instagram, meta.com/brand/resources/instagram/threads,
# about.meta.com/brand/resources/facebook/logo, bsky.social/about/blog/press-faq, telegram.org/tour/screenshots,
# youtube.com/howyoutubeworks/resources/brand-resources (YouTube added 2026-11-27, same source).
BRANDS = {
    "instagram": "M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077",
    "threads": "M18.263 11.097c-.03-3.486-1.92-5.586-5.111-5.586-2.13 0-3.922.963-4.863 2.499l2.062 1.438c.535-.843 1.272-1.543 2.628-1.543 1.528 0 2.318.85 2.544 2.431a15 15 0 0 0-2.236-.173c-4.125 0-6.068 1.867-6.068 4.336s1.943 3.99 4.804 3.99c3.139 0 5.013-2.115 5.781-4.735.798.361 1.348 1.204 1.348 2.47 0 3.387-3.907 5.232-7.22 5.232-4.885 0-8.077-3.207-8.077-8.424 0-6.392 4.223-10.487 9.9-10.487 3.808 0 5.69 1.671 6.97 3.914l2.108-1.475C21.44 2.078 18.331 0 13.663 0 6.227 0 1.168 5.277 1.168 12.934c0 7 4.953 11.066 10.856 11.066 4.878 0 9.809-2.846 9.809-7.716 0-2.545-1.46-4.231-3.569-5.187m-6.33 4.855c-1.077 0-2.026-.512-2.026-1.453 0-1.483 1.822-1.934 3.606-1.934.678 0 1.34.045 1.927.173-.422 1.927-1.671 3.215-3.508 3.214Z",
    "bluesky": "M5.202 2.857C7.954 4.922 10.913 9.11 12 11.358c1.087-2.247 4.046-6.436 6.798-8.501C20.783 1.366 24 .213 24 3.883c0 .732-.42 6.156-.667 7.037-.856 3.061-3.978 3.842-6.755 3.37 4.854.826 6.089 3.562 3.422 6.299-5.065 5.196-7.28-1.304-7.847-2.97-.104-.305-.152-.448-.153-.327 0-.121-.05.022-.153.327-.568 1.666-2.782 8.166-7.847 2.97-2.667-2.737-1.432-5.473 3.422-6.3-2.777.473-5.899-.308-6.755-3.369C.42 10.04 0 4.615 0 3.883c0-3.67 3.217-2.517 5.202-1.026",
    "telegram": "M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z",
    "facebook": "M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z",
    "youtube": "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z",
}


def mark(name):
    """The inline mark for a channel or action, decorative: the link around it carries the accessible name."""
    if name.lower() in BRANDS:
        return (f'<svg class="mk mk-brand" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" role="img" '
                f'aria-label="{E(name)}" focusable="false"><path d="{BRANDS[name.lower()]}"/></svg>')
    return (f'<svg class="mk" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{MARKS[name.lower()]}</svg>') if name.lower() in MARKS else ""


def chan(name, url, extra=""):
    """A link to one of our channels: the mark, the name (hidden from sight on phones, still read aloud) and what follows."""
    return (f'<a class="chan" href="{E(url)}" rel="me noopener" aria-label="{E(name)}">{mark(name)}<span class="t">{E(name)}</span>{extra}</a>')


def accounts():
    return [a for a in desk.CONFIG.get("accounts", []) if a.get("url")]


# What the masthead counts, set by build() before any page is written: articles in the last 24 hours and the newsrooms behind them.
MARKETS = None  # official rates for the pages that show them, loaded once per build


def crypto_credit():
    return (f' Crypto prices: <a href="{markets.CMC_HOME}" rel="noopener">{markets.CMC_CREDIT}</a>.'
            if (MARKETS or {}).get("crypto", {}).get("coins") else "")
# The main navigation. Key is what a page passes as active; Play is the daily games hub.
# The menu panel: everything that is not a section. Key is what a page passes as active.
NAV = [("/latest/", "Latest", "latest"), ("/brief/", "Brief", "brief"), ("/board/", "Board", "board"), ("/feed/", "Feed", "feed"),
       ("/paper/", "Yesterday\u2019s paper", "paper"), ("/numbers/", "Numbers", "numbers"), ("/play/", "Play", "play"),
       ("/week/", "Week", "week"), ("/about/", "About", "about"), ("/how-it-works/", "How it works", "how")]


THEME_BTN = ('<button type="button" class="themebtn" aria-label="Switch to the dark theme" aria-pressed="false">'
             '<svg class="sun" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
             '<circle cx="8" cy="8" r="2.6"/><path d="M8 1.6v1.6M8 12.8v1.6M1.6 8h1.6M12.8 8h1.6M3.5 3.5l1.1 1.1M11.4 11.4l1.1 1.1M3.5 12.5l1.1-1.1M11.4 4.6l1.1-1.1"/></svg>'
             '<svg class="moon" width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
             '<path d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8z"/></svg></button>')


# Pages that have shipped. A view is built, linked from the menu and the footer only while its key is here.
SHIPPED = {"numbers", "board", "feed", "paper", "play"}


def nav_items():
    return [(h, n, k) for h, n, k in NAV if k not in ("board", "feed", "paper", "numbers", "play") or k in SHIPPED]


def menu_html(active):
    """The menu button and its panel: a details element, so it opens without a script and with the keyboard."""
    items = "".join(f'<li><a href="{BASE}{h}"{" aria-current=\"page\"" if active == k else ""}>{n}</a></li>' for h, n, k in nav_items())
    return (f'<details class="menu"><summary aria-label="Menu"><svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" '
            f'aria-hidden="true" focusable="false"><path d="M3 6h14M3 10h14M3 14h14"/></svg><span class="mlab">Menu</span></summary><nav class="mpanel" aria-label="Menu"><ul>{items}</ul></nav></details>')


def section_nav(active):
    links = "".join(f'<a href="{BASE}{topic_path(t)}"{" aria-current=\"page\"" if active == t.lower() else ""}>{t}</a>' for t in TOPIC_ORDER)
    return f'<nav class="sections" aria-label="Sections">{links}</nav>'


SEARCH_LINK = (f'<a class="iconbtn" href="{{b}}/search/" aria-label="Search"><svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" '
               f'stroke-linecap="round" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="5.5"/><path d="m13.2 13.2 4 4"/></svg></a>')


def page(title, body, desc="", path="/", image=None, og_type="website", ld=None, og_title=None, active="", front=False,
         noindex=False, rel=None, main_class="", feed=None, styles=("views",), scripts=(), body_class="", canonical=None):
    """Every page. path is relative to the site root and becomes the canonical and og:url; image is the
    site-relative link-preview image (the shared default when a article has no photo). rel: {"prev": path, "next": path}.
    styles and scripts name extra files of assets/ (views, paper, play / paper, play) loaded only by the pages that use them."""
    url = SITE + (canonical or path)  # canonical: a page that repeats another one (/paper/) points at the original
    img = ORIGIN + (image or DEFAULT_OG)
    og_dims = f'<meta property="og:image:width" content="{OG_W}"><meta property="og:image:height" content="{OG_H}">\n' \
        if image in (None, DEFAULT_OG) or image.startswith(f"{BASE}/og/") else ""
    links = "".join(f'<link rel="{k}" href="{E(SITE + v)}">' for k, v in (rel or {}).items())
    # a topic or company page offers its own feed beside the site-wide one: feed = (title, path)
    own_feed = f'<link rel="alternate" type="application/rss+xml" title="{E(feed[0])}" href="{E(SITE + feed[1])}">\n' if feed else ""
    now = datetime.now(timezone.utc)
    if front:
        active = "front"
    word = (f'<h1 class="word"><a href="{BASE}/" aria-label="boardread. front page">boardread.</a></h1>' if front
            else f'<a class="word" href="{BASE}/" aria-label="boardread. front page">boardread.</a>')
    nl = desk.CONFIG.get("newsletter_url")
    foot_sections = "".join(f'<li><a href="{BASE}{topic_path(t)}">{t}</a></li>' for t in TOPIC_ORDER)
    follow_links = "".join(f'<li>{chan(a["name"], a["url"])}</li>' for a in accounts()) + f'<li><a class="chan" href="{BASE}/feed.xml" aria-label="RSS">{mark("rss")}<span class="t">RSS</span></a></li>'
    css = "".join(f'<link rel="stylesheet" href="{BASE}/assets/{n}.css?v={ASSET_V}">' for n in styles)
    js = "".join(f'<script src="{BASE}/assets/{n}.js?v={ASSET_V}" defer></script>' for n in scripts)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; manifest-src 'self'; form-action 'self'; base-uri 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#ffffff">
<script src="{BASE}/assets/theme.js?v={ASSET_V}"></script>
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
{'<meta name="robots" content="noindex">' if noindex else '<meta name="robots" content="max-image-preview:large">'}
<link rel="canonical" href="{E(url)}">{links}
<link rel="icon" href="{BASE}/icon.svg" type="image/svg+xml"><link rel="icon" href="{BASE}/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="{BASE}/apple-touch-icon.png"><link rel="manifest" href="{BASE}/manifest.webmanifest">
{own_feed}<link rel="alternate" type="application/rss+xml" title="boardread." href="{BASE}/feed.xml">
<link rel="sitemap" type="application/xml" href="{BASE}/sitemap.xml">
<link rel="preload" href="{BASE}/fonts/LibreFranklin-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{BASE}/fonts/LibreFranklin-800.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{BASE}/fonts/Newsreader-var.woff2" as="font" type="font/woff2" crossorigin>
<meta property="og:site_name" content="{NAME}"><meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(og_title or title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(url)}"><meta property="og:image" content="{E(img)}">
{og_dims}<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(og_title or title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{E(img)}">
{"".join(ld_json(x) for x in (ld if isinstance(ld, list) else [ld])) if ld else ""}
<style>{FACES}</style><link rel="stylesheet" href="{BASE}/assets/site.css?v={ASSET_V}">{css}
<script src="{BASE}/assets/site.js?v={ASSET_V}" defer></script>{js}</head>
<body class="{'front-page' if front else 'compact'} {body_class}">
<a class="skip" href="#main">Skip to the news</a>
<header class="mh"><div class="bar"><div class="wrap barin">
<div class="bl">{menu_html(active)}{SEARCH_LINK.replace("{b}", BASE)}</div>
{word}
<div class="br"><ul class="chans" aria-label="Boardread on other channels">{"".join(f'<li>{chan(a["name"], a["url"])}</li>' for a in accounts())}</ul>{THEME_BTN}</div>
</div></div>
<div class="wrap">{section_nav(active)}{markets.strip(MARKETS, BASE)}</div></header>
<main id="main" class="wrap {main_class}">{body}</main>
<footer class="foot"><div class="wrap">
<div class="foot-grid">
<div><h2>Sections</h2><ul>{foot_sections}</ul></div>
<div><h2>Boardread</h2><ul><li><a href="{BASE}/about/">About</a></li><li><a href="{BASE}/how-it-works/">How it works</a></li>{f'<li><a href="{BASE}/play/">Play</a></li>' if "play" in SHIPPED else ""}<li><a href="{BASE}/standards/">Standards and corrections</a></li><li><a href="{BASE}/contact/">Contact</a></li>{f'<li><a href="{E(nl)}">Newsletter</a></li>' if nl else ''}</ul></div>
<div><h2>Legal</h2><ul><li><a href="{LEGAL['impressum']}">Impressum</a></li><li><a href="{LEGAL['privacy']}">Privacy</a></li></ul></div>
<div><h2>Follow</h2><ul>{follow_links}</ul></div>
</div>
<div class="foot-base"><span>Written by AI from the sources listed. Corrections: <a href="{BASE}/contact/">contact</a>. All times UTC.{crypto_credit()} &copy; {now.year} Boardread.</span><span><button type="button" class="kbd-hint" data-keys hidden>Keyboard shortcuts</button></span></div>
</footer></body></html>"""


# ---------------------------------------------------------------- pieces

PHOTOS = {}  # post id -> {"dim": (w, h), "dim_t": (w, h), "focus": (fx, fy), "face": bool}, filled while the images are written


def fit(p, thumb, ratio, fixed=False):
    """(src, (w, h), ratio, object-position) of the photo of p in a box of shape `ratio`.

    w and h are the file's own size, so the browser reserves the right box before the file arrives. The position comes
    from the photo's focal point and the box shape, so a face stays inside every crop; a face is never cut into a strip
    wider than 3:2. The same call serves every page, so the thumbnail in a list and the figure on the article agree."""
    use_thumb = thumb or not p.get("_hires")
    src = f"{BASE}/img/{p['id']}-t.jpg" if use_thumb else f"{BASE}/img/{p['id']}.jpg"
    m = PHOTOS.get(p["id"], {})
    size = m.get("dim_t" if use_thumb else "dim") or ((480, 320) if use_thumb else (960, 640))
    ratio = ratio if fixed else focus.box_ratio(ratio, size, m.get("face"))  # fixed: the stylesheet sets the box, so the shape is not ours to change
    return src, size, ratio, focus.object_position(m.get("focus") or focus.PRIOR_SCENE, size, focus.ratio_value(ratio))


def photo_img(p, thumb=True, ratio="3/2", alt="", load="lazy", box=True, fixed=False):
    """The <img> of p. `box`: the tag carries its own aspect-ratio (when no wrapper does), so nothing moves while it loads."""
    src, (w, h), ratio, pos = fit(p, thumb, ratio, fixed)
    lazy = 'fetchpriority="high"' if load == "eager" else 'loading="lazy" decoding="async"'
    style = f"aspect-ratio:{ratio};" if box else ""
    return f'<img src="{src}" width="{w}" height="{h}" alt="{E(alt)}" {lazy} style="{style}object-position:{pos}">'


def pic(p, thumb=False, eager=False, ratio="3/2", alt=""):
    """The photo in a box of the given shape (3:2 unless a page asks for another). The wrapper holds the shape, the image
    fills it, so the page does not shift as photos arrive."""
    if not p.get("_thumb"):
        return ""
    ratio = fit(p, thumb, ratio)[2]
    return f'<span class="pic" style="aspect-ratio:{ratio}">{photo_img(p, thumb, ratio, alt=alt, load="eager" if eager else "lazy", box=False)}</span>'


def by(p):
    return E(", ".join(outlets.newsrooms(p)))




def coverage(p):
    """Distinct newsrooms behind a article, aggregators not counted."""
    return len(outlets.newsrooms(p))


def cover(p):
    """Coverage as text: "4 newsrooms". The names are on the article page."""
    n = coverage(p)
    return f'<span class="cover">{n} newsroom{"" if n == 1 else "s"}</span>' if n else ""


def meta(*parts):
    return '<span class="meta">' + '<span class="sep">&middot;</span>'.join(x for x in parts if x) + "</span>"


def t_tag(p):
    return f'<time datetime="{iso(p["published"])}">{stamp(p["published"])}</time>'


def lead_block(p):
    return (f'<article class="lead"><a class="story-link" href="{href(p)}">{pic(p, eager=True)}'
            f'<span class="kick">{E(topic(p))}</span><h2 class="h-xl">{E(p["headlines"][0])}</h2>'
            f'<p class="dek">{E(p.get("dek", ""))}</p>'
            f'{meta(t_tag(p), cover(p))}</a></article>')


def pair_block(rows):
    cells = "".join(f'<article><a class="story-link" href="{href(p)}">{pic(p, thumb=True)}<span class="kick">{E(topic(p))}</span>'
                    f'<h3 class="h-l">{E(p["headlines"][0])}</h3>{meta(t_tag(p), cover(p))}</a></article>' for p in rows)
    return f'<div class="pair">{cells}</div>' if rows else ""


def stream(rows, n=10):
    out, last = [], None
    days = {day_of(p["published"]) for p in rows[:n]}
    for p in rows[:n]:
        d = day_of(p["published"])
        if len(days) > 1 and d != last:
            out.append(f'<li class="day">{day_label(d)}</li>')
        last = d
        out.append(f'<li><a href="{href(p)}">{meta(f"<time datetime=\"{iso(p['published'])}\">{hhmm(p['published'])}</time>", E(topic(p)))}'
                   f'<span class="h-s">{E(p["headlines"][0])}</span></a></li>')
    return f'<ul class="stream">{"".join(out)}</ul>'


def ranked(rows, n=5):
    items = "".join(f'<li><span class="n" aria-hidden="true">{i}</span><a href="{href(p)}"><span class="h-s">{E(p["headlines"][0])}</span>'
                    f'{meta(E(topic(p)), stamp(p["published"]))}</a></li>' for i, p in enumerate(rows[:n], 1))
    return f'<ol class="rank">{items}</ol>'


def item(p):
    return (f'<li><a class="item{"" if p.get("_thumb") else " text"}" href="{href(p)}"><div>{meta(t_tag(p))}'
            f'<span class="h-m">{E(p["headlines"][0])}</span></div>{pic(p, thumb=True)}</a></li>')


def sec_head(label, link=None, more="", level=2):
    right = f'<a class="more" href="{link}">{more}</a>' if link else ""
    return f'<div class="sec"><h{level}>{label}</h{level}>{right}</div>'


def topic_block(t, rows, used=()):
    """One topic: a featured article and up to three more. A article already shown higher on the page is passed over."""
    fresh = [p for p in rows[:12] if p not in used] or rows[:12]
    feat = max(fresh, key=lambda p: (bool(p.get("_hires")), p.get("score", 0)))
    if isinstance(used, list):
        used.append(feat)
    rest = [p for p in rows if p is not feat][:3]
    return (f'<section class="block" aria-label="{t}">{sec_head(t, f"{BASE}{topic_path(t)}", f"More {t}")}'
            f'<div class="block-grid{"" if rest else " solo"}"><article class="feat"><a class="story-link" href="{href(feat)}">{pic(feat, thumb=True)}'
            f'<h3 class="h-l">{E(feat["headlines"][0])}</h3><p class="dek">{E(feat.get("dek", ""))}</p>'
            f'{meta(t_tag(feat), cover(feat))}</a></article><ul class="list">{"".join(item(p) for p in rest)}</ul></div></section>')


def follow_block():
    fol, nl = stats(), desk.CONFIG.get("newsletter_url")
    links = "".join(f'<li><a href="{E(a["url"])}" rel="me noopener" aria-label="{E(a["name"])}"><span class="who">{mark(a["name"])}<span>{E(a["name"])}</span></span>'
                    + (f'<span>{fol[a["name"]]:,} followers</span>' if isinstance(fol.get(a["name"]), int) else "<span>&nearr;</span>")
                    + "</a></li>" for a in accounts())
    letter = f'<a class="nl" href="{E(nl)}">Get the weekly Top 10 by email</a>' if nl else ""
    return (f'<section class="follow" aria-labelledby="fh"><h2 id="fh">Follow Boardread</h2>'
            f'<p>The same news on the channels you already use, each with its sources.</p><ul>{links}</ul>{letter}</section>')


def listing_row(p):
    return (f'<li><a class="row{"" if p.get("_thumb") else " text"}" href="{href(p)}"><div>{meta(E(topic(p)), t_tag(p), cover(p))}'
            f'<h2 class="h-l">{E(p["headlines"][0])}</h2><p class="dek">{E(p.get("dek", ""))}</p></div>{pic(p, thumb=True)}</a></li>')


def pager(path, n, total):
    if total <= 1:
        return ""
    link = lambda k, text: f'<a href="{BASE}{path}{"" if k == 1 else f"page/{k}/"}" rel="{"prev" if k < n else "next"}">{text}</a>'  # noqa: E731
    return (f'<nav class="pager" aria-label="Pages">{link(n - 1, "&larr; Newer") if n > 1 else "<span class=ph></span>"}'
            f'<span>Page {n} of {total}</span>{link(n + 1, "Older &rarr;") if n < total else "<span class=ph></span>"}</nav>')


def listing(rows, path, n, total, aside=""):
    if not rows:
        return '<div class="empty">The first articles are on their way.</div>'
    first = rows[0] if n == 1 and rows[0].get("_hires") else None
    lead = (f'<div class="leadrow"><a class="story-link" href="{href(first)}">{pic(first, eager=True, ratio="16/9")}<span class="kick">{E(topic(first))}</span>'
            f'<h2 class="h-xl">{E(first["headlines"][0])}</h2><p class="dek">{E(first.get("dek", ""))}</p>'
            f'{meta(t_tag(first), cover(first))}</a></div>') if first else ""
    body = lead + f'<ol>{"".join(listing_row(p) for p in rows if p is not first)}</ol>' + pager(path, n, total)
    # a section with few articles has no "Most important" column; the column still holds its place, so the lead photo is
    # the same size on every listing page
    return f'<div class="listing{"" if aside else " solo"}"><div>{body}</div><aside aria-label="Most important"{"" if aside else " hidden"}>{aside}</aside></div>'


def pagehead(title, sub=""):
    return f'<div class="pagehead"><h1>{E(title)}</h1>{f"<p>{E(sub)}</p>" if sub else ""}</div>'


def share_links(p):
    u, h = f"{SITE}/s/{p['id']}/", p["headlines"][0]
    q = lambda s: urllib.parse.quote(s, safe="")  # noqa: E731
    items = (("X", f"https://x.com/intent/post?text={q(h)}&url={q(u)}"),
             ("Bluesky", f"https://bsky.app/intent/compose?text={q(h + ' ' + u)}"),
             ("LinkedIn", f"https://www.linkedin.com/sharing/share-offsite/?url={q(u)}"),
             ("WhatsApp", f"https://wa.me/?text={q(h + ' ' + u)}"))
    return ('<div class="share">' + f'<button type="button" data-copy="{E(u)}" aria-label="Copy link" hidden>{mark("copy")}<span class="t">Copy link</span></button>'
            + "".join(f'<a href="{E(h2)}" target="_blank" rel="noopener noreferrer" aria-label="Share on {n}">{mark(n)}<span class="t">{n}</span></a>' for n, h2 in items) + "</div>")


def og_image(photo, dest, at=None, size=None):
    """A 1200x630 JPEG cut from the article's photo, for link previews (Facebook, Telegram, Threads, X).

    The photos are 1050-1400 px wide in every aspect ratio, so the preview is a cover crop whose window is centred on the
    photo's focal point (the face of a portrait), as far as the edges allow. ffmpeg is on the Actions image and on the desk's Mac."""
    px, py = focus.position(at or focus.PRIOR_SCENE, size or focus.jpeg_size(photo) or (OG_W, OG_H), OG_W / OG_H)
    vf = f"scale={OG_W}:{OG_H}:force_original_aspect_ratio=increase,crop={OG_W}:{OG_H}:(iw-{OG_W})*{px:.4f}:(ih-{OG_H})*{py:.4f}"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(photo), "-vf", vf, "-q:v", "3", str(dest)],
                       check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False  # the article still builds; its preview falls back to the shared image
    return True


def card_html(p, photo=None):
    """The share card as a page: topic, headline, coverage meter and the address, the article photo on the right when it has one.
    Same type and monochrome as the site; the fonts are read from the files, as this page is rendered from disk."""
    head, n = p["headlines"][0], coverage(p)
    size = 70 if len(head) <= 60 else 60 if len(head) <= 95 else 50 if len(head) <= 130 else 42
    face = "".join(f"@font-face{{font-family:'Libre Franklin';font-weight:{w};src:url('file://{ASSETS / 'fonts' / f'LibreFranklin-{w}.woff2'}') format('woff2')}}" for w in (400, 600, 800))
    m = PHOTOS.get(p.get("id"), {})
    pos = focus.object_position(m.get("focus") or focus.PRIOR_SCENE, m.get("dim") or focus.jpeg_size(photo) or (960, 640), 420 / OG_H) if photo else ""
    img = (f'<div class="ph"><img src="file://{photo}" style="object-position:{pos}"></div>' if photo
           else "")
    return f"""<!doctype html><meta charset="utf-8"><style>{face}
*{{box-sizing:border-box;margin:0}}body{{width:{OG_W}px;height:{OG_H}px;background:#fff;color:#111;font-family:'Libre Franklin',Arial,sans-serif;display:flex;overflow:hidden}}
.t{{flex:1;padding:52px 56px 48px;display:flex;flex-direction:column;justify-content:space-between;min-width:0}}
.w{{font-weight:800;font-size:38px;letter-spacing:-.055em}}.k{{font-weight:600;font-size:24px;color:#4d4d50;margin-top:34px}}
h1{{font-weight:800;font-size:{size}px;line-height:1.06;letter-spacing:-.035em;margin-top:14px}}
.b{{display:flex;justify-content:space-between;align-items:center;font-size:26px;font-weight:600;border-top:2px solid #0a0a0a;padding-top:22px}}
.c{{white-space:nowrap;font-size:24px;color:#5c5c5c}}
.u{{color:#0a0a0a;font-weight:800;letter-spacing:-.02em}}
.ph{{width:420px;flex:none;position:relative}}.ph.art{{color:#0a0a0a;background:#fff;border-left:2px solid #111}}.ph.art svg{{position:absolute;inset:0;width:100%;height:100%}}.ph img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}</style>
<body><div class="t"><div><div class="w">boardread.</div><div class="k">{E(topic(p))}</div><h1>{E(head)}</h1></div>
<div class="b"><span class="c">{n} newsroom{"" if n == 1 else "s"}</span><span class="u">boardread.news</span></div></div>{img}</body>"""


def share_card(p, photo, dest):
    """The article's 1200x630 link-preview image, drawn by headless Chrome (the card the desk's own templates use).
    False when Chrome or ffmpeg is missing; the caller then falls back to the cropped photo."""
    from . import render
    dest = Path(dest)
    png = dest.with_suffix(".png")
    try:
        render.shoot(card_html(p, photo.resolve() if photo else None), png, OG_W, OG_H)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-q:v", "3", str(dest)], check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        png.unlink(missing_ok=True)
    return dest.exists()


def photo_alt(p):
    """Alt text from the Commons file name, without the camera numbers, dates and "(cropped)" tags that mean nothing read aloud.
    A scene carries its own: its file name names a place the story may not be about."""
    if p.get("photo_alt"):
        return p["photo_alt"]
    t = Path(p.get("photo_file") or "").stem.replace("_", " ")
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{5,}\b|\b\d{8}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip(" -,.")


def credit_line(p):
    """The photo credit as licensed. A stand-in scene says so: it is not a photo of this event."""
    from . import entities
    c = entities.clean_credit((p.get("credit") or "").strip())
    if not c or p.get("photo_kind") != "scene":
        return c
    what = "of the sport" if p.get("topic") == "Sport" else ""
    return f"Archive photo {what}, not from this event. {c}".replace(" ,", ",")


def resized(photo, dest, width):
    """The photo at a page-sized width (a 1400 px original is 400-600 KB). Falls back to the original."""
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(photo), "-vf", f"scale='min({width},iw)':-2", "-q:v", "4", str(dest)],
                       check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        shutil.copy(photo, dest)


def article_ld(p, image):
    # Fields follow Google's Article structured data: https://developers.google.com/search/docs/appearance/structured-data/article
    # (headline kept under the ~110 characters it recommends; author and publisher are the Organization, not a person)
    url = f"{SITE}/s/{p['id']}/"
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "mainEntityOfPage": {"@type": "WebPage", "@id": url},
          "headline": clip(p["headlines"][0], 110), "description": p.get("dek", ""),
          "image": [ORIGIN + (image or DEFAULT_OG)], "datePublished": iso(p["published"]), "dateModified": iso(p["published"]),
          "articleSection": topic(p), "inLanguage": "en", "isAccessibleForFree": True,
          "author": {"@type": "Organization", "name": NAME, "url": SITE + "/about/"},
          "publisher": seo.organization(SITE, NAME, accounts())}
    if p.get("company"):
        ld["about"] = {"@type": "Organization", "name": p["company"]}
    return ld


def seat_list(p):
    """[(newsroom, url or None)]: one seat per newsroom the article names, linked when the article URLs hold a link to it.
    The meter, the count in the byline and this list all come from the same names, so they always agree."""
    links = {o.lower(): u for o, u in outlets.source_mix(p)}
    return [(n, links.get(n.lower())) for n in outlets.newsrooms(p)]


# Words that say nothing about what a story is about; the rest of a headline and summary is what two stories can share.
_COMMON = {"about", "after", "ahead", "amid", "announces", "before", "could", "from", "have", "into", "more", "other", "over", "says", "than", "that",
           "their", "there", "these", "this", "those", "were", "which", "while", "will", "with", "would", "year", "years", "percent", "first", "second",
           "week", "weeks", "month", "months", "report", "reports", "reported", "plans", "plan", "new", "says", "said", "also", "since", "under"}


def _topic_words(p):
    """The words a story is about: its capitalised names and its longer plain words, lower-cased, from the headline and summary."""
    text = f'{p["headlines"][0]} {p.get("dek", "")}'
    names = {w.lower() for w in re.findall(r"\b[A-Z][A-Za-z0-9&]{2,}", text[1:]) if w.lower() not in _COMMON}
    plain = {w for w in re.findall(r"[a-z]{6,}", text.lower()) if w not in _COMMON}
    return {w.removesuffix("'s") for w in names | plain}


def related(p, rows, n=3, exclude=()):
    """Stories that are about the same thing, closest first: the same company, then the names and words the two share. A story the page
    already links as Older or Newer is not repeated, and a story that shares nothing with this one is not "related": no related
    list is better than the latest items of the section under that heading."""
    skip = {id(o) for o in exclude} | {id(p)}
    mine = _topic_words(p)
    scored = []
    for o in rows:
        if id(o) in skip:
            continue
        same_co = bool(co_of(p)) and co_of(o).lower() == co_of(p).lower()
        shared = len(mine & _topic_words(o))
        if not same_co and shared < 2:
            continue
        scored.append((6 * same_co + shared + (0.5 if topic(o) == topic(p) else 0), o["published"], o))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [o for _, _, o in scored[:n]]


def co_of(p):
    """The company a article is about: the tagged company, else the first logo name the headline carries."""
    return ((p.get("company") or "").strip() or next((n for n in p.get("logo_names") or [] if n), "")).strip()


def more_on(p, name, rows):
    """True when "More on <name>" leads somewhere: the name is in the text a reader sees on this page, and the search the link
    opens (headline, summary, company) finds at least two other articles."""
    n = name.lower()
    own = " ".join([p["headlines"][0], p.get("dek") or "", p.get("body") or ""]).lower()
    if n not in own:
        return False
    return sum(1 for o in rows if o is not p and n in " ".join([o["headlines"][0], o.get("dek") or "", o.get("company") or ""]).lower()) >= 2


def ticker_html(t):
    """"NASDAQ: NVDA" as a link to Google Finance; plain text for an exchange the desk has no Google code for.
    Never a price: the page names the listing and nothing else."""
    text = desk.R.T.entities.ticker_text(t)
    if not text:
        return ""
    url = desk.R.T.entities.google_finance_url(t)
    return (f'<a class="tk" href="{E(url)}" rel="nofollow noopener">{E(text)}</a>' if url
            else f'<span class="tk">{E(text)}</span>')


def ticker_of(p):
    """The post's ticker, only while it still belongs to the company the page names."""
    return p.get("ticker") if p.get("company") and p.get("company") == co_of(p) else None


def co_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def companies(rows, minimum=2):
    """{slug: (name, [stories newest first])} for companies with at least `minimum` articles. rows is newest first."""
    by_slug, names = {}, {}
    for p in rows:
        n = co_of(p)
        if n and co_slug(n):
            by_slug.setdefault(co_slug(n), []).append(p)
            names.setdefault(co_slug(n), n)
    return {k: (names[k], v) for k, v in by_slug.items() if len(v) >= minimum}


def feeds_scanned():
    """Working feeds in sources.json: the count the desk fetches every run."""
    try:
        return len(json.loads((desk.HERE / "sources.json").read_text()).get("working", []))
    except (OSError, ValueError):
        return 0


def desk_counts(rows):
    """Live figures for the how-it-works page and the per-story panel, from what is on the site now."""
    rooms = {o.lower() for p in rows for o in outlets.newsrooms(p)}
    return {"feeds": feeds_scanned(), "newsrooms": len(rooms), "stories": len(rows),
            "three_plus": sum(1 for p in rows if coverage(p) >= 3), "companies": len(companies(rows, 1)),
            "photos": sum(1 for p in rows if p.get("credit"))}


def figure_stated(p):
    """The post's figure, when the headline or the dek states it; else "". A figure the text does not state is never set large."""
    fig = (p.get("figure") or "").strip()
    return fig if fig and any(desk._in_text(fig, t) for t in (p["headlines"][0], p.get("dek") or "")) else ""


def number_box(p):
    """"The number": the figure the post carries, set large with the dek sentence that states it. Not when the headline
    already carries it (the box would only repeat the headline), and never a figure the text does not state."""
    fig = (p.get("figure") or "").strip()
    if not fig or desk._in_text(fig, p["headlines"][0]):
        return ""
    dek = p.get("dek") or ""
    if desk._in_text(fig, dek):
        return (f'<aside class="numbox" aria-labelledby="nb"><h2 id="nb">The number</h2><p class="big">{E(fig)}</p>'
                f'<p class="ncap">{E(dek)}</p></aside>')
    return ""


def how_made(p, counts):
    """The per-story panel: what the desk read and which fixed checks the text passed. Every published article has
    passed them (copy.verify and desk.audit run before a post is queued and again before it is published)."""
    rooms = outlets.newsrooms(p)
    fig = (p.get("figure") or "").strip()
    checks = ["Numbers: every number in the text appears in the source text."
              + (f" The figure {fig} is stated in the text." if figure_stated(p) else ""),
              "Names: each sentence is compared with the source text; a sentence whose words are mostly missing from it is rejected.",
              "Photo licence: " + ("the licence allows reuse and the credit line is shown." if p.get("credit") else "this article has no photo."),
              "Audit: topic, photo, hashtag and stock-phrase checks passed."]
    return (f'<details class="made"><summary>How this article was made</summary><div class="made-body">'
            f'<p>An AI model wrote it from the text of {len(rooms)} newsroom{"" if len(rooms) == 1 else "s"} and had no other input. '
            f'Fixed code checked it before it went up.</p>'
            f'<dl><dt>Feeds scanned</dt><dd>{counts["feeds"]} feeds, every 30 minutes</dd>'
            f'<dt>Newsrooms used</dt><dd>{E(", ".join(rooms)) or "none listed"}</dd>'
            f'<dt>Checks passed</dt><dd><ul>{"".join(f"<li>{E(c)}</li>" for c in checks)}</ul></dd></dl>'
            f'<p><a href="{BASE}/how-it-works/">How the desk works, with live counts</a></p></div></details>')


def story(p, rows, cos=None, counts=None):
    """One article page. rows is every shown article, newest first; cos is companies(rows)."""
    cos = companies(rows) if cos is None else cos
    counts = counts or desk_counts(rows)
    names = seat_list(p)
    linked = [f'<a href="{E(u)}" rel="nofollow noopener" target="_blank">{E(o)}</a>' if u else E(o) for o, u in names]
    outlets_line = (", ".join(linked[:-1]) + " and " + linked[-1]) if len(linked) > 1 else (linked[0] if linked else "")
    reported = (f'<span>Reported by {outlets_line}</span>' if outlets_line else "")
    insta = f'<p class="reported"><a href="{E(p["permalink"])}" rel="noopener" target="_blank">The post on Instagram &nearr;</a></p>' if p.get("permalink") else ""
    paras = "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or "").split("\n") if x.strip())
    alt = photo_alt(p)
    fig = (f'<figure>{pic(p, eager=True, ratio="16/9", alt=alt)}'
           f'<figcaption class="meta">{E(credit_line(p))}</figcaption></figure>') if p.get("_hires") else ""
    i = rows.index(p)
    newer, older = (rows[i - 1] if i > 0 else None), (rows[i + 1] if i + 1 < len(rows) else None)
    rel = related(p, rows, exclude=[o for o in (newer, older) if o])
    more = (f'<section class="related" aria-labelledby="rel"><h2 id="rel">Related news</h2><ul>'
            + "".join(f'<li><a href="{href(o)}"><span class="h-s">{E(o["headlines"][0])}</span>{meta(E(topic(o)), t_tag(o))}</a></li>' for o in rel) + "</ul></section>") if rel else ""
    nav = "".join(f'<a href="{href(o)}" rel="{r}"><span class="kick">{k}</span><span class="h-s">{E(o["headlines"][0])}</span></a>'
                  for o, r, k in ((older, "prev", "&larr; Older"), (newer, "next", "Newer &rarr;")) if o)
    prevnext = f'<nav class="prevnext{"" if older and newer else " one"}" aria-label="More news">{nav}</nav>' if nav else ""
    image = f"{BASE}/og/{p['id']}.jpg" if p.get("_og") else None
    name = co_of(p)
    company = ""
    if name:
        if co_slug(name) in cos:
            company = f'<span>About <a href="{BASE}/c/{co_slug(name)}/">{E(name)}</a></span>'
        elif more_on(p, name, rows):  # a search that finds nothing else is a dead end, and a name the text never uses is unexplained
            company = f'<span><a href="{BASE}/search/?q={urllib.parse.quote(name)}" rel="nofollow">More on {E(name)}</a></span>'
        if ticker_of(p):
            company += f"<span>{ticker_html(ticker_of(p))}</span>"
    ctx = markets.context_for(p, MARKETS, BASE)
    body = f"""<article class="art">
<header class="art-head"><a class="kick" href="{BASE}{topic_path(topic(p))}">{E(topic(p))}</a>
<h1>{E(p['headlines'][0])}</h1>{f'<p class="dek">{E(p["dek"])}</p>' if (p.get("dek") or "").strip() else ""}
<div class="byline">{reported}<span>Boardread desk, written by AI</span></div>
<div class="mt art-meta"><time datetime="{iso(p['published'])}">{when(p['published'])}</time><span>{cover(p)}</span>{company}</div></header>
{fig}
<div class="art-body">{f'<section class="happened" aria-labelledby="wh"><h2 id="wh" class="lab">What happened</h2><div class="body">{paras}</div></section>' if paras else ""}
<p class="disclose">Written by AI from the sources listed. Numbers are checked against the source text before publishing. <a href="{BASE}/standards/">How we work and how to report an error</a>.</p>
<div class="reportedby">{insta}</div>
{ctx}{number_box(p)}
<section class="sharebox"><h2 class="sh">Share</h2>{share_links(p)}</section>
{how_made(p, counts)}</div>
{more}{prevnext}</article>"""
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": NAME, "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": topic(p), "item": f"{SITE}{topic_path(topic(p))}"},
        {"@type": "ListItem", "position": 3, "name": clip(p["headlines"][0], 110)}]}
    # no dek: the first sentence of the report, then the headline, so no page goes out without a description
    desc = (p.get("dek") or "").strip() or next((x for x in (p.get("body") or "").split("\n") if x.strip()), "") or p["headlines"][0]
    return page(f'{p["headlines"][0]} · boardread.', body, desc, f"/s/{p['id']}/", image, "article",
                [article_ld(p, image), crumbs], p["headlines"][0], active=topic(p).lower())


# ---------------------------------------------------------------- feeds

def rss(title, link, items, self_path="/feed.xml"):
    """items: (title, url, pubDate, description, extra) where extra may carry category, image (site path) and image_bytes."""
    def one(t, u, d, desc, extra):
        pic_ = extra.get("image")
        return (f'<item><title>{E(t)}</title><link>{E(u)}</link><guid isPermaLink="true">{E(u)}</guid><pubDate>{d}</pubDate>'
                f"<description>{E(desc)}</description>"
                + (f"<category>{E(extra['category'])}</category>" if extra.get("category") else "")
                + f"<dc:creator>{NAME}</dc:creator>"
                + (f'<enclosure url="{E(ORIGIN + pic_)}" length="{extra.get("image_bytes", 0)}" type="image/jpeg"/>'
                   f'<media:content url="{E(ORIGIN + pic_)}" medium="image" type="image/jpeg" width="{OG_W}" height="{OG_H}"/>' if pic_ else "")
                + "</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:media="http://search.yahoo.com/mrss/" xmlns:atom="http://www.w3.org/2005/Atom">'
            f'<channel><title>{E(title)}</title><link>{E(link)}</link><description>{TAGLINE}</description>'
            f'<atom:link href="{E(SITE + self_path)}" rel="self" type="application/rss+xml"/>'
            f"<language>en</language><lastBuildDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>"
            f"{''.join(one(*i) for i in items)}</channel></rss>")


def urlset(rows):
    """Sitemap protocol: https://www.sitemaps.org/protocol.html"""
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{E(u)}</loc><lastmod>{m}</lastmod></url>" for u, m in rows) + "</urlset>")


def news_sitemap(rows, now):
    """Google News sitemap, only articles from the last 48 hours:
    https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap"""
    recent = [p for p in rows if now - dt(p["published"]) <= timedelta(hours=48)]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
            + "".join(f"<url><loc>{E(f'{SITE}/s/{p['id']}/')}</loc><news:news><news:publication><news:name>{NAME}</news:name>"
                      f"<news:language>en</news:language></news:publication><news:publication_date>{iso(p['published'])}</news:publication_date>"
                      f"<news:title>{E(p['headlines'][0])}</news:title></news:news></url>" for p in recent)
            + "</urlset>")


def search_index(rows):
    return json.dumps([{"headline": p["headlines"][0], "dek": p.get("dek", ""), "topic": topic(p), "date": iso(p["published"]),
                        "url": href(p), "company": p.get("company", ""), "sources": ", ".join(p.get("sources") or [])}
                       for p in rows], ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- static pages

def contact_lines():
    mail = desk.CONFIG.get("contact_email")
    parts = [f'<li>By email: <a href="mailto:{E(mail)}">{E(mail)}</a></li>'] if mail else []
    parts.append(f'<li>Corrections and tips in public: <a href="{CONTACT_ISSUES}" rel="noopener">open an issue on GitHub</a>.</li>')
    parts += [f'<li>Direct message on <a href="{E(a["url"])}" rel="me noopener">{E(a["name"])}</a>.</li>'
              for a in accounts() if a["name"] in ("Instagram", "Bluesky", "Telegram")]
    return "".join(parts)


def about_page():
    return pagehead("About Boardread", "The news that moves business, written by an automated desk, with every source linked.") + f"""<div class="prose">
<p>Boardread reports what moves business: markets, the economy, politics, world affairs, technology and AI. It is written for consultants, managers and business students who need the day's developments in a minute, and want to open the original reporting when it matters.</p>
<h2>How the desk works</h2>
<ol class="steps">
<li><div><b>It reads the news.</b> Every 30 minutes the desk fetches {feeds_scanned()} feeds from newsrooms and research labs.</div></li>
<li><div><b>It ranks.</b> Coverage of the same event is grouped into one article and scored. Only articles above a fixed importance bar, and under a day old, are taken further.</div></li>
<li><div><b>It writes.</b> An AI model writes a short report from the text of the sources. It has no other input and no tools.</div></li>
<li><div><b>It checks.</b> Fixed code checks the text before anything is public: every number must appear in the source, sentences that read as commentary are rejected, and articles about deaths, violence and abuse are skipped.</div></li>
<li><div><b>It publishes with the sources.</b> Each article names the newsrooms it draws on and links to them. Photos are licensed images with their credit shown.</div></li>
</ol>
<h2>Limits</h2>
<p>Boardread does no original reporting. It summarises what named newsrooms have reported, and says which ones. Read the linked source for the full report. Opinion and speculation are not published.</p>
<h2>Follow</h2>
<p>The business news goes out on <a href="{BASE}/feed.xml">RSS</a> (the latest 50, no Sport){"".join(f', <a href="{E(a["url"])}" rel="me noopener">{E(a["name"])}</a>' for a in accounts())}. Sport has <a href="{BASE}/sport/feed.xml">its own feed</a>, and so does every section and company.</p>
<p>See the <a href="{BASE}/standards/">editorial standards and corrections policy</a>, the <a href="{BASE}/contact/">contact page</a> and the <a href="{LEGAL['impressum']}">Impressum</a>.</p>
</div>"""


def standards_page():
    return pagehead("Editorial standards and corrections", "What a Boardread article promises, and what happens when it is wrong.") + f"""<div class="prose">
<h2>Standards</h2>
<ul>
<li><b>Sources are named and linked.</b> Every article lists the newsrooms it draws on, each with a link to the original.</li>
<li><b>AI writes, code checks.</b> Articles are written by an AI model from the source text. Numbers must appear in the source; commentary is rejected before publishing. The disclosure "Written by AI from the sources listed" appears on every article.</li>
<li><b>No original reporting.</b> Boardread summarises named reporting. It does not use anonymous sources of its own.</li>
<li><b>Photos are credited.</b> Images are licensed, and the credit line sits under the picture. A photo illustrates the topic and may not show the event.</li>
<li><b>Times are UTC.</b> Each article shows when it was published.</li>
<li><b>Topics we skip.</b> Articles centred on deaths, violence, abuse and similar subjects are not published by the desk.</li>
</ul>
<h2>Corrections</h2>
<p>If an article misstates a fact, a name or a number, tell us with the link to the article and the correct information. The first thing checked is the source: if the source says something different from the article, the article is wrong and is corrected or withdrawn. If the source itself was corrected, the article follows it.</p>
<ul>{contact_lines()}</ul>
<h2>Who is responsible</h2>
<p>The operator named in the <a href="{LEGAL['impressum']}">Impressum</a> is responsible for the site, including the output of its automated desk.</p>
</div>"""


def contact_page():
    return pagehead("Contact", "Corrections, tips and questions.") + f"""<div class="prose">
<p>Include the link to the article you are writing about. Corrections are read first.</p>
<ul>{contact_lines()}</ul>
<p>The operator's details are in the <a href="{LEGAL['impressum']}">Impressum</a>.</p>
</div>"""


def search_page():
    return pagehead("Search", "Search Boardread.") + f"""<div class="searchwrap">
<form class="sbox" role="search" action="{BASE}/search/" method="get" data-index="{BASE}/search.json">
<input type="search" name="q" id="q" placeholder="Search the news" aria-label="Search the news" autocomplete="off" autofocus>
<button type="submit">Search</button></form>
<p class="meta" id="sstatus" role="status" aria-live="polite"></p>
<ol class="hits" id="hits"></ol>
<noscript><p class="empty">Search needs JavaScript. Browse the <a href="{BASE}/latest/">latest articles</a> or the <a href="{BASE}/archive/">archive</a> instead.</p></noscript>
</div>"""


def not_found():
    return pagehead("Page not found") + f"""<div class="prose"><ul class="gl">
<li><a href="{BASE}/">Front page</a></li><li><a href="{BASE}/latest/">Latest</a></li><li><a href="{BASE}/search/">Search</a></li></ul></div>"""


# ---------------------------------------------------------------- build

def put(out, path, html_):
    d = out / path.strip("/")
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html_)


def paged(out, path, rows, title, desc, head, active, aside="", sitemap=None, feed=None):
    """A listing at path, one page per PER articles: path, path/page/2/, ..."""
    total = max(1, -(-len(rows) // PER))
    for n in range(1, total + 1):
        here = path if n == 1 else f"{path}page/{n}/"
        rel = {}
        if n > 1:
            rel["prev"] = path if n == 2 else f"{path}page/{n - 1}/"
        if n < total:
            rel["next"] = f"{path}page/{n + 1}/"
        put(out, here, page(title + (f" · page {n}" if n > 1 else "") + " · boardread.",
                            head + listing(rows[(n - 1) * PER:n * PER], path, n, total, aside if n == 1 else ""),
                            desc, here, active=active, rel=rel, feed=feed))
        if sitemap is not None and rows:
            sitemap.append((SITE + here, iso(max(p["published"] for p in rows))))


def window(rows, hours=24):
    """Articles within `hours` of the newest one: what "today" means on a site that may be a few hours stale."""
    if not rows:
        return []
    top = dt(rows[0]["published"])
    return [p for p in rows if top - dt(p["published"]) <= timedelta(hours=hours)]


def by_score(rows):
    return sorted(rows, key=lambda p: (p.get("score", 0), p["published"]), reverse=True)


def most_covered(rows, n=5):
    """[(name, slug, articles)] companies ranked by articles in the 7 days up to the newest article, ties by newsrooms behind them."""
    if not rows:
        return []
    top = dt(rows[0]["published"])
    tally = {}
    for p in rows:
        if top - dt(p["published"]) <= timedelta(days=7) and co_of(p):
            name, slug = co_of(p), co_slug(co_of(p))
            c = tally.setdefault(slug, [name, 0, 0])
            c[1] += 1
            c[2] += coverage(p)
    return [(c[0], k, c[1]) for k, c in sorted(tally.items(), key=lambda kv: (-kv[1][1], -kv[1][2], kv[1][0]))[:n]]


def covered_list(rows, cos, n=5):
    """The ranking as an ordered list; a company with a page links to it, one without to the search. Only companies named by
    two or more articles count, and the module is left out until three companies qualify: a ranking of ones ranks nothing."""
    ranking = [(name, slug, k) for name, slug, k in most_covered(rows, max(n, 50)) if k >= 2][:n]
    if len(ranking) < 3:
        return ""
    out = []
    for i, (name, slug, k) in enumerate(ranking, 1):
        link = f"{BASE}/c/{slug}/" if slug in cos else f"{BASE}/search/?q={urllib.parse.quote(name)}"
        nofollow = "" if slug in cos else ' rel="nofollow"'
        out.append(f'<li><span class="n" aria-hidden="true">{i}</span><a href="{link}"{nofollow}><span class="h-s">{E(name)}</span>'
                   f'{meta(f"{k} articles this week")}</a></li>')
    return f'<ol class="rank">{"".join(out)}</ol>'


def most_covered_block(shown, cos, n=5):
    lst = covered_list(shown, cos, n)
    return (f'<div class="covered">{sec_head("Most covered this week", f"{BASE}/week/", "All", level=3)}{lst}</div>') if lst else ""


from . import views  # noqa: E402 (imports this module, so only once it is loaded)


def build(out=desk.HERE / "_site"):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    for d in ("img", "og", "assets"):
        (out / d).mkdir(parents=True)
    shutil.copytree(ASSETS / "fonts", out / "fonts")  # Libre Franklin and its OFL licence
    for f in ASSET_FILES:
        if (ASSETS / f).exists():
            shutil.copy(ASSETS / f, out / "assets" / f)
    shutil.copy(ASSETS / "words.txt", out / "assets" / "words.txt")  # the guess list of the word game
    shutil.copy(ASSETS / "words-NOTICE.txt", out / "assets" / "words-NOTICE.txt")
    for f in ("og-default.png", "logo.png", "icon.svg", "favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png"):  # the preview image of every non-story page, the publisher logo, the favicon
        shutil.copy(ASSETS / f, out / f)
    for f in ASSETS.glob("google*.html"):  # Search Console ownership files; they must stay for the property to stay verified
        shutil.copy(f, out / f.name)
    from . import indexnow
    shutil.copy(ASSETS / f"{indexnow.KEY}.txt", out / f"{indexnow.KEY}.txt")  # proves the IndexNow key belongs to this host
    if (ASSETS / "CNAME").exists():  # the custom domain GitHub Pages serves this site under; added at the cut-over
        shutil.copy(ASSETS / "CNAME", out / "CNAME")
    shown = []
    PHOTOS.clear()
    for p in published():
        photo = desk.MEDIA / p["id"] / "photo.jpg"
        if photo.exists():
            resized(photo, out / "img" / f"{p['id']}.jpg", 960)
            resized(photo, out / "img" / f"{p['id']}-t.jpg", 480)  # not thumb.jpg: that one is a crop of the Instagram card, text included
            big, small = out / "img" / f"{p['id']}.jpg", out / "img" / f"{p['id']}-t.jpg"
            at, is_face = focus.for_post(p, photo)
            PHOTOS[p["id"]] = {"dim": focus.jpeg_size(big) or (960, 640), "dim_t": focus.jpeg_size(small) or (480, 320), "focus": at, "face": is_face}
            p["_hires"] = p["_thumb"] = True
        # no photo: the story is a text row. media/<id>/thumb.jpg is a crop of the Instagram card with the headline
        # set into it, so it is never used as a picture on the site (it showed "Global stocks" in a tile)
        shown.append(p)  # a article without any picture still has a page: text is the story
    # every story gets a card: the photo-less ones carry the same headline and meter, so a shared link is never the generic image
    def card(p):
        photo = out / "img" / f"{p['id']}.jpg"  # the photo as the site shows it, so a shared card looks like the site
        photo = photo if photo.exists() else None
        dest = out / "og" / f"{p['id']}.jpg"
        m = PHOTOS.get(p["id"], {})
        return share_card(p, photo, dest) or bool(photo and og_image(photo, dest, m.get("focus"), m.get("dim")))
    with ThreadPoolExecutor(max_workers=6) as pool:
        for p, ok in zip(shown, pool.map(card, shown)):
            if ok:
                p["_og"] = True
    global MARKETS
    # DESK_SITE_OFFLINE=1 builds from the last good copy of the rates without touching the network (tests, a plane)
    MARKETS = markets.load(live=os.environ.get("DESK_SITE_OFFLINE") != "1")
    coins = markets.crypto() if os.environ.get("DESK_SITE_OFFLINE") != "1" else None
    if coins:  # read at build time for this build only; never written to state (see markets.CMC_URL)
        MARKETS = {**(MARKETS or {"series": {}}), "crypto": coins}
    sm = []
    # Business stays the core: the front page, Latest, the brief, the feeds and every view are made from `news`; sport has
    # its own block on the front page, its own section page and feed, and appears in the archive, search and sitemap.
    news = [p for p in shown if not is_sport(p)]
    sport = [p for p in shown if is_sport(p)]
    desc = "Markets, economy, politics, world, tech and AI: every article with its sources."
    if news:
        site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": SITE + "/", "inLanguage": "en",
                   "potentialAction": {"@type": "SearchAction", "target": f"{SITE}/search/?q={{search_term_string}}", "query-input": "required name=search_term_string"},
                   "publisher": seo.organization(SITE, NAME, accounts())}
        put(out, "/", page(f"boardread. · {TAGLINE}", views.front(news, companies(news), MARKETS, sport), desc, "/", ld=site_ld, front=True))
    else:
        put(out, "/", page(f"boardread. · {TAGLINE}", '<div class="empty">The first articles are on their way.</div>', desc, "/", front=True))
    sm.append((SITE + "/", iso(shown[0]["published"]) if shown else None))
    top5 = lambda rows: ranked(by_score(window(rows))[:5], 5)  # noqa: E731
    aside = lambda rows: (sec_head("Most important", level=2) + top5(rows)) if len(rows) > 3 else ""  # noqa: E731
    paged(out, "/latest/", news, "Latest", desc, pagehead("Latest", "Business, newest first. Sport has its own page."), "latest", aside(news), sm)
    for t in TOPIC_ORDER:
        rows = [p for p in shown if topic(p) == t]
        paged(out, topic_path(t), rows, t, TOPICS[t], pagehead(t, TOPICS[t]), t.lower(), aside(rows), sm,
              feed=(f"boardread. {t}", f"{topic_path(t)}feed.xml"))
    cos, counts = companies(news), desk_counts(shown)
    for p in shown:
        put(out, f"/s/{p['id']}/", story(p, sport if is_sport(p) else news, cos, counts))
        sm.append((f"{SITE}/s/{p['id']}/", iso(p["published"])))
    days = {}
    for p in shown:
        days.setdefault(day_of(p["published"]), []).append(p)
    put(out, "/archive/", page("Archive · boardread.", pagehead("Archive", "Every day of Boardread, newest first.") + '<div class="prose days">'
        + "".join(f'<a href="{BASE}/archive/{d}/">{day_label(d)}<span>{len(ps)} {"article" if len(ps) == 1 else "articles"}</span></a>' for d, ps in days.items())
        + "</div>", "Every day of Boardread.", "/archive/"))
    sm.append((SITE + "/archive/", iso(shown[0]["published"]) if shown else None))
    for d, ps in days.items():
        paged(out, f"/archive/{d}/", ps, day_label(d), f"Boardread articles of {day_label(d)}.", pagehead(day_label(d), f"{len(ps)} articles, newest first."), "", "", sm)
    # weeks: one page per ISO week (the newsletter's issues), and /week/ for the last seven days
    weeks = {}
    for p in news:
        weeks.setdefault(week_of(p["published"]), []).append(p)
    this_week = datetime.now(timezone.utc).strftime("%G-W%V")
    wdesc = "The week's ten leading articles."

    def top_list(rows, heading, sub, active):
        body = pagehead(heading, sub) + (f'<div class="prose" style="max-width:50rem">{ranked(rows, 10)}</div>' if rows
                                         else '<div class="empty">The week has just begun.</div>')
        return body

    issues = []
    for wk in sorted(weeks, reverse=True):
        top = sorted(weeks[wk], key=shared, reverse=True)[:10]
        put(out, f"/week/{wk}/", page(f"Top 10 · {wk} · boardread.", top_list(top, "Top 10", f"Week {wk[-2:]}, {wk[:4]}. Ranked by shares and saves, then news value.", "week"),
                                      wdesc, f"/week/{wk}/", active="week"))
        sm.append((f"{SITE}/week/{wk}/", iso(max(p["published"] for p in weeks[wk]))))
        if wk != this_week:  # an unfinished week is not an issue yet
            issues.append((wk, top))
    last7 = [p for p in news if datetime.now(timezone.utc) - dt(p["published"]) <= timedelta(days=7)] or news[:10]
    span = (f'{dt(last7[-1]["published"]).strftime("%-d %b")} to {dt(last7[0]["published"]).strftime("%-d %b")}' if last7 else "")
    past = "".join(f'<li><a href="{BASE}/week/{w}/">Week {w[-2:]}, {w[:4]}</a></li>' for w in sorted(weeks, reverse=True) if w != this_week)
    mc = covered_list(news, companies(news), 10)
    put(out, "/week/", page("This week · boardread.", top_list(sorted(last7, key=lambda p: (views.front_score(p), p["published"]), reverse=True)[:10], "This week",
                                                                       f"The ten leading articles, {span}, by news value.", "week")
        + (f'<div class="prose" style="max-width:50rem"><h2>Most covered this week</h2><p>Companies ranked by how many articles named them in the last seven days.</p>{mc}</div>' if mc else "")
        + (f'<div class="prose"><h2>Past weeks</h2><ul>{past}</ul></div>' if past else ""), wdesc, "/week/", active="week"))
    sm.append((SITE + "/week/", iso(shown[0]["published"]) if shown else None))
    put(out, "/search/", page("Search · boardread.", search_page(), "Search every Boardread article.", "/search/", active="search", noindex=True))  # one page for every ?q=: not a page to index
    (out / "search.json").write_text(search_index(shown))
    for key, title, fn, d in (("about", "About", about_page, "What Boardread is and how the desk works."),
                              ("standards", "Editorial standards and corrections", standards_page, "What a Boardread article promises and how corrections work."),
                              ("contact", "Contact", contact_page, "Corrections, tips and questions.")):
        put(out, f"/{key}/", page(f"{title} · boardread.", fn(), d, f"/{key}/"))
        sm.append((f"{SITE}/{key}/", iso(shown[0]["published"]) if shown else None))
    (out / "404.html").write_text(page("Page not found · boardread.", not_found(), "The page you asked for is not here. Start from the front page or search.", "/404.html", noindex=True))
    (out / "feed.xml").write_text(rss("boardread", SITE + "/", [
        (p["headlines"][0], f"{SITE}/s/{p['id']}/", format_datetime(dt(p["published"])), p.get("dek", ""),
         {"category": topic(p), "image": f"{BASE}/og/{p['id']}.jpg" if p.get("_og") else None,
          "image_bytes": (out / "og" / f"{p['id']}.jpg").stat().st_size if p.get("_og") else 0})
        for p in news[:50]]))
    # an empty channel is no feed: until the first week has finished, the running week's top ten is the one item
    weekly = issues[:12] or [(wk, sorted(weeks[wk], key=shared, reverse=True)[:10]) for wk in sorted(weeks, reverse=True)[:1]]
    (out / "weekly.xml").write_text(rss("boardread weekly", SITE + "/week/", [
        (f"Top 10 · {wk}{'' if wk != this_week else ', so far'}: {top[0]['headlines'][0]}", f"{SITE}/week/{wk}/",
         format_datetime(dt(top[0]["published"]) + (timedelta(days=1) if wk != this_week else timedelta())),
         " · ".join(p["headlines"][0] for p in top), {"category": "Weekly"}) for wk, top in weekly], self_path="/weekly.xml"))
    from . import sitepages  # imports this module, so only once it is loaded
    sitepages.build(out, news, sm, cos, everything=shown)
    sitepages.feed_for(out, sport, "/sport/", "boardread. Sport", f"{SITE}/sport/")
    (out / "sitemap.xml").write_text(urlset([(u, m) for u, m in sm if m]))
    (out / "news-sitemap.xml").write_text(news_sitemap(shown, datetime.now(timezone.utc)))
    (out / "manifest.webmanifest").write_text(json.dumps({"name": "Boardread", "short_name": "Boardread", "description": TAGLINE, "start_url": BASE + "/", "scope": BASE + "/",
        "display": "browser", "background_color": "#ffffff", "theme_color": "#ffffff",
        "icons": [{"src": f"{BASE}/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": f"{BASE}/icon-512.png", "sizes": "512x512", "type": "image/png"}]}))
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\nSitemap: {SITE}/news-sitemap.xml\n")
    (out / ".nojekyll").write_text("")
    print(f"site: {len(shown)} articles, {len(weeks)} weeks -> {out}")
    return out


def redirects(out, old_base="/news"):
    """Stubs for the old home of the site (keremozdemir.de/news/...), to be served from the main site's repository
    after the cut-over: every article, topic and week page, plus the front page, sends the reader to the new address
    with a meta refresh, a canonical link and a script. Feeds cannot be redirected this way and are not stubbed."""
    out = Path(out)
    paths = ["/", "/latest/", "/week/", "/search/", "/about/", "/archive/"] + [topic_path(t) for t in TOPIC_ORDER]
    paths += [f"/s/{p['id']}/" for p in published()] + [f"/week/{w}/" for w in {week_of(p["published"]) for p in published()}]
    for path in paths:
        new = f"{SITE}{path}"
        d = out / (old_base.strip("/") + path).strip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Boardread has moved</title>'
            f'<meta name="robots" content="noindex"><link rel="canonical" href="{E(new)}">'
            f'<meta http-equiv="refresh" content="0; url={E(new)}"></head><body><p>Boardread has moved to '
            f'<a href="{E(new)}">{E(new)}</a>.</p></body></html>')
    print(f"redirects: {len(paths)} stubs -> {out}")
    return out
