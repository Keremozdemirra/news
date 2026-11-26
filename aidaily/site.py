"""The news pages at keremozdemir.de/news: built from the committed posts after every run.

Static files only, no scripts, no third-party requests: thumbnails are copied in from the media
branch, so a reader's browser talks to one origin. Every post that reached a channel appears: published on
Instagram, or web tier (status "web"), which is the site and the social channels only.

  /news/                 the latest stories
  /news/s/<id>/          one story: card, report, every source link (what the SOURCE DM points to)
  /news/week/<YYYY-Www>/ the week's ten most shared stories (the newsletter's issue)
  /news/feed.xml         every story, for readers
  /news/weekly.xml       one item per finished week, for the newsletter tool's RSS-to-email
  /news/sitemap.xml      every story, topic and week page with its lastmod
  /news/news-sitemap.xml the last 48 hours of stories, in Google News' format
  /news/og/<id>.jpg      the 1200x630 link-preview image of a story, cut from its photo at build time
"""
import html
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from . import desk

E = lambda s: html.escape(s or "", quote=True)  # noqa: E731
SITE = desk.CONFIG["site_url"]
BASE = "/" + SITE.split("/", 3)[3] if SITE.count("/") >= 3 else ""
ORIGIN = "/".join(SITE.split("/")[:3])
NAME = "Boardread"
ASSETS = Path(__file__).resolve().parent.parent / "assets-site"
OG_W, OG_H = 1200, 630


def published():
    """Posts live on the site: published on Instagram or published to the web tier. Nothing on a page may say
    which one it was, except the Instagram link a post carries only when it has a permalink."""
    rows = [p for p, _ in desk.posts() if p.get("status") in ("published", "web") and p.get("published") and p.get("kind") != "story"]
    return sorted(rows, key=lambda p: p["published"], reverse=True)


def when(iso):
    return datetime.fromisoformat(iso).strftime("%-d %b %Y, %H:%M UTC")


def week_of(iso):
    return datetime.fromisoformat(iso).strftime("%G-W%V")


def shared(p):
    i = p.get("insights") or {}
    # shares and saves say a reader found it worth keeping; before the weekly numbers arrive, rank decides
    return ((i.get("shares") or 0) + (i.get("saved") or 0), p.get("score", 0))


# Headlines and body are Libre Franklin, the face of the Instagram cards (SIL OFL, self-hosted from
# assets-site/fonts, no request leaves the origin). The bar is the main site's own: its Fraunces name and
# its Plex Mono sections, served from the main site's /fonts/. Colour tokens and light/dark are the main site's.
MAIN_FONTS = {
    "Fraunces": "fraunces-6NU78FyLNQOQZAnv9bYEvDiIdE9Ea92uemAk_WBq8U_9v0c2Wa0KxC9TeP2Xz5c",
    "IBM Plex Mono": "ibmplexmono--F63fjptAgt5VM-kVkqdyU8n1i8q131nj-o",
}
FRANKLIN = "LibreFranklin-var.woff2"
FACES = (f"@font-face{{font-family:'Libre Franklin';font-weight:100 900;font-display:swap;src:url('{BASE}/fonts/{FRANKLIN}') format('woff2')}}"
         + "".join(f"@font-face{{font-family:'{f}';font-weight:300 700;font-display:swap;src:url('/fonts/{n}.woff2') format('woff2')}}"
                   for f, n in MAIN_FONTS.items()))

CSS = FACES + """
:root{--paper:#fcfcfb;--ink:#16171a;--soft:#5b5f66;--faint:#8b9098;--rule:#dcdde0;--mark:#f0f0ee;
--serif:"Fraunces",Georgia,serif;--sans:"Libre Franklin",-apple-system,"Segoe UI",Helvetica,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media(prefers-color-scheme:dark){:root{--paper:#111214;--ink:#e9eaec;--soft:#9aa0a8;--faint:#6b7078;--rule:#25272b;--mark:#191a1d}}
*{box-sizing:border-box}html{background:var(--paper)}body{margin:0;background:var(--paper);color:var(--ink);
font:400 17px/1.6 var(--sans);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit;text-decoration:none}img{display:block;max-width:100%}
.wrap{max-width:1180px;margin:0 auto;padding:0 40px}
.mono{font:500 11px/1.5 var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--soft)}
.bar{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--paper) 90%,transparent);backdrop-filter:blur(12px);border-bottom:1px solid var(--rule)}
.bar .wrap{display:flex;align-items:center;justify-content:space-between;height:64px;gap:24px}
.home{font-family:var(--serif);font-size:1.05rem;font-variation-settings:"SOFT" 0,"WONK" 0,"opsz" 24;white-space:nowrap}
.nav{display:flex;gap:26px;font:500 11.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
.nav a:hover,.nav a.on{color:var(--ink)}.nav a.on{box-shadow:0 1px 0 var(--ink);padding-bottom:6px}
.head{padding:88px 0 0}
.title{font:800 clamp(56px,7.4vw,104px)/.9 var(--sans);letter-spacing:-.052em;margin:0}
.head .mono{margin-top:22px}
.tabs{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px 28px;margin-top:56px;padding:16px 0;border-top:1px solid var(--ink);border-bottom:1px solid var(--rule)}
.tabs nav{display:flex;gap:24px;flex-wrap:wrap}.tabs a:hover,.tabs a.on{color:var(--ink)}.tabs a.on{box-shadow:0 1px 0 var(--ink)}
.lead{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:48px;padding:48px 0 56px;border-bottom:1px solid var(--rule);align-items:end}
.lead figure,.story figure{margin:0;background:var(--mark);overflow:hidden}
.lead img{width:100%;aspect-ratio:3/2;object-fit:cover;transition:transform 1.2s cubic-bezier(.16,1,.3,1)}
.lead:hover img,.row:hover .thumb img{transform:scale(1.025)}
.lead h2{font:800 clamp(30px,3.3vw,46px)/1.04 var(--sans);letter-spacing:-.035em;margin:14px 0 18px;text-wrap:balance}
.lead p{font-size:18px;line-height:1.55;color:var(--soft);margin:0 0 22px}
.rows{list-style:none;margin:0;padding:0}
.row{display:grid;grid-template-columns:56px minmax(0,1fr) 170px 176px;gap:28px;align-items:center;padding:30px 0;border-bottom:1px solid var(--rule)}
.row .num{align-self:start;padding-top:6px}
.row h3{font:800 24px/1.14 var(--sans);letter-spacing:-.025em;margin:0 0 8px;text-wrap:balance}
.row p{margin:0;font-size:15.5px;line-height:1.5;color:var(--soft);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.row .side{text-align:right;line-height:1.9}
.thumb{display:block;overflow:hidden;background:var(--mark)}.thumb img{width:100%;aspect-ratio:3/2;object-fit:cover;transition:transform 1.2s cubic-bezier(.16,1,.3,1)}
.row.text{grid-template-columns:56px minmax(0,1fr) 170px 176px}.row.text .thumb{visibility:hidden}
.row:hover h3,.lead:hover h2{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:5px}
.empty{padding:120px 0;color:var(--soft);font:800 34px/1.15 var(--sans);letter-spacing:-.03em}
.story{max-width:860px;padding:40px 0 24px}
.story h1{font:800 clamp(36px,4.6vw,60px)/1.02 var(--sans);letter-spacing:-.042em;margin:18px 0 22px;text-wrap:balance}
.story .dek{font-size:21px;line-height:1.5;color:var(--soft);margin:0 0 36px}
.story figure{margin:0 0 10px}.story figure img{width:100%;aspect-ratio:3/2;object-fit:cover}
.credit{margin-bottom:36px}
.story .body p{font-size:19px;line-height:1.65;margin:0 0 20px}
.srcs{margin-top:44px;border-top:1px solid var(--ink)}
.srcs a{display:flex;justify-content:space-between;align-items:center;padding:18px 0;border-bottom:1px solid var(--rule);font-weight:600}
.srcs a span{color:var(--soft)}.srcs a:hover span{color:var(--ink)}
.more{margin-top:72px}
footer{border-top:1px solid var(--rule);margin-top:72px;padding:28px 0 56px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:14px}
footer a:hover{color:var(--ink)}footer nav{display:flex;gap:22px}
@media(max-width:980px){.lead{grid-template-columns:1fr;gap:26px}.row,.row.text{grid-template-columns:40px minmax(0,1fr) 140px}.row .side{display:none}.nav a.x{display:none}}
@media(max-width:620px){.wrap{padding:0 20px}.head{padding-top:56px}.row,.row.text{grid-template-columns:minmax(0,1fr) 112px;gap:16px}.row .num{display:none}.row h3{font-size:19px}.row p{display:none}.row.text{grid-template-columns:1fr}.row.text .thumb{display:none}.nav{gap:16px}}
"""


def stats():
    """Followers per platform from the latest weekly file, and the counts the desk itself keeps."""
    latest = sorted((desk.STATE / "insights").glob("*.json"))
    acct = desk._load(latest[-1], {}).get("account", {}) if latest else {}
    followers = {"Instagram": acct.get("followers_count")} if acct.get("followers_count") else {}
    followers.update(desk._load(desk.STATE / "followers.json", {}))
    pub = published()
    return {"followers": followers, "stories": len(pub),
            "sources": len({x for p in pub for x in p.get("sources") or []})}


SECTIONS = [("/products/", "Products"), ("/projects/", "Projects"), ("/games/", "Games"),
            ("/discoveries/", "Discoveries"), (f"{BASE}/", "News"), ("/about/", "About"), ("/contact/", "Contact")]
TOPIC_ORDER = ["Business", "Markets", "Economy", "Politics", "World", "Tech", "AI", "Culture"]


def topic(p):
    return p.get("topic") or (p.get("categories") or ["News"])[0].title()


def clock(iso):
    return datetime.fromisoformat(iso).strftime("%-d %b · %H:%M")


def counts():
    """The figures under the title: only what the desk measured, only accounts that exist."""
    st = stats()
    parts = ["The news that moves business"]
    if st["stories"]:
        parts.append(f"{st['stories']:,} {'article' if st['stories'] == 1 else 'articles'}")
    if st["sources"]:
        parts.append(f"{st['sources']} newsrooms cited")
    total = sum(v for v in st["followers"].values() if isinstance(v, int))
    if total:
        parts.append(f"{total:,} followers")
    return " · ".join(parts)


def follow():
    st = stats()["followers"]
    return "".join(f'<a href="{E(a["url"])}" rel="me noopener">{E(a["name"])}'
                   + (f" {st[a['name']]:,}" if st.get(a["name"]) else "") + " ↗</a>"
                   for a in desk.CONFIG.get("accounts", []) if a.get("url"))


def tabs(active=""):
    items = [(f"{BASE}/", "All", "")] + [(f"{BASE}/t/{t.lower()}/", t, t.lower()) for t in TOPIC_ORDER] \
        + [(f"{BASE}/week/", "Top 10", "week")]
    links = "".join(f'<a href="{h}"{" class=\"on\"" if active == k else ""}>{n}</a>' for h, n, k in items)
    return f'<div class="tabs mono"><nav>{links}</nav><nav>{follow()}</nav></div>'


DEFAULT_OG = f"{BASE}/og-default.png"


def clip(text, n):
    """At most n characters, cut at a word and marked, for fields a consumer truncates or rejects (JSON-LD headline: 110)."""
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def ld_json(data):
    # "<" escaped so no text inside a field can close the script element
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def page(title, body, desc="", path="/", image=None, og_type="website", ld=None, og_title=None):
    """Every page: the main site's bar (its name back home, its sections), then the desk.

    path is relative to the news root and becomes the canonical and og:url; image is the site-relative
    link-preview image (the shared default when a story has no photo)."""
    url = SITE + path
    og_dims = f'<meta property="og:image:width" content="{OG_W}"><meta property="og:image:height" content="{OG_H}">\n' \
        if image in (None, DEFAULT_OG) or image.startswith(f"{BASE}/og/") else ""
    nav = "".join(f'<a href="{h}"{" class=\"on\"" if n == "News" else (" class=\"x\"" if n not in ("About", "Contact") else "")}>{n}</a>'
                  for h, n in SECTIONS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; font-src 'self'; style-src 'unsafe-inline'; form-action https:; base-uri 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="color-scheme" content="light dark">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(url)}">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="boardread." href="{BASE}/feed.xml">
<link rel="sitemap" type="application/xml" href="{BASE}/sitemap.xml">
<meta property="og:site_name" content="{NAME}"><meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(og_title or title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(url)}"><meta property="og:image" content="{E(ORIGIN + (image or DEFAULT_OG))}">
{og_dims}<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{E(og_title or title)}">
<meta name="twitter:description" content="{E(desc)}"><meta name="twitter:image" content="{E(ORIGIN + (image or DEFAULT_OG))}">
{ld_json(ld) if ld else ""}
<style>{CSS}</style></head><body>
<div class="bar"><div class="wrap"><a class="home" href="/">Kerem Özdemir</a>
<nav class="nav" aria-label="Sections">{nav}</nav></div></div>
<main class="wrap">{body}
<footer class="mono"><span>boardread. · Kerem Özdemir · Written by AI.</span>
<nav><a href="/">Home</a><a href="{BASE}/feed.xml">RSS</a><a href="/impressum/">Impressum</a><a href="/privacy/">Privacy</a></nav></footer>
</main></body></html>"""


def head(title, sub, active=""):
    return f'<header class="head"><h1 class="title">{title}</h1><div class="mono">{E(sub)}</div></header>{tabs(active)}'


def img(p):
    return f"{BASE}/img/{p['id']}.jpg" if p.get("_photo") else ""


def lead(p):
    return (f'<a class="lead" href="{BASE}/s/{p["id"]}/"><figure><img src="{img(p)}" alt=""></figure>'
            f'<div><div class="mono">{E(topic(p))} · {clock(p["published"])}</div>'
            f'<h2>{E(p["headlines"][0])}</h2><p>{E(p.get("dek", ""))}</p>'
            f'<div class="mono">Reported by {E("; ".join(p.get("sources") or []))}</div></div></a>')


def row(p, n):
    pic = f'<span class="thumb"><img src="{img(p)}" alt="" loading="lazy"></span>' if p.get("_photo") else '<span class="thumb"></span>'
    return (f'<li><a class="row{"" if p.get("_photo") else " text"}" href="{BASE}/s/{p["id"]}/"><span class="num mono">{n:02d}</span>'
            f'<div><h3>{E(p["headlines"][0])}</h3><p>{E(p.get("dek", ""))}</p></div>'
            f'<div class="side mono">{E(topic(p))}<br>{clock(p["published"])}</div>{pic}</a></li>')


def listing(rows):
    if not rows:
        return '<div class="empty">The first articles are on their way.</div>'
    first = next((p for p in rows[:3] if p.get("_photo")), None)
    rest = [p for p in rows if p is not first][:120]
    return (lead(first) if first else "") + '<ol class="rows">' + "".join(row(p, i) for i, p in enumerate(rest, 2 if first else 1)) + "</ol>"


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


def iso(s):
    return datetime.fromisoformat(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def article_ld(p, image):
    # Fields follow Google's Article structured data: https://developers.google.com/search/docs/appearance/structured-data/article
    # (headline kept under the ~110 characters it recommends; author and publisher are the Organization, not a person)
    url = f"{SITE}/s/{p['id']}/"
    return {"@context": "https://schema.org", "@type": "NewsArticle", "mainEntityOfPage": {"@type": "WebPage", "@id": url},
            "headline": clip(p["headlines"][0], 110), "description": p.get("dek", ""),
            "image": [ORIGIN + (image or DEFAULT_OG)], "datePublished": iso(p["published"]), "dateModified": iso(p["published"]),
            "articleSection": topic(p), "inLanguage": "en", "isAccessibleForFree": True,
            "author": {"@type": "Organization", "name": NAME, "url": SITE + "/"},
            "publisher": {"@type": "Organization", "name": NAME, "url": SITE + "/", "logo": {"@type": "ImageObject", "url": f"{SITE}/logo.png"}}}


def story(p, more=()):
    srcs = "".join(f'<a href="{E(u)}" rel="nofollow noopener">{E(u.split("/")[2].removeprefix("www."))}<span>↗</span></a>'
                   for u in p.get("source_urls") or p.get("urls", []))
    if p.get("permalink"):
        srcs += f'<a href="{E(p["permalink"])}">The post on Instagram<span>↗</span></a>'
    paras = "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or "").split("\n") if x.strip())
    fig = (f'<figure><img src="{img(p)}" alt=""></figure><div class="credit mono">{E(p.get("credit", ""))}</div>'
           if p.get("_photo") else "")
    others = ('<section class="more"><div class="tabs mono"><nav><span>More news</span></nav></div><ol class="rows">'
              + "".join(row(o, i) for i, o in enumerate(more, 1)) + "</ol></section>") if more else ""
    image = f"{BASE}/og/{p['id']}.jpg" if p.get("_og") else None
    return page(f'{p["headlines"][0]} · boardread.', f"""<article class="story">
<div class="mono"><a href="{BASE}/">boardread.</a> · {E(topic(p))} · {clock(p['published'])} UTC</div>
<h1>{E(p['headlines'][0])}</h1><p class="dek">{E(p.get('dek', ''))}</p>{fig}
<div class="body">{paras}</div>
<div class="srcs"><div class="mono" style="padding:16px 0">Reported by {E('; '.join(p.get('sources') or []))}</div>{srcs}</div>
<div class="mono" style="padding:20px 0 0;text-transform:none;letter-spacing:.02em">Written by AI from the sources listed. <a href="/contact/" style="text-decoration:underline">Corrections: contact</a></div>
</article>{others}""", p.get("dek", ""), f"/s/{p['id']}/", image, "article", article_ld(p, image), p["headlines"][0])


def week_page(week, rows):
    body = ('<ol class="rows">' + "".join(row(p, i) for i, p in enumerate(rows, 1)) + "</ol>") if rows \
        else '<div class="empty">The week has just begun.</div>'
    return head("Top 10.", f"Week {week[-2:]} · {week[:4]} · most shared", "week") + body


def rss(title, link, items):
    """items: (title, url, pubDate, description, extra) where extra may carry category, image (site path) and image_bytes."""
    def item(t, u, d, desc, extra):
        pic = extra.get("image")
        return (f'<item><title>{E(t)}</title><link>{E(u)}</link><guid isPermaLink="true">{E(u)}</guid><pubDate>{d}</pubDate>'
                f"<description>{E(desc)}</description>"
                + (f"<category>{E(extra['category'])}</category>" if extra.get("category") else "")
                + f"<dc:creator>{NAME}</dc:creator>"
                + (f'<enclosure url="{E(ORIGIN + pic)}" length="{extra.get("image_bytes", 0)}" type="image/jpeg"/>'
                   f'<media:content url="{E(ORIGIN + pic)}" medium="image" type="image/jpeg" width="{OG_W}" height="{OG_H}"/>' if pic else "")
                + "</item>")
    body = "".join(item(*i) for i in items)
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:media="http://search.yahoo.com/mrss/" xmlns:atom="http://www.w3.org/2005/Atom">'
            f'<channel><title>{E(title)}</title><link>{E(link)}</link><description>The news that moves business</description>'
            f"<language>en</language>{body}</channel></rss>")


def urlset(rows):
    """Sitemap protocol: https://www.sitemaps.org/protocol.html"""
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{E(u)}</loc><lastmod>{m}</lastmod></url>" for u, m in rows) + "</urlset>")


def news_sitemap(rows, now):
    """Google News sitemap, only articles from the last 48 hours:
    https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap"""
    recent = [p for p in rows if now - datetime.fromisoformat(p["published"]) <= timedelta(hours=48)]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
            + "".join(f"<url><loc>{E(f'{SITE}/s/{p['id']}/')}</loc><news:news><news:publication><news:name>{NAME}</news:name>"
                      f"<news:language>en</news:language></news:publication><news:publication_date>{iso(p['published'])}</news:publication_date>"
                      f"<news:title>{E(p['headlines'][0])}</news:title></news:news></url>" for p in recent)
            + "</urlset>")


def build(out=desk.HERE / "_site"):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "img").mkdir(parents=True)
    (out / "og").mkdir()
    shutil.copytree(ASSETS / "fonts", out / "fonts")  # Libre Franklin + its OFL licence
    rows = published()
    shown = []
    for p in rows:
        photo, thumb = desk.MEDIA / p["id"] / "photo.jpg", desk.MEDIA / p["id"] / "thumb.jpg"
        if not (photo.exists() or thumb.exists()):
            continue  # its media were pruned before it was ever built; nothing to show
        if photo.exists():
            shutil.copy(photo, out / "img" / f"{p['id']}.jpg")
            p["_photo"] = True
            if og_image(photo, out / "og" / f"{p['id']}.jpg"):
                p["_og"] = True
        shown.append(p)
    for f in ("og-default.png", "logo.png"):  # the preview image of every non-story page, and the publisher logo
        shutil.copy(ASSETS / f, out / f)
    desc = "Business, markets, politics, tech and AI: every article with its sources."
    (out / "index.html").write_text(page("boardread. · The news that moves business",
                                         head("boardread.", counts()) + listing(shown), desc, "/"))
    for t in TOPIC_ORDER:
        d = out / "t" / t.lower()
        d.mkdir(parents=True)
        (d / "index.html").write_text(page(f"{t} · boardread.", head(f"{t}.", counts(), t.lower())
                                           + listing([p for p in shown if topic(p) == t]), desc, f"/t/{t.lower()}/"))
    for i, p in enumerate(shown):
        d = out / "s" / p["id"]
        d.mkdir(parents=True)
        more = [o for o in shown if o is not p][:4]
        (d / "index.html").write_text(story(p, more))
    weeks = {}
    for p in shown:
        weeks.setdefault(week_of(p["published"]), []).append(p)
    this_week = datetime.now(timezone.utc).strftime("%G-W%V")
    issues = []
    for wk in sorted(weeks, reverse=True):
        top = sorted(weeks[wk], key=shared, reverse=True)[:10]
        d = out / "week" / wk
        d.mkdir(parents=True)
        (d / "index.html").write_text(page(f"Top 10 · {wk} · boardread.", week_page(wk, top),
                                          "The ten most shared stories of the week, each with its sources.", f"/week/{wk}/"))
        if wk != this_week:  # an unfinished week is not an issue yet
            issues.append((wk, top))
    latest = issues[0][0] if issues else (sorted(weeks)[-1] if weeks else None)
    (out / "week").mkdir(exist_ok=True)
    this_top = sorted(weeks.get(this_week, []), key=shared, reverse=True)[:10]
    past = "".join(f'<a href="{BASE}/week/{w}/">Week {w[-2:]} · {w[:4]}</a>' for w in sorted(weeks, reverse=True) if w != this_week)
    (out / "week" / "index.html").write_text(page("Top 10 · boardread.", week_page(this_week, this_top)
        + (f'<div class="tabs mono" style="margin-top:48px"><nav>{past}</nav></div>' if past else ""),
        "The ten most shared stories of the week, each with its sources.", "/week/"))
    (out / "feed.xml").write_text(rss("boardread", SITE + "/", [
        (p["headlines"][0], f"{SITE}/s/{p['id']}/", format_datetime(datetime.fromisoformat(p["published"])), p.get("dek", ""),
         {"category": topic(p), "image": f"{BASE}/og/{p['id']}.jpg" if p.get("_og") else None,
          "image_bytes": (out / "og" / f"{p['id']}.jpg").stat().st_size if p.get("_og") else 0})
        for p in shown[:50]]))
    (out / "weekly.xml").write_text(rss("boardread weekly", SITE + "/week/", [
        (f"Top 10 · {wk}: {top[0]['headlines'][0]}", f"{SITE}/week/{wk}/",
         format_datetime(datetime.fromisoformat(top[0]["published"]) + timedelta(days=1)),
         " · ".join(p["headlines"][0] for p in top), {"category": "Weekly"}) for wk, top in issues[:12]]))
    stamp = lambda ps: iso(max(p["published"] for p in ps))  # noqa: E731
    pages = [(SITE + "/", stamp(shown) if shown else None), (SITE + "/week/", stamp(shown) if shown else None)]
    pages += [(f"{SITE}/t/{t.lower()}/", stamp(ps)) for t in TOPIC_ORDER if (ps := [p for p in shown if topic(p) == t])]
    pages += [(f"{SITE}/week/{wk}/", stamp(ps)) for wk, ps in weeks.items()]
    pages += [(f"{SITE}/s/{p['id']}/", iso(p["published"])) for p in shown]
    (out / "sitemap.xml").write_text(urlset([(u, m) for u, m in pages if m]))
    (out / "news-sitemap.xml").write_text(news_sitemap(shown, datetime.now(timezone.utc)))
    (out / ".nojekyll").write_text("")
    print(f"site: {len(shown)} stories, {len(weeks)} weeks -> {out}")
    return out
