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
    if(Math.round(h/(s*lh))<=lines&&el.scrollWidth<=el.clientWidth+1)break;}});
 // a photo starts below the text block, so no word ever sits on it
 document.querySelectorAll('[data-below]').forEach(function(img){var t=document.querySelector('[data-text]');
  if(t){var y=Math.ceil(t.getBoundingClientRect().bottom)+36;img.style.top=y+'px';img.style.height=(1920-y)+'px';}});
 // a figure fills the box it is given: as tall as the box allows, never wider than the text width
 document.querySelectorAll('[data-fill]').forEach(function(el){var box=el.parentElement;
  var room=1500-box.getBoundingClientRect().top-parseFloat(getComputedStyle(box).paddingTop),wide=box.clientWidth;
  for(var s=Math.min(560,Math.floor(room/0.9));s>=60;s-=6){el.style.fontSize=s+'px';
    var r=el.getBoundingClientRect();if(r.width<=wide&&r.height+s*0.2<=room)break;}});});
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


def key_number(hook, story):
    """The figure the cover can set large: the hook's own number ("29" from "29 SEATS UNOPPOSED"), else the headline's
    figure; "" when there is none."""
    m = re.search(r"[$€£]?\d[\d.,]*%?", hook)
    if m:
        return m.group(0)
    return T._headline_figure(story) if story.get("headline") else ""


def cover(story, hook, line, photo_uri="", credit="", kind="reel", focus=(0.5, 0.35), cutout_uri=""):
    """A 1080x1920 cover that fills the frame:
      - with a photo of the story's subject (cardvideo.photo_fits): the text in the upper half, the photo cropped
        on its focal point filling the lower half, its credit on the frame;
      - without one: the type fills it: the hook and the line set larger, "Full story" straight under the line, and
        below a thin rule the key number set huge when there is one (29 for "29 SEATS UNOPPOSED"), else the topic
        as a quiet large word.
    The series mark sits on top of every cover. cutout_uri: the subject cut out instead of the crop (off until a
    Linux tool is approved; Apple's Vision runs only on a Mac)."""
    mark = (f'<div style="position:absolute;left:{LEFT}px;top:250px;font-size:28px;font-weight:700;letter-spacing:6px;'
            f'color:{GREY}">A BOARDREAD STORY</div>')
    row = "".join(_chip(c) for c in chips(story))
    pic_mode = bool(photo_uri or cutout_uri)
    hook_html = (f'<div data-fit data-max="330" data-min="110" data-lines="3" data-lh="0.9" style="font-size:330px;'
                 f'font-weight:800;line-height:0.9;letter-spacing:-0.035em;text-transform:uppercase;text-wrap:balance">'
                 f'{T.e(hook)}</div>')
    size = 50 if pic_mode else (76 if len(line) < 70 else 66)
    line_html = f'<div style="margin-top:30px;font-size:{size}px;font-weight:500;line-height:1.13;color:#e9e9e7">{T.t(line)}</div>'
    more = (f'<div style="margin-top:22px;font-size:34px;font-weight:500;color:{GREY}">Full story: '
            f'<span style="color:{PAPER};font-weight:700">{T.e(T.domain())}</span></div>')
    cred = (f'<div data-credit style="margin-top:14px;font-size:22px;line-height:1.3;color:{GREY}">{T.e(credit)}</div>'
            if credit else "")
    pic, art = "", ""
    if pic_mode:
        if cutout_uri:
            pic = (f'<img src="{cutout_uri}" style="position:absolute;left:0;width:1080px;bottom:0;height:740px;'
                   f'object-fit:contain;object-position:center bottom">')
        else:
            pic = (f'<img data-below src="{photo_uri}" style="position:absolute;left:0;width:1080px;top:1180px;height:740px;'
                   f'object-fit:cover;object-position:{focus[0] * 100:.0f}% {focus[1] * 100:.0f}%">')
        body = f'<div>{row}</div>{hook_html}{line_html}{cred}{more}'
    else:
        big = key_number(hook, story)
        word = big or (story.get("topic") or "")
        tone = PAPER if big else "#2f2f2f"  # the number is content; a topic word is only texture
        # the rule and the figure take whatever height is left above y 1500; FILL sizes the figure to it
        art = (f'<div style="margin-top:44px;border-top:3px solid {PAPER};padding-top:20px;flex:1;min-height:0;'
               f'display:flex;align-items:flex-start"><div data-fill style="font-size:100px;font-weight:800;line-height:0.86;'
               f'letter-spacing:-0.05em;color:{tone};white-space:nowrap">{T.e(word)}</div></div>') if word else ""
        body = f'<div>{row}</div>{hook_html}{line_html}{more}{art}'
    text = (f'<div data-text style="position:absolute;left:{LEFT}px;width:{RIGHT - LEFT}px;top:330px;'
            f'{"height:1170px;display:flex;flex-direction:column" if not pic_mode else ""}">{body}</div>')
    return _head() + (f'<div style="position:relative;width:{W}px;height:{H}px;overflow:hidden;color:{PAPER};'
                      f"font-family:'Libre Franklin',sans-serif\">{pic}{mark}{text}</div>{FIT}</body></html>")


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
