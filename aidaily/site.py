"""Boardread's news site, built from the committed posts after every run.

Static files only. Scripts are two small vanilla files (copy link, search); no third-party requests: photos are
copied in from the media branch and fonts are self-hosted, so a reader's browser talks to one origin.
Every post that reached a channel appears: published on Instagram, or web tier (status "web").

Where it is served comes from desk.json "site_url". A bare origin (https://boardread.news) puts everything at /;
an origin with a path (https://keremozdemir.de/news) puts everything under that path. One value, no other switch.

  /                      front page: lead, latest, most important, one block per topic, this week, follow
  /latest/               every story, newest first, paged        /latest/page/<n>/
  /t/<topic>/            one topic, paged
  /s/<id>/               one story: photo, report, sources, share, related, previous and next
  /week/                 the last seven days, ranked            /week/<YYYY-Www>/  one finished ISO week
  /archive/              one page per day                       /archive/<YYYY-MM-DD>/
  /search/               client-side search over /search.json
  /about/ /standards/ /contact/ /404.html   (Impressum and Privacy are keremozdemir.de's, same operator)
  /feed.xml /weekly.xml /sitemap.xml /news-sitemap.xml /robots.txt
  /og/<id>.jpg           the 1200x630 link-preview image of a story, cut from its photo at build time
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

from . import desk, outlets

E = lambda s: html.escape(s or "", quote=True)  # noqa: E731
# DESK_SITE_URL builds the same pages for another address (a local preview, a staging host) without touching desk.json
SITE = (os.environ.get("DESK_SITE_URL") or desk.CONFIG["site_url"]).rstrip("/")
BASE = "/" + SITE.split("/", 3)[3] if SITE.count("/") >= 3 else ""
ORIGIN = "/".join(SITE.split("/")[:3])
NAME = "Boardread"
TAGLINE = "The news that moves business"
ASSETS = Path(__file__).resolve().parent.parent / "assets-site"
OG_W, OG_H = 1200, 630
PER = 20  # stories on one listing page
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
}
TOPIC_ORDER = list(TOPICS)
# Same operator as keremozdemir.de, whose Impressum and Privacy pages are the legal notice of this site too.
LEGAL = {"impressum": "https://keremozdemir.de/impressum/", "privacy": "https://keremozdemir.de/privacy/"}
CONTACT_ISSUES = "https://github.com/Keremozdemirra/news/issues"


def published():
    """Posts live on the site: published on Instagram or published to the web tier. Nothing on a page may say
    which one it was, except the Instagram link a post carries only when it has a permalink."""
    rows = [p for p, _ in desk.posts() if p.get("status") in ("published", "web") and p.get("published") and p.get("kind") != "story"]
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


def day_label(day):
    return datetime.strptime(day, "%Y-%m-%d").strftime("%-d %B %Y")


def week_of(iso):
    return dt(iso).strftime("%G-W%V")


def iso(s):
    return dt(s).strftime("%Y-%m-%dT%H:%M:%SZ")


def shared(p):
    i = p.get("insights") or {}
    # shares and saves say a reader found it worth keeping; before the weekly numbers arrive, rank decides
    return ((i.get("shares") or 0) + (i.get("saved") or 0), p.get("score", 0))


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


ASSET_V = hashlib.sha1(b"".join((ASSETS / f).read_bytes() for f in ("site.css", "site.js"))).hexdigest()[:8]
FACES = (
    "@font-face{font-family:'Libre Franklin';font-weight:400;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-400.woff2') format('woff2')}"
    "@font-face{font-family:'Libre Franklin';font-weight:500;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-500.woff2') format('woff2')}"
    "@font-face{font-family:'Libre Franklin';font-weight:600;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-600.woff2') format('woff2')}"
    "@font-face{font-family:'Libre Franklin';font-weight:800;font-style:normal;font-display:swap;src:url('{b}/fonts/LibreFranklin-800.woff2') format('woff2')}"
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
# a trademark redrawn from memory comes out subtly wrong, so the letterform ones spell the destination and the rest are
# generic shapes. x, linkedin and copy are that site's drawings (src/components/icon.tsx), path data unchanged.
SQ = '<rect x="1.6" y="1.6" width="12.8" height="12.8" rx="2.4"/>'
MARKS = {
    "x": SQ + '<path d="M5.2 5.2 10.8 10.8M10.8 5.2 5.2 10.8"/>',
    "linkedin": SQ + '<path d="M5 6.6v4.2M5 4.5v.1"/><path d="M8.2 10.8V6.6M8.2 8.2c0-1 .8-1.6 1.6-1.6s1.4.6 1.4 1.7v2.5"/>',
    "copy": '<rect x="5.6" y="5.6" width="8.8" height="8.8" rx="1.3"/><path d="M10.9 3.2a1.4 1.4 0 0 0-1.3-1.1H3a1.4 1.4 0 0 0-1.4 1.4v6.6c0 .6.4 1.2 1.1 1.3"/>',
    "check": '<path d="m3 8.4 3.4 3.4L13 5.2"/>',
    # the letters "Ig": a stroke, and a g with its tail
    "instagram": SQ + '<path d="M5 6.4v4.2M5 4.6v.1"/><circle cx="9.4" cy="8.2" r="1.7"/><path d="M11.1 6.6v4.2c0 .9-.7 1.4-1.6 1.4"/>',
    "threads": SQ + '<path d="M5 5.4h6M8 5.4v5.6"/>',
    "bluesky": SQ + '<path d="M6 3.8v8.4"/><path d="M6 9.4c0-1.4 1-2.4 2.3-2.4s2.2 1 2.2 2.4-1 2.4-2.2 2.4S6 10.8 6 9.4z"/>',
    "facebook": SQ + '<path d="M9.2 13.2V8.4M7.4 8.4h3.6M9.2 8.4V6.2c0-1 .6-1.6 1.7-1.6"/>',
    # a paper plane, as plain as the thing itself
    "telegram": '<path d="M14.2 2.2 1.8 7l4 1.6 1.2 4.4 2.3-2.7 3.1 2.2z"/><path d="m5.8 8.6 8.4-6.4"/>',
    "rss": '<circle cx="3.6" cy="12.4" r=".9"/><path d="M2.6 7.6a5.8 5.8 0 0 1 5.8 5.8M2.6 2.8a10.6 10.6 0 0 1 10.6 10.6"/>',
    "whatsapp": '<path d="M8 1.9a6.1 6.1 0 0 0-5.2 9.2l-.8 3 3.1-.8A6.1 6.1 0 1 0 8 1.9z"/><path d="m5.6 6 .9 3.8 1.5-2.5 1.5 2.5.9-3.8"/>',
}


def mark(name):
    """The inline mark for a channel or action, decorative: the link around it carries the accessible name."""
    return (f'<svg class="mk" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{MARKS[name.lower()]}</svg>') if name.lower() in MARKS else ""


def chan(name, url, extra=""):
    """A link to one of our channels: the mark, the name (hidden from sight on phones, still read aloud) and what follows."""
    return (f'<a class="chan" href="{E(url)}" rel="me noopener" aria-label="{E(name)}">{mark(name)}<span class="t">{E(name)}</span>{extra}</a>')


def accounts():
    return [a for a in desk.CONFIG.get("accounts", []) if a.get("url")]


def nav_bar(active):
    items = [(f"{BASE}/latest/", "Latest", "latest"), (f"{BASE}/brief/", "Brief", "brief")] + [(f"{BASE}/t/{t.lower()}/", t, t.lower()) for t in TOPIC_ORDER] \
        + [(f"{BASE}/week/", "This week", "week")]
    links = "".join(f'<li><a href="{h}"{" aria-current=\"page\"" if active == k else ""}>{n}</a></li>' for h, n, k in items)
    return (f'<div class="sections"><div class="wrap"><nav aria-label="Sections"><ul>{links}</ul></nav>'
            f'<a class="find kick" href="{BASE}/search/"{" aria-current=\"page\"" if active == "search" else ""}>Search</a></div></div>')


def page(title, body, desc="", path="/", image=None, og_type="website", ld=None, og_title=None, active="", front=False,
         noindex=False, rel=None, main_class="", feed=None):
    """Every page. path is relative to the site root and becomes the canonical and og:url; image is the
    site-relative link-preview image (the shared default when a story has no photo). rel: {"prev": path, "next": path}."""
    url = SITE + path
    img = ORIGIN + (image or DEFAULT_OG)
    og_dims = f'<meta property="og:image:width" content="{OG_W}"><meta property="og:image:height" content="{OG_H}">\n' \
        if image in (None, DEFAULT_OG) or image.startswith(f"{BASE}/og/") else ""
    links = "".join(f'<link rel="{k}" href="{E(SITE + v)}">' for k, v in (rel or {}).items())
    # a topic or company page offers its own feed beside the site-wide one: feed = (title, path)
    own_feed = f'<link rel="alternate" type="application/rss+xml" title="{E(feed[0])}" href="{E(SITE + feed[1])}">\n' if feed else ""
    today = datetime.now(timezone.utc).strftime("%A %-d %B %Y")
    word = f'<a class="word" href="{BASE}/" aria-label="boardread. front page">boardread.</a>'
    mast = (f'<div class="mast"><h1 class="word"><a href="{BASE}/" aria-label="boardread. front page">boardread.</a></h1>'
            f'<p class="tag">{TAGLINE}</p></div>') if front else f'<div class="mast">{word}<p class="tag">{TAGLINE}</p></div>'
    foot_topics = "".join(f'<li><a href="{BASE}/t/{t.lower()}/">{t}</a></li>' for t in TOPIC_ORDER)
    follow_links = "".join(f'<li>{chan(a["name"], a["url"])}</li>' for a in accounts()) + f'<li><a class="chan" href="{BASE}/feed.xml" aria-label="RSS">{mark("rss")}<span class="t">RSS</span></a></li>'
    nl = desk.CONFIG.get("newsletter_url")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#0d0d0e" media="(prefers-color-scheme: dark)">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
{'<meta name="robots" content="noindex">' if noindex else '<meta name="robots" content="max-image-preview:large">'}
<link rel="canonical" href="{E(url)}">{links}
<link rel="icon" href="{BASE}/icon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="boardread." href="{BASE}/feed.xml">
{own_feed}<link rel="sitemap" type="application/xml" href="{BASE}/sitemap.xml">
<link rel="preload" href="{BASE}/fonts/LibreFranklin-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{BASE}/fonts/LibreFranklin-800.woff2" as="font" type="font/woff2" crossorigin>
<meta property="og:site_name" content="{NAME}"><meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(og_title or title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(url)}"><meta property="og:image" content="{E(img)}">
{og_dims}<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(og_title or title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{E(img)}">
{"".join(ld_json(x) for x in (ld if isinstance(ld, list) else [ld])) if ld else ""}
<style>{FACES}</style><link rel="stylesheet" href="{BASE}/assets/site.css?v={ASSET_V}">
<script src="{BASE}/assets/site.js?v={ASSET_V}" defer></script></head>
<body class="{'' if front else 'compact'}">
<a class="skip" href="#main">Skip to the news</a>
<header>
<div class="top"><div class="wrap"><span class="dates"><span class="dl">{today}</span><span class="ds">{datetime.now(timezone.utc).strftime("%-d %b %Y")}</span></span><nav aria-label="About Boardread"><a href="{BASE}/quiz/">Quiz</a><a href="{BASE}/about/">About</a><a href="{BASE}/standards/">Standards</a><a href="{BASE}/archive/">Archive</a><a href="{BASE}/feed.xml">RSS</a></nav>
<ul class="chans" aria-label="Boardread on other channels">{"".join(f'<li>{chan(a["name"], a["url"])}</li>' for a in accounts())}</ul></div></div>
<div class="wrap">{mast}</div>
{nav_bar(active)}
</header>
<main id="main" class="wrap {main_class}">{body}</main>
<footer class="foot"><div class="wrap">
<div class="foot-grid">
<div><a class="word" href="{BASE}/" aria-label="boardread. front page">boardread.</a><p>{TAGLINE}. Markets, economy, politics, world, tech and AI, every story with its sources linked.</p></div>
<div><h2>Sections</h2><ul>{foot_topics}</ul></div>
<div><h2>Boardread</h2><ul><li><a href="{BASE}/about/">About</a></li><li><a href="{BASE}/standards/">Standards and corrections</a></li><li><a href="{BASE}/contact/">Contact</a></li><li><a href="{BASE}/brief/">The brief</a></li><li><a href="{BASE}/quiz/">Quiz</a></li><li><a href="{BASE}/how-it-works/">How it works</a></li><li><a href="{BASE}/archive/">Archive</a></li><li><a href="{BASE}/feed.xml">RSS feed</a></li>{f'<li><a href="{E(nl)}">Newsletter</a></li>' if nl else ''}</ul></div>
<div><h2>Follow</h2><ul>{follow_links}</ul></div>
</div>
<div class="foot-base"><span>Written by AI from the sources listed. <a href="{BASE}/standards/">Corrections</a>. All times UTC.</span>
<span><button type="button" class="kbd-hint" data-keys hidden>Keyboard shortcuts</button> &middot; &copy; {datetime.now(timezone.utc).year} Boardread &middot; <a href="{LEGAL['impressum']}">Impressum</a> &middot; <a href="{LEGAL['privacy']}">Privacy</a></span></div>
</div></footer></body></html>"""


# ---------------------------------------------------------------- pieces

def pic(p, thumb=False, eager=False):
    """The photo in a 3:2 box. width and height give the box before the file arrives, so nothing shifts."""
    if not p.get("_thumb"):
        return ""
    src = f"{BASE}/img/{p['id']}-t.jpg" if thumb or not p.get("_hires") else f"{BASE}/img/{p['id']}.jpg"
    w, h = (480, 320) if thumb or not p.get("_hires") else (960, 640)
    load = 'fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
    return f'<span class="pic"><img src="{src}" width="{w}" height="{h}" alt="" {load}></span>'


def by(p):
    return E(", ".join(outlets.newsrooms(p)))


COVER_TICKS = 6  # the bar fills up to this many newsrooms; more than that is still "reported widely"


def coverage(p):
    """Distinct newsrooms behind a story, aggregators not counted."""
    return len(outlets.newsrooms(p))


def cover(p):
    """The coverage meter: a short bar and the count, so a one-outlet claim reads differently from a widely reported one."""
    n = coverage(p)
    if not n:
        return ""
    ticks = "".join(f'<i{" class=on" if k < n else ""}></i>' for k in range(COVER_TICKS))
    return f'<span class="cover"><span class="bar" aria-hidden="true">{ticks}</span>Reported by {n} newsroom{"" if n == 1 else "s"}</span>'


def meta(*parts):
    return '<span class="meta">' + '<span class="sep">&middot;</span>'.join(x for x in parts if x) + "</span>"


def t_tag(p):
    return f'<time datetime="{iso(p["published"])}">{clock(p["published"])}</time>'


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
                    f'{meta(E(topic(p)), clock(p["published"]))}</a></li>' for i, p in enumerate(rows[:n], 1))
    return f'<ol class="rank">{items}</ol>'


def item(p):
    return (f'<li><a class="item{"" if p.get("_thumb") else " text"}" href="{href(p)}"><div>{meta(t_tag(p))}'
            f'<span class="h-m">{E(p["headlines"][0])}</span></div>{pic(p, thumb=True)}</a></li>')


def sec_head(label, link=None, more="", level=2):
    right = f'<a class="more" href="{link}">{more}</a>' if link else ""
    return f'<div class="sec"><h{level}>{label}</h{level}>{right}</div>'


def topic_block(t, rows, used=()):
    """One topic: a featured story and up to three more. A story already shown higher on the page is passed over."""
    fresh = [p for p in rows[:12] if p not in used] or rows[:12]
    feat = max(fresh, key=lambda p: (bool(p.get("_hires")), p.get("score", 0)))
    if isinstance(used, list):
        used.append(feat)
    rest = [p for p in rows if p is not feat][:3]
    return (f'<section class="block" aria-label="{t}">{sec_head(t, f"{BASE}/t/{t.lower()}/", f"More {t}")}'
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
            f'<p>The same stories on the channels you already use, each with its sources.</p><ul>{links}</ul>{letter}</section>')


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
        return '<div class="empty">The first stories are on their way.</div>'
    first = rows[0] if n == 1 and rows[0].get("_hires") else None
    lead = (f'<div class="leadrow"><a class="story-link" href="{href(first)}">{pic(first, eager=True)}<span class="kick">{E(topic(first))}</span>'
            f'<h2 class="h-xl">{E(first["headlines"][0])}</h2><p class="dek">{E(first.get("dek", ""))}</p>'
            f'{meta(t_tag(first), cover(first))}</a></div>') if first else ""
    body = lead + f'<ol>{"".join(listing_row(p) for p in rows if p is not first)}</ol>' + pager(path, n, total)
    return f'<div class="listing"><div>{body}</div><aside aria-label="Most important">{aside}</aside></div>' if aside else body


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


def og_image(photo, dest):
    """A 1200x630 JPEG cut from the story's photo, for link previews (Facebook, Telegram, Threads, X).

    The photos are 1050-1400 px wide in every aspect ratio, so the preview is a cover crop, biased to the top
    third because the subject of a portrait photo sits there. ffmpeg is on the Actions image and on the desk's Mac."""
    vf = f"scale={OG_W}:{OG_H}:force_original_aspect_ratio=increase,crop={OG_W}:{OG_H}:(iw-{OG_W})/2:(ih-{OG_H})*0.3"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(photo), "-vf", vf, "-q:v", "3", str(dest)],
                       check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False  # the story still builds; its preview falls back to the shared image
    return True


def card_html(p, photo=None):
    """The share card as a page: topic, headline, coverage meter and the address, the story photo on the right when it has one.
    Same type and monochrome as the site; the fonts are read from the files, as this page is rendered from disk."""
    head, n = p["headlines"][0], coverage(p)
    size = 70 if len(head) <= 60 else 60 if len(head) <= 95 else 50 if len(head) <= 130 else 42
    face = "".join(f"@font-face{{font-family:'Libre Franklin';font-weight:{w};src:url('file://{ASSETS / 'fonts' / f'LibreFranklin-{w}.woff2'}') format('woff2')}}" for w in (400, 600, 800))
    ticks = "".join(f'<i{" class=on" if k < n else ""}></i>' for k in range(COVER_TICKS))
    img = f'<div class="ph"><img src="file://{photo}"></div>' if photo else ""
    return f"""<!doctype html><meta charset="utf-8"><style>{face}
*{{box-sizing:border-box;margin:0}}body{{width:{OG_W}px;height:{OG_H}px;background:#fff;color:#0a0a0a;font-family:'Libre Franklin',Arial,sans-serif;display:flex;overflow:hidden}}
.t{{flex:1;padding:52px 56px 48px;display:flex;flex-direction:column;justify-content:space-between;min-width:0}}
.w{{font-weight:800;font-size:38px;letter-spacing:-.055em}}.k{{font-weight:600;font-size:24px;color:#4d4d50;margin-top:34px}}
h1{{font-weight:800;font-size:{size}px;line-height:1.06;letter-spacing:-.035em;margin-top:14px}}
.b{{display:flex;justify-content:space-between;align-items:center;font-size:26px;font-weight:600;border-top:2px solid #0a0a0a;padding-top:22px}}
.c{{display:flex;align-items:center;gap:14px;white-space:nowrap;font-size:24px}}.bar{{display:flex;gap:4px}}.bar i{{width:22px;height:10px;background:#e1e1e3}}.bar i.on{{background:#0a0a0a}}
.u{{color:#0a0a0a;font-weight:800;letter-spacing:-.02em}}
.ph{{width:420px;flex:none;position:relative}}.ph img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 28%}}</style>
<body><div class="t"><div><div class="w">boardread.</div><div class="k">{E(topic(p))}</div><h1>{E(head)}</h1></div>
<div class="b"><span class="c"><span class="bar">{ticks}</span>Reported by {n} newsroom{"" if n == 1 else "s"}</span><span class="u">boardread.news</span></div></div>{img}</body>"""


def share_card(p, photo, dest):
    """The story's 1200x630 link-preview image, drawn by headless Chrome (the card the desk's own templates use).
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
          "author": {"@type": "Organization", "name": NAME, "url": SITE + "/"},
          "publisher": {"@type": "Organization", "name": NAME, "url": SITE + "/", "logo": {"@type": "ImageObject", "url": f"{SITE}/logo.png"}}}
    if p.get("company"):
        ld["about"] = {"@type": "Organization", "name": p["company"]}
    return ld


def related(p, rows, n=4):
    pool = [o for o in rows if o is not p]
    same_co = [o for o in pool if p.get("company") and o.get("company") == p["company"]]
    same_t = [o for o in pool if topic(o) == topic(p) and o not in same_co]
    return (same_co + same_t + [o for o in pool if o not in same_co and o not in same_t])[:n]


def co_of(p):
    """The company a story is about: the tagged company, else the first logo name the headline carries."""
    return ((p.get("company") or "").strip() or next((n for n in p.get("logo_names") or [] if n), "")).strip()


def co_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def companies(rows, minimum=2):
    """{slug: (name, [stories newest first])} for companies with at least `minimum` stories. rows is newest first."""
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


def number_box(p):
    """"The number": the figure the post carries, only when the headline or the dek states it. A figure the text
    does not state is not set large on the page."""
    fig = (p.get("figure") or "").strip()
    if not fig:
        return ""
    for text in (p["headlines"][0], p.get("dek") or ""):
        if desk._in_text(fig, text):
            return (f'<aside class="numbox" aria-labelledby="nb"><h2 id="nb">The number</h2><p class="big">{E(fig)}</p>'
                    f'<p class="cap">{E(text)}</p></aside>')
    return ""


def how_made(p, counts):
    """The per-story panel: what the desk read and which fixed checks the text passed. Every published story has
    passed them (copy.verify and desk.audit run before a post is queued and again before it is published)."""
    rooms = outlets.newsrooms(p)
    fig = (p.get("figure") or "").strip()
    checks = ["Numbers: every number in the text appears in the source text."
              + (f" The figure {fig} is in the headline." if number_box(p) else ""),
              "Names: each sentence is compared with the source text; a sentence whose words are mostly missing from it is rejected.",
              "Photo licence: " + ("the licence allows reuse and the credit line is shown." if p.get("credit") else "this story has no photo."),
              "Audit: topic, photo, hashtag and stock-phrase checks passed."]
    return (f'<details class="made"><summary>How this story was made</summary><div class="made-body">'
            f'<p>An AI model wrote it from the text of {len(rooms)} newsroom{"" if len(rooms) == 1 else "s"} and had no other input. '
            f'Fixed code checked it before it went up.</p>'
            f'<dl><dt>Feeds scanned</dt><dd>{counts["feeds"]} feeds, every 30 minutes</dd>'
            f'<dt>Newsrooms used</dt><dd>{E(", ".join(rooms)) or "none listed"}</dd>'
            f'<dt>Checks passed</dt><dd><ul>{"".join(f"<li>{E(c)}</li>" for c in checks)}</ul></dd></dl>'
            f'<p><a href="{BASE}/how-it-works/">How the desk works, with live counts</a></p></div></details>')


def story(p, rows, cos=None, counts=None):
    """One story page. rows is every shown story, newest first; cos is companies(rows)."""
    cos = companies(rows) if cos is None else cos
    counts = counts or desk_counts(rows)
    mix = outlets.source_mix(p)
    srcs = "".join(f'<li><a href="{E(u)}" rel="nofollow noopener" target="_blank"><b>{E(o)}</b><span>Read the original &nearr;</span></a></li>'
                   for o, u in mix)
    if p.get("permalink"):
        srcs += f'<li><a href="{E(p["permalink"])}" rel="noopener" target="_blank"><b>The post on Instagram</b><span>instagram.com &nearr;</span></a></li>'
    paras = "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or "").split("\n") if x.strip())
    alt = Path(p.get("photo_file") or "").stem
    fig = (f'<figure><span class="pic"><img src="{BASE}/img/{p["id"]}.jpg" width="960" height="640" alt="{E(alt)}" fetchpriority="high"></span>'
           f'<figcaption class="meta">{E(p.get("credit", ""))}</figcaption></figure>') if p.get("_hires") else ""
    rel = related(p, rows)
    more = (f'<section class="related" aria-labelledby="rel">{sec_head("Related stories", level=2).replace("<h2", "<h2 id=\"rel\"", 1)}<div class="related-grid">'
            + "".join(f'<article><a class="story-link" href="{href(o)}">{pic(o, thumb=True)}<span class="kick">{E(topic(o))}</span>'
                      f'<h3 class="h-m">{E(o["headlines"][0])}</h3>{meta(t_tag(o))}</a></article>' for o in rel) + "</div></section>") if rel else ""
    i = rows.index(p)
    newer, older = (rows[i - 1] if i > 0 else None), (rows[i + 1] if i + 1 < len(rows) else None)
    nav = "".join(f'<a href="{href(o)}" rel="{r}"><span class="kick">{k}</span><span class="h-s">{E(o["headlines"][0])}</span></a>'
                  for o, r, k in ((older, "prev", "&larr; Older"), (newer, "next", "Newer &rarr;")) if o)
    prevnext = f'<nav class="prevnext{"" if older and newer else " one"}" aria-label="More stories">{nav}</nav>' if nav else ""
    image = f"{BASE}/og/{p['id']}.jpg" if p.get("_og") else None
    name = co_of(p)
    company = ""
    if name:
        company = (f'<span>About <a href="{BASE}/c/{co_slug(name)}/">{E(name)}</a></span>' if co_slug(name) in cos
                   else f'<span><a href="{BASE}/search/?q={urllib.parse.quote(name)}">More on {E(name)}</a></span>')
    body = f"""<article class="art"><div>
<header class="art-head"><a class="kick" href="{BASE}/t/{topic(p).lower()}/">{E(topic(p))}</a>
<h1>{E(p['headlines'][0])}</h1><p class="dek">{E(p.get('dek', ''))}</p>
<div class="byline meta"><span>By the Boardread desk (AI)</span><span><time datetime="{iso(p['published'])}">{when(p['published'])}</time></span><span>{cover(p)}</span>{company}</div></header>
{fig}<section class="happened" aria-labelledby="wh"><h2 id="wh" class="lab">What happened</h2><div class="body">{paras}</div></section>
{number_box(p)}{how_made(p, counts)}
<p class="disclose">Written by AI from the sources listed. Numbers are checked against the source text before publishing. <a href="{BASE}/standards/">How we work and how to report an error</a>.</p>
</div>
<aside class="rail" aria-label="About this story"><section><h2>Reported by</h2><ul class="src">{srcs}</ul></section>
<section><h2>Share</h2>{share_links(p)}</section></aside>
{more}{prevnext}</article>"""
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": NAME, "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": topic(p), "item": f"{SITE}/t/{topic(p).lower()}/"},
        {"@type": "ListItem", "position": 3, "name": clip(p["headlines"][0], 110)}]}
    return page(f'{p["headlines"][0]} · boardread.', body, p.get("dek", ""), f"/s/{p['id']}/", image, "article",
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
            f"<language>en</language>{''.join(one(*i) for i in items)}</channel></rss>")


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
<li><div><b>It reads the news.</b> Every 30 minutes the desk fetches more than 80 feeds from newsrooms and research labs.</div></li>
<li><div><b>It ranks.</b> Coverage of the same event is grouped into one story and scored. Only stories above a fixed importance bar, and under a day old, are taken further.</div></li>
<li><div><b>It writes.</b> An AI model writes a short report from the text of the sources. It has no other input and no tools.</div></li>
<li><div><b>It checks.</b> Fixed code checks the text before anything is public: every number must appear in the source, sentences that read as commentary are rejected, and stories about deaths, violence and abuse are skipped.</div></li>
<li><div><b>It publishes with the sources.</b> Each story names the newsrooms it draws on and links to them. Photos are licensed images with their credit shown.</div></li>
</ol>
<h2>Limits</h2>
<p>Boardread does no original reporting. It summarises what named newsrooms have reported, and says which ones. Read the linked source for the full story. Opinion and speculation are not published.</p>
<h2>Follow</h2>
<p>The same stories go out on <a href="{BASE}/feed.xml">RSS</a>{"".join(f', <a href="{E(a["url"])}" rel="me noopener">{E(a["name"])}</a>' for a in accounts())}.</p>
<p>See the <a href="{BASE}/standards/">editorial standards and corrections policy</a>, the <a href="{BASE}/contact/">contact page</a> and the <a href="{LEGAL['impressum']}">Impressum</a>.</p>
</div>"""


def standards_page():
    return pagehead("Editorial standards and corrections", "What a Boardread story promises, and what happens when it is wrong.") + f"""<div class="prose">
<h2>Standards</h2>
<ul>
<li><b>Sources are named and linked.</b> Every story lists the newsrooms it draws on, each with a link to the original.</li>
<li><b>AI writes, code checks.</b> Stories are written by an AI model from the source text. Numbers must appear in the source; commentary is rejected before publishing. The disclosure "Written by AI from the sources listed" appears on every story.</li>
<li><b>No original reporting.</b> Boardread summarises named reporting. It does not use anonymous sources of its own.</li>
<li><b>Photos are credited.</b> Images are licensed, and the credit line sits under the picture. A photo illustrates the topic and may not show the event.</li>
<li><b>Times are UTC.</b> Each story shows when it was published.</li>
<li><b>Topics we skip.</b> Stories centred on deaths, violence, abuse and similar subjects are not published by the desk.</li>
</ul>
<h2>Corrections</h2>
<p>If a story misstates a fact, a name or a number, tell us with the link to the story and the correct information. The first thing checked is the source: if the source says something different from the story, the story is wrong and is corrected or withdrawn. If the source itself was corrected, the story follows it.</p>
<ul>{contact_lines()}</ul>
<h2>Who is responsible</h2>
<p>The operator named in the <a href="{LEGAL['impressum']}">Impressum</a> is responsible for the site, including the output of its automated desk.</p>
</div>"""


def contact_page():
    return pagehead("Contact", "Corrections, tips and questions.") + f"""<div class="prose">
<p>Include the link to the story you are writing about. Corrections are read first.</p>
<ul>{contact_lines()}</ul>
<p>The operator's details are in the <a href="{LEGAL['impressum']}">Impressum</a>.</p>
</div>"""


def search_page():
    return pagehead("Search", "Every Boardread story: headline, summary, topic and company.") + f"""<div class="searchwrap">
<form class="sbox" role="search" action="{BASE}/search/" method="get" data-index="{BASE}/search.json">
<input type="search" name="q" id="q" placeholder="Search stories" aria-label="Search stories" autocomplete="off" autofocus>
<button type="submit">Search</button></form>
<p class="meta" id="sstatus" role="status" aria-live="polite"></p>
<ol class="hits" id="hits"></ol>
<noscript><p class="empty">Search needs JavaScript. Browse the <a href="{BASE}/latest/">latest stories</a> or the <a href="{BASE}/archive/">archive</a> instead.</p></noscript>
</div>"""


def not_found():
    return pagehead("Page not found", "The story may have moved or never existed.") + f"""<div class="prose">
<p>Try the <a href="{BASE}/">front page</a>, the <a href="{BASE}/latest/">latest stories</a> or the <a href="{BASE}/search/">search</a>.</p></div>"""


# ---------------------------------------------------------------- build

def put(out, path, html_):
    d = out / path.strip("/")
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html_)


def paged(out, path, rows, title, desc, head, active, aside="", sitemap=None, feed=None):
    """A listing at path, one page per PER stories: path, path/page/2/, ..."""
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
    """Stories within `hours` of the newest one: what "today" means on a site that may be a few hours stale."""
    if not rows:
        return []
    top = dt(rows[0]["published"])
    return [p for p in rows if top - dt(p["published"]) <= timedelta(hours=hours)]


def by_score(rows):
    return sorted(rows, key=lambda p: (p.get("score", 0), p["published"]), reverse=True)


def most_covered(rows, n=5):
    """[(name, slug, stories)] companies ranked by stories in the 7 days up to the newest story, ties by newsrooms behind them."""
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
    """The ranking as an ordered list; a company with a page links to it, one without to the search."""
    out = []
    for i, (name, slug, k) in enumerate(most_covered(rows, n), 1):
        link = f"{BASE}/c/{slug}/" if slug in cos else f"{BASE}/search/?q={urllib.parse.quote(name)}"
        noun = "story" if k == 1 else "stories"
        out.append(f'<li><span class="n" aria-hidden="true">{i}</span><a href="{link}"><span class="h-s">{E(name)}</span>'
                   f'{meta(f"{k} {noun} this week")}</a></li>')
    return f'<ol class="rank">{"".join(out)}</ol>' if out else ""


def most_covered_block(shown, cos, n=5):
    lst = covered_list(shown, cos, n)
    return (f'<div class="covered">{sec_head("Most covered this week", f"{BASE}/week/", "All", level=3)}{lst}</div>') if lst else ""


def home(shown, cos=None):
    cos = companies(shown) if cos is None else cos
    today = window(shown)
    ranked_today = by_score(today)
    lead = next((p for p in ranked_today if p.get("_hires")), ranked_today[0]) if ranked_today else None
    pairs = [p for p in ranked_today if p is not lead and p.get("_thumb")][:2]
    pairs += [p for p in ranked_today if p is not lead and p not in pairs][:2 - len(pairs)]
    week = by_score([p for p in shown if dt(shown[0]["published"]) - dt(p["published"]) <= timedelta(days=7)])
    week = sorted(week, key=shared, reverse=True)
    used = [lead] + pairs
    blocks = ""
    for t in TOPIC_ORDER:
        if rows := [p for p in shown if topic(p) == t]:
            blocks += topic_block(t, rows, used)
    front = (f'<div class="front"><section class="latest" aria-labelledby="lh">{sec_head("Latest", f"{BASE}/latest/", "All latest").replace("<h2", "<h2 id=\"lh\"", 1)}'
             f'{stream(shown, 10)}</section>'
             f'<div class="lead-col">{lead_block(lead)}{pair_block(pairs)}</div>'
             f'<section class="important" aria-labelledby="ih">{sec_head("Most important today").replace("<h2", "<h2 id=\"ih\"", 1)}{ranked(ranked_today, 5)}'
             f'<p class="col-foot"><a href="{BASE}/week/">The week\'s top stories</a></p>'
             f'{most_covered_block(shown, cos)}</section></div>')
    duo = (f'<div class="duo"><section aria-labelledby="wh">{sec_head("This week", f"{BASE}/week/", "Top 10").replace("<h2", "<h2 id=\"wh\"", 1)}'
           f'{ranked(week, 5)}</section>{follow_block()}</div>')
    return '<p class="since" id="since" role="status" hidden></p>' + front + blocks + duo


def build(out=desk.HERE / "_site"):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    for d in ("img", "og", "assets"):
        (out / d).mkdir(parents=True)
    shutil.copytree(ASSETS / "fonts", out / "fonts")  # Libre Franklin and its OFL licence
    for f in ("site.css", "site.js"):
        shutil.copy(ASSETS / f, out / "assets" / f)
    for f in ("og-default.png", "logo.png", "icon.svg"):  # the preview image of every non-story page, the publisher logo, the favicon
        shutil.copy(ASSETS / f, out / f)
    if (ASSETS / "CNAME").exists():  # the custom domain GitHub Pages serves this site under; added at the cut-over
        shutil.copy(ASSETS / "CNAME", out / "CNAME")
    shown = []
    for p in published():
        photo = desk.MEDIA / p["id"] / "photo.jpg"
        if photo.exists():
            resized(photo, out / "img" / f"{p['id']}.jpg", 960)
            resized(photo, out / "img" / f"{p['id']}-t.jpg", 480)  # not thumb.jpg: that one is a crop of the Instagram card, text included
            p["_hires"] = p["_thumb"] = True
        # no photo: the story is a text row. media/<id>/thumb.jpg is a crop of the Instagram card with the headline
        # set into it, so it is never used as a picture on the site (it showed "Global stocks" in a tile)
        shown.append(p)  # a story without any picture still has a page: text is the story
    # every story gets a card: the photo-less ones carry the same headline and meter, so a shared link is never the generic image
    def card(p):
        photo = desk.MEDIA / p["id"] / "photo.jpg"
        photo = photo if photo.exists() else None
        dest = out / "og" / f"{p['id']}.jpg"
        return share_card(p, photo, dest) or bool(photo and og_image(photo, dest))
    with ThreadPoolExecutor(max_workers=6) as pool:
        for p, ok in zip(shown, pool.map(card, shown)):
            if ok:
                p["_og"] = True
    sm = []
    desc = "Markets, economy, politics, world, tech and AI: every story with its sources."
    if shown:
        site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": SITE + "/", "inLanguage": "en",
                   "potentialAction": {"@type": "SearchAction", "target": f"{SITE}/search/?q={{search_term_string}}", "query-input": "required name=search_term_string"}}
        put(out, "/", page(f"boardread. · {TAGLINE}", home(shown, companies(shown)), desc, "/", ld=site_ld, active="", front=True))
    else:
        put(out, "/", page(f"boardread. · {TAGLINE}", '<div class="empty">The first stories are on their way.</div>', desc, "/", front=True))
    sm.append((SITE + "/", iso(shown[0]["published"]) if shown else None))
    top5 = lambda rows: ranked(by_score(window(rows))[:5], 5)  # noqa: E731
    aside = lambda rows: (sec_head("Most important", level=2) + top5(rows)) if len(rows) > 3 else ""  # noqa: E731
    paged(out, "/latest/", shown, "Latest", desc, pagehead("Latest", "Every story, newest first. Times are UTC."), "latest", aside(shown), sm)
    for t in TOPIC_ORDER:
        rows = [p for p in shown if topic(p) == t]
        paged(out, f"/t/{t.lower()}/", rows, t, TOPICS[t], pagehead(t, TOPICS[t]), t.lower(), aside(rows), sm,
              feed=(f"boardread. {t}", f"/t/{t.lower()}/feed.xml"))
    cos, counts = companies(shown), desk_counts(shown)
    for p in shown:
        put(out, f"/s/{p['id']}/", story(p, shown, cos, counts))
        sm.append((f"{SITE}/s/{p['id']}/", iso(p["published"])))
    days = {}
    for p in shown:
        days.setdefault(day_of(p["published"]), []).append(p)
    put(out, "/archive/", page("Archive · boardread.", pagehead("Archive", "Every day of Boardread, newest first.") + '<div class="prose days">'
        + "".join(f'<a href="{BASE}/archive/{d}/">{day_label(d)}<span>{len(ps)} {"story" if len(ps) == 1 else "stories"}</span></a>' for d, ps in days.items())
        + "</div>", "Every day of Boardread.", "/archive/"))
    sm.append((SITE + "/archive/", iso(shown[0]["published"]) if shown else None))
    for d, ps in days.items():
        paged(out, f"/archive/{d}/", ps, day_label(d), f"Boardread stories of {day_label(d)}.", pagehead(day_label(d), f"{len(ps)} stories, newest first."), "", "", sm)
    # weeks: one page per ISO week (the newsletter's issues), and /week/ for the last seven days
    weeks = {}
    for p in shown:
        weeks.setdefault(week_of(p["published"]), []).append(p)
    this_week = datetime.now(timezone.utc).strftime("%G-W%V")
    wdesc = "The ten most shared stories of the week, each with its sources."

    def top_list(rows, heading, sub, active):
        body = pagehead(heading, sub) + (f'<div class="prose" style="max-width:50rem">{ranked(rows, 10)}</div>' if rows
                                         else '<div class="empty">The week has just begun.</div>')
        return body

    issues = []
    for wk in sorted(weeks, reverse=True):
        top = sorted(weeks[wk], key=shared, reverse=True)[:10]
        put(out, f"/week/{wk}/", page(f"Top 10 · {wk} · boardread.", top_list(top, "Top 10", f"Week {wk[-2:]}, {wk[:4]}, most shared", "week"),
                                      wdesc, f"/week/{wk}/", active="week"))
        sm.append((f"{SITE}/week/{wk}/", iso(max(p["published"] for p in weeks[wk]))))
        if wk != this_week:  # an unfinished week is not an issue yet
            issues.append((wk, top))
    last7 = [p for p in shown if datetime.now(timezone.utc) - dt(p["published"]) <= timedelta(days=7)] or shown[:10]
    past = "".join(f'<li><a href="{BASE}/week/{w}/">Week {w[-2:]}, {w[:4]}</a></li>' for w in sorted(weeks, reverse=True) if w != this_week)
    mc = covered_list(shown, companies(shown), 10)
    put(out, "/week/", page("This week · boardread.", top_list(sorted(last7, key=shared, reverse=True)[:10], "This week", "The ten most shared stories of the last seven days", "week")
        + (f'<div class="prose" style="max-width:50rem"><h2>Most covered this week</h2><p>Companies ranked by how many stories named them in the last seven days.</p>{mc}</div>' if mc else "")
        + (f'<div class="prose"><h2>Past weeks</h2><ul>{past}</ul></div>' if past else ""), wdesc, "/week/", active="week"))
    sm.append((SITE + "/week/", iso(shown[0]["published"]) if shown else None))
    put(out, "/search/", page("Search · boardread.", search_page(), "Search every Boardread story.", "/search/", active="search"))
    (out / "search.json").write_text(search_index(shown))
    for key, title, fn, d in (("about", "About", about_page, "What Boardread is and how the desk works."),
                              ("standards", "Editorial standards and corrections", standards_page, "What a Boardread story promises and how corrections work."),
                              ("contact", "Contact", contact_page, "Corrections, tips and questions.")):
        put(out, f"/{key}/", page(f"{title} · boardread.", fn(), d, f"/{key}/"))
        sm.append((f"{SITE}/{key}/", iso(shown[0]["published"]) if shown else None))
    (out / "404.html").write_text(page("Page not found · boardread.", not_found(), "", "/404.html", noindex=True))
    (out / "feed.xml").write_text(rss("boardread", SITE + "/", [
        (p["headlines"][0], f"{SITE}/s/{p['id']}/", format_datetime(dt(p["published"])), p.get("dek", ""),
         {"category": topic(p), "image": f"{BASE}/og/{p['id']}.jpg" if p.get("_og") else None,
          "image_bytes": (out / "og" / f"{p['id']}.jpg").stat().st_size if p.get("_og") else 0})
        for p in shown[:50]]))
    (out / "weekly.xml").write_text(rss("boardread weekly", SITE + "/week/", [
        (f"Top 10 · {wk}: {top[0]['headlines'][0]}", f"{SITE}/week/{wk}/", format_datetime(dt(top[0]["published"]) + timedelta(days=1)),
         " · ".join(p["headlines"][0] for p in top), {"category": "Weekly"}) for wk, top in issues[:12]]))
    from . import sitepages  # imports this module, so only once it is loaded
    sitepages.build(out, shown, sm, cos)
    (out / "sitemap.xml").write_text(urlset([(u, m) for u, m in sm if m]))
    (out / "news-sitemap.xml").write_text(news_sitemap(shown, datetime.now(timezone.utc)))
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    (out / ".nojekyll").write_text("")
    print(f"site: {len(shown)} stories, {len(weeks)} weeks -> {out}")
    return out


def redirects(out, old_base="/news"):
    """Stubs for the old home of the site (keremozdemir.de/news/...), to be served from the main site's repository
    after the cut-over: every story, topic and week page, plus the front page, sends the reader to the new address
    with a meta refresh, a canonical link and a script. Feeds cannot be redirected this way and are not stubbed."""
    out = Path(out)
    paths = ["/", "/latest/", "/week/", "/search/", "/about/", "/archive/"] + [f"/t/{t.lower()}/" for t in TOPIC_ORDER]
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
