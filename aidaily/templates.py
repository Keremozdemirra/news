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
    """(path, credit, Commons file, kind, alt) of the photo a story carries; kind is person, company or scene.

    Every story gets a picture: the named person, else the company's own photos (its aircraft, its headquarters),
    else a hand-vetted scene that fits the article (scenes.fits). Searching Commons for the other proper names in a
    headline was dropped on 2026-11-27: it gave a Ford car museum for Ontario's premier Doug Ford, an Ebola
    symptoms diagram, Trump at a UFC fight and a satellite view of Russia."""
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


def _breaking(story, dark=False):
    """A label before the meta line of a card whose story scores at the desk's breaking bar, the way Bloomberg,
    CNBC and the FT flag one on Instagram. Ink on a white chip over a photo, white on ink on paper."""
    from . import desk
    if (story.get("score") or 0) < desk.CONFIG.get("breaking_score", 99):
        return ""
    fg, bg = (BLACK, WHITE) if dark else (WHITE, BLACK)
    return (f'<span data-breaking style="display:inline-block;margin-right:16px;padding:5px 14px 4px;background:{bg};color:{fg};'
            f'font-weight:800;letter-spacing:2px;text-transform:uppercase">Breaking</span>')


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
<span class="c-meta" style="font-size:26px;color:#D6D6D6">{_breaking(story, True)}{_meta_html(_meta_card(story), WHITE)}</span>
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
<div style="font-size:24px;color:{GREY}">{_breaking(story)}{_meta_html(_meta_card(story), BLACK)}</div>
<div style="margin-top:88px">{_logo_block(*_own_logo(story), 62)}</div>
<div class="num" style="margin-top:52px;font-size:{300 if len(fig) <= 4 else 250 if len(fig) == 5 else 205}px;font-weight:800;line-height:0.82;letter-spacing:-12px">{e(fig)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 76, 70, 60)}px;font-weight:800;line-height:1.04;letter-spacing:{TRACK}">{t(title)}</h1>
{backer}<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;color:{GREY}">{_breaking(story)}{_meta_html(_meta_card(story), BLACK)}</div>
<div style="margin-top:88px">{_logo_block(*_own_logo(story), 62)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 104, 92, 78)}px;font-weight:800;line-height:1.0;letter-spacing:{TRACK}">{t(title)}</h1>
{_hook(story, title)}<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""


def hook_shown(story):
    """True when a text-only card carries its dek. Only a dek that adds two content words to the headline, short enough
    for three lines, and only when the report has more to say: the detail slide then prints the report alone, so no
    sentence is read twice across the two slides."""
    from . import copy, desk
    title = story.get("headline") or story.get("title") or ""
    dek = (story.get("dek") or "").strip()
    return (layout(story) == "headline" and bool(dek) and len(dek) <= 150 and bool(desk.body(story))
            and len(copy._stems(dek) - copy._stems(title, short=True)) >= 2)


def _hook(story, title):
    """The dek under a text-only headline: the second fact, set where the card was empty paper. Only a dek that adds
    to the headline, and short enough to stay a line or three."""
    if not hook_shown(story):
        return ""
    dek = story["dek"].strip()
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


def number_line(story):
    """The sentence that states the post's figure, as written ("€550M" is "€550 million" in the headline): the headline
    first, then the dek. "" when there is no figure or no sentence of ours states it."""
    from . import copy, desk
    fig = short_figure(story["figure"]) if story.get("figure") else _headline_figure(story)
    raw = story.get("figure") or fig
    if not fig:
        return ""
    title = story.get("headline") or story.get("title") or ""
    for x in (title, (story.get("dek") or "").strip()):
        if x and (desk._in_text(raw, x) or desk._in_text(fig, x) or key_figure(x) == fig) and copy.figure_ok(raw, x):
            return x
    return ""


def number_slide(story, brand=BRAND):
    """The number and its context: the figure set large, the headline or dek sentence that states it, and who reported
    it. None when the post has no figure its own text states (a figure the reader cannot find is not set large)."""
    from . import desk
    line = number_line(story)
    if not line:
        return None
    fig = short_figure(story["figure"]) if story.get("figure") else _headline_figure(story)
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


# Instagram stories, 1080x1920. Brand v2 (brand/v2/BRAND.md): ink #121212 and paper only, Libre Franklin 800 headlines
# tracked -0.03em, photos full-bleed and full colour with their credit. Instagram draws its profile row and progress
# bar over the top ~250 px and the reply bar over the bottom ~250 px, so everything a reader must see sits between
# them. The profile row already says "boardread", so the top carries only the format and the date; the wordmark
# anchors the bottom block with the call to action, the way a newspaper puts its flag on the fold.
# The Graph API publishes no sticker on a story (link, poll, quiz: "not supported", IG User Media reference,
# updated 2026-09-28), so every call to action is set in the image: a quiz points to the next story, the rest to
# the article behind the link in the profile.
STORY_BG = "#121212"
INK, DIM, MUTE, RULE = "#ffffff", "#e2e2e2", "#8f8f8f", "#5a5a5a"
SAFE_TOP, SAFE_BOTTOM, SIDE = 250, 250, 72
CTA_ARTICLE, CTA_ARTICLES, CTA_ANSWER = "Full article: link in bio", "Full articles: link in bio", "Answer in the next story"


def _story_pos(uri, w, h, portrait=True):
    """CSS object-position that keeps the photo's focal point (the face of a portrait) in a w x h frame."""
    try:
        return _pos(uri, w, h, None if portrait else {"scene": True})
    except Exception:  # noqa: BLE001  an unreadable file: a portrait is held at its upper third, a scene at its centre
        return "50% 28%" if portrait else "50% 45%"


def _kicker(kicker, label, on_photo=False):
    shade = "text-shadow:0 2px 18px rgba(0,0,0,.45);" if on_photo else ""
    return (f'<div style="position:absolute;left:{SIDE}px;right:{SIDE}px;top:{SAFE_TOP}px;display:flex;justify-content:space-between;'
            f'align-items:baseline;font-size:34px;font-weight:700;letter-spacing:3px;text-transform:uppercase;{shade}">'
            f'<span>{e(kicker)}</span><span style="color:{DIM if on_photo else MUTE}">{e(label)}</span></div>')


def _foot_row(cta):
    """The bottom of every story: the wordmark and what to do next, on one baseline."""
    return (f'<div style="margin-top:56px;display:flex;justify-content:space-between;align-items:baseline">'
            f'<span style="font-size:58px;font-weight:800;letter-spacing:-0.03em">boardread.</span>'
            f'<span style="font-size:34px;font-weight:700;color:{DIM}">{e(cta)}</span></div>')


def _frame(body, kicker, label, cta, photo="", portrait=False, depth=1060):
    """The 9:16 canvas. A photo runs edge to edge from the top of the frame, `depth` px deep, and fades into the ink
    ground, so the type below never sits on a face; it is cropped on its focal point. body is the bottom-anchored
    column; it grows upward from the foot row."""
    bg = ""
    if photo:
        pos = _story_pos(photo, 1080, depth, portrait)
        bg = (f'<img data-bleed src="{photo}" style="position:absolute;left:0;top:0;width:1080px;height:{depth}px;object-fit:cover;object-position:{pos}">'
              f'<div style="position:absolute;left:0;top:0;width:1080px;height:{depth + 2}px;background:linear-gradient(180deg,'
              f'rgba(18,18,18,.72) 0px,rgba(18,18,18,.35) 300px,rgba(18,18,18,0) 460px,rgba(18,18,18,0) {depth - 420}px,rgba(18,18,18,.85) {depth - 150}px,{STORY_BG} {depth}px)"></div>')
    return head() + f"""
<div style="position:relative;width:1080px;height:1920px;background:{STORY_BG};color:{INK};font-family:'Libre Franklin',sans-serif;overflow:hidden">
{bg}{_kicker(kicker, label, bool(photo))}
<div style="position:absolute;left:{SIDE}px;right:{SIDE}px;top:{SAFE_TOP + 90}px;bottom:{SAFE_BOTTOM}px;display:flex;flex-direction:column;justify-content:flex-end">
{body}{_foot_row(cta)}</div></div></body></html>"""


def _h(text_html, size, color=INK, top=0, weight=800, lh=0.98, track=-0.035):
    return (f'<div style="margin-top:{top}px;font-size:{size}px;font-weight:{weight};line-height:{lh};letter-spacing:{track}em;'
            f'color:{color};text-wrap:balance">{text_html}</div>')


def _scale(text, steps):
    """The largest size whose length bound the text fits: steps is ((max_chars, px), ...), the last px is the floor."""
    for n, px in steps:
        if len(text) <= n:
            return px
    return steps[-1][1]


def _credit(text, size=28):
    """A photo credit is part of the licence, so it is always set, in the same place in the bottom block."""
    return f'<div data-credit style="margin-top:28px;font-size:{size}px;line-height:1.3;color:{MUTE}">{e(text)}</div>' if text else ""


def _story_head(text, size=150, top=0):
    """The big line a typographic story opens with. Markup is passed, so a <br> can place the break."""
    return _h(text, size, top=top, lh=0.9, track=-0.04)


def _story_foot(text):
    return _foot_row(text)


def story_frame(card_uri, kicker="New post"):
    """The post's card on the story canvas: there is something new on the feed."""
    body = (f'<div style="flex:1;display:flex;align-items:center;justify-content:center">'
            f'<img src="{card_uri}" style="width:936px;height:1170px;object-fit:cover;border-radius:10px"></div>')
    return _frame(body, kicker, "", "Comment SOURCE for the links")


def _rows(items, size, gap, num_size=None):
    """Numbered rows: big numeral, headline beside it. No rules: the numerals and the space carry the rhythm."""
    num_size = num_size or size
    return "".join(f'<div style="display:grid;grid-template-columns:{int(num_size * 1.25)}px 1fr;gap:12px;margin-top:{gap if i > 1 else 0}px;align-items:baseline">'
                   f'<span style="font-size:{num_size}px;font-weight:800;color:{MUTE};letter-spacing:-0.03em">{i}</span>'
                   f'<span style="font-size:{size}px;font-weight:800;line-height:1.08;letter-spacing:-0.025em;text-wrap:pretty">{e(h)}</span></div>'
                   for i, h in items)


def story_list(title, headlines, label, foot=CTA_ARTICLES, lead_photo="", lead_credit="", kicker="Briefing"):
    """A numbered list: the last 12 hours, the day's top five, a topic board, the most shared and saved.
    With a photo for the first headline the list becomes a front page: the lead on the photo, the rest under it.
    Without one, the title is set large and the rows fill the frame from the bottom up."""
    n = len(headlines)
    if lead_photo and n >= 3:
        lead, rest = headlines[0], list(enumerate(headlines[1:], 2))
        size = 38 if n >= 5 else 42
        body = (_h(title, 64, color=DIM, lh=1, track=-0.03)
                + f'<div style="margin-top:28px;display:grid;grid-template-columns:78px 1fr;gap:12px;align-items:baseline">'
                f'<span style="font-size:70px;font-weight:800;letter-spacing:-0.03em">1</span>'
                + _h(e(lead), _scale(lead, ((50, 76), (75, 68), (999, 60)))) + '</div>'
                + _credit(lead_credit)
                + f'<div style="margin-top:52px">{_rows(rest, size, 30, 46)}</div>')
        return _frame(body, kicker, label, foot, lead_photo, depth=900)
    size, gap = ((70, 56) if n <= 3 else (58, 44) if n == 4 else (48, 34))
    body = (f'{_story_head(title, 150 if n <= 3 else 130 if n == 4 else 112)}'
            f'<div style="flex:1;min-height:60px"></div>{_rows(list(enumerate(headlines, 1)), size, gap, 72)}')
    return _frame(body, kicker, label, foot)


def story_number(figure, headline, label, unit="", qualifier="", photo="", credit=""):
    """One figure from a published post and the headline it belongs to. A quantity carries its unit; a qualifier the
    headline puts before it ("Up to") stays, so the figure is never stated more firmly than it was."""
    size = 440 if len(figure) <= 3 else 360 if len(figure) <= 4 else 290 if len(figure) <= 6 else 220
    pre = _h(e(qualifier), 72, color=DIM, lh=1) if qualifier else ""
    unit_html = _h(e(unit), 110, top=8, lh=1) if unit else ""
    body = (pre + _h(e(figure), size, top=8 if qualifier else 0, lh=0.84, track=-0.055) + unit_html
            + _h(e(headline), _scale(headline, ((50, 64), (75, 58), (999, 52))), top=56, lh=1.06) + _credit(credit))
    return _frame(body, "The number", label, CTA_ARTICLE, photo, depth=900)


def _logo_chip(uri, h=110, pad="30px 40px"):
    if not uri:
        return ""
    return (f'<div style="display:inline-flex;align-self:flex-start;align-items:center;background:#fff;border-radius:22px;padding:{pad}">'
            f'<img src="{uri}" style="height:{h}px;max-width:620px;object-fit:contain"></div>')


def story_company(logo_uri, name, rows, label, photo="", credit=""):
    """Company file: the company's last headlines, newest first, each with its date, under its logo (on its own
    photo when it has one). rows are (date, headline)."""
    items = "".join(f'<div style="margin-top:{44 if i else 0}px">'
                    f'<div style="font-size:34px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:{MUTE}">{e(d)}</div>'
                    f'<div style="margin-top:10px;font-size:{_scale(h, ((55, 54), (80, 48), (999, 44)))}px;font-weight:800;line-height:1.08;letter-spacing:-0.025em">{e(h)}</div></div>'
                    for i, (d, h) in enumerate(rows))
    top = _logo_chip(logo_uri) or _h(e(name), 120, lh=0.95)
    body = (f'{"" if photo else _story_head("Company<br>file.")}<div style="flex:1;min-height:40px"></div>{top}'
            f'<div style="margin-top:64px">{items}</div>{_credit(credit)}')
    return _frame(body, "Company file", label, CTA_ARTICLES, photo, depth=860)


def story_person(photo_uri, name, headline, credit, label):
    """In the news: the person of the day in a licensed portrait, full frame, with the headline that put them there."""
    body = (_h(e(name), _scale(name, ((14, 150), (20, 124), (999, 104))), lh=0.9, track=-0.045)
            + _h(e(headline), _scale(headline, ((55, 60), (80, 54), (999, 48))), color=DIM, top=36, weight=700, lh=1.12, track=-0.02)
            + _credit(credit))
    return _frame(body, "In the news", label, CTA_ARTICLE, photo_uri, portrait=True, depth=1180)


def _options(options, size=56, cols=1):
    """Lettered options. data-opt marks each one so the answer story and the tests can read them back."""
    tiles = "".join(f'<div data-opt="{"ABCD"[i]}" style="display:flex;gap:28px;align-items:baseline;padding:30px 36px;border:3px solid {RULE};border-radius:18px">'
                    f'<span style="font-size:{size - 8}px;font-weight:800;color:{MUTE}">{"ABCD"[i]}</span>'
                    f'<span data-t style="font-size:{size}px;font-weight:800;letter-spacing:-0.025em;line-height:1.04">{e(o)}</span></div>'
                    for i, o in enumerate(options))
    return f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:20px">{tiles}</div>'


BLANK = f'<span style="display:inline-block;min-width:220px;border-bottom:12px solid {INK}">&nbsp;</span>'


def _marked(headline, mark):
    """The headline as markup with the filled-in value picked out: the one place the answer sits in the sentence."""
    m = re.search(rf"(?<![\w.,$€£]){re.escape(mark)}(?!\w)", headline, re.I) if mark else None
    if not m:
        return e(headline)
    return (f'{e(headline[:m.start()])}<span style="background:{INK};color:{STORY_BG};padding:0 10px;border-radius:8px;'
            f'box-decoration-break:clone;-webkit-box-decoration-break:clone">{e(m.group(0))}</span>{e(headline[m.end():])}')


# Quiz pairs. The answer is the very next story, so swiping from the question must look like one option lighting up
# in place: both frames come from _qa with the same slots. Every block sits at a fixed position, the options have a
# fixed height and one font size for the pair, so neither a longer title nor the filled-in headline can move them.
QA_TITLE_TOP, QA_TITLE_H = 330, 280          # two lines at 140 px
QA_PROMPT_GAP, QA_OPT_GAP, QA_FOOT_TOP = 40, 18, 1558
QA_CELL_H = {"bigger": 350, "photo": 104, "text": 116}


def _fit_px(texts, width, base, floor=34, em=0.6):
    """One font size for every text in the set: the largest that sets the longest on one line in `width` px."""
    n = max((len(t) for t in texts), default=1) or 1
    return max(floor, min(base, int(width / (em * n))))


def _qa_slots(options, kind, photo):
    cols = 1 if kind == "bigger" or max((len(o) for o in options), default=0) > (13 if photo else 10) else 2
    cell_h = QA_CELL_H["bigger" if kind == "bigger" else "photo" if photo else "text"]
    rows = -(-len(options) // cols)
    opt_h = rows * cell_h + (rows - 1) * QA_OPT_GAP
    opt_top = QA_FOOT_TOP - 56 - opt_h
    return cols, cell_h, opt_top


def _qa(options, label, *, title, prompt="", prompt_size=60, kind="text", photo="", credit="", chip="",
        right=None, figs=(), subs=(), kinds=(), cta=CTA_ANSWER, text_px=None):
    """One frame of a quiz pair. right=None is the question; an index is the answer with that option lit."""
    cols, cell_h, opt_top = _qa_slots(options, kind, photo)
    cell_w = (936 - (cols - 1) * 20) // cols
    px = text_px or _fit_px(options, cell_w - 64 - 90, 92 if kind == "bigger" else 58 if cols == 1 else 56)
    cells = ""
    for i, o in enumerate(options):
        on = right == i
        look = (f"background:{INK};color:{STORY_BG};border-color:{INK}" if on else
                f"color:{MUTE if right is not None else INK}")
        x, y = (i % cols) * (cell_w + 20), (i // cols) * (cell_h + QA_OPT_GAP)
        fig = (f'<span style="position:absolute;right:32px;top:30px;font-size:72px;font-weight:800;letter-spacing:-0.03em">{e(figs[i])}</span>'
               if right is not None and i < len(figs) and figs[i] else "")
        sub_c = "#3a3a3a" if on else MUTE
        sub = (f'<div style="position:absolute;left:32px;right:32px;bottom:26px;font-size:34px;font-weight:600;line-height:1.2;color:{sub_c};'
               f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{e(subs[i])}</div>' if right is not None and i < len(subs) and subs[i] else "")
        kind_l = (f'<div style="margin-top:12px;font-size:44px;font-weight:700;color:{sub_c if on else DIM}">{e(kinds[i])}</div>'
                  if i < len(kinds) and kinds[i] else "")
        if kind == "bigger":
            inner = (f'<div style="font-size:64px;font-weight:800;line-height:1;color:{STORY_BG if on else MUTE}">{"AB"[i]}</div>'
                     f'<div style="margin-top:22px;white-space:nowrap"><span data-t style="font-size:{px}px;font-weight:800;line-height:1;letter-spacing:-0.035em">{e(o)}</span></div>'
                     f'{kind_l}{fig}{sub}')
            pad = "28px 32px"
        else:
            inner = (f'<span style="font-size:{px - 6}px;font-weight:800;width:62px;flex:none;color:{STORY_BG if on else MUTE}">{"ABCD"[i]}</span>'
                     f'<span data-t style="font-size:{px}px;font-weight:800;letter-spacing:-0.025em;white-space:nowrap">{e(o)}</span>')
            pad = "0 32px"
        flex = "" if kind == "bigger" else "display:flex;align-items:center;gap:20px;"
        cells += (f'<div data-opt="{"ABCD"[i]}"{" data-on" if on else ""} data-box style="position:absolute;left:{x}px;top:{y}px;width:{cell_w}px;'
                  f'height:{cell_h}px;{flex}padding:{pad};border:3px solid {RULE};border-radius:18px;{look}">{inner}</div>')
    bg = ""
    if photo:
        depth = opt_top - 150
        pos = _story_pos(photo, 1080, depth, True)
        bg = (f'<img data-bleed src="{photo}" style="position:absolute;left:0;top:0;width:1080px;height:{depth}px;object-fit:cover;object-position:{pos}">'
              f'<div style="position:absolute;left:0;top:0;width:1080px;height:{depth + 2}px;background:linear-gradient(180deg,'
              f'rgba(18,18,18,.72) 0px,rgba(18,18,18,.35) 300px,rgba(18,18,18,0) 460px,rgba(18,18,18,0) {depth - 520}px,'
              f'rgba(18,18,18,.9) {depth - 160}px,{STORY_BG} {depth}px)"></div>')
    # with a portrait the title and the prompt sit low, over the fade, so the face keeps the top of the frame
    # one line of title and a short prompt slot (two lines and the credit) beside a portrait
    title_h = 140 if photo else QA_TITLE_H
    title_top = opt_top - 44 - 210 - QA_PROMPT_GAP - title_h if photo else QA_TITLE_TOP
    title_html = (f'<div data-slot="title" style="position:absolute;left:{SIDE}px;right:{SIDE}px;top:{title_top}px;height:{title_h}px;'
                  f'display:flex;align-items:flex-end;justify-content:space-between;gap:24px">'
                  f'<div style="font-size:{132 if photo else 140}px;font-weight:800;line-height:.9;letter-spacing:-0.045em">{title}</div>{chip}</div>')
    p_top = title_top + title_h + QA_PROMPT_GAP
    prompt_html = (f'<div data-slot="prompt" style="position:absolute;left:{SIDE}px;right:{SIDE}px;top:{p_top}px;height:{opt_top - 44 - p_top}px;'
                   f'display:flex;flex-direction:column;justify-content:flex-end;overflow:hidden">'
                   f'<div style="font-size:{prompt_size}px;font-weight:800;line-height:1.14;letter-spacing:-0.025em;color:{INK if right is None else DIM};'
                   f'text-wrap:balance">{prompt}</div>{_credit(credit)}</div>')
    return head() + f"""
<div style="position:relative;width:1080px;height:1920px;background:{STORY_BG};color:{INK};font-family:'Libre Franklin',sans-serif;overflow:hidden">
{bg}{_kicker("Quiz", label, bool(photo))}{title_html}{prompt_html}
<div data-slot="options" style="position:absolute;left:{SIDE}px;top:{opt_top}px;width:936px">{cells}</div>
<div data-slot="foot" style="position:absolute;left:{SIDE}px;right:{SIDE}px;top:{QA_FOOT_TOP}px">{_foot_row(cta).replace('margin-top:56px;', '')}</div>
</div></body></html>"""


def quiz_pair(title, options, right, label, *, hint="", headline="", mark="", kind="text", photo="", q_credit="", a_credit="",
              logo_uri="", figs=(), subs=(), kinds=()):
    """(question, answer) for one quiz, from one set of slots. hint is the question's headline with ___ for the gap;
    headline and mark are the answer's full headline and the value picked out in it."""
    size = (44 if photo else _scale(max(hint, headline, key=len), ((50, 72), (75, 64), (999, 56)))) if (hint or headline) else 60
    cols, cell_h, _ = _qa_slots(options, kind, photo)
    px = _fit_px(options, (936 - (cols - 1) * 20) // cols - 64 - 90, 92 if kind == "bigger" else 58 if cols == 1 else 56)
    common = dict(prompt_size=size, kind=kind, photo=photo, figs=figs, subs=subs, kinds=kinds, text_px=px)
    q = _qa(options, label, title=title, prompt=e(hint).replace("___", BLANK), credit=q_credit, **common)
    chip = _logo_chip(logo_uri, 64, "18px 28px") if logo_uri else ""
    a = _qa(options, label, title=f'<span style="white-space:nowrap">Answer {"ABCD"[right]}</span>', prompt=_marked(headline, mark),
            credit=a_credit, chip=chip, right=right, cta=CTA_ARTICLE, **common)
    return q, a


def story_quiz(hint, label, options=(), title="Guess the<br>company."):
    """The question side of a quiz pair (Guess the company, Fill the number)."""
    return quiz_pair(title, list(options), 0, label, hint=hint)[0]


def story_whois(photo_uri, label, options, credit=""):
    """The question side of Who is this?: the portrait, no name, four names."""
    return quiz_pair("Who is this?", list(options), 0, label, kind="photo", photo=photo_uri, q_credit=credit)[0]


def story_bigger(kind, a, b, label):
    """The question side of Which is bigger?: two companies and the kind of figure compared. No figure."""
    return quiz_pair("Which is<br>bigger?", [a[0], b[0]], 0, label, kind="bigger", kinds=[kind, kind])[0]


def story_answer(letter, options, label, headline="", mark="", logo_uri="", photo_uri="", credit=""):
    """The answer side alone, for callers that have no question; the desk builds both sides with quiz_pair."""
    texts = [o if isinstance(o, str) else o[0] for o in options]
    figs = [("" if isinstance(o, str) else (tuple(o) + ("", ""))[1]) for o in options]
    subs = [("" if isinstance(o, str) else (tuple(o) + ("", ""))[2]) for o in options]
    kind = "bigger" if any(figs) else "photo" if photo_uri else "text"
    return quiz_pair("", texts, "ABCD".index(letter), label, headline=headline, mark=mark, kind=kind, photo=photo_uri,
                     a_credit=credit, logo_uri=logo_uri, figs=figs, subs=subs)[1]


def story_numbers(rows, label):
    """The week in numbers: up to five figures from the week's posts, each with its headline. A row is
    (figure, headline, unit, qualifier); the type steps down with the row count."""
    n = len(rows)
    fig, txt, gap = (130, 40, 52) if n <= 3 else (108, 36, 40) if n == 4 else (96, 34, 32)
    items = ""
    for i, (f, h, *extra) in enumerate(rows):
        u, q = (list(extra) + ["", ""])[:2]
        items += (f'<div style="margin-top:{gap if i else 0}px"><div style="font-size:{fig}px;font-weight:800;letter-spacing:-0.045em;line-height:.92">'
                  + (f'<span style="font-size:{fig * 4 // 10}px;letter-spacing:-0.02em;color:{DIM}">{e(q)} </span>' if q else "")
                  + e(f) + (f'<span style="font-size:{fig // 2}px;letter-spacing:-0.03em"> {e(u)}</span>' if u else "") + '</div>'
                  f'<div style="margin-top:8px;font-size:{txt}px;font-weight:700;line-height:1.16;color:{DIM}">{e(h)}</div></div>')
    body = f'{_story_head("The week<br>in numbers.", 120)}<div style="flex:1;min-height:40px"></div>{items}'
    return _frame(body, "Week in numbers", label, CTA_ARTICLES)


def story_today(logo_uris, label):
    """In the news today: the logos of the companies in today's headlines."""
    # full rows only: a lone tile on the last row reads as a mistake (2x2, 2x3 or 3x3)
    logo_uris = logo_uris[:9] if len(logo_uris) >= 9 else logo_uris[:6] if len(logo_uris) >= 6 else logo_uris[:4]
    n = len(logo_uris)
    cols = 2 if n <= 4 else 3
    side = (936 - 24 * (cols - 1)) // cols
    tiles = "".join(f'<div style="width:{side}px;height:{side}px;background:#fff;border-radius:22px;'
                    f'display:flex;align-items:center;justify-content:center"><img src="{u}" style="max-width:72%;max-height:56%;object-fit:contain"></div>'
                    for u in logo_uris)
    body = (f'{_story_head("In the news<br>today.", 140)}<div style="flex:1;min-height:40px"></div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:24px;width:936px">{tiles}</div>')
    return _frame(body, "Today", label, CTA_ARTICLES)


def story_rates(rows, label, source):
    """Rates and oil: official prints the desk already shows on the site, each with its own date. A row is
    (name, value, change, date); change is the move against the previous print, set with an arrow, never colour."""
    items = "".join(f'<div style="display:grid;grid-template-columns:1fr auto;align-items:baseline;margin-top:{30 if i else 0}px">'
                    f'<div><div style="font-size:52px;font-weight:800;letter-spacing:-0.025em">{e(n)}</div>'
                    f'<div style="margin-top:6px;font-size:34px;font-weight:600;color:{MUTE}">{e(d)}</div></div>'
                    f'<div style="text-align:right"><div style="font-size:76px;font-weight:800;letter-spacing:-0.04em;line-height:1">{e(v)}</div>'
                    f'<div style="margin-top:8px;font-size:38px;font-weight:700;color:{DIM}">{e(c)}</div></div></div>'
                    for i, (n, v, c, d) in enumerate(rows))
    body = (f'{_story_head("Rates and oil.", 104)}<div style="flex:1;min-height:40px"></div>{items}'
            f'<div data-credit style="margin-top:40px;font-size:28px;line-height:1.3;color:{MUTE}">{e(source)}</div>')
    return _frame(body, "Markets", label, "Every rate: link in bio")


def _chart_svg(pts, w=936, h=560):
    """A bare line chart: the series as one white line, a hairline at its first value, the last value marked."""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    xy = [(round(i * w / (len(pts) - 1), 1), round(h - (v - lo) / (hi - lo) * h, 1)) for i, (_, v) in enumerate(pts)]
    line = " ".join(f"{x},{y}" for x, y in xy)
    y0 = xy[0][1]
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display:block;overflow:visible">'
            f'<line x1="0" y1="{y0}" x2="{w}" y2="{y0}" stroke="{RULE}" stroke-width="3" stroke-dasharray="10 10"/>'
            f'<polyline points="{line}" fill="none" stroke="{INK}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{xy[-1][0]}" cy="{xy[-1][1]}" r="14" fill="{INK}"/></svg>')


def story_chart(name, pts, first, last, move, span, label, source):
    """One series over its last months, from the official prints: the name, the move in words a reader can check
    against the line, the first and last values with their dates under the ends of the line."""
    body = (f'{_h(e(name), 120, lh=0.92, track=-0.04)}'
            f'{_h(e(move), 64, color=DIM, top=24, lh=1.05, track=-0.03)}'
            f'<div style="flex:1;min-height:40px"></div>{_chart_svg(pts)}'
            f'<div style="margin-top:28px;display:flex;justify-content:space-between;font-size:34px;font-weight:700;color:{DIM}">'
            f'<span>{e(first)}</span><span style="color:{INK}">{e(last)}</span></div>'
            f'<div data-credit style="margin-top:28px;font-size:28px;line-height:1.3;color:{MUTE}">{e(source)}</div>')
    return _frame(body, f"Chart · {span}", label, "More numbers: link in bio")


def story_follow(handle, line, label):
    body = (_h(e(handle), 172, lh=0.9, track=-0.05)
            + _h(e(line), 76, color=DIM, top=48, lh=1.05, track=-0.03))
    return _frame(body, "Follow", label, "Tap the name above to follow")


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
