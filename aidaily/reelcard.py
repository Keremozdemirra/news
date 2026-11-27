"""The 9:16 video card (a feed post sent as a Reel): the text goes where the picture leaves room, and a short
sequence instead of one static block.

The 4:5 carousel card keeps its one layout (templates.card). A Reel places its text block in one of three places
over the full-bleed photo, or, when none of them is free, beside the photo on black:

  top           text in the upper third over the card's scrim turned over (sky, ceiling, wall)
  middle        text across the middle over a band of the same scrim
  lower         text in the lower third over the card's scrim (the Reel as it was)
  photo-top     the photo in the upper band, the text on black below it
  photo-bottom  the text on black above, the photo in a band below it

Where: each of the three places is measured on the frame. A place is out when a face is in it (focus.py's point, with
room for the measured head); of the rest, the quietest wins (the least detail under the text), together with any
within QUIET_RATIO of it. When every free place is busy (BUSY_MAX) or a face fills the frame, the band layouts take
over. Among the places that qualify the post id picks one, and the last Reel's layout goes to the back, so the text
does not sit in the same spot Reel after Reel when the picture allows another.

Safe area, measured on the Instagram player of a 19.5:9 phone (2026-11-27): the 9:16 video fills the screen's
height, so about 54 px of each side of a 1080 px frame is cut off, and the like/comment/share column covers the right
of the lower half. Text runs from x=120 to x=880 (about 6% of the screen on the left after the crop, clear of the
right 15%), from y=250 down to y=1500 (clear of the username and caption over the bottom fifth).

The sequence: the headline, then one fact from the published dek set large on its own (a figure when the dek has
one the headline lacks), then who reported it, then the end frame. Black and white type, the card's scrim and
nothing else: no colour, no added imagery.

(reel.py is the daily recap Reel, a different thing.)
"""
import re
import subprocess
import zlib

from . import templates as T

W, H = 1080, 1920
LEFT, RIGHT = 120, 880
SAFE_TOP, SAFE_BOTTOM = 250, H - T.REEL_SAFE_BOTTOM  # 250 .. 1500
LAYOUTS = ("top", "middle", "lower", "photo-top", "photo-bottom")
PLACES = ("top", "middle", "lower")

# per layout: the photo band (y0, y1); the text box (top, bottom, anchor); the foot (wordmark and credit) at a top edge
# ("top", y) or bottom edge ("bottom", y); the scrim; the span the text and foot cover, which must be free of faces
GEO = {
    "top": {"band": (0, H), "box": (410, 900, "start"), "foot": ("top", SAFE_TOP), "scrim": "top", "span": (SAFE_TOP, 900)},
    "middle": {"band": (0, H), "box": (650, 1150, "center"), "foot": ("top", 1176), "scrim": "middle", "span": (640, 1300)},
    "lower": {"band": (0, H), "box": (840, 1330, "end"), "foot": ("bottom", SAFE_BOTTOM), "scrim": "bottom",
              "span": (840, SAFE_BOTTOM)},
    "photo-top": {"band": (0, 760), "box": (880, 1390, "start"), "foot": ("bottom", SAFE_BOTTOM), "credit": 776},
    "photo-bottom": {"band": (990, 1610), "box": (320, 890, "start"), "foot": ("top", SAFE_TOP), "credit": 904},
}
SCRIM = {  # the card's own gradient (templates.card, tall), the same turned over, and the same as a band
    "bottom": "rgba(0,0,0,.35) 0%,rgba(0,0,0,0) 18%,rgba(0,0,0,0) 34%,rgba(0,0,0,.84) 58%,rgba(0,0,0,.94) 100%",
    "top": "rgba(0,0,0,.94) 0%,rgba(0,0,0,.88) 30%,rgba(0,0,0,.6) 46%,rgba(0,0,0,0) 62%,rgba(0,0,0,0) 86%,rgba(0,0,0,.35) 100%",
    "middle": "rgba(0,0,0,.35) 0%,rgba(0,0,0,0) 16%,rgba(0,0,0,0) 24%,rgba(0,0,0,.84) 36%,rgba(0,0,0,.9) 50%,"
              "rgba(0,0,0,.84) 66%,rgba(0,0,0,0) 78%,rgba(0,0,0,.35) 100%",
}
CREDIT_PX = 24  # legible on a phone, quiet in grey; the card's 16 px vanished in the Instagram player
# room kept around the subject's point: half a measured head plus a gap, or, when the head was not measured, a margin
# that clears a close-up of a head and shoulders
FACE_GAP, FACE_MARGIN = 60, 380
# places within this ratio of the quietest count as alike; above BUSY_MAX no place is quiet enough to set text on
QUIET_RATIO, BUSY_MAX = 1.2, 30

HEAD_SECONDS, HEAD_ALONE, SOURCE_SECONDS, END_SECONDS = 4.2, 5.4, 2.0, 1.6
FADE_IN, FADE_OUT, RISE = 0.4, 0.3, 26
FACT_MAX_CHARS = 170
# a number worth setting large: money, a share, or a count in the thousands or with a unit word
NUMBER = re.compile(r"(?:[A-Z]{1,2})?[$€£¥₩]\s?\d[\d,.]*\s?(?:[BMKT]\b|bn\b|billion|million|trillion)?"
                    r"|\b\d[\d,.]*\s?(?:%|percent\b)"
                    r"|\b\d[\d.]*\s(?:billion|million|trillion)(?:\s(?:won|yen|euros?|dollars?|pounds?|yuan))?"
                    r"|\b\d{1,3}(?:,\d{3})+\b", re.I)


# where the text may go

def subject_y(src_w, src_h, fx, fy, band_h=H):
    """Where the focal point lands, in px from the top of a band of `band_h` filled from the photo and cropped around
    the point as cardvideo.camera crops it (the camera push moves it a little toward the centre, never out)."""
    aw = min(src_w, src_h * W / band_h)
    ah = aw * band_h / W
    ay = min(max(fy * src_h - ah / 2, 0), src_h - ah)
    return (fy * src_h - ay) * band_h / ah


def busyness(path, src_size, fxy, spans):
    """How much detail the full-bleed 9:16 crop has in each (y0, y1) span: the mean luminance step between
    neighbouring pixels of a 54x96 decode. Sky, wall and shadow score low; text over them reads."""
    from . import focus as F
    sw, sh = src_size
    fx, fy = fxy
    aw = min(sw, sh * W / H)
    ah = aw * H / W
    ax = min(max(fx * sw - aw / 2, 0), sw - aw)
    ay = min(max(fy * sh - ah / 2, 0), sh - ah)
    w, h = 54, 96
    try:
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-vf",
                            f"crop={int(aw)}:{int(ah)}:{int(ax)}:{int(ay)},scale={w}:{h}:flags=area,format=gray",
                            "-f", "rawvideo", "-"], capture_output=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    g = r.stdout
    if len(g) != w * h:
        return None
    out = []
    for y0, y1 in spans:
        a, b = int(y0 * h / H), max(int(y1 * h / H), int(y0 * h / H) + 2)
        steps = [abs(g[y * w + x] - g[y * w + x + 1]) + abs(g[y * w + x] - g[(y + 1) * w + x])
                 for y in range(a, min(b, h - 1)) for x in range(w - 1)]
        out.append(sum(steps) / max(len(steps), 1))
    return out


def face_margin(src_size, head):
    """Px above and below the focal point that the text keeps clear of: half the measured head (`head`, a share of the
    photo's height) on the 9:16 frame plus FACE_GAP, else FACE_MARGIN."""
    if not head:
        return FACE_MARGIN
    sw, sh = src_size
    ah = min(sw, sh * W / H) * H / W  # the crop's height in photo px
    return head * sh * H / ah / 2 + FACE_GAP


def allowed(src_size, fxy, face, path=None, head=None):
    """The layouts the text may take: the places free of a face and quiet enough (the quietest and any close to it),
    else the two band layouts. Footage (src_size None) has no face to protect, the library holds no clips of people
    (broll), and moves, so every place is open."""
    if not src_size:
        return list(PLACES)
    free = list(PLACES)
    if face:
        y, m = subject_y(*src_size, *fxy), face_margin(src_size, head)
        free = [n for n in PLACES if GEO[n]["span"][1] < y - m or GEO[n]["span"][0] > y + m]
    if free and path:
        b = busyness(path, src_size, fxy, [GEO[n]["span"] for n in free])
        if b:
            low = min(b)
            free = [n for n, v in zip(free, b) if v <= low * QUIET_RATIO and v <= BUSY_MAX]
    return free or ["photo-top", "photo-bottom"]


def pick(seed, options, avoid=None):
    """One of `options` by the post id; `avoid` (the last Reel's layout) only when nothing else is allowed."""
    usable = [n for n in LAYOUTS if n in options and n != avoid] or [n for n in LAYOUTS if n in options]
    return usable[zlib.crc32(str(seed).encode()) % len(usable)]


# what the Reel says

def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"'])", text or "") if s.strip()]


def _words(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def fact(story):
    """(big, line): one sentence of the published dek that the headline does not already say, and a figure from that
    sentence, as written there, when it has one the headline lacks (else ""). A sentence with such a figure goes
    first. Both empty when the dek adds nothing."""
    head = story.get("headline") or story.get("title") or ""
    hw = _words(head)
    found = []
    for s in _sentences(story.get("dek", "")):
        if not 30 <= len(s) <= FACT_MAX_CHARS:
            continue
        sw = _words(s)
        if sw and len(sw & hw) / len(sw) > 0.6:  # the dek restating the headline is no second beat
            continue
        m = next((m for m in NUMBER.finditer(s) if m.group(0).strip() not in head), None)
        found.append((T.short_figure(m.group(0).strip().rstrip(".,")) if m else "", s))
    return next((f for f in found if f[0]), found[0] if found else ("", ""))


def source_line(story):
    """Who reported it, by name ("Reported by Reuters, Bloomberg and Nikkei Asia"), when more than one newsroom did; who
    announced it, for a release. "" when the meta line already says it all."""
    if story.get("primary"):
        return f"Announced by {re.sub(r' [Bb]log$', '', story['primary'])}"
    names = [n for n in (story.get("outlets") or []) if n][:3]
    if len(names) < 2:  # one newsroom: the meta line already says "Source: <name>"
        return ""
    return "Reported by " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])


def plan(story):
    """([(part, t_in, t_out)], total seconds). t_out None stays to the end; the parts are the layers layer() draws."""
    big, line = fact(story)
    src = source_line(story)
    head = HEAD_SECONDS if line else HEAD_ALONE
    out, t = [("base", 0.0, None), ("meta", 0.0, head), ("head", 0.08, head)], head
    if line:
        d = round(min(max(len(line.split()) / 3.0 + (1.2 if big else 0.8), 3.0), 4.6), 2)
        out.append(("fact", t, t + d))
        t += d
    if src:
        out.append(("source", t, t + SOURCE_SECONDS))
        t += SOURCE_SECONDS
    out.append(("end", t, None))
    return out, round(t + END_SECONDS, 2)


# the layers

FIT = """<script>
// The text fills the box width: the largest size from data-max down at which it takes at most data-lines lines,
// fits data-room px of height and breaks no word. Run once the fonts are in, so every layer of a Reel measures alike.
function fit(){document.querySelectorAll('[data-fit]').forEach(function(el){
  var max=+el.dataset.max,min=+el.dataset.min,lines=+el.dataset.lines,room=+el.dataset.room,lh=parseFloat(el.dataset.lh);
  for(var s=max;s>=min;s-=2){el.style.fontSize=s+'px';
    var h=el.getBoundingClientRect().height;
    if(Math.round(h/(s*lh))<=lines&&h<=room&&el.scrollWidth<=el.clientWidth+1)break;}
});}
document.fonts.ready.then(fit);
</script>"""


def _fit(text, max_px, min_px, lines, room, lh, weight=800, track=T.TRACK, extra="", wrap="balance"):
    return (f'<div data-fit data-max="{max_px}" data-min="{min_px}" data-lines="{lines}" data-room="{room}" data-lh="{lh}" '
            f'style="font-size:{max_px}px;font-weight:{weight};line-height:{lh};letter-spacing:{track};text-wrap:{wrap};'
            f'overflow-wrap:normal;{extra}">{T.t(text)}</div>')


def _credit_text(story):
    """The photo or footage credit line exactly as the card's foot sets it (archive label, "Edited" for CC BY)."""
    m = re.search(r'<div style="margin-top:10px;font-size:\d+px;color:[^"]+">(.*?)</div>', T._foot(story, T.BRAND, dark=True, edited=True))
    return m.group(1) if m else ""


def _wordmark():
    """The foot's wordmark row (templates._foot) without the credit line."""
    return (f'<div style="display:flex;justify-content:space-between;align-items:baseline;font-size:24px">'
            f'<span style="font-size:34px;font-weight:800;letter-spacing:{T.TRACK}">{T.e(T.BRAND["name"])}</span>'
            f'<span style="color:{T.GREY_DARK}">{T.e(T.domain())}</span></div>')


def layer(story, name, part):
    """One transparent 1080x1920 layer of layout `name`: base (scrim or black ground, wordmark, credit), meta, head,
    fact, source or end. Every part is drawn on its own page with the same geometry, so the layers line up."""
    g = GEO[name]
    top, bottom, anchor = g["box"]
    room = bottom - top
    y0, y1 = g["band"]
    box = (f'position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;top:{top}px;height:{room}px;display:flex;'
           f'flex-direction:column;justify-content:{"center" if anchor == "center" else "flex-" + anchor}')
    if part == "base":
        if g["band"] == (0, H):
            inner = f'<div style="position:absolute;inset:0;background:linear-gradient(180deg,{SCRIM[g["scrim"]]})"></div>'
        else:  # black everywhere but the photo band
            inner = (f'<div style="position:absolute;left:0;right:0;top:0;height:{y0}px;background:{T.BLACK}"></div>'
                     f'<div style="position:absolute;left:0;right:0;top:{y1}px;bottom:0;background:{T.BLACK}"></div>')
        side, y = g["foot"]
        pos = f"bottom:{H - y}px" if side == "bottom" else f"top:{y}px"
        credit = _credit_text(story)
        cred = (f'<div style="margin-top:10px;font-size:{CREDIT_PX}px;line-height:1.3;color:{T.GREY_DARK}">{credit}</div>'
                if credit else "")
        if "credit" in g:  # the band layouts: the wordmark row where the foot goes, the credit as a caption by the photo
            inner += f'<div style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;{pos}">{_wordmark()}</div>'
            if credit:
                inner += (f'<div style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;top:{g["credit"]}px;'
                          f'font-size:{CREDIT_PX}px;line-height:1.3;color:{T.GREY_DARK}">{credit}</div>')
        else:
            inner += f'<div style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;{pos}">{_wordmark()}{cred}</div>'
    elif part in ("meta", "head"):
        # both drawn and one hidden, so the headline sits exactly where it will under the meta line
        meta = (f'<div style="font-size:30px;color:#D6D6D6;margin-bottom:24px;{"visibility:hidden" if part == "head" else ""}">'
                f'{T._breaking(story, True)}{T._meta_html(T._meta_card(story), T.WHITE)}</div>')
        # "pretty" fills each line and only keeps a last word from standing alone; "balance" would narrow every line
        head = _fit(story.get("headline") or story["title"], 136, 60, 4, room - 80, 1.02, wrap="pretty",
                    extra="visibility:hidden" if part == "meta" else "")
        inner = f'<div style="{box}">{meta}{head}</div>'
    elif part == "fact":
        big, line = fact(story)
        parts = _fit(big, 300, 120, 1, 330, 0.95, track="-0.04em", extra="margin-bottom:24px") if big else ""
        parts += _fit(line, 72 if big else 88, 44, 5 if big else 6, room - (360 if big else 0), 1.14,
                      weight=500 if big else 700, track="-0.01em", wrap="pretty")
        inner = f'<div style="{box}">{parts}</div>'
    elif part == "source":
        inner = f'<div style="{box}">' + _fit(source_line(story), 84, 48, 4, room, 1.1, weight=700, track="-0.015em", wrap="pretty") + "</div>"
    elif part == "end":
        inner = (f'<div style="position:absolute;inset:0;background:{T.STORY_BG};display:flex;flex-direction:column;'
                 f'justify-content:center;padding:0 {W - RIGHT}px 180px {LEFT}px">'
                 f'<div style="font-size:150px;font-weight:800;letter-spacing:-6px;line-height:1">{T.e(T.BRAND["name"])}</div>'
                 f'<div style="margin-top:48px;font-size:64px;font-weight:700;letter-spacing:-1.5px">{T.e(T.domain())}</div>'
                 f'<div style="margin-top:20px;font-size:52px;font-weight:500;color:#9aa0a8;letter-spacing:-1px">'
                 f'Full story and sources</div></div>')
    else:
        raise ValueError(part)
    return T.head().replace("<body>", '<body style="background:transparent">') + (
        f'<div style="position:relative;width:{W}px;height:{H}px;color:{T.WHITE};font-family:\'Libre Franklin\',sans-serif;'
        f'overflow:hidden">{inner}</div>{FIT}</body></html>')
