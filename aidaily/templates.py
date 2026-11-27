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
    for tag, text, is_person in [("person", story.get("person", ""), True),
                                 ("company", story.get("image_query", "") if sport else co, False)]:
        ph, credit, file_ = entities.fresh_photo([(text, is_person)], USED, fetch=fetch, allow=allow, teams=sport)
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


def _sourceline(story):
    if story.get("primary"):
        return f"Announced by {re.sub(r' [Bb]log$', '', story['primary'])}"
    n = len(story.get("timeline") or story.get("outlets") or [])
    return f"Reported by {n} newsrooms" if n > 1 else f"Source: {story['source']}"


def _logo_tile(uri, size):
    return (f'<div style="width:{size}px;height:{size}px;border-radius:{size // 5}px;overflow:hidden;box-shadow:0 0 0 1px {LINE};'
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
            f'<span style="font-size:34px;font-weight:800;letter-spacing:-0.5px">{e(brand["name"])}</span>'
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
            f'<div style="height:96px;padding:0 26px;background:#fff;border-radius:20px;display:flex;align-items:center;'
            f'box-shadow:0 6px 24px rgba(0,0,0,.25)"><img src="{u}" style="height:{(76 if _aspect(u) < 1.6 else 44) if u.endswith(".svg") else 72}px;'
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
<span class="c-meta" style="font-size:26px;font-weight:600;color:#d6d6d6">{e(_meta_card(story))}</span>
<h1 class="c-head" style="margin:22px 0 56px;font-size:{_size(title, 88, 78, 66)}px;font-weight:800;line-height:1.02;letter-spacing:-1.5px">{e(title)}</h1>
<div class="c-foot">{_foot(story, brand, dark=True, edited=motion)}</div></div></div></body></html>"""
    if kind == "figure":
        fig = story.get("figure") or key_figure(title)
        backer = (f'<div style="margin-top:26px;display:flex;align-items:center;gap:14px;font-size:26px;color:{GREY}"><span>Backed by</span>'
                  f'{_logo_block(a["backer"], story.get("backer", ""), 30)}</div>') if story.get("backer") else ""
        return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(_meta_card(story))}</div>
<div style="margin-top:88px">{_logo_block(a['logo'], story.get('company', ''), 62)}</div>
<div style="margin-top:52px;font-size:{300 if len(fig) <= 4 else 250 if len(fig) == 5 else 205}px;font-weight:800;line-height:0.82;letter-spacing:-12px">{e(fig)}</div>
<div style="flex:1"></div>
<h1 style="margin:0;font-size:{_size(title, 76, 70, 60)}px;font-weight:800;line-height:1.04;letter-spacing:-1.5px">{e(title)}</h1>
{backer}<div style="margin-top:64px">{_foot(story, brand)}</div></div></body></html>"""
    return head() + f"""
<div style="width:1080px;height:1350px;padding:72px;background:{WHITE};color:{BLACK};font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column">
<div style="font-size:24px;font-weight:500;color:{GREY}">{e(_meta_card(story))}</div>
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
<span style="font-size:34px;font-weight:800;letter-spacing:-0.5px">{e(brand['name'])}</span><span style="color:{GREY}">{e(domain())}</span></div>
</div></body></html>"""


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
        return _pos(uri, w, h, None if portrait else {})
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
              f'rgba(18,18,18,.6) 0px,rgba(18,18,18,0) 380px,rgba(18,18,18,0) {depth - 420}px,rgba(18,18,18,.85) {depth - 150}px,{STORY_BG} {depth}px)"></div>')
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


def story_quiz(hint, label, options=(), title="Guess the<br>company."):
    """A headline with one gap and lettered options; the answer is the next story. Guess the company and Fill the
    number use it."""
    hint_html = e(hint).replace("___", BLANK)
    size = _scale(hint, ((50, 76), (75, 66), (999, 58)))
    long_opt = max((len(o) for o in options), default=0) > 10
    body = (f'{_story_head(title, 140)}<div style="flex:1;min-height:40px"></div>'
            f'{_h(hint_html, size, lh=1.14, track=-0.025)}'
            f'<div style="margin-top:64px">{_options(options, 52 if long_opt else 60, 1 if long_opt else 2)}</div>')
    return _frame(body, "Quiz", label, CTA_ANSWER)


def story_whois(photo_uri, label, options, credit=""):
    """Who is this?: a licensed portrait, full frame, no name, four names. The answer is the next story."""
    body = (f'{_story_head("Who is this?", 132)}{_credit(credit)}'
            f'<div style="margin-top:44px">{_options(options, 46, 1 if max(map(len, options)) > 13 else 2)}</div>')
    return _frame(body, "Quiz", label, CTA_ANSWER, photo_uri, portrait=True, depth=1000)


def story_bigger(kind, a, b, label):
    """Which is bigger?: two companies and the kind of figure compared, each with its logo when there is one. No figure."""
    def side(letter, co):
        return (f'<div data-opt="{letter}" style="padding:44px 40px;border:3px solid {RULE};border-radius:22px">'
                f'<div style="font-size:64px;font-weight:800;color:{MUTE};line-height:1">{letter}</div>'
                f'<div style="margin-top:24px"><span data-t style="font-size:{_scale(co[0], ((12, 92), (20, 76), (999, 64)))}px;font-weight:800;'
                f'line-height:1;letter-spacing:-0.035em">{e(co[0])}</span></div>'
                f'<div style="margin-top:10px;font-size:44px;font-weight:700;color:{DIM}">{e(kind)}</div></div>')
    body = (f'{_story_head("Which is<br>bigger?", 150)}<div style="flex:1;min-height:40px"></div>'
            f'{side("A", a)}<div style="margin:22px 0;text-align:center;font-size:44px;font-weight:800;color:{MUTE}">or</div>{side("B", b)}')
    return _frame(body, "Quiz", label, CTA_ANSWER)


def _marked(headline, mark):
    """The headline as markup with the filled-in value picked out: the one place the answer sits in the sentence."""
    m = re.search(rf"(?<![\w.,$€£]){re.escape(mark)}(?!\w)", headline, re.I) if mark else None
    if not m:
        return e(headline)
    return (f'{e(headline[:m.start()])}<span style="background:{INK};color:{STORY_BG};padding:0 10px;border-radius:8px;'
            f'box-decoration-break:clone;-webkit-box-decoration-break:clone">{e(m.group(0))}</span>{e(headline[m.end():])}')


def story_answer(letter, options, label, headline="", mark="", logo_uri="", photo_uri="", credit=""):
    """The answer to a quiz: "Answer D", the full headline with the filled-in value picked out, and the options again
    with the right one lit and the rest dimmed. An option is a string or (text, figure, source headline); the figure
    and headline show beside and under it, which is how Which is bigger? reveals its two numbers. A portrait, when
    the question showed one, fills the frame again."""
    right = "ABCD".index(letter)
    rows = ""
    # beside a portrait the names go two by two, so the face keeps the top of the frame
    pair = bool(photo_uri) and all(isinstance(o, str) and len(o) <= 14 for o in options) and len(options) == 4
    for i, o in enumerate(options):
        text, fig, sub = (o, "", "") if isinstance(o, str) else (tuple(o) + ("", ""))[:3]
        on = i == right
        size = (44 if pair else 50 if photo_uri else 56) if len(options) > 2 else 60
        fig_html = f'<span style="margin-left:auto;font-size:{size + 8}px;font-weight:800;letter-spacing:-0.03em">{e(fig)}</span>' if fig else ""
        sub_html = (f'<div style="margin-top:10px;font-size:34px;font-weight:600;line-height:1.2;color:{"#3a3a3a" if on else MUTE}">{e(sub)}</div>'
                    if sub else "")
        look = f"background:{INK};color:{STORY_BG};border:3px solid {INK}" if on else f"border:3px solid {RULE};color:{MUTE}"
        rows += (f'<div data-opt="{"ABCD"[i]}"{" data-on" if on else ""} style="margin-top:{0 if pair or not i else 18}px;padding:26px 36px;border-radius:18px;{look}">'
                 f'<div style="display:flex;gap:28px;align-items:baseline"><span style="font-size:{size - 6}px;font-weight:800">{"ABCD"[i]}</span>'
                 f'<span data-t style="font-size:{size}px;font-weight:800;letter-spacing:-0.025em;line-height:1.04">{e(text)}</span>{fig_html}</div>{sub_html}</div>')
    chip = f'<div style="margin-top:40px">{_logo_chip(logo_uri, 72, "20px 30px")}</div>' if logo_uri else ""
    head_html = (f'<span style="font-size:{150 if photo_uri else 180}px;font-weight:800;letter-spacing:-0.045em;line-height:.9;white-space:nowrap">'
                 f'Answer {e(letter)}</span>{chip}')
    big = 0 if photo_uri else 8
    text = (_h(_marked(headline, mark), _scale(headline, ((50, 64 + big), (75, 58 + big), (999, 52 + big))), color=DIM, top=48, lh=1.2, track=-0.02)
            if headline else "")
    spacer = "" if photo_uri else '<div style="flex:1;min-height:40px"></div>'
    body = f'{head_html}{spacer}{text}{_credit(credit) if photo_uri else ""}<div style="margin-top:56px;{'display:grid;grid-template-columns:1fr 1fr;gap:18px' if pair else ''}">{rows}</div>'
    return _frame(body, "Quiz", label, CTA_ARTICLE, photo_uri, portrait=True, depth=760)


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


def story_follow(handle, line, label):
    body = (_h(e(handle), 172, lh=0.9, track=-0.05)
            + _h(e(line), 76, color=DIM, top=48, lh=1.05, track=-0.03))
    return _frame(body, "Follow", label, "Tap the name above to follow")


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
               f'font-size:{_size(headline, 104, 92, 78)}px;font-weight:800;line-height:1.02;letter-spacing:-2px">{e(headline)}</h1></div>')
    return _reel_shell(kicker + mid + '<div style="height:150px"></div>')


def reel_end(url=None, line="Sources for every story"):
    url = url or domain()
    return _reel_shell(
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 72px">'
        f'<div style="font-size:92px;font-weight:800;letter-spacing:-3px;line-height:1.05">{e(url)}</div>'
        f'<div style="margin-top:36px;font-size:64px;font-weight:600;color:#9aa0a8;letter-spacing:-1.5px">{e(line)}</div></div>')
