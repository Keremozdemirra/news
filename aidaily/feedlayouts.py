"""A family of 4:5 feed layouts, chosen per story from what its photos support, never twice in a row.

Kerem, 2026-11-27: every card looked the same. A reference post he showed fitted a place photo, a round portrait
and the headline into one frame. Variety is allowed as long as the brand holds: black and white, Newsreader and
Libre Franklin, flat and square, no gradients on the new layouts, green and red only for market moves.

Layouts, in the order they are preferred when the story supports them:

- split: two named parties side by side (two people, or two companies), each with its own licensed photo
- place: the place or scene photo with a round portrait of the person the headline names
- number: the key figure the headline or dek states, set huge under a strip of the photo
- photo: the full-photo card (templates.card), its text on the top or the bottom, whichever is quieter
- type: the headline set large in Newsreader, with a small crop of the photo; for a generic archive scene

choose() returns the first layout that fits and differs from the previous post's. Every photo on a card is
credited on it. Text keeps FEED_SAFE px from the sides and FEED_SAFE_Y from top and bottom: the profile grid crops a 4:5
post to 3:4 (about 34 px a side) and Instagram draws its tag button in the bottom left. The 9:16 numbers are templates.REEL_SAFE_*, shared
with the Reels (reelcard.py).
"""
import re
import unicodedata
import zlib
from pathlib import Path

from . import entities, focus, people, scenes
from . import templates as T

FEED_SAFE = 72  # left and right: the 3:4 grid crop takes about 34 px a side
FEED_SAFE_Y = 64  # top and bottom: the feed shows a 4:5 post whole; the full-photo card has always sat at 64
W, H = 1080, 1350
NAMES = ("split", "place", "number", "photo", "type")
FONT_DIR = Path(__file__).resolve().parent.parent / "assets-site" / "fonts"

# people often in the news whom the quiz lists (people.GROUPS) leave out on purpose: no peer group would be fair
FACES = {
    "heads of government": ["Vladimir Putin", "Benjamin Netanyahu", "Kim Jong Un", "Javier Milei", "Rodrigo Duterte",
                            "Sara Duterte", "Ferdinand Marcos Jr.", "Lai Ching-te", "Lee Jae-myung", "Anthony Albanese",
                            "Christopher Luxon", "Prabowo Subianto", "Cyril Ramaphosa", "Masoud Pezeshkian"],
}
ROLE = {"US governors": "politician governor", "central bankers": "economist central banker",
        "heads of government": "politician president prime minister", "US administration": "politician",
        "tech leaders": "businessperson executive", "finance leaders": "businessperson banker executive",
        "industry chiefs": "businessperson executive"}


def _fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _known():
    """[(full name, role words)] of every listed person; a surname shared by two of them never matches alone."""
    out = []
    for group, sides in people.GROUPS.items():
        for names in sides.values():
            out += [(n, ROLE[group]) for n in names]
    for group, names in FACES.items():
        out += [(n, ROLE[group]) for n in names]
    return out


def _surname(name):
    """The folded last name, trailing y's dropped: "Zelenskyy" and "Zelensky" are one person."""
    parts = [p for p in re.sub(r"\b(Jr|Sr)\.?$", "", name).split() if p]
    return re.sub(r"y+$", "", _fold(parts[-1])) if parts else ""


def _at(name, headline, own=False):
    """Where in the headline the person is named, or -1. A surname followed by a capitalised word is a thing named
    after them ("Trump Tower", "Trump Media"), not the person."""
    full = re.search(rf"(?<![A-Za-z]){re.escape(_fold(name))}(?![a-z])", _fold(headline))
    if full:
        return full.start()
    last = _surname(name)
    # the story's own person was resolved from the article, so a surname two listed people share still counts
    if len(last) < 4 or (not own and sum(1 for n, _ in _known() if _surname(n) == last) > 1):
        return -1
    flat = unicodedata.normalize("NFKD", headline or "").encode("ascii", "ignore").decode()
    for m in re.finditer(rf"(?<![A-Za-z]){re.escape(last)}y*(?:'s|\u2019s)?(?![a-z])", flat, re.I):
        if not re.match(r"\s+[A-Z][a-z]", flat[m.end():]):
            return m.start()
    return -1


def named(name, headline):
    """The person's full name, or a surname no other listed person has, as a word in the headline."""
    return _at(name, headline) >= 0


def people_named(story):
    """[(name, role)] of the people the headline names: the story's own person first, then listed people."""
    head_ = story.get("headline") or story.get("title") or ""
    out = []
    p = story.get("person", "")
    if p and _at(p, head_, own=True) >= 0:
        out.append((p, story.get("person_role") or None))  # "" finds nobody in entities.candidates; None does
    for n, role in _known():
        if named(n, head_) and not any(_surname(n) == _surname(x) for x, _ in out):
            out.append((n, role))
    # the story's own person leads; the rest in headline order, so a split reads left to right like the headline
    return out[:1] + sorted(out[1:], key=lambda r: _at(r[0], head_)) if out and out[0][0] == p else out


def _sport(story):
    return story.get("lane") == "sport" or story.get("topic") == "Sport"


def _shot(subject, story, fetch):
    """{"uri", "credit", "file"} of a fresh licensed photo of one subject, or None. Files go on T.USED at once."""
    head_ = story.get("headline") or story.get("title") or ""
    ph, credit, file_ = entities.fresh_photo([subject], T.USED, fetch=fetch, allow=head_ + " " + (story.get("company") or ""))
    if not file_ or not credit or re.search(r"\bBY-SA\b", credit) or entities.AI_MADE.search(file_):
        return None
    T.USED.add(file_)
    T.BATCH.add(file_)
    return {"uri": ph.as_uri(), "credit": credit, "file": file_}


def extras(story, fetch=True):
    """The second photos the person and two-party layouts need, looked up once and kept on the story.

    portrait: the person the headline names, when the card's own photo is not already them.
    scene: a place or scene photo, when the card's own photo is the person.
    pair: two named parties, each with their own photo: two people, else the company and another organisation."""
    if "_extras" in story:
        return story["_extras"]
    a = T.assets(story, fetch=fetch)
    out = {"portrait": None, "scene": None, "pair": []}
    story["_extras"] = out
    if _sport(story) or not fetch or not a.get("photo"):
        return out
    head_ = story.get("headline") or story.get("title") or ""
    own = {"uri": a["photo"], "credit": a["credit"], "file": a["file"]}
    who = people_named(story)
    if who:
        name, role = who[0]
        if a.get("kind") == "person" and name == story.get("person"):
            out["portrait"] = own
            text = head_ + " " + story.get("summary", "") + " " + story.get("dek", "")
            ph, credit, file_, _alt = scenes.photo(text, story.get("topic", ""), T.USED, T.LAST, fetch=fetch, title=head_,
                                                   batch=T.BATCH, data=_places_only(head_))
            if file_ and credit and not re.search(r"\bBY-SA\b", credit):
                T.USED.add(file_)
                T.BATCH.add(file_)
                out["scene"] = {"uri": ph.as_uri(), "credit": credit, "file": file_}
        else:
            # the card's own photo stands as the place only when it is one: a named ground, the company's premises,
            # or a scene vetted for a place the article names; a generic factory floor says nothing about the person
            placed = a.get("kind") in ("place", "company") or _place_scene(a.get("file", ""), " ".join(
                [head_, story.get("dek", ""), story.get("summary", ""), story.get("body", "")]))
            out["portrait"] = _shot((name, True, role), story, fetch) if placed else None
            out["scene"] = own if out["portrait"] else None
    # exactly two parties: a third named one (Putin beside Zelenskyy and Trump, Kohl's beside Target and Best Buy)
    # would be left off a two-photo card
    if len(who) == 2:
        pair = []
        for name, role in who[:2]:
            shot = out["portrait"] if out["portrait"] and name == who[0][0] else _shot((name, True, role), story, fetch)
            if shot:
                pair.append((name, shot))
        out["pair"] = pair if len(pair) == 2 else []
    if not out["pair"]:
        names = [n for n in a.get("logo_names") or [] if n]
        # "Target, Best Buy and Kohl's": a listed third party may have no logo, so a comma list never splits
        if len(names) == 2 and len(who) < 2 and not re.search(r",[^,]+\band\b", head_):
            names.sort(key=lambda n: _fold(head_).find(_fold(n).split()[0]))  # left to right as the headline reads
            pair = []
            logos = dict(zip(a.get("logo_names") or [], a.get("logos") or []))
            for n in names[:2]:
                shot = own if a.get("kind") == "company" and n == story.get("company") else _shot((n, False), story, fetch)
                # few companies have a licensed photo of their premises: the logo the card already carries stands in
                shot = shot or ({"logo": logos[n]} if logos.get(n) else None)
                if shot:
                    pair.append((n, shot))
            out["pair"] = pair if len(pair) == 2 else []
    return out


# a scene tagged with a place is not always a view of it: euro banknotes are tagged "eurozone", a ballot box "Poland"
PLACE_VIEW = re.compile(r"skyline|building|chamber|harbour|district|towers|bridge|steps|parliament|palace", re.I)


def _is_view(item, text):
    """A vetted scene that shows a place, and the text names that place."""
    return bool(item.get("place")) and PLACE_VIEW.search(item.get("alt", "")) is not None and scenes.fits(item, text)


def _places_only(headline):
    """scenes.json with only the views of a place the headline names: the place layout shows where the story is."""
    data = scenes.load()
    keep = lambda items: [i for i in items if _is_view(i, headline)]  # noqa: E731
    return {**data, "rules": [{**r, "files": keep(r["files"])} for r in data["rules"]],
            "topics": {t: keep(items) for t, items in data["topics"].items()}}


def _place_scene(file_, text):
    """The card's own scene is a view of a place the article (already vetted against it) names."""
    data = scenes.load()
    items = [i for r in data["rules"] for i in r["files"]] + [i for t in data["topics"].values() for i in t]
    return any(i["file"] == file_ and _is_view(i, text) for i in items)


def _figure(story):
    """The key figure, only when the headline or the dek states it: a number the reader can check in the text.
    The copy step's deks add to the headline and seldom repeat its figure (none of 13 on 2026-11-27 did), so the
    dek alone would leave this layout unused."""
    fig = T.short_figure(story["figure"]) if story.get("figure") else T._headline_figure(story)
    core = re.search(r"\d[\d,.]*\d|\d", fig or "")
    text = (story.get("headline") or story.get("title") or "") + " \n " + story.get("dek", "")
    # "$387M" on the card, "$387 million" in the text: the number itself must be there, not inside a longer one
    if not (fig and core and re.search(rf"(?<![\d.,]){re.escape(core.group())}(?![\d]|[.,]\d)", text)):
        return ""
    from . import copy
    # a money amount or a share; a bare count or a year ("2029", "92") says nothing at 300 px
    ok = copy.figure_ok(fig, text) and re.search(r"[$€£%]|bn\b|[BMK]$|trillion|billion|million", fig)
    return fig if ok and len(fig) <= 9 else ""


DEAL = re.compile(r"\b(takeover|merger|merge|acqui\w+|buy\w*|bid|deal|joins?|leav\w+|sues?|pulls?|partner\w*|"
                  r"talks|rival\w*|vs\.?|versus)\b", re.I)


def is_deal(story):
    """Two logos alone carry a card only when the headline sets the two companies against or beside each other."""
    return DEAL.search(story.get("headline") or story.get("title") or "") is not None


def fits(story, fetch=True):
    """The layouts this story supports, most fitting first."""
    a = T.assets(story, fetch=fetch)
    x = extras(story, fetch)
    strong = a.get("photo") and a.get("kind") in ("person", "company", "place")
    out = []
    if x["pair"] and any(not s.get("logo") for _, s in x["pair"]) or len(x["pair"]) == 2 and is_deal(story):
        out.append("split")
    if x["portrait"] and x["scene"] and x["portrait"]["file"] != x["scene"]["file"]:
        out.append("place")
    if _figure(story) and a.get("photo"):
        out.append("number")
    if strong:
        out.append("photo")
    out.append("type")
    if a.get("photo") and not strong:
        out.append("photo")  # a generic archive scene can still fill a card, after the type-led one
    return out


def choose(story, prev="", fetch=True):
    """The first fitting layout that is not the previous post's."""
    options = fits(story, fetch)
    return next((o for o in options if o != prev), options[0])


def quiet_side(uri, person=False):
    """"top" when the upper part of the photo, as the 4:5 card crops it, is calmer than the lower part and holds no
    face; else "bottom". Detail is measured as the mean step between neighbouring pixels of a 36 x 45 grey decode."""
    from urllib.parse import unquote, urlparse
    path = unquote(urlparse(uri).path) if uri.startswith("file:") else ""
    if not path:
        return "bottom"
    import subprocess
    try:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf",
                              "scale=36:45:force_original_aspect_ratio=increase,crop=36:45", "-f", "rawvideo",
                              "-pix_fmt", "gray", "-"], capture_output=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return "bottom"
    if len(raw) < 36 * 45:
        return "bottom"

    def busy(r0, r1):
        steps = [abs(raw[y * 36 + x] - raw[y * 36 + x + 1]) + abs(raw[y * 36 + x] - raw[(y + 1) * 36 + x])
                 for y in range(r0, r1) for x in range(35)]
        return sum(steps) / len(steps)
    # the skin-tone finder is only trusted on a photo of a person: a face low in the frame wants the text on top
    face = focus.detect_face(path) if person else None
    if face:
        return "top" if face[1] > 0.58 else "bottom"
    return "top" if busy(1, 18) < 0.75 * busy(27, 44) else "bottom"


# ---- rendering -------------------------------------------------------------------------------------------------

def _head():
    font = (FONT_DIR / "Newsreader-var.woff2").resolve().as_uri()
    return T.head().replace("<style>", "<style>@font-face{font-family:'Newsreader';font-weight:400 700;"
                            f"src:url('{font}') format('woff2')}}", 1)


SERIF = "'Newsreader','Source Serif 4',Georgia,serif"


def _credits(shots, dark):
    """One line naming every photo's author and licence: both photos on a two-photo card."""
    parts = []
    for label, s in shots:
        c = entities.clean_credit(s["credit"]).removeprefix("Photo: ")
        parts.append(f"{label}: {c}" if label else c)
    # as on every card: Commons holds no picture of today's event, so the reader is told the photos are archive ones
    text = ("Archive photos, not from this event. Photos: " if len(parts) > 1 else
            entities.archive_label("", "") + " Photo: ") + "; ".join(parts)
    grey = T.GREY_DARK if dark else T.GREY
    return f'<div data-credit style="margin-top:10px;font-size:16px;line-height:1.3;color:{grey}">{T.e(text)}</div>'


def _foot(brand, dark, shots):
    grey = T.GREY_DARK if dark else T.GREY
    return (f'<div><div style="display:flex;justify-content:space-between;align-items:baseline;font-size:24px">'
            f'<span style="font-size:34px;font-weight:800;letter-spacing:{T.TRACK}">{T.e(brand["name"])}</span>'
            f'<span style="color:{grey}">{T.e(T.domain())}</span></div>{_credits(shots, dark) if shots else ""}</div>')


def _meta(story, dark):
    ink = T.WHITE if dark else T.BLACK
    grey = "#D6D6D6" if dark else T.GREY
    return (f'<div data-text style="font-size:24px;color:{grey}">{T._breaking(story, dark)}'
            f'{T._meta_html(T._meta_card(story), ink)}</div>')


def _serif(title, sizes, color):
    big, mid, small = sizes
    return (f'<h1 data-text style="margin:0;font-family:{SERIF};font-weight:600;font-size:{T._size(title, big, mid, small)}px;'
            f'line-height:1.06;letter-spacing:-0.015em;color:{color}">{T.t(title)}</h1>')


def _img(uri, w, h, about=None, extra=""):
    return (f'<img src="{uri}" style="display:block;width:{w}px;height:{h}px;object-fit:cover;'
            f'object-position:{T._pos(uri, w, h, about)};{extra}">')


def _page(body, bg, fg):
    return _head() + (f'<div style="position:relative;width:{W}px;height:{H}px;overflow:hidden;background:{bg};color:{fg};'
                      f"font-family:'Libre Franklin',sans-serif\">{body}</div></body></html>")


def place_card(story, brand=T.BRAND):
    """The scene full width on top, a round portrait on a white rule over its lower edge, the headline on ink."""
    x = extras(story)
    title = story.get("headline") or story["title"]
    who = people_named(story)[0][0]
    top = 760
    body = (f'<div style="position:absolute;left:0;top:0">{_img(x["scene"]["uri"], W, top, {"person": ""})}</div>'
            f'<div style="position:absolute;left:0;top:{top}px;width:{W}px;height:{H - top}px;background:{T.BLACK}"></div>'
            f'<div data-portrait style="position:absolute;right:{FEED_SAFE}px;top:{top - 200}px;width:300px;height:300px;'
            f'border-radius:50%;overflow:hidden;border:6px solid {T.WHITE};background:{T.BLACK}">'
            f'{_img(x["portrait"]["uri"], 288, 288, None)}</div>'
            f'<div style="position:absolute;left:{FEED_SAFE}px;right:{FEED_SAFE + 330}px;top:{top + 40}px">{_meta(story, True)}</div>'
            f'<div style="position:absolute;left:{FEED_SAFE}px;right:{FEED_SAFE}px;top:{top + 140}px;bottom:{FEED_SAFE}px;'
            f'display:flex;flex-direction:column;justify-content:space-between">'
            f'{_serif(title, (78, 70, 60), T.WHITE)}'
            f'{_foot(brand, True, [("Place", x["scene"]), (who, x["portrait"])])}</div>')
    return _page(body, T.BLACK, T.WHITE)


def split_card(story, brand=T.BRAND):
    """Two parties side by side, a white rule between them, each named on a black label; the headline on paper."""
    (n1, s1), (n2, s2) = extras(story)["pair"]
    title = story.get("headline") or story["title"]
    ph = 760
    is_person = bool(people_named(story))

    def half(name, shot, left):
        about = None if is_person else {"person": ""}
        art = (f'<div style="width:537px;height:{ph}px;background:{T.WHITE};display:flex;align-items:center;justify-content:center">'
               f'<img src="{shot["logo"]}" style="max-width:340px;max-height:200px;object-fit:contain"></div>'
               if shot.get("logo") else _img(shot["uri"], 537, ph, about))
        return (f'<div style="position:absolute;left:{left}px;top:0;width:537px;height:{ph}px;overflow:hidden">'
                f'{art}'
                f'<div data-text style="position:absolute;left:{FEED_SAFE if left == 0 else 30}px;bottom:28px;padding:10px 18px 9px;'
                f'background:{T.BLACK};color:{T.WHITE};font-size:26px;font-weight:700">{T.e(name)}</div></div>')
    body = (half(n1, s1, 0) + half(n2, s2, 543)
            + f'<div style="position:absolute;left:537px;top:0;width:6px;height:{ph}px;background:{T.WHITE}"></div>'
            # a logo panel is white on white paper: a hairline marks where the panels end
            + (f'<div style="position:absolute;left:0;top:{ph}px;width:{W}px;height:1px;background:{T.LINE}"></div>'
               f'<div style="position:absolute;left:540px;top:0;width:1px;height:{ph}px;background:{T.LINE}"></div>'
               if s1.get("logo") or s2.get("logo") else "")
            + f'<div style="position:absolute;left:{FEED_SAFE}px;right:{FEED_SAFE}px;top:{ph + 44}px;bottom:{FEED_SAFE}px;'
            f'display:flex;flex-direction:column">{_meta(story, False)}<div style="height:26px"></div>'
            f'{_serif(title, (80, 72, 62), T.BLACK)}<div style="flex:1"></div>{_foot(brand, False, [(n, x) for n, x in ((n1, s1), (n2, s2)) if not x.get("logo")])}</div>')
    return _page(body, T.WHITE, T.BLACK)


def number_card(story, brand=T.BRAND):
    """A strip of the photo, then the figure huge, then the headline."""
    a = T.assets(story)
    title = story.get("headline") or story["title"]
    fig = _figure(story)
    strip = 540
    size = 320 if len(fig) <= 4 else 270 if len(fig) == 5 else 220 if len(fig) <= 7 else 170
    body = (f'<div style="position:absolute;left:0;top:0">{_img(a["photo"], W, strip, {"person": story.get("person"), "photo_file": story.get("photo_file")})}</div>'
            f'<div style="position:absolute;left:{FEED_SAFE}px;right:{FEED_SAFE}px;top:{strip + 40}px;bottom:{FEED_SAFE}px;'
            f'display:flex;flex-direction:column">{_meta(story, False)}'
            f'<div data-text class="num" style="margin-top:34px;font-size:{size}px;font-weight:800;line-height:0.82;'
            f'letter-spacing:-0.04em">{T.e(fig)}</div><div style="flex:1"></div>'
            f'{_serif(title, (64, 58, 50), T.BLACK)}<div style="height:40px"></div>'
            f'{_foot(brand, False, [("", {"credit": a["credit"]})] if a.get("credit") else [])}</div>')
    return _page(body, T.WHITE, T.BLACK)


def type_card(story, brand=T.BRAND):
    """The headline set large in Newsreader on paper or ink (alternating by headline), a small photo crop above it."""
    a = T.assets(story)
    title = story.get("headline") or story["title"]
    dark = zlib.crc32(title.encode()) % 2 == 1
    bg, fg = (T.BLACK, T.WHITE) if dark else (T.WHITE, T.BLACK)
    crop = (f'<div style="width:280px;height:280px;overflow:hidden;outline:1px solid {T.LINE if not dark else "#3A3A3A"}">'
            f'{_img(a["photo"], 280, 280, {"person": story.get("person"), "photo_file": story.get("photo_file")})}</div>') if a.get("photo") else ""
    shots = [("", {"credit": a["credit"]})] if a.get("photo") and a.get("credit") else []
    body = (f'<div style="position:absolute;inset:{FEED_SAFE}px;display:flex;flex-direction:column">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:40px">'
            f'{_meta(story, dark)}{crop}</div><div style="flex:1"></div>'
            f'{_serif(title, (104, 92, 80), fg)}<div style="height:56px"></div>{_foot(brand, dark, shots)}</div>')
    return _page(body, bg, fg)


def html(story, name, brand=T.BRAND):
    """The card in the named layout."""
    if name == "split":
        return split_card(story, brand)
    if name == "place":
        return place_card(story, brand)
    if name == "number":
        return number_card(story, brand)
    if name == "type":
        return type_card(story, brand)
    a = T.assets(story)
    return T.card(story, brand, place=quiet_side(a["photo"], a.get("kind") == "person") if a.get("photo") else "bottom")


def credits(story, name):
    """[{"file", "credit"}] of every photo the card in this layout shows, for the post record and the audit."""
    a = T.assets(story)
    x = story.get("_extras") or {}
    if name == "split":
        return [{"file": s["file"], "credit": s["credit"], "name": n} for n, s in x["pair"] if not s.get("logo")]
    if name == "place":
        return [{"file": x["scene"]["file"], "credit": x["scene"]["credit"], "name": "Place"},
                {"file": x["portrait"]["file"], "credit": x["portrait"]["credit"], "name": people_named(story)[0][0]}]
    return [{"file": a["file"], "credit": a["credit"], "name": ""}] if a.get("file") else []
