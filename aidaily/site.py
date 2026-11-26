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


CSS = """
:root{--ink:#111;--grey:#6f6f6f;--line:#e4e4e2;--bg:#fcfcfb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:17px/1.5 -apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif}
a{color:inherit}main{max-width:1080px;margin:0 auto;padding:40px 24px 80px}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:12px;border-bottom:2px solid var(--ink);padding-bottom:18px}
.brand{font-size:30px;font-weight:800;letter-spacing:-.5px;text-decoration:none}
.tag{color:var(--grey)}nav a{margin-left:18px;font-weight:600;text-decoration:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:28px;margin-top:32px}
.item img{width:100%;aspect-ratio:4/5;object-fit:cover;border:1px solid var(--line);border-radius:6px;display:block}
.item h2{font-size:20px;line-height:1.2;margin:12px 0 6px;letter-spacing:-.2px}
.item a{text-decoration:none}.meta{color:var(--grey);font-size:14px}
article{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:40px;margin-top:32px}
article img{width:100%;border:1px solid var(--line);border-radius:6px}
article h1{font-size:38px;line-height:1.08;letter-spacing:-.8px;margin:0 0 18px}
.sources li{margin:6px 0}.cta{margin-top:28px;padding:18px 20px;border:1px solid var(--line);border-radius:8px}
ol.week{padding-left:22px}ol.week li{margin:0 0 26px}
.strip{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;padding:14px 0;border-bottom:1px solid var(--line);color:var(--grey);font-size:15px}
.strip b{color:var(--ink)}.follow a{margin-left:16px;font-weight:600;color:var(--ink);text-decoration:none}.n{color:var(--grey);font-weight:400}
footer{margin-top:64px;padding-top:18px;border-top:1px solid var(--line);color:var(--grey);font-size:14px}
@media(max-width:760px){article{grid-template-columns:1fr}article h1{font-size:30px}}
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
    """Where to follow, and the numbers: only accounts that exist, only figures the desk measured."""
    st = stats()
    links = [f'<a href="{E(a["url"])}" rel="me noopener">{E(a["name"])}'
             + (f' <span class="n">{st["followers"][a["name"]]:,}</span>' if st["followers"].get(a["name"]) else "")
             + "</a>" for a in desk.CONFIG.get("accounts", []) if a.get("url")]
    total = sum(v for v in st["followers"].values() if isinstance(v, int))
    nums = [f"<b>{st['stories']:,}</b> stories"] if st["stories"] else []
    if st["sources"]:
        nums.append(f"<b>{st['sources']}</b> newsrooms cited")
    if total:
        nums.append(f"<b>{total:,}</b> followers")
    if not links and not nums:
        return ""
    return (f'<div class="strip"><span>{" · ".join(nums)}</span>'
            f'<span class="follow">{"".join(links)}</span></div>')


def page(title, body, desc=""):
    news = desk.CONFIG.get("newsletter_url")
    sub = f'<a href="{E(news)}">Weekly email</a>' if news else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action https:; base-uri 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{E(title)}</title><meta name="description" content="{E(desc)}">
<link rel="alternate" type="application/rss+xml" title="boardread" href="{BASE}/feed.xml">
<style>{CSS}</style></head><body><main>
<header><div><a class="brand" href="{BASE}/">boardread.</a> <span class="tag">The news that moves business</span></div>
<nav><a href="{BASE}/week/">Top 10</a>{sub}<a href="{BASE}/feed.xml">RSS</a></nav></header>
{strip()}
{body}
<footer>Summaries written with AI, checked against the reports they cite. Every story links its sources.
<br><a href="/impressum/">Impressum</a> · <a href="/privacy/">Privacy</a> · <a href="/">keremozdemir.de</a></footer>
</main></body></html>"""


def card(p):
    return (f'<div class="item"><a href="{BASE}/s/{p["id"]}/"><img src="{BASE}/img/{p["id"]}.jpg" alt="" loading="lazy">'
            f'<h2>{E(p["headlines"][0])}</h2></a><div class="meta">{E(p.get("topic") or (p.get("categories") or [""])[0].title())} · '
            f'{when(p["published"])}</div></div>')


def story(p):
    srcs = "".join(f'<li><a href="{E(u)}" rel="nofollow noopener">{E(u.split("/")[2])}</a></li>'
                   for u in p.get("source_urls") or p.get("urls", []))
    paras = "".join(f"<p>{E(x)}</p>" for x in (p.get("body") or p.get("dek") or "").split("\n") if x.strip())
    ig = f'<p><a href="{E(p["permalink"])}">See the post on Instagram</a></p>' if p.get("permalink") else ""
    credit = f'<p class="meta">{E(p["credit"])}</p>' if p.get("credit") else ""
    return page(p["headlines"][0], f"""<article><div><img src="{BASE}/img/{p['id']}.jpg" alt="">{credit}</div><div>
<div class="meta">{E(p.get('topic') or (p.get('categories') or [''])[0].title())} · {when(p['published'])}</div>
<h1>{E(p['headlines'][0])}</h1>{paras}
<h3>Reported by {E('; '.join(p.get('sources') or []))}</h3><ul class="sources">{srcs}</ul>{ig}
<div class="cta"><a href="{BASE}/week/">This week's Top 10</a>: the stories readers shared most.</div>
</div></article>""", p.get("dek", ""))


def week_page(week, rows):
    items = "".join(f'<li><a href="{BASE}/s/{p["id"]}/"><strong>{E(p["headlines"][0])}</strong></a><br>'
                    f'{E(p.get("dek", ""))}<br><span class="meta">{E("; ".join(p.get("sources") or []))}</span></li>'
                    for p in rows)
    return f'<h1>Top 10 · {week}</h1><p class="meta">Most shared this week.</p><ol class="week">{items}</ol>'


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
    rows = published()
    shown = []
    for p in rows:
        thumb = desk.MEDIA / p["id"] / "thumb.jpg"
        if thumb.exists():
            shutil.copy(thumb, out / "img" / f"{p['id']}.jpg")
            shown.append(p)
    (out / "index.html").write_text(page("boardread · The news that moves business",
                                         f'<div class="grid">{"".join(card(p) for p in shown[:120])}</div>'
                                         if shown else "<p>The first stories are on their way.</p>",
                                         "Business, markets, politics, tech and AI: every story that matters, with its sources."))
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
        (d / "index.html").write_text(page(f"Top 10 · {wk}", week_page(wk, top)))
        if wk != this_week:  # an unfinished week is not an issue yet
            issues.append((wk, top))
    latest = issues[0][0] if issues else (sorted(weeks)[-1] if weeks else None)
    (out / "week").mkdir(exist_ok=True)
    (out / "week" / "index.html").write_text(page("Top 10",
        (f'<p>Latest issue: <a href="{BASE}/week/{latest}/">{latest}</a></p>' if latest else "<p>No issue yet.</p>")
        + "<ul>" + "".join(f'<li><a href="{BASE}/week/{w}/">{w}</a></li>' for w in sorted(weeks, reverse=True)) + "</ul>"))
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
