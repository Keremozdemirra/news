"""Card templates. The owner approved this system on 2026-09-28.

One family (Libre Franklin), white or near-black ground, no accent colour:
colour comes from the company's logo and the person's photo. A card shows a
logo, the key figure when there is one, the headline and the source, and
nothing else. Three layouts, picked by what the story has:

- photo: a person the story is about, with a reusable Commons photo
- figure: a number in the headline (a round, a price, a percentage)
- headline: everything else
"""
import html
import re
from datetime import datetime

from . import entities

FONTS = "https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;700;800&display=swap"
BRAND = {"name": "boardread.", "handle": "@boardread"}
WHITE, BLACK, GREY, GREY_DARK, LINE = "#fcfcfb", "#111111", "#6f6f6f", "#a3a3a3", "#e4e4e2"
LABEL = {"funding": "Funding", "launch": "Launch", "research": "Research", "policy": "Policy",
         "statement": "Statement", "markets": "Markets", "business": "Business", "news": "News"}
FIGURE = re.compile(r"(?:[$€£]\s?\d[\d,.]*\s?(?:[BMK]\b|billion|million|trillion|bn)?|\b\d[\d,.]*\s?(?:%|percent))", re.I)


def e(s):
    return html.escape(s or "", quote=True)


def key_figure(text):
    m = FIGURE.search(text or "")
    if not m:
        return ""
    f = m.group(0).strip()
    f = re.sub(r"\s?billion", "B", f, flags=re.I)
    f = re.sub(r"\s?million", "M", f, flags=re.I)
    return re.sub(r"\s?percent", "%", f, flags=re.I)


def day(story):
    try:
        return datetime.fromisoformat(story["published"]).strftime("%-d %b %Y")
    except (KeyError, TypeError, ValueError):
        return ""


# Commons files already on recent posts; the desk fills it before a render so no photo repeats for weeks
USED = set()


def assets(story, fetch=True):
    """Logos and a photo for a story, resolved once and kept on the story."""
    if "_assets" not in story:
        co = story.get("company", "")
        lg = entities.logo(co, story.get("company_domain", ""), fetch=fetch)
        bk = entities.logo(story.get("backer", ""), fetch=fetch) if story.get("backer") else None
        names = []
        for n in [co, story.get("backer", "")] + list(story.get("orgs") or []):
            if n and n.lower() not in {x.lower() for x in names}:
                names.append(n)
        logos = []
        for n in names[:3]:
            f = lg if n == co else entities.logo(n, fetch=fetch)
            if f:
                logos.append(f.as_uri())
        subjects = [(story.get("person", ""), True), (story.get("image_query", ""), False), (co, False)]
        ph, credit, file_ = entities.fresh_photo(subjects, USED, fetch=fetch)
        if file_:
            USED.add(file_)
        story["_assets"] = {"logo": lg.as_uri() if lg else "", "backer": bk.as_uri() if bk else "",
                            "logos": logos, "photo": ph.as_uri() if ph else "", "credit": credit, "file": file_}
    return story["_assets"]


def layout(story):
    a = assets(story)
    if a["photo"]:
        return "photo"
    if story.get("figure") or key_figure(story.get("headline") or story["title"]):
        return "figure"
    return "headline"


def head():
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><link href="{FONTS}" rel="stylesheet">'
            "<style>body{margin:0}*{box-sizing:border-box}h1{text-wrap:balance}</style></head><body>")


TOPICS = {"AI", "Tech", "Business", "Markets", "Economy", "Politics", "World", "Culture"}


def _meta(story):
    topic = story.get("topic") if story.get("topic") in TOPICS else LABEL.get(story.get("category"), "News")
    parts = [topic, day(story)]
    return " · ".join(p for p in parts if p)


def _sourceline(story):
    if story.get("primary"):
        return f"Announced by {re.sub(r' [Bb]log$', '', story['primary'])}"
    n = len(story.get("timeline") or story.get("outlets") or [])
    return f"Reported by {n} newsrooms" if n > 1 else f"Source: {story['source']}"


def _logo_tile(uri, size):
    return (f'<div style="width:{size}px;height:{size}px;border-radius:{size // 5}px;overflow:hidden;box-shadow:0 0 0 1px {LINE};'
            f'background:#fff;display:flex;align-items:center;justify-content:center">'
            f'<img src="{uri}" style="width:100%;height:100%;object-fit:contain"></div>')


def _aspect(uri):
    """Width over height of a local SVG from its viewBox or width/height; 4 (a wordmark) when unreadable."""
    try:
        from urllib.parse import unquote, urlparse
        head_ = open(unquote(urlparse(uri).path), encoding="utf-8", errors="replace").read(4000)
        vb = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', head_)
        if vb:
            return float(vb.group(1)) / float(vb.group(2))
        w, h = re.search(r'\swidth="([\d.]+)', head_), re.search(r'\sheight="([\d.]+)', head_)
        return float(w.group(1)) / float(h.group(1)) if w and h else 4.0
    except (OSError, ValueError, ZeroDivisionError):
        return 4.0


def _logo_block(uri, name, h=60, invert=False):
    """A vector logo sits as a wordmark; a raster site icon gets a tile."""
    if not uri:
        return f'<div style="font-size:40px;font-weight:800">{e(name)}</div>' if name else ""
    if uri.endswith(".svg"):
        inv = "filter:invert(1);" if invert else ""
        # a symbol-only logo (Meta's loop) at wordmark height reads as a speck; give it twice the height
        if _aspect(uri) < 1.6:
            h *= 2
        return f'<img src="{uri}" style="height:{h}px;max-width:560px;object-fit:contain;object-position:left;{inv}display:block">'
    return _logo_tile(uri, int(h * 2.4))


def _foot(story, brand, dark=False):
    grey = GREY_DARK if dark else GREY
    credit = assets(story)["credit"]
    c = f'<div style="margin-top:10px;font-size:16px;color:{grey}">{e(credit)}</div>' if credit and layout(story) == "photo" else ""
    return (f'<div><div style="display:flex;justify-content:space-between;align-items:baseline;font-size:24px">'
            f'<span style="font-size:34px;font-weight:800;letter-spacing:-0.5px">{e(brand["name"])}</span>'
            f'<span style="color:{grey}">{e(_sourceline(story))}</span></div>{c}</div>')


def _size(text, big, mid, small):
    n = len(text)
    return big if n < 55 else mid if n < 85 else small


def card(story, brand=BRAND):
    """4:5 card for every platform."""
    a = assets(story)
    title = story.get("headline") or story["title"]
    kind = layout(story)
    if kind == "photo":
        # the photo fills the card; logos of every organisation in the story sit on white chips over it
        chips = "".join(
            f'<div style="height:96px;padding:0 26px;background:#fff;border-radius:20px;display:flex;align-items:center;'
            f'box-shadow:0 6px 24px rgba(0,0,0,.25)"><img src="{u}" style="height:{(76 if _aspect(u) < 1.6 else 44) if u.endswith(".svg") else 72}px;'
            f'max-width:300px;object-fit:contain;display:block"></div>' for u in a.get("logos", []))
        return head() + f"""
<div style="position:relative;width:1080px;height:1350px;background:{BLACK};color:{WHITE};font-family:'Libre Franklin',sans-serif;overflow:hidden">
<img src="{a['photo']}" style="position:absolute;inset:0;width:1080px;height:1350px;object-fit:cover;object-position:50% 25%">
<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.35) 0%,rgba(0,0,0,0) 22%,rgba(0,0,0,0) 38%,rgba(0,0,0,.82) 66%,rgba(0,0,0,.94) 100%)"></div>
<div style="position:absolute;left:64px;right:64px;top:64px;display:flex;gap:18px;flex-wrap:wrap">{chips}</div>
<div style="position:absolute;left:72px;right:72px;bottom:64px;display:flex;flex-direction:column">
<span style="font-size:26px;font-weight:600;color:#d6d6d6">{e(_meta(story))}</span>
<h1 style="margin:22px 0 56px;font-size:{_size(title, 88, 78, 66)}px;font-weight:800;line-height:1.02;letter-spacing:-1.5px">{e(title)}</h1>
{_foot(story, brand, dark=True)}</div></div></body></html>"""
    if kind == "figure":
        fig = story.get("figure") or key_figure(title)
        backer = (f'<div style="margin-top:26px;display:flex;align-items:center;gap:14px;font-size:26px;color:{GREY}"><span>Backed by</span>'
                  f'{_logo_block(a["backer"], story.get("backer", ""), 30)}</div>') if story.get("backer") else ""
        return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(_meta(story))}</div>
<div style="margin-top:88px">{_logo_block(a['logo'], story.get('company', ''), 62)}</div>
<div style="margin-top:52px;font-size:{300 if len(fig) <= 4 else 250 if len(fig) == 5 else 205}px;font-weight:800;line-height:0.82;letter-spacing:-12px">{e(fig)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 76, 70, 60)}px;font-weight:800;line-height:1.04;letter-spacing:-1.5px">{e(title)}</h1>
{backer}<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(_meta(story))}</div>
<div style="margin-top:88px">{_logo_block(a['logo'], story.get('company', ''), 62)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 104, 92, 78)}px;font-weight:800;line-height:1.0;letter-spacing:-2px">{e(title)}</h1>
<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""


def detail(story, body, outlets, brand=BRAND):
    """Second slide of a single-story post: the checked report text and who reported it."""
    a = assets(story)
    title = story.get("headline") or story["title"]
    paras = "".join(f'<p style="margin:0 0 28px">{e(p)}</p>' for p in (body or story.get("dek", "")).split("\n") if p.strip())
    n = len(body or "")
    size = 56 if n < 260 else 50 if n < 380 else 44 if n < 520 else 38
    src = "; ".join(outlets) if outlets else story.get("source", "")
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:24px;font-weight:500;color:{GREY}">{e(_meta(story))}</span>
<div style="opacity:0.9">{_logo_block(a['logo'], '', 34) if a['logo'] else ''}</div></div>
<h2 style="margin:72px 0 0;font-size:52px;font-weight:800;line-height:1.08;letter-spacing:-1px;text-wrap:balance">{e(title)}</h2>
<div style="margin-top:44px;height:2px;width:96px;background:{BLACK}"></div>
<div style="margin-top:44px;font-size:{size}px;font-weight:500;line-height:1.32;letter-spacing:-0.3px">{paras}</div>
<div style="flex:1"></div>
<div style="font-size:24px;color:{GREY};line-height:1.4">Reported by {e(src)}</div>
<div style="margin-top:28px;display:flex;justify-content:space-between;align-items:baseline;font-size:24px">
<span style="font-size:34px;font-weight:800;letter-spacing:-0.5px">{e(brand['name'])}</span><span style="color:{GREY}">keremozdemir.de/news</span></div>
</div></body></html>"""


STORY_BG = "#111214"


def _story_shell(inner, kicker):
    return head() + f"""
<div style="width:1080px;height:1920px;background:{STORY_BG};color:#f2f2f0;font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column;padding:120px 60px 140px">
<div style="display:flex;justify-content:space-between;align-items:baseline">
<span style="font-size:64px;font-weight:800;letter-spacing:-2.5px">boardread.</span>
<span style="font-size:26px;font-weight:600;letter-spacing:3px;text-transform:uppercase;color:#9aa0a8">{e(kicker)}</span></div>
{inner}</div></body></html>"""


def story_frame(card_uri, kicker="New post"):
    """The post's card on the story canvas: the story says there is something new on the feed."""
    inner = (f'<div style="flex:1;display:flex;align-items:center;justify-content:center">'
             f'<img src="{card_uri}" style="width:900px;height:1125px;object-fit:cover;border-radius:22px;'
             f'box-shadow:0 40px 120px rgba(0,0,0,.55)"></div>'
             f'<div style="font-size:34px;font-weight:600;color:#9aa0a8;text-align:center">Full story on the feed · comment SOURCE for the links</div>')
    return _story_shell(inner, kicker)


def story_digest(headlines, label):
    """The evening story: the day's top stories as a numbered list."""
    rows = "".join(f'<div style="display:grid;grid-template-columns:92px 1fr;gap:20px;padding:34px 0;border-top:1px solid #2a2c31">'
                   f'<span style="font-size:52px;font-weight:800;color:#6b7078;letter-spacing:-2px">{i:02d}</span>'
                   f'<span style="font-size:{50 if len(h) < 70 else 44}px;font-weight:800;line-height:1.08;letter-spacing:-1.5px">{e(h)}</span></div>'
                   for i, h in enumerate(headlines, 1))
    inner = (f'<div style="margin-top:110px;font-size:120px;font-weight:800;letter-spacing:-5px;line-height:.92">Today\'s<br>top {len(headlines)}.</div>'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{rows}</div>'
             f'<div style="font-size:34px;font-weight:600;color:#9aa0a8;text-align:center">Every story with its sources: keremozdemir.de/news</div>')
    return _story_shell(inner, label)


def feed_card(story, brand=BRAND, tag=None):
    return card(story, brand)


pro_card = feed_card  # LinkedIn takes the same card


def daily_cover(day_label, headlines, brand=BRAND):
    """First slide of the Instagram carousel: the date, the count, and the stories in swipe order."""
    items = "".join(f'<li style="margin-top:22px"><span style="color:{GREY}">{i:02d}</span>&nbsp;&nbsp;{e(h)}</li>'
                    for i, h in enumerate(headlines, 1))
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(day_label)}</div>
<h1 style="margin:88px 0 0;font-size:128px;font-weight:800;line-height:0.95;letter-spacing:-3px">Today: {len(headlines)} stories</h1>
<div style="flex:1"></div>
<ol style="list-style:none;margin:0;padding:0;font-size:{30 if len(headlines) <= 5 else 27}px;font-weight:500;line-height:1.25">{items}</ol>
<div style="margin-top:64px;display:flex;justify-content:space-between;align-items:baseline;font-size:24px">
<span style="font-size:34px;font-weight:800;letter-spacing:-0.5px">{e(brand['name'])}</span><span style="color:{GREY}">Swipe for each story</span></div>
</div></body></html>"""


def carousel(stories, week_label, brand=BRAND):
    """LinkedIn document post: a cover, then one card per story, printed to PDF."""
    cover = f"""<section style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column;page-break-after:always">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(week_label)}</div><div style="flex:1"></div>
<h1 style="margin:0;font-size:120px;font-weight:800;line-height:0.95;letter-spacing:-3px">Top {len(stories)} this week</h1>
<div style="margin-top:64px;font-size:34px;font-weight:800">{e(brand['name'])}</div></section>"""
    pages = [cover]
    for s in stories:
        inner = card(s, brand).split("<body>", 1)[1].rsplit("</body>", 1)[0]
        pages.append(f'<section style="page-break-after:always">{inner}</section>')
    return head().replace("</style>", "@page{size:1080px 1350px;margin:0}</style>") + "".join(pages) + "</body></html>"
