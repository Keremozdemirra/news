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
from datetime import datetime, timezone

from . import entities, scenes

FONTS = "https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;700;800&display=swap"
BRAND = {"name": "boardread.", "handle": "@boardread"}
# brand v2 (brand/v2/BRAND.md, 2026-11-26): ink, paper, grey and hairline; black and white only, flat surfaces
WHITE, BLACK, GREY, GREY_DARK, LINE = "#FFFFFF", "#121212", "#5A5A5A", "#C9C9C9", "#E2E2E2"
TRACK = "-0.03em"  # Franklin 800 headlines and the wordmark, as the site and the brand sheet set them
LABEL = {"funding": "Funding", "launch": "Launch", "research": "Research", "policy": "Policy",
         "statement": "Statement", "markets": "Markets", "business": "Business", "news": "News"}
FIGURE = re.compile(r"(?:(?<![A-Za-z])(?:[A-Z]{1,2})?[$€£]\s?\d[\d,.]*\s?(?:[BMK]\b|billion|million|trillion|bn)?|\b\d[\d,.]*\s?(?:%|percent))", re.I)


def e(s):
    return html.escape(s or "", quote=True)


def typo(s):
    """Typographer's quotes and apostrophes for text set large on a card: 'fake' reads as a typo at 88 px."""
    s = s or ""
    s = re.sub(r"(?<=\w)'(?=\w)", "\u2019", s)               # it's, Nvidia's
    s = re.sub(r"(^|[\s(\[{\u2014-])'", "\\1\u2018", s)     # opening single
    s = s.replace("'", "\u2019")                               # closing single, and plural possessive
    s = re.sub(r'(^|[\s(\[{\u2014-])"', "\\1\u201c", s)     # opening double
    return s.replace('"', "\u201d")


def t(s):
    """Escaped, with typographer's quotes: every headline and report line on a card or slide goes through this."""
    return e(typo(s))


def key_figure(text):
    m = FIGURE.search(text or "")
    if not m:
        return ""
    f = m.group(0).strip()
    f = re.sub(r"\s?billion", "B", f, flags=re.I)
    f = re.sub(r"\s?million", "M", f, flags=re.I)
    return re.sub(r"\s?percent", "%", f, flags=re.I)


def short_figure(fig):
    """"C$8.5 billion" -> "C$8.5B", "40 percent" -> "40%": the unit words shortened, every other character kept
    (key_figure would read "$8.5 billion" out of it and drop the C)."""
    f = re.sub(r"\s?billion\b", "B", fig or "", flags=re.I)
    f = re.sub(r"\s?million\b", "M", f, flags=re.I)
    f = re.sub(r"\s?trillion\b", "T", f, flags=re.I)
    return re.sub(r"\s?percent\b", "%", f, flags=re.I).strip()


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
LAST = {}  # file -> when a post last used it, for the scene photos' least-recently-used rotation


def pick_photo(story, head_, co, fetch=True, sport=False):
    """(path, credit, Commons file, kind, alt) of the photo a story carries; kind is person, company, name or scene.

    Every story gets a picture, from the nearest to the story outward: the named person, the company's own photos
    (its aircraft, its headquarters), another proper name the headline carries (a place, an organisation), and last
    a hand-vetted scene for the topic. A search that guessed at a topic once put a stranger's wall on a story, so the
    scenes are a fixed list and the rest only use files whose own title names the subject."""
    allow = head_ + " " + (co or "")
    title = story.get("headline") or story.get("title") or ""
    ph, credit, file_, kind, alt = None, "", "", "", ""
    # a club name finds a city, a street or a bridge ("Sunderland"); sport looks for the named ground instead
    # the person's role picks the right one of several people with the name (entities.person_entity); the company's
    # own photo only when the headline names the company, like its logo: a Stellantis plant in France once ran over
    # a headline about Ontario's premier
    own_co = co if co and in_headline(co, head_) else ""
    for tag, subject in [("person", (story.get("person", ""), True, story.get("person_role", "") if not sport else None)),
                         ("company", (story.get("image_query", "") if sport else own_co, False))]:
        ph, credit, file_ = entities.fresh_photo([subject], USED, fetch=fetch, allow=allow, teams=sport)
        if file_:
            kind = tag
            break
    if not file_ and fetch and not sport:
        for name in entities.headline_names(title, skip=[story.get("person", ""), co]):
            if entities.is_human(name):
                continue
            ph, credit, file_ = entities.fresh_photo([(name, False)], USED, fetch=fetch, allow=allow, strict=True)
            if file_:
                kind = "name"
                break
    if not file_ and fetch:
        text = title + " " + story.get("summary", "")
        ph, credit, file_, alt = scenes.photo(text, story.get("topic", ""), USED, LAST, fetch=fetch, sport=sport)
        kind = "scene" if file_ else ""
    if file_:
        USED.add(file_)
        LAST[file_] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ph, credit, file_, kind, alt


def assets(story, fetch=True):
    """Logos and a photo for a story, resolved once and kept on the story."""
    if "_assets" not in story:
        co = story.get("company", "")
        # a club or event is a subject for a photo; its badge is a trademark, so sport shows no logo
        sport = story.get("lane") == "sport" or story.get("topic") == "Sport"
        lg = None if sport else entities.logo(co, story.get("company_domain", ""), fetch=fetch)
        bk = entities.logo(story.get("backer", ""), fetch=fetch) if story.get("backer") and not sport else None
        # a logo says "this story is about us": only an organisation the headline names gets one. BCG was quoted
        # in an FCC/SpaceX story and its logo on the card read as if BCG were the news.
        head_ = (story.get("headline") or story.get("title") or "").lower()
        names = []
        for n in ([] if sport else [co, story.get("backer", "")] + list(story.get("orgs") or [])):
            if n and n.lower() not in {x.lower() for x in names} and in_headline(n, head_):
                names.append(n)
        logos, logo_names = [], []
        # the main company without a logo of its own: another organisation's logo alone would read as its story
        if co and co in names and not lg:
            names = []
        for n in names[:3]:
            f = lg if n == co else entities.logo(n, fetch=fetch)
            if f:
                logos.append(f.as_uri())
                logo_names.append(n)
        ph, credit, file_, kind, alt = pick_photo(story, head_, co, fetch, sport)
        # a ticker names a listed company, so it follows the logo rule: the story's own company, named in the headline
        tk = entities.ticker(co, fetch=fetch) if co and co in names else None
        story["_assets"] = {"logo": lg.as_uri() if lg else "", "backer": bk.as_uri() if bk else "", "ticker": tk,
                            "logos": logos, "logo_names": logo_names, "photo": ph.as_uri() if ph else "",
                            "credit": credit, "file": file_, "kind": kind, "alt": alt}
    return story["_assets"]


def _own_logo(story):
    """(logo uri, name) for the story's company, only when the headline names it: on 2026-11-27 Stellantis's logo
    headed a slide about Ontario's premier because the company was named further down the report."""
    a = assets(story)
    co = story.get("company", "")
    if co and co in (a.get("logo_names") or []):
        return a["logo"], co
    if co and not a.get("logo") and in_headline(co, (story.get("headline") or story.get("title") or "").lower()):
        return "", co  # no logo file: the name is set in type, and only because the headline names it too
    return "", ""


def layout(story):
    a = assets(story)
    if a["photo"]:
        return "photo"
    if story.get("figure") or _headline_figure(story):
        return "figure"
    return "headline"


def _headline_figure(story):
    """The headline's own figure, unless the copy step left the figure out on purpose (a word, or a number with a
    qualifier such as "more than £400m" that a giant "£400m" would drop)."""
    from . import copy
    title = story.get("headline") or story["title"]
    fig = key_figure(title)
    return fig if fig and copy.figure_ok(fig, title) and copy.figure_ok(fig, story.get("dek", "")) else ""


def head():
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><link href="{FONTS}" rel="stylesheet">'
            "<style>body{margin:0}*{box-sizing:border-box}h1,h2{text-wrap:balance}"
            ".num{font-variant-numeric:tabular-nums}.kick{font-weight:700}</style></head><body>")


TOPICS = {"AI", "Tech", "Business", "Markets", "Economy", "Politics", "World", "Culture", "Sport"}


def _meta(story):
    topic = story.get("topic") if story.get("topic") in TOPICS else LABEL.get(story.get("category"), "News")
    parts = [topic, day(story)]
    return " · ".join(p for p in parts if p)


def domain():
    from . import desk  # desk imports render, which imports this module: resolved at call time
    return desk.brand_domain()


def _meta_card(story):
    """The topic and date line of a card, with how many newsrooms carried it (the footer's right side is the domain)."""
    return f"{_meta(story)} · {_sourceline(story)}"


def _meta_html(text, ink):
    """The meta line as the site sets it: the kicker (the topic, before the first " · ") in Franklin 700 ink, the
    rest in 500 secondary, figures tabular."""
    kick, _, rest = text.partition(" · ")
    rest = f'<span style="font-weight:500"> · {e(rest)}</span>' if rest else ""
    return f'<span class="num"><span class="kick" style="color:{ink}">{e(kick)}</span>{rest}</span>'


def _sourceline(story):
    if story.get("primary"):
        return f"Announced by {re.sub(r' [Bb]log$', '', story['primary'])}"
    from . import desk  # resolved at call time: desk imports render, which imports this module
    names = desk.outlets(story, story)
    n = len(names)
    return f"Reported by {n} newsrooms" if n > 1 else f"Source: {names[0] if names else desk.outlet(story['source'])}"


def _logo_tile(uri, size):
    return (f'<div style="width:{size}px;height:{size}px;overflow:hidden;outline:1px solid {LINE};'
            f'background:#fff;display:flex;align-items:center;justify-content:center">'
            f'<img src="{uri}" style="width:100%;height:100%;object-fit:contain"></div>')


_POS = {}


def _pos(uri, w, h, about=None):
    """CSS object-position for the photo at `uri` in a w x h box, centred on its focal point (the face of a portrait), so the crop
    does not cut the forehead or the chin. `about`: a dict with person / photo_file of the story, or None for a portrait."""
    from urllib.parse import unquote, urlparse
    from . import focus
    path = unquote(urlparse(uri).path) if uri.startswith("file:") else ""
    if (path, bool(about)) not in _POS:
        at = focus.for_post(about if about is not None else {"person": "portrait"}, path)[0] if path else focus.PRIOR_SCENE
        _POS[path, bool(about)] = (at, focus.jpeg_size(path) or (w, h))
    at, size = _POS[path, bool(about)]
    return focus.object_position(at, size, w / h)


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


def _foot(story, brand, dark=False, edited=False):
    grey = GREY_DARK if dark else GREY
    credit = assets(story)["credit"]
    if edited and credit and re.search(r"\bCC BY\b", credit):
        credit += ". Edited"  # CC BY 4.0 3(a)(1)(B): say the material was modified; a moving crop is a modification
    c = f'<div style="margin-top:10px;font-size:16px;color:{grey}">{e(credit)}</div>' if credit and layout(story) == "photo" else ""
    return (f'<div><div style="display:flex;justify-content:space-between;align-items:baseline;font-size:24px">'
            f'<span style="font-size:34px;font-weight:800;letter-spacing:{TRACK}">{e(brand["name"])}</span>'
            f'<span style="color:{grey}">{e(domain())}</span></div>{c}</div>')


def _size(text, big, mid, small):
    n = len(text)
    return big if n < 55 else mid if n < 85 else small


def card(story, brand=BRAND, motion=False, height=1350):
    """4:5 card for every platform.

    motion: the photo layout without its photo, on a transparent ground, for cardvideo.py to lay over the moving
    photo; its parts carry class names so the video can bring them in one by one. height 1920 is the same card as a
    9:16 Reel, with the text kept clear of the bands Instagram draws its own buttons and caption over."""
    a = assets(story)
    title = story.get("headline") or story["title"]
    kind = layout(story)
    if kind == "photo":
        # the photo fills the card; logos of every organisation in the story sit on white chips over it
        chips = "".join(
            f'<div style="height:96px;padding:0 26px;background:#fff;display:flex;align-items:center">'
            f'<img src="{u}" style="height:{(76 if _aspect(u) < 1.6 else 44) if u.endswith(".svg") else 72}px;'
            f'max-width:300px;object-fit:contain;display:block"></div>' for u in a.get("logos", []))
        tall = height > 1350
        top, side, bottom = (240, 150, 420) if tall else (64, 72, 64)
        grad = ("rgba(0,0,0,.35) 0%,rgba(0,0,0,0) 18%,rgba(0,0,0,0) 34%,rgba(0,0,0,.84) 58%,rgba(0,0,0,.94) 100%" if tall else
                "rgba(0,0,0,.35) 0%,rgba(0,0,0,0) 22%,rgba(0,0,0,0) 38%,rgba(0,0,0,.82) 66%,rgba(0,0,0,.94) 100%")
        photo = "" if motion else (f'<img src="{a["photo"]}" style="position:absolute;inset:0;width:1080px;height:{height}px;object-fit:cover;'
                                   f'object-position:{_pos(a["photo"], 1080, height, {"person": story.get("person"), "photo_file": story.get("photo_file")})}">')
        return head().replace("<body>", "<body style=\"background:transparent\">" if motion else "<body>") + f"""
<div style="position:relative;width:1080px;height:{height}px;background:{'transparent' if motion else BLACK};color:{WHITE};font-family:'Libre Franklin',sans-serif;overflow:hidden">
{photo}
<div class="c-grad" style="position:absolute;inset:0;background:linear-gradient(180deg,{grad})"></div>
<div class="c-chips" style="position:absolute;left:64px;right:64px;top:{top}px;display:flex;gap:18px;flex-wrap:wrap">{chips}</div>
<div style="position:absolute;left:72px;right:{side}px;bottom:{bottom}px;display:flex;flex-direction:column">
<span class="c-meta" style="font-size:26px;color:#D6D6D6">{_meta_html(_meta_card(story), WHITE)}</span>
<h1 class="c-head" style="margin:22px 0 56px;font-size:{_size(title, 88, 78, 66)}px;font-weight:800;line-height:1.02;letter-spacing:{TRACK}">{t(title)}</h1>
<div class="c-foot">{_foot(story, brand, dark=True, edited=motion)}</div></div></div></body></html>"""
    if kind == "figure":
        # one way to set a big figure: "C$8.5 billion" from the copy step reads "C$8.5B", like every other card
        fig = short_figure(story["figure"]) if story.get("figure") else _headline_figure(story)
        # "Backed by" says an investor put money in: only on a funding round, never on a buyout or a loan
        funding = re.search(r"\b(raises?|raised|funding|round|valuation|valued)\b", title, re.I)
        backer = (f'<div style="margin-top:26px;display:flex;align-items:center;gap:14px;font-size:26px;color:{GREY}"><span>Backed by</span>'
                  f'{_logo_block(a["backer"], story.get("backer", ""), 30)}</div>') if story.get("backer") and funding else ""
        return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;color:{GREY}">{_meta_html(_meta_card(story), BLACK)}</div>
<div style="margin-top:88px">{_logo_block(*_own_logo(story), 62)}</div>
<div class="num" style="margin-top:52px;font-size:{300 if len(fig) <= 4 else 250 if len(fig) == 5 else 205}px;font-weight:800;line-height:0.82;letter-spacing:-12px">{e(fig)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 76, 70, 60)}px;font-weight:800;line-height:1.04;letter-spacing:{TRACK}">{t(title)}</h1>
{backer}<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;color:{GREY}">{_meta_html(_meta_card(story), BLACK)}</div>
<div style="margin-top:88px">{_logo_block(*_own_logo(story), 62)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 104, 92, 78)}px;font-weight:800;line-height:1.0;letter-spacing:{TRACK}">{t(title)}</h1>
{_hook(story, title)}<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""


def _hook(story, title):
    """The dek under a text-only headline: the second fact, set where the card was empty paper. Only a dek that adds
    to the headline, and short enough to stay a line or three."""
    from . import copy
    dek = (story.get("dek") or "").strip()
    # two content words the headline lacks, or it is the headline again
    if not dek or len(dek) > 150 or len(copy._stems(dek) - copy._stems(title, short=True)) < 2:
        return ""
    return (f'<div style="margin-top:36px;padding-top:28px;border-top:2px solid {BLACK};font-size:38px;font-weight:500;'
            f'line-height:1.28;color:{GREY}">{t(dek)}</div>')


def detail(story, body, outlets, brand=BRAND, so_what="", label="What it means"):
    """Second slide of a single-story post: the checked report text and who reported it.
    A checked "what it means" sentence, when there is one, sits under the report with a small label."""
    a = assets(story)
    title = story.get("headline") or story["title"]
    paras = "".join(f'<p style="margin:0 0 28px">{t(p)}</p>' for p in (body or story.get("dek", "")).split("\n") if p.strip())
    n = len(body or "")
    size = 56 if n < 260 else 50 if n < 380 else 44 if n < 520 else 38
    meaning = ""
    if so_what:
        size = max(size - 6, 34)  # the extra block needs the room
        meaning = (f'<div style="margin-top:8px;padding-top:36px;border-top:1px solid {LINE}">'
                   f'<div style="font-size:22px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:{GREY}">{e(label)}</div>'
                   f'<div style="margin-top:16px;font-size:{max(size - 4, 34)}px;font-weight:700;line-height:1.28;letter-spacing:-0.3px">{t(so_what)}</div></div>')
    from . import desk
    src = desk.reported_by(outlets) if outlets else story.get("source", "")
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="display:flex;justify-content:space-between;align-items:center;min-height:68px;padding-bottom:20px;border-bottom:2px solid {BLACK}"><span style="font-size:24px;color:{GREY}">{_meta_html(_meta(story), BLACK)}</span>
<div style="opacity:0.9">{_logo_block(_own_logo(story)[0], '', 34) if _own_logo(story)[0] else ''}</div></div>
<h2 style="margin:56px 0 0;font-size:52px;font-weight:800;line-height:1.08;letter-spacing:{TRACK}">{t(title)}</h2>
<div style="margin-top:40px;font-size:{size}px;font-weight:500;line-height:1.32;letter-spacing:-0.3px">{paras}</div>{meaning}
<div style="flex:1"></div>
<div style="padding-top:24px;border-top:1px solid {LINE};font-size:24px;color:{GREY};line-height:1.4">Reported by {e(src)}</div>
<div style="margin-top:28px;display:flex;justify-content:space-between;align-items:baseline;font-size:24px">
<span style="font-size:34px;font-weight:800;letter-spacing:{TRACK}">{e(brand['name'])}</span><span style="color:{GREY}">{e(domain())}</span></div>
</div></body></html>"""


def _slide(story, kicker, inner, brand=BRAND):
    """A paper slide of the extended carousel: kicker row on the 2px section rule, the content, the footer."""
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="min-height:68px;padding-bottom:20px;border-bottom:2px solid {BLACK};font-size:24px;color:{GREY};display:flex;align-items:center">{_meta_html(kicker + " · " + _meta(story), BLACK)}</div>
{inner}
<div style="flex:1"></div>
<div style="margin-top:28px;display:flex;justify-content:space-between;align-items:baseline;font-size:24px">
<span style="font-size:34px;font-weight:800;letter-spacing:{TRACK}">{e(brand['name'])}</span><span style="color:{GREY}">{e(domain())}</span></div>
</div></body></html>"""


def number_slide(story, brand=BRAND):
    """The number and its context: the figure set large, the headline or dek sentence that states it, and who reported
    it. None when the post has no figure its own text states (a figure the reader cannot find is not set large)."""
    from . import copy, desk
    fig = short_figure(story["figure"]) if story.get("figure") else _headline_figure(story)
    raw = story.get("figure") or fig
    title = story.get("headline") or story.get("title") or ""
    # the sentence that states it, as written ("€550M" is "€550 million" in the headline)
    line = next((x for x in (title, story.get("dek") or "")
                 if raw and (desk._in_text(raw, x) or desk._in_text(fig, x) or key_figure(x) == fig)), "")
    if not fig or not line or not copy.figure_ok(raw, line):
        return None
    names = desk.outlets(story, story)
    src = f"Source: {desk.reported_by(names)}" if names else ""
    size = 300 if len(fig) <= 4 else 250 if len(fig) <= 6 else 190
    inner = (f'<div class="num" style="margin-top:120px;font-size:{size}px;font-weight:800;line-height:0.86;letter-spacing:{TRACK}">{e(fig)}</div>'
             f'<div style="margin-top:72px;font-size:52px;font-weight:700;line-height:1.16;letter-spacing:-0.01em">{t(line)}</div>'
             f'<div style="margin-top:40px;font-size:26px;color:{GREY}">{e(src)}</div>')
    return _slide(story, "The number", inner, brand)


def sources_slide(story, outlets, cta=False, brand=BRAND):
    """Every newsroom that reported it, in the order they ran it, and where the links are."""
    names = list(outlets) or [story.get("source", "")]
    shown = names[:8]
    rows = "".join(f'<li style="display:flex;gap:28px;padding:22px 0;border-bottom:1px solid {LINE}">'
                   f'<span class="num" style="color:{GREY};width:44px">{i:02d}</span><span>{e(n)}</span></li>'
                   for i, n in enumerate(shown, 1))
    more = f'<div style="margin-top:20px;font-size:28px;color:{GREY}">and {len(names) - 8} more</div>' if len(names) > 8 else ""
    ask = ("Comment SOURCE and we send the links to your DMs." if cta else
           f"Every link is on the article at {domain()}.")
    head_ = f"Reported by {len(names)} newsrooms" if len(names) > 1 else f"Reported by {names[0]}"
    # one newsroom is named in the heading; a list of one would say it twice
    listed = (f'<ol style="list-style:none;margin:48px 0 0;padding:0;font-size:40px;font-weight:700;border-top:1px solid {LINE}">'
              f'{rows}</ol>{more}') if len(names) > 1 else ""
    inner = (f'<h2 style="margin:64px 0 0;font-size:72px;font-weight:800;line-height:1.02;letter-spacing:{TRACK}">{e(head_)}</h2>'
             f'{listed}'
             f'<div style="margin-top:48px;font-size:34px;font-weight:500;line-height:1.3">{e(ask)}</div>')
    return _slide(story, "Sources", inner, brand)


STORY_BG = "#111214"
INK, DIM, MUTE, RULE = "#f2f2f0", "#9aa0a8", "#6b7078", "#2a2c31"
# Instagram draws its profile row and progress bar over the top ~250 px of a story and the reply bar over the
# bottom ~250 px; everything a reader must see stays between them, so the wordmark sits just below the top band.
SAFE_TOP, SAFE_BOTTOM, SIDE = 250, 250, 64


def _story_shell(inner, kicker):
    return head() + f"""
<div style="width:1080px;height:1920px;background:{STORY_BG};color:{INK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column;padding:{SAFE_TOP}px {SIDE}px {SAFE_BOTTOM}px">
<div style="display:flex;justify-content:space-between;align-items:baseline">
<span style="font-size:60px;font-weight:800;letter-spacing:-2.5px">boardread.</span>
<span style="font-size:34px;font-weight:600;letter-spacing:3px;text-transform:uppercase;color:{DIM}">{e(kicker)}</span></div>
{inner}</div></body></html>"""


def story_frame(card_uri, kicker="New post"):
    """The post's card on the story canvas: the story says there is something new on the feed."""
    inner = (f'<div style="flex:1;display:flex;align-items:center;justify-content:center">'
             f'<img src="{card_uri}" style="width:880px;height:1100px;object-fit:cover;border-radius:22px;'
             f'box-shadow:0 40px 120px rgba(0,0,0,.55)"></div>'
             f'{_story_foot("Comment SOURCE for the links")}')
    return _story_shell(inner, kicker)


def _story_foot(text):
    return f'<div style="font-size:36px;font-weight:600;color:{DIM};text-align:center;padding-top:24px">{e(text)}</div>'


def _credit(text, size=30):
    """A photo credit is part of the licence, so it is always set, in the same place under the picture."""
    return f'<div style="margin-top:16px;font-size:{size}px;line-height:1.25;color:{DIM}">{e(text)}</div>' if text else ""


def _story_head(text, size=112, top=64):
    """The big line a story opens with. The caller passes markup, so a <br> can place the break."""
    return f'<div style="margin-top:{top}px;font-size:{size}px;font-weight:800;letter-spacing:-5px;line-height:.92">{text}</div>'


def _story_tag(text):
    return (f'<div style="margin-top:64px;font-size:40px;font-weight:700;letter-spacing:4px;text-transform:uppercase;'
            f'color:{DIM}">{e(text)}</div>')


def story_list(title, headlines, label, foot="On the feed"):
    """A numbered list: the last 12 hours, the day's top five, a topic board, the most shared and saved.
    The type steps down with the row count so five three-line headlines still fit between the safe zones."""
    n = len(headlines)
    big, pad = (62, 44) if n <= 3 else (54, 34) if n == 4 else (48, 30)
    rows = "".join(f'<div style="display:grid;grid-template-columns:{104 if n <= 3 else 88}px 1fr;gap:16px;padding:{pad}px 0;border-top:1px solid {RULE}">'
                   f'<span style="font-size:{big}px;font-weight:800;color:{MUTE};letter-spacing:-2px">{i:02d}</span>'
                   f'<span style="font-size:{big if len(h) < 66 else big - 4}px;font-weight:800;line-height:1.1;letter-spacing:-1.2px">{t(h)}</span></div>'
                   for i, h in enumerate(headlines, 1))
    inner = (f'{_story_head(title, 104 if n >= 5 else 112)}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{rows}</div>{_story_foot(foot)}')
    return _story_shell(inner, label)


def story_number(figure, headline, label, unit="", qualifier=""):
    """One figure from a published post, and the headline it belongs to. A quantity carries its unit beside it,
    and a qualifier the headline puts before it ("Up to") stays, so the figure is never stated more firmly than it was."""
    size = 300 if len(figure) <= 4 else 250 if len(figure) <= 6 else 200
    pre = f'<div style="margin-bottom:20px;font-size:64px;font-weight:700;letter-spacing:-2px;color:{DIM}">{e(qualifier)}</div>' if qualifier else ""
    unit = f'<div style="margin-top:24px;font-size:96px;font-weight:800;letter-spacing:-4px;line-height:1">{e(unit)}</div>' if unit else ""
    inner = (f'{_story_tag("Number")}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{pre}'
             f'<div style="font-size:{size}px;font-weight:800;letter-spacing:-12px;line-height:.85">{e(figure)}</div>{unit}'
             f'<div style="margin-top:64px;font-size:56px;font-weight:800;line-height:1.1;letter-spacing:-2px">{t(headline)}</div></div>'
             f'{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def _logo_chip(uri, h=130, pad="34px 44px"):
    if not uri:
        return ""
    return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;background:#fff;border-radius:28px;padding:{pad}">'
            f'<img src="{uri}" style="height:{h}px;max-width:560px;object-fit:contain"></div>')


def story_company(logo_uri, name, rows, label):
    """Company file: the logo and the company's last headlines, each with its date. rows are (date, headline)."""
    items = "".join(f'<div style="padding:30px 0;border-top:1px solid {RULE}">'
                    f'<div style="font-size:34px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:{DIM}">{e(d)}</div>'
                    f'<div style="margin-top:10px;font-size:46px;font-weight:800;line-height:1.1;letter-spacing:-1.3px">{t(h)}</div></div>'
                    for d, h in rows)
    top = _logo_chip(logo_uri, 110, "28px 40px") or f'<div style="font-size:110px;font-weight:800;letter-spacing:-5px">{e(name)}</div>'
    inner = (f'{_story_head("Company<br>file.")}<div style="margin-top:48px">{top}</div>'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{items}</div>{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def story_person(photo_uri, name, headline, credit, label):
    """In the news: the person of the day in a licensed portrait, with the headline that put them there."""
    inner = (f'{_story_tag("In the news")}'
             f'<div style="margin-top:30px;border-radius:24px;overflow:hidden;height:700px"><img src="{photo_uri}" style="width:100%;height:100%;object-fit:cover;object-position:{_pos(photo_uri, 912, 700)}"></div>'
             f'{_credit(credit)}'
             f'<div style="margin-top:32px;font-size:88px;font-weight:800;letter-spacing:-4px;line-height:.95">{e(name)}</div>'
             f'<div style="margin-top:20px;font-size:42px;font-weight:700;line-height:1.15;letter-spacing:-1px;color:#d6d6d4">{t(headline)}</div>'
             f'<div style="flex:1"></div>{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def _options(options, size=52):
    return "".join(f'<div style="display:flex;gap:30px;align-items:center;padding:22px 34px;border:3px solid #3a3d43;border-radius:22px;margin-top:18px">'
                   f'<span style="font-size:{size - 4}px;font-weight:800;color:{DIM}">{"ABCD"[i]}</span>'
                   f'<span style="font-size:{size}px;font-weight:800;letter-spacing:-1.5px;line-height:1.05">{e(o)}</span></div>'
                   for i, o in enumerate(options))


BLANK = f'<span style="display:inline-block;min-width:200px;border-bottom:10px solid {INK}">&nbsp;</span>'


def story_quiz(hint, label, options=(), title="Guess the<br>company."):
    """A headline with one gap and lettered options; the answer is the next story. Guess the company,
    Fill the number and Complete the headline all use it."""
    hint_html = e(hint).replace("___", BLANK)
    size = 64 if len(hint) < 75 else 56
    inner = (f'{_story_head(title)}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center"><div style="font-size:{size}px;font-weight:800;line-height:1.12;letter-spacing:-2px">{hint_html}</div>'
             f'<div style="margin-top:44px">{_options(options)}</div></div>{_story_foot("Tap for the answer")}')
    return _story_shell(inner, label)


def story_whois(photo_uri, label, options, credit=""):
    """Who is this?: a licensed portrait, no name, four names. The answer is the next story."""
    inner = (f'{_story_head("Who is this?", top=48)}'
             f'<div style="margin-top:28px;border-radius:24px;overflow:hidden;width:700px;height:515px"><img src="{photo_uri}" style="width:100%;height:100%;object-fit:cover;object-position:{_pos(photo_uri, 700, 515)}"></div>'
             f'{_credit(credit)}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{_options(options, 44)}</div>{_story_foot("Tap for the answer")}')
    return _story_shell(inner, label)


def story_bigger(kind, a, b, label):
    """Which is bigger?: two companies and the kind of figure compared, each with its logo chip when there is one. No figure."""
    def side(letter, co):
        chip = _logo_chip(co[1], 84, "20px 30px")
        chip = f'<div style="margin-bottom:22px">{chip}</div>' if chip else ""
        return (f'<div style="padding:50px 0;border-top:1px solid {RULE};display:grid;grid-template-columns:110px 1fr;gap:20px;align-items:center">'
                f'<span style="font-size:96px;font-weight:800;color:{DIM};line-height:1">{letter}</span>'
                f'<div>{chip}<span style="font-size:64px;font-weight:800;line-height:1.1;letter-spacing:-2px">{e(co[0])} {e(kind)}</span></div></div>')
    inner = (f'{_story_head("Which is<br>bigger?")}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{side("A", a)}{side("B", b)}</div>'
             f'{_story_foot("Tap for the answer")}')
    return _story_shell(inner, label)


def _marked(headline, mark):
    """The headline as markup with the filled-in value picked out: the one place the answer sits in the sentence."""
    m = re.search(rf"(?<![\w.,$€£]){re.escape(mark)}(?!\w)", headline, re.I) if mark else None
    if not m:
        return e(headline)
    return (f'{e(headline[:m.start()])}<span style="background:{INK};color:{STORY_BG};padding:0 8px;border-radius:10px">'
            f'{e(m.group(0))}</span>{e(headline[m.end():])}')


def story_answer(letter, options, label, headline="", mark="", logo_uri="", photo_uri="", credit=""):
    """The answer to a quiz: "Answer D", the full headline with the filled-in value picked out, and the options again
    with the right one lit and the rest dimmed. An option is a string or (text, figure, source headline); the figure
    and headline show beside and under it, which is how Which is bigger? reveals its two numbers."""
    right = "ABCD".index(letter)
    rows = ""
    for i, o in enumerate(options):
        text, fig, sub = (o, "", "") if isinstance(o, str) else (tuple(o) + ("", ""))[:3]
        on = i == right
        sub_c = "#3a3d43" if on else DIM
        size = 52 if len(options) > 2 else 60
        fig_html = f'<span style="margin-left:auto;font-size:{size}px;font-weight:800;letter-spacing:-2px">{e(fig)}</span>' if fig else ""
        sub_html = f'<div style="margin-top:8px;font-size:34px;font-weight:600;line-height:1.2;color:{sub_c}">{e(sub)}</div>' if sub else ""
        look = f"background:{INK};color:{STORY_BG}" if on else f"border:3px solid #3a3d43;color:{DIM}"
        rows += (f'<div style="margin-top:18px;padding:22px 34px;border-radius:22px;{look}">'
                 f'<div style="display:flex;gap:30px;align-items:center"><span style="font-size:{size - 4}px;font-weight:800">{"ABCD"[i]}</span>'
                 f'<span style="font-size:{size}px;font-weight:800;letter-spacing:-1.5px;line-height:1.05">{e(text)}</span>{fig_html}</div>{sub_html}</div>')
    chip = _logo_chip(logo_uri, 70, "18px 28px")
    head_html = (f'<div style="margin-top:64px;display:flex;justify-content:space-between;align-items:center">'
                 f'<span style="font-size:128px;font-weight:800;letter-spacing:-6px;line-height:.92">Answer {e(letter)}</span>{chip}</div>')
    size = 60 if len(headline) < 60 else 54 if len(headline) < 75 else 50
    text = (f'<div style="font-size:{size}px;font-weight:800;line-height:1.18;letter-spacing:-1.5px;color:#d6d6d4">{_marked(headline, mark)}</div>')
    if photo_uri:
        # the portrait sits beside the headline, in the same 1.36:1 frame as the question, so a face is never cut to a strip
        story = (f'<div style="margin-top:36px;display:flex;gap:32px;align-items:flex-start">'
                 f'<div style="flex:none;border-radius:24px;overflow:hidden;width:430px;height:316px"><img src="{photo_uri}" '
                 f'style="width:100%;height:100%;object-fit:cover;object-position:{_pos(photo_uri, 430, 316)}"></div>'
                 f'<div style="font-size:42px;font-weight:800;line-height:1.18;letter-spacing:-1px;color:#d6d6d4">{_marked(headline, mark)}</div></div>'
                 f'{_credit(credit)}')
    else:
        story = f'<div style="margin-top:36px">{text}</div>' if headline else ""
    inner = f'{head_html}{story}<div style="margin-top:44px">{rows}</div><div style="flex:1"></div>{_story_foot("On the feed")}'
    return _story_shell(inner, label)


def story_numbers(rows, label):
    """The week in numbers: up to five figures from the week's posts, each with its headline. A row is
    (figure, headline, unit, qualifier); the type steps down with the row count."""
    n = len(rows)
    fig, txt, pad = (96, 38, 30) if n <= 3 else (80, 36, 24) if n == 4 else (72, 34, 20)
    items = ""
    for f, h, *extra in rows:
        u, q = (list(extra) + ["", ""])[:2]
        items += (f'<div style="padding:{pad}px 0;border-top:1px solid {RULE}"><div style="font-size:{fig}px;font-weight:800;letter-spacing:-4px;line-height:.95">'
                  + (f'<span style="font-size:{fig // 2}px;letter-spacing:-1px;color:{DIM}">{e(q)} </span>' if q else "")
                  + e(f) + (f'<span style="font-size:{fig * 5 // 9}px;letter-spacing:-2px"> {e(u)}</span>' if u else "") + '</div>'
                  f'<div style="margin-top:8px;font-size:{txt}px;font-weight:700;line-height:1.15;color:#d6d6d4">{t(h)}</div></div>')
    inner = (f'{_story_head("The week<br>in numbers.", 96)}'
             f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">{items}</div>{_story_foot("On the feed")}')
    return _story_shell(inner, label)


def story_today(logo_uris, label):
    """In the news today: the logos of the companies in today's headlines, nothing else."""
    # full rows only: a lone tile on the last row reads as a mistake (2x2, 2x3 or 3x2)
    logo_uris = logo_uris[:6] if len(logo_uris) >= 6 else logo_uris[:4] if len(logo_uris) >= 4 else logo_uris
    n = len(logo_uris)
    cols = 2 if n <= 4 else 3
    side = (952 - 36 * (cols - 1)) // cols
    tiles = "".join(f'<div style="width:{side}px;height:{side}px;background:#fff;border-radius:34px;'
                    f'display:flex;align-items:center;justify-content:center"><img src="{u}" style="max-width:70%;max-height:60%;object-fit:contain"></div>'
                    for u in logo_uris)
    inner = (f'{_story_head("In the news<br>today.")}'
             f'<div style="flex:1;display:flex;align-items:center;justify-content:center">'
             f'<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:36px;width:952px">{tiles}</div></div>')
    return _story_shell(inner, label)


def story_follow(handle, line, label):
    inner = (f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center">'
             f'<div style="font-size:160px;font-weight:800;letter-spacing:-8px;line-height:.9">{e(handle)}</div>'
             f'<div style="margin-top:56px;font-size:64px;font-weight:800;line-height:1.1;letter-spacing:-2px;color:#d6d6d4">{e(line)}</div></div>')
    return _story_shell(inner, label)


def feed_card(story, brand=BRAND, tag=None):
    return card(story, brand)


pro_card = feed_card  # LinkedIn takes the same card


def daily_cover(day_label, headlines, brand=BRAND):
    """First slide of the Instagram carousel: the date, the count, and the stories in swipe order."""
    items = "".join(f'<li style="margin-top:22px"><span style="color:{GREY}">{i:02d}</span>&nbsp;&nbsp;{t(h)}</li>'
                    for i, h in enumerate(headlines, 1))
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(day_label)}</div>
<h1 style="margin:88px 0 0;font-size:128px;font-weight:800;line-height:0.95;letter-spacing:-3px">Today: {len(headlines)} stories</h1>
<div style="flex:1"></div>
<ol style="list-style:none;margin:0;padding:0;font-size:{30 if len(headlines) <= 5 else 27}px;font-weight:500;line-height:1.25">{items}</ol>
<div style="margin-top:64px;display:flex;justify-content:space-between;align-items:baseline;font-size:24px">
<span style="font-size:34px;font-weight:800;letter-spacing:{TRACK}">{e(brand['name'])}</span><span style="color:{GREY}">Swipe through the news</span></div>
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


# The daily recap reel: 1080x1920 frames on the story canvas (near-black ground, light type, Libre Franklin),
# the same dark the stories use. The opening frame is the wordmark and the date, nothing that announces the video.

def _reel_shell(inner):
    return head() + (f'<div style="width:1080px;height:1920px;background:{STORY_BG};color:#f2f2f0;'
                     f"font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column\">{inner}</div></body></html>")


def reel_cover(date_label, brand=BRAND):
    """date_label is the day, "26 Nov"."""
    return _reel_shell(
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 72px">'
        f'<div style="font-size:150px;font-weight:800;letter-spacing:-6px;line-height:1">{e(brand["name"])}</div>'
        f'<div style="margin-top:36px;font-size:84px;font-weight:600;color:#9aa0a8;letter-spacing:-2px">{e(date_label)}</div></div>')


def reel_card(n, total, headline, topic, card_uri=""):
    """One story: the card at full width, centred, under a kicker big enough to read on a phone. Without the card
    image the headline is set large instead."""
    kicker = (f'<div style="padding:150px 72px 0;display:flex;justify-content:space-between;align-items:baseline;'
              f'font-size:46px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#9aa0a8">'
              f'<span>{n:02d} / {total:02d}</span><span>{e(topic)}</span></div>')
    if card_uri:
        mid = (f'<div style="flex:1;display:flex;align-items:center"><img src="{card_uri}" '
               f'style="width:1080px;height:1350px;display:block"></div>')
    else:
        mid = (f'<div style="flex:1;display:flex;align-items:center;padding:0 72px"><h1 style="margin:0;'
               f'font-size:{_size(headline, 104, 92, 78)}px;font-weight:800;line-height:1.02;letter-spacing:-2px">{t(headline)}</h1></div>')
    return _reel_shell(kicker + mid + '<div style="height:150px"></div>')


def reel_end(url=None, line="Sources for every story"):
    url = url or domain()
    return _reel_shell(
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 72px">'
        f'<div style="font-size:92px;font-weight:800;letter-spacing:-3px;line-height:1.05">{e(url)}</div>'
        f'<div style="margin-top:36px;font-size:64px;font-weight:600;color:#9aa0a8;letter-spacing:-1.5px">{e(line)}</div></div>')
