"""Cover frames for Reels and Shorts, and the daily "Today" card: samples only until Kerem approves (2026-11-28);
nothing in the publish path calls this.

Principles taken from a strong news-Reels account and set in Boardread's own system (black and white, Libre Franklin,
flat chips, no colour, no hype):
  - a series mark on every cover, so the grid reads as one publication;
  - a huge 2-4 word hook from the headline (hooks.py), one plain line under it; the full headline is frame 2;
  - 2-3 small topic chips: who, which sector, what kind of event;
  - where the photo shows the story's subject (cardvideo.photo_fits), the subject cut out on flat black, its
    credit kept on the frame.
"""
import re

from . import templates as T

W, H = 1080, 1920
LEFT, RIGHT = 120, 880  # the Reels/Shorts safe width (reelcard.py)
INK, PAPER, GREY = T.BLACK, T.WHITE, "#9aa0a8"
FIT = """<script>
document.fonts.ready.then(function(){document.querySelectorAll('[data-fit]').forEach(function(el){
  var max=+el.dataset.max,min=+el.dataset.min,lines=+el.dataset.lines,lh=parseFloat(el.dataset.lh);
  for(var s=max;s>=min;s-=4){el.style.fontSize=s+'px';var h=el.getBoundingClientRect().height;
    if(Math.round(h/(s*lh))<=lines&&el.scrollWidth<=el.clientWidth+1)break;}});});
</script>"""


def chips(story):
    """Who, which sector, what kind of event: at most three short labels, each from the story's own fields."""
    from . import desk
    head = (story.get("headline") or story.get("title") or "").lower()
    out = [story.get("company") or story.get("person") or "", story.get("topic") or ""]
    event = next((t.lstrip("#").replace("interestrates", "rates") for k, t in desk.SUBJECT_TAGS if re.search(rf"\b{k}", head)), "")
    out.append(event.capitalize() if event else "")
    seen, labels = set(), []
    for x in out:
        if x and x.lower() not in seen and len(x) <= 24:
            seen.add(x.lower())
            labels.append(x)
    return labels[:3]


def _chip(text, h=54):
    return (f'<span data-tag style="display:inline-block;height:{h}px;line-height:{h}px;padding:0 {round(h * 0.36)}px;'
            f'margin:0 14px 14px 0;background:{PAPER};color:{INK};font-size:28px;font-weight:700;letter-spacing:.5px;'
            f'border-radius:{round(h * T.CHIP_RADIUS) if hasattr(T, "CHIP_RADIUS") else round(h * 0.18)}px">{T.e(text)}</span>')


def _head():
    return T.head().replace("<body>", f'<body style="margin:0;background:{T.STORY_BG}">')


def cover(story, hook, line, cutout_uri="", credit="", kind="reel"):
    """A 1080x1920 cover: the series mark at the top, then the chips, the hook and its line, and the way to the full
    story at the foot. With a cut-out the text sits high and the subject stands below it on flat black (its top at
    y 1180, never under the text: a face never carries type), its credit under the line; without one the text is
    centred so no band of the frame is left empty (gate.DEAD). A very short hook and line still leave one: the gate
    refuses that cover and the video keeps its usual first frame."""
    mark = (f'<div style="position:absolute;left:{LEFT}px;top:250px;font-size:28px;font-weight:700;letter-spacing:6px;'
            f'color:{GREY}">A BOARDREAD STORY</div>')
    row = "".join(_chip(c) for c in chips(story))
    hook_html = (f'<div data-fit data-max="320" data-min="110" data-lines="3" data-lh="0.9" style="font-size:320px;'
                 f'font-weight:800;line-height:0.9;letter-spacing:-0.035em;text-transform:uppercase;text-wrap:balance">'
                 f'{T.e(hook)}</div>')
    # a short line is set larger, so a short hook and line still fill the frame (gate.DEAD)
    size = 50 if cutout_uri else (78 if len(line) < 60 else 62)
    line_html = (f'<div style="margin-top:36px;font-size:{size}px;font-weight:500;line-height:1.14;'
                 f'color:#e9e9e7">{T.t(line)}</div>')
    cred = (f'<div data-credit style="margin-top:26px;font-size:22px;line-height:1.3;color:{GREY}">{T.e(credit)}</div>'
            if credit else "")
    if cutout_uri:
        body = (f'<div style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;top:330px">'
                f'<div>{row}</div>{hook_html}{line_html}{cred}</div>')
        pic = (f'<img src="{cutout_uri}" style="position:absolute;left:0;width:1080px;bottom:0;height:740px;'
               f'object-fit:contain;object-position:center bottom">')
        foot = ""
    else:
        body = (f'<div style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;top:330px;height:1090px;display:flex;'
                f'flex-direction:column;justify-content:center"><div>{row}</div>{hook_html}{line_html}</div>')
        pic = ""
        foot = (f'<div style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;bottom:{1920 - 1500}px;font-size:34px;'
                f'font-weight:500;color:{GREY}">Full story: <span style="color:{PAPER};font-weight:700">{T.e(T.domain())}</span></div>')
    return _head() + (f'<div style="position:relative;width:{W}px;height:{H}px;overflow:hidden;color:{PAPER};'
                      f"font-family:'Libre Franklin',sans-serif\">{pic}{mark}{body}{foot}</div>{FIT}</body></html>")


def today_card(items, day_label, fmt="feed"):
    """The day's four stories as one numbered card: feed 1080x1350 (72 px margins, clear of the slide counter in the
    top right) or story 1080x1920 (250 px top and bottom)."""
    h, pad_y, pad_x = (1350, 72, 72) if fmt == "feed" else (1920, 250, 120)
    rows = "".join(
        f'<div style="display:flex;gap:34px;align-items:flex-start;padding:26px 0;border-top:2px solid #2c2c2c">'
        f'<div style="font-size:{100 if fmt == "feed" else 120}px;font-weight:800;line-height:0.9;min-width:80px">{i}</div>'
        f'<div style="font-size:{54 if fmt == "feed" else 64}px;font-weight:700;line-height:1.12;letter-spacing:-0.01em">{T.t(t)}</div></div>'
        for i, t in enumerate(items[:4], start=1))
    return _head() + (
        f'<div style="position:relative;width:1080px;height:{h}px;overflow:hidden;color:{PAPER};padding:{pad_y}px {pad_x}px;'
        f"box-sizing:border-box;font-family:'Libre Franklin',sans-serif;display:flex;flex-direction:column\">"
        f'<div style="font-size:26px;font-weight:700;letter-spacing:6px;color:{GREY}">A BOARDREAD STORY</div>'
        f'<div style="margin-top:18px;font-size:150px;font-weight:800;line-height:0.9;letter-spacing:-0.04em">Today</div>'
        f'<div style="margin:14px 0 40px;font-size:40px;font-weight:500;color:{GREY}">{T.e(day_label)}</div>'
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:space-evenly">{rows}</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;border-top:2px solid #2c2c2c;padding-top:24px">'
        f'<span style="font-size:44px;font-weight:800;letter-spacing:{T.TRACK}">{T.e(T.BRAND["name"])}</span>'
        f'<span style="font-size:30px;color:{GREY}">{T.e(T.domain())}</span></div></div></body></html>')
