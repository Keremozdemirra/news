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


def in_headline(name, headline):
    """The name, or its first word when that is distinctive ("Norse" for Norse Atlantic Airways), is in the headline."""
    n = name.lower().strip()
    first = n.split()[0] if n.split() else ""
    return n in headline or (len(first) > 3 and re.search(rf"\b{re.escape(first)}\b", headline) is not None)


# Commons files already on recent posts; the desk fills it before a render so no photo repeats for weeks
USED = set()


def assets(story, fetch=True):
    """Logos and a photo for a story, resolved once and kept on the story."""
    if "_assets" not in story:
        co = story.get("company", "")
        lg = entities.logo(co, story.get("company_domain", ""), fetch=fetch)
        bk = entities.logo(story.get("backer", ""), fetch=fetch) if story.get("backer") else None
        # a logo says "this story is about us": only an organisation the headline names gets one. BCG was quoted
        # in an FCC/SpaceX story and its logo on the card read as if BCG were the news.
        head_ = (story.get("headline") or story.get("title") or "").lower()
        names = []
        for n in [co, story.get("backer", "")] + list(story.get("orgs") or []):
            if n and n.lower() not in {x.lower() for x in names} and in_headline(n, head_):
                names.append(n)
        logos, logo_names = [], []
        for n in names[:3]:
            f = lg if n == co else entities.logo(n, fetch=fetch)
            if f:
                logos.append(f.as_uri())
                logo_names.append(n)
        # the company's own photos (its aircraft, its headquarters) beat a generic scene the model suggests
        subjects = [(story.get("person", ""), True), (co, False), (story.get("image_query", ""), False)]
        ph, credit, file_ = entities.fresh_photo(subjects, USED, fetch=fetch, allow=head_ + " " + (co or ""))
        if file_:
            USED.add(file_)
        story["_assets"] = {"logo": lg.as_uri() if lg else "", "backer": bk.as_uri() if bk else "",
                            "logos": logos, "logo_names": logo_names, "photo": ph.as_uri() if ph else "",
                            "credit": credit, "file": file_}
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
<img src="{a['photo']}" style="position:absolute;inset:0;width:1080px;height:1350px;object-fit:cover;object-position:50% {'25%' if story.get('person') else '50%'}">
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


def detail(story, body, outlets, brand=BRAND, so_what="", label="What it means"):
    """Second slide of a single-story post: the checked report text and who reported it.
    A checked "what it means" sentence, when there is one, sits under the report with a small label."""
    a = assets(story)
    title = story.get("headline") or story["title"]
    paras = "".join(f'<p style="margin:0 0 28px">{e(p)}</p>' for p in (body or story.get("dek", "")).split("\n") if p.strip())
    n = len(body or "")
    size = 56 if n < 260 else 50 if n < 380 else 44 if n < 520 else 38
    meaning = ""
    if so_what:
        size = max(size - 6, 34)  # the extra block needs the room
        meaning = (f'<div style="margin-top:8px;padding-top:36px;border-top:1px solid {LINE}">'
                   f'<div style="font-size:22px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:{GREY}">{e(label)}</div>'
                   f'<div style="margin-top:16px;font-size:{max(size - 4, 34)}px;font-weight:700;line-height:1.28;letter-spacing:-0.3px">{e(so_what)}</div></div>')
    src = "; ".join(outlets) if outlets else story.get("source", "")
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:24px;font-weight:500;color:{GREY}">{e(_meta(story))}</span>
<div style="opacity:0.9">{_logo_block(a['logo'], '', 34) if a['logo'] else ''}</div></div>
<h2 style="margin:72px 0 0;font-size:52px;font-weight:800;line-height:1.08;letter-spacing:-1px;text-wrap:balance">{e(title)}</h2>
<div style="margin-top:44px;height:2px;width:96px;background:{BLACK}"></div>
<div style="margin-top:44px;font-size:{size}px;font-weight:500;line-height:1.32;letter-spacing:-0.3px">{paras}</div>{meaning}
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
             f'<div style="font-size:34px;font-weight:600;color:#9aa0a8;text-align:center">Comment SOURCE for the links</div>')
    return _story_shell(inner, kicker)


def _story_foot(text):
    return f'<div style="font-size:34px;font-weight:600;color:#9aa0a8;text-align:center">{e(text)}</div>'


def _story_head(text, size=120, top=100):
    """The big line a story opens with. The caller passes markup, so a <br> can place the break."""
    return f'<div style="margin-top:{top}px;font-size:{size}px;font-weight:800;letter-spacing:-6px;line-height:.9">{text}</div>'


def _story_tag(text):
    return (f'<div style="margin-top:100px;font-size:40px;font-weight:700;letter-spacing:4px;text-transform:uppercase;'
            f'color:#9aa0a8">{e(text)}</div>')


def story_list(title, headlines, label, compact=False, foot="On the feed"):
    """A numbered list: the last 12 hours, the day's top five, a topic board, the most shared and saved."""
    few = len(headlines) <= 3
    big, small, pad = (40, 36, 22) if compact else (62, 54, 56) if few else (50, 44, 34)
    rows = "".join(f'<div style="display:grid;grid-template-columns:{110 if few else 92}px 1fr;gap:20px;padding:{pad}px 0;border-top:1px solid #2a2c31">'
                   f'<span style="font-size:{big + 2}px;font-weight:800;color:#6b7078;letter-spacing:-2px">{i:02d}</span>'
                   f'<span style="font-size:{big if len(h) < 70 else small}px;font-weight:800;line-height:1.08;letter-spacing:-1.5px">{e(h)}</span></div>'
                   for i, h in enumerate(headlines, 1))
    inner = (f'<div style="margin-top:{70 if compact else 110}px;font-size:{104 if compact else 120}px;font-weight:800;letter-spacing:-5px;line-height:.92">{title}</div>'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{rows}</div>{_story_foot(foot)}')
    return _story_shell(inner, label)


def story_number(figure, headline, label, unit=""):
    """One figure from a published post, and the headline it belongs to. A quantity carries its unit beside it."""
    size = 330 if len(figure) <= 4 else 270 if len(figure) <= 6 else 210
    unit = f'<div style="margin-top:24px;font-size:100px;font-weight:800;letter-spacing:-4px;line-height:1">{e(unit)}</div>' if unit else ""
    inner = (f'{_story_tag("Number")}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">'
             f'<div style="font-size:{size}px;font-weight:800;letter-spacing:-14px;line-height:.85">{e(figure)}</div>{unit}'
             f'<div style="margin-top:70px;font-size:60px;font-weight:800;line-height:1.08;letter-spacing:-2px">{e(headline)}</div></div>'
             f'{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def _logo_chip(uri, h=130, pad="34px 44px"):
    if not uri:
        return ""
    return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;background:#fff;border-radius:28px;padding:{pad}">'
            f'<img src="{uri}" style="height:{h}px;max-width:620px;object-fit:contain"></div>')


def story_company(logo_uri, name, rows, label):
    """Company file: the logo and the company's last headlines, each with its date. rows are (date, headline)."""
    items = "".join(f'<div style="padding:34px 0;border-top:1px solid #2a2c31">'
                    f'<div style="font-size:30px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#9aa0a8">{e(d)}</div>'
                    f'<div style="margin-top:10px;font-size:50px;font-weight:800;line-height:1.1;letter-spacing:-1.5px">{e(h)}</div></div>'
                    for d, h in rows)
    top = _logo_chip(logo_uri) or f'<div style="font-size:120px;font-weight:800;letter-spacing:-5px">{e(name)}</div>'
    inner = (f'{_story_head("Company<br>file.")}<div style="margin-top:56px">{top}</div>'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{items}</div>{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def story_person(photo_uri, name, headline, credit, label):
    """In the news: the person of the day in a licensed portrait, with the headline that put them there."""
    inner = (f'<div style="margin-top:80px;font-size:40px;font-weight:700;letter-spacing:4px;text-transform:uppercase;color:#9aa0a8">In the news</div>'
             f'<div style="margin-top:36px;border-radius:24px;overflow:hidden;height:1010px"><img src="{photo_uri}" style="width:100%;height:100%;object-fit:cover;object-position:50% 25%"></div>'
             f'<div style="margin-top:44px;font-size:96px;font-weight:800;letter-spacing:-4px;line-height:.95">{e(name)}</div>'
             f'<div style="margin-top:24px;font-size:44px;font-weight:700;line-height:1.15;letter-spacing:-1px;color:#d6d6d4">{e(headline)}</div>'
             f'<div style="flex:1"></div><div style="font-size:22px;color:#6b7078;text-align:center;margin-bottom:18px">{e(credit)}</div>{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def _options(options, size=52):
    return "".join(f'<div style="display:flex;gap:30px;align-items:center;padding:24px 34px;border:3px solid #3a3d43;border-radius:22px;margin-top:20px">'
                   f'<span style="font-size:{size - 4}px;font-weight:800;color:#9aa0a8">{"ABCD"[i]}</span>'
                   f'<span style="font-size:{size}px;font-weight:800;letter-spacing:-1.5px;line-height:1.05">{e(o)}</span></div>'
                   for i, o in enumerate(options))


BLANK = '<span style="display:inline-block;min-width:200px;border-bottom:10px solid #f2f2f0">&nbsp;</span>'


def story_quiz(hint, label, options=(), title="Guess the<br>company."):
    """A headline with one gap and lettered options; the answer is the next story. Guess the company,
    Fill the number and Complete the headline all use it."""
    hint_html = e(hint).replace("___", BLANK)
    size = 64 if len(hint) < 75 else 56
    inner = (f'{_story_head(title)}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center"><div style="font-size:{size}px;font-weight:800;line-height:1.12;letter-spacing:-2px">{hint_html}</div>'
             f'<div style="margin-top:56px">{_options(options)}</div></div>{_story_foot("Answer on the next story")}')
    return _story_shell(inner, label)


def story_whois(photo_uri, label, options, credit=""):
    """Who is this?: a licensed portrait, no name, four names. The answer is the next story."""
    inner = (f'{_story_head("Who is<br>this?", top=70)}'
             f'<div style="margin-top:36px;border-radius:24px;overflow:hidden;height:600px"><img src="{photo_uri}" style="width:100%;height:100%;object-fit:cover;object-position:50% 25%"></div>'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;margin-top:10px">{_options(options, 46)}</div>'
             f'<div style="font-size:22px;color:#6b7078;text-align:center;margin:26px 0 18px">{e(credit)}</div>{_story_foot("Answer on the next story")}')
    return _story_shell(inner, label)


def story_bigger(kind, a, b, label):
    """Which is bigger?: two companies and the kind of figure compared, each with its logo chip when there is one. No figure."""
    def side(letter, co):
        chip = _logo_chip(co[1], 84, "20px 30px")
        chip = f'<div style="margin-bottom:22px">{chip}</div>' if chip else ""
        return (f'<div style="padding:50px 0;border-top:1px solid #2a2c31;display:grid;grid-template-columns:110px 1fr;gap:20px;align-items:center">'
                f'<span style="font-size:96px;font-weight:800;color:#9aa0a8;line-height:1">{letter}</span>'
                f'<div>{chip}<span style="font-size:64px;font-weight:800;line-height:1.1;letter-spacing:-2px">{e(co[0])} {e(kind)}</span></div></div>')
    inner = (f'{_story_head("Which is<br>bigger?")}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{side("A", a)}{side("B", b)}</div>'
             f'{_story_foot("Answer on the next story")}')
    return _story_shell(inner, label)


def story_answer(letter, value, lines, label, logo_uri="", photo_uri="", credit=""):
    """Every quiz answer reads "Answer: <letter> <value>." and then shows what it was about."""
    text = f"Answer: {letter} {value}."
    size = 120 if len(text) <= 18 else 100 if len(text) <= 26 else 80
    media = _logo_chip(logo_uri)
    if photo_uri:
        media = (f'<div style="border-radius:24px;overflow:hidden;height:640px"><img src="{photo_uri}" '
                 f'style="width:100%;height:100%;object-fit:cover;object-position:50% 25%"></div>')
    rows = "".join(f'<div style="font-size:{72 if len(lines) == 1 else 48}px;font-weight:800;line-height:1.1;letter-spacing:-2px">{e(l)}</div>' for l in lines)
    cred = f'<div style="font-size:22px;color:#6b7078;text-align:center;margin-bottom:18px">{e(credit)}</div>' if credit else ""
    inner = (f'<div style="margin-top:110px;font-size:{size}px;font-weight:800;letter-spacing:-5px;line-height:.92;text-wrap:balance">{e(text)}</div>'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;gap:50px">{media}{rows}</div>{cred}{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def story_numbers(rows, label):
    """The week in numbers: five figures from the week's posts, each with its headline."""
    items = "".join(f'<div style="padding:30px 0;border-top:1px solid #2a2c31"><div style="font-size:104px;font-weight:800;letter-spacing:-5px;line-height:.95">{e(f)}'
                    + (f'<span style="font-size:56px;letter-spacing:-2px"> {e(u[0])}</span>' if u and u[0] else "") + '</div>'
                    f'<div style="margin-top:10px;font-size:36px;font-weight:700;line-height:1.15;color:#d6d6d4">{e(h)}</div></div>' for f, h, *u in rows)
    inner = (f'{_story_head("The week<br>in numbers.", 110)}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{items}</div>{_story_foot("keremozdemir.de/news")}')
    return _story_shell(inner, label)


def story_today(logo_uris, label):
    """In the news today: the logos of the companies in today's headlines, nothing else."""
    n = len(logo_uris)
    cols = 2 if n <= 4 else 3
    tiles = "".join(f'<div style="width:{(960 - 40 * (cols - 1)) // cols}px;height:{(960 - 40 * (cols - 1)) // cols}px;background:#fff;border-radius:34px;'
                    f'display:flex;align-items:center;justify-content:center"><img src="{u}" style="max-width:70%;max-height:60%;object-fit:contain"></div>'
                    for u in logo_uris)
    inner = (f'{_story_head("In the news<br>today.", 110)}'
             f'<div style="flex:1;display:flex;align-items:center;justify-content:center">'
             f'<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:40px;width:960px">{tiles}</div></div>')
    return _story_shell(inner, label)


def story_follow(handle, line, label):
    inner = (f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">'
             f'<div style="font-size:176px;font-weight:800;letter-spacing:-9px;line-height:.9">{e(handle)}</div>'
             f'<div style="margin-top:56px;font-size:64px;font-weight:800;line-height:1.1;letter-spacing:-2px;color:#d6d6d4">{e(line)}</div></div>')
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


# The daily recap reel: 1080x1920 frames in the card style (white ground, Libre Franklin, no accent colour).
# The opening line is the brand and the date, nothing that announces the video.

def _reel_shell(inner):
    return head() + (f'<div style="width:1080px;height:1920px;background:{WHITE};color:{BLACK};'
                     f"font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column;padding:0\">{inner}</div></body></html>")


def reel_cover(date_label):
    """date_label is the whole opening line, "Boardread · 26 Nov"."""
    return _reel_shell(
        f'<div style="flex:1;display:flex;align-items:center;padding:0 72px">'
        f'<div style="font-size:92px;font-weight:800;letter-spacing:-3px;line-height:1.05">{e(date_label)}</div></div>')


def reel_card(n, total, headline, topic, card_uri=""):
    """One story. With the post's own card image it is shown whole under a counter; without it the headline is set big."""
    top = (f'<div style="padding:120px 72px 0;display:flex;justify-content:space-between;align-items:baseline;'
           f'font-size:34px;font-weight:600;color:{GREY}"><span>{n:02d} / {total:02d}</span><span>{e(topic)}</span></div>')
    if card_uri:
        mid = (f'<div style="flex:1;display:flex;align-items:center"><img src="{card_uri}" '
               f'style="width:1080px;height:1350px;display:block"></div>')
    else:
        mid = (f'<div style="flex:1;display:flex;align-items:center;padding:0 72px"><h1 style="margin:0;'
               f'font-size:{_size(headline, 104, 92, 78)}px;font-weight:800;line-height:1.02;letter-spacing:-2px">{e(headline)}</h1></div>')
    # the card already carries the brand; the frame needs only the counter above it
    return _reel_shell(top + mid + '<div style="height:120px"></div>')


def reel_end(url="keremozdemir.de/news"):
    return _reel_shell(
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 72px">'
        f'<div style="font-size:84px;font-weight:800;letter-spacing:-3px;line-height:1.05">{e(url)}</div></div>')
