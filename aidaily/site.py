"""The news pages at keremozdemir.de/news: built from the committed posts after every run.

Static files only, no scripts, no third-party requests: thumbnails are copied in from the media
branch, so a reader's browser talks to one origin. Only published posts appear.

  /news/                 the latest stories
  /news/s/<id>/          one story: card, report, every source link (what the SOURCE DM points to)
  /news/week/<YYYY-Www>/ the week's ten most shared stories (the newsletter's issue)
  /news/feed.xml         every story, for readers
  /news/weekly.xml       one item per finished week, for the newsletter tool's RSS-to-email
"""
import html
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from . import desk

E = lambda s: html.escape(s or "", quote=True)  # noqa: E731
SITE = desk.CONFIG["site_url"]
BASE = "/" + SITE.split("/", 3)[3] if SITE.count("/") >= 3 else ""


def published():
    rows = [p for p, _ in desk.posts() if p.get("status") == "published" and p.get("published")]
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
:root{--paper:#fcfcfb;--ink:#16171a;--soft:#5b5f66;--rule:#dcdde0;--accent:#c2371c;--mark:#f0f0ee;
--serif:"Fraunces",Georgia,serif;--sans:"Libre Franklin",-apple-system,"Segoe UI",Helvetica,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media(prefers-color-scheme:dark){:root{--paper:#111214;--ink:#e9eaec;--soft:#9aa0a8;--rule:#292b30;--accent:#f5694b;--mark:#1c1d20}}
*{box-sizing:border-box}html{background:var(--paper)}body{margin:0;background:var(--paper);color:var(--ink);
font:400 17px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}img{display:block;max-width:100%}
.wrap{max-width:1240px;margin:0 auto;padding:0 40px}
.bar{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--rule)}
.bar .wrap{display:flex;align-items:center;justify-content:space-between;height:64px;gap:24px}
.home{font-family:var(--serif);font-size:1.05rem;font-variation-settings:"SOFT" 0,"WONK" 0,"opsz" 24;white-space:nowrap;flex-shrink:0}
.nav{display:flex;gap:26px;font:500 11.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
.nav a:hover,.nav a.on{color:var(--ink)}.nav a.on{box-shadow:0 2px 0 var(--accent);padding-bottom:6px}
.mast{padding:72px 0 28px;border-bottom:1px solid var(--rule)}
.eyebrow,.meta,.chips a,.stats{font:600 11.5px/1.4 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
.mast h1{font:800 clamp(64px,10vw,148px)/.88 var(--sans);letter-spacing:-.055em;margin:18px 0 18px}
.mast h1 i{font-style:normal;color:var(--accent)}
.mast p{font:400 22px/1.35 var(--sans);color:var(--soft);margin:0;max-width:620px}
.row{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;margin-top:34px}
.stats b{color:var(--ink);font-weight:700}.stats span+span:before{content:"·";margin:0 12px}
.follow{display:flex;gap:10px;flex-wrap:wrap}
.follow a{font:600 12px/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;border:1px solid var(--rule);border-radius:999px;padding:9px 14px}
.follow a:hover{border-color:var(--ink)}.follow .n{color:var(--soft);margin-left:6px}
.chips{display:flex;gap:8px;flex-wrap:wrap;padding:22px 0;border-bottom:1px solid var(--rule)}
.chips a{border:1px solid var(--rule);border-radius:999px;padding:8px 13px}.chips a.on,.chips a:hover{color:var(--ink);border-color:var(--ink)}
.lead{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:56px;padding:48px 0;border-bottom:1px solid var(--rule);align-items:center}
.lead img,.card img{width:100%;aspect-ratio:4/5;object-fit:cover;background:var(--mark);border-radius:4px}
.lead h2{font:800 clamp(32px,3.8vw,50px)/1.04 var(--sans);letter-spacing:-.035em;margin:16px 0 20px}
.lead p{font-size:19px;color:var(--soft);margin:0 0 22px}
.topic{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:48px 36px;padding:48px 0}
.card h3{font:800 22px/1.15 var(--sans);letter-spacing:-.025em;margin:16px 0 10px}
.card:hover h3,.lead:hover h2{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:4px}
.empty{padding:120px 0;text-align:center;color:var(--soft);font:800 32px/1.2 var(--sans);letter-spacing:-.03em}
.story{display:grid;grid-template-columns:minmax(0,440px) minmax(0,1fr);gap:64px;padding:48px 0 24px}
.story h1{font:800 clamp(34px,4.2vw,54px)/1.04 var(--sans);letter-spacing:-.04em;margin:14px 0 26px}
.story .body p{font-size:20px;line-height:1.55;margin:0 0 18px}
.back{display:inline-block;margin-top:34px;font:600 11.5px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--soft)}
.src{margin-top:34px;border-top:1px solid var(--rule);padding-top:20px}
.src ul{list-style:none;padding:0;margin:12px 0 0}.src li{padding:10px 0;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between}
.src li a:after{content:" ↗";color:var(--soft)}
.credit{margin-top:10px;font-size:13px;color:var(--soft)}
.cta{margin-top:34px;padding:22px 24px;background:var(--mark);border-radius:6px;font-size:16px}
.cta a{border-bottom:1px solid var(--accent)}
.top{list-style:none;counter-reset:n;padding:24px 0 0;margin:0}
.top li{counter-increment:n;display:grid;grid-template-columns:90px 120px minmax(0,1fr);gap:28px;align-items:center;padding:24px 0;border-bottom:1px solid var(--rule)}
.top li:before{content:counter(n,decimal-leading-zero);font:800 50px/1 var(--sans);letter-spacing:-.05em;color:var(--accent)}
.top img{width:120px;aspect-ratio:4/5;object-fit:cover;border-radius:3px}
.top h3{font:800 24px/1.15 var(--sans);letter-spacing:-.03em;margin:0 0 8px}
.weeks a{display:inline-block;margin:0 10px 10px 0;border-bottom:1px solid var(--rule)}
footer{border-top:1px solid var(--rule);margin-top:40px;padding:28px 0 48px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:14px;font:600 11.5px/1.6 var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--soft)}
footer a:hover{color:var(--ink)}footer nav{display:flex;gap:20px}
@media(max-width:980px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.lead,.story{grid-template-columns:1fr;gap:28px}.nav a.x{display:none}}
@media(max-width:620px){.wrap{padding:0 20px}.grid{grid-template-columns:1fr}.nav{gap:16px}.top li{grid-template-columns:56px minmax(0,1fr)}.top img{display:none}.top li:before{font-size:38px}}
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


def strip():
    """Where to follow and the numbers: only accounts that exist, only figures the desk measured."""
    st = stats()
    links = "".join(f'<a href="{E(a["url"])}" rel="me noopener">{E(a["name"])}'
                    + (f'<span class="n">{st["followers"][a["name"]]:,}</span>' if st["followers"].get(a["name"]) else "")
                    + "</a>" for a in desk.CONFIG.get("accounts", []) if a.get("url"))
    total = sum(v for v in st["followers"].values() if isinstance(v, int))
    nums = []
    if st["stories"]:
        nums.append(f"<span><b>{st['stories']:,}</b> stories</span>")
    if st["sources"]:
        nums.append(f"<span><b>{st['sources']}</b> newsrooms cited</span>")
    if total:
        nums.append(f"<span><b>{total:,}</b> followers</span>")
    return f'<div class="row"><div class="stats">{"".join(nums)}</div><div class="follow">{links}</div></div>'


SECTIONS = [("/products/", "Products"), ("/projects/", "Projects"), ("/games/", "Games"),
            ("/discoveries/", "Discoveries"), (f"{BASE}/", "News"), ("/about/", "About"), ("/contact/", "Contact")]
TOPIC_ORDER = ["Business", "Markets", "Economy", "Politics", "World", "Tech", "AI", "Culture"]


def topic(p):
    return p.get("topic") or (p.get("categories") or ["News"])[0].title()


def page(title, body, desc="", mast=False):
    """Every page: the main site's bar (its name back home, its sections), then the desk."""
    nav = "".join(f'<a href="{h}"{" class=\"on\"" if n == "News" else (" class=\"x\"" if n not in ("About", "Contact") else "")}>{n}</a>'
                  for h, n in SECTIONS)
    top = (f'<section class="mast"><div class="eyebrow">News desk · keremozdemir.de</div>'
           f'<h1>board<br>read<i>.</i></h1><p>The news that moves business: markets, politics, tech and AI, '
           f'one story at a time, every one with its sources.</p>{strip()}</section>') if mast else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; font-src 'self'; style-src 'unsafe-inline'; form-action https:; base-uri 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="color-scheme" content="light dark">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="boardread." href="{BASE}/feed.xml">
<style>{CSS}</style></head><body>
<div class="bar"><div class="wrap"><a class="home" href="/">Kerem Özdemir</a>
<nav class="nav" aria-label="Sections">{nav}</nav></div></div>
<main class="wrap">{top}{body}
<footer><span>boardread. · a news desk by Kerem Özdemir · written by AI from the reports each story links</span>
<nav><a href="/">Home</a><a href="{BASE}/week/">Top 10</a><a href="{BASE}/feed.xml">RSS</a><a href="/impressum/">Impressum</a><a href="/privacy/">Privacy</a></nav></footer>
</main></body></html>"""


def chips(active=None):
    items = [("", "All")] + [(t.lower(), t) for t in TOPIC_ORDER]
    return '<div class="chips">' + "".join(
        f'<a href="{BASE}/{(slug + "/") if slug else ""}"{" class=\"on\"" if (active or "") == slug else ""}>{name}</a>'
        if not slug else f'<a href="{BASE}/t/{slug}/"{" class=\"on\"" if active == slug else ""}>{name}</a>'
        for slug, name in items) + f'<a href="{BASE}/week/">Top 10</a></div>'


def card(p):
    return (f'<a class="card" href="{BASE}/s/{p["id"]}/"><img src="{BASE}/img/{p["id"]}.jpg" alt="" loading="lazy">'
            f'<h3>{E(p["headlines"][0])}</h3><div class="meta"><span class="topic">{E(topic(p))}</span> · {when(p["published"])}</div></a>')


def lead(p):
    return (f'<a class="lead" href="{BASE}/s/{p["id"]}/"><img src="{BASE}/img/{p["id"]}.jpg" alt="">'
            f'<div><div class="meta"><span class="topic">{E(topic(p))}</span> · {when(p["published"])}</div>'
            f'<h2>{E(p["headlines"][0])}</h2><p>{E(p.get("dek", ""))}</p>'
            f'<div class="meta">Reported by {E("; ".join(p.get("sources") or []))}</div></div></a>')


def listing(rows):
    if not rows:
        return '<div class="empty">The first stories are on their way.</div>'
    return lead(rows[0]) + f'<div class="grid">{"".join(card(p) for p in rows[1:120])}</div>'


def story(p):
    srcs = "".join(f'<li><a href="{E(u)}" rel="nofollow noopener">{E(u.split("/")[2].removeprefix("www."))}</a></li>'
                   for u in p.get("source_urls") or p.get("urls", []))
    paras = "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or p.get("dek") or "").split("\n") if x.strip())
    ig = f' · <a href="{E(p["permalink"])}">Instagram post ↗</a>' if p.get("permalink") else ""
    credit = f'<div class="credit">{E(p["credit"])}</div>' if p.get("credit") else ""
    return page(f'{p["headlines"][0]} · boardread.', f"""<a class="back" href="{BASE}/">← All stories</a>
<article class="story"><div><img src="{BASE}/img/{p['id']}.jpg" alt="">{credit}</div><div>
<div class="meta"><span class="topic">{E(topic(p))}</span> · {when(p['published'])}{ig}</div>
<h1>{E(p['headlines'][0])}</h1><div class="body">{paras}</div>
<div class="src"><div class="meta">Reported by {E('; '.join(p.get('sources') or []))}</div><ul>{srcs}</ul></div>
<div class="cta">The ten stories readers shared most this week: <a href="{BASE}/week/">Top 10</a></div>
</div></article>""", p.get("dek", ""))


def week_page(week, rows):
    items = "".join(f'<li><img src="{BASE}/img/{p["id"]}.jpg" alt=""><a href="{BASE}/s/{p["id"]}/"><h3>{E(p["headlines"][0])}</h3>'
                    f'<div class="meta"><span class="topic">{E(topic(p))}</span> · {E("; ".join(p.get("sources") or []))}</div></a></li>'
                    for p in rows)
    return (f'<a class="back" href="{BASE}/">← All stories</a><section class="mast"><div class="eyebrow">Week {week[-2:]} · {week[:4]}</div>'
            f'<h1>Top 10<i>.</i></h1><p>Most shared this week.</p></section><ol class="top">{items}</ol>')


def rss(title, link, items):
    body = "".join(f"<item><title>{E(t)}</title><link>{E(u)}</link><guid>{E(u)}</guid><pubDate>{d}</pubDate>"
                   f"<description>{E(desc)}</description></item>" for t, u, d, desc in items)
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{E(title)}</title>'
            f"<link>{E(link)}</link><description>The news that moves business</description>{body}</channel></rss>")


def build(out=desk.HERE / "_site"):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "img").mkdir(parents=True)
    shutil.copytree(Path(__file__).resolve().parent.parent / "assets-site" / "fonts", out / "fonts")  # Libre Franklin + its OFL licence
    rows = published()
    shown = []
    for p in rows:
        thumb = desk.MEDIA / p["id"] / "thumb.jpg"
        if thumb.exists():
            shutil.copy(thumb, out / "img" / f"{p['id']}.jpg")
            shown.append(p)
    desc = "Business, markets, politics, tech and AI: every story that matters, with its sources."
    (out / "index.html").write_text(page("boardread. · The news that moves business", chips() + listing(shown), desc, mast=True))
    for t in TOPIC_ORDER:
        d = out / "t" / t.lower()
        d.mkdir(parents=True)
        (d / "index.html").write_text(page(f"{t} · boardread.", chips(t.lower()) + listing([p for p in shown if topic(p) == t]),
                                           desc, mast=True))
    for p in shown:
        d = out / "s" / p["id"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(story(p))
    weeks = {}
    for p in shown:
        weeks.setdefault(week_of(p["published"]), []).append(p)
    this_week = datetime.now(timezone.utc).strftime("%G-W%V")
    issues = []
    for wk in sorted(weeks, reverse=True):
        top = sorted(weeks[wk], key=shared, reverse=True)[:10]
        d = out / "week" / wk
        d.mkdir(parents=True)
        (d / "index.html").write_text(page(f"Top 10 · {wk} · boardread.", week_page(wk, top)))
        if wk != this_week:  # an unfinished week is not an issue yet
            issues.append((wk, top))
    latest = issues[0][0] if issues else (sorted(weeks)[-1] if weeks else None)
    (out / "week").mkdir(exist_ok=True)
    this_top = sorted(weeks.get(this_week, []), key=shared, reverse=True)[:10]
    past = "".join(f'<a href="{BASE}/week/{w}/">Week {w[-2:]} · {w[:4]}</a>' for w in sorted(weeks, reverse=True) if w != this_week)
    (out / "week" / "index.html").write_text(page("Top 10 · boardread.", week_page(this_week, this_top)
        + (f'<div class="src"><div class="meta">Earlier weeks</div><p class="weeks">{past}</p></div>' if past else "")))
    (out / "feed.xml").write_text(rss("boardread", SITE + "/", [
        (p["headlines"][0], f"{SITE}/s/{p['id']}/", format_datetime(datetime.fromisoformat(p["published"])), p.get("dek", ""))
        for p in shown[:50]]))
    (out / "weekly.xml").write_text(rss("boardread weekly", SITE + "/week/", [
        (f"Top 10 · {wk}: {top[0]['headlines'][0]}", f"{SITE}/week/{wk}/",
         format_datetime(datetime.fromisoformat(top[0]["published"]) + timedelta(days=1)),
         " · ".join(p["headlines"][0] for p in top)) for wk, top in issues[:12]]))
    (out / ".nojekyll").write_text("")
    print(f"site: {len(shown)} stories, {len(weeks)} weeks -> {out}")
    return out
