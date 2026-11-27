"""The per-story Reel prototype: one post.json in, one 1080x1920 MP4 out. Not wired into the pipeline.

Two modes, chosen by plan():
  footage  a licensed clip found by footage.match(), 7.6 s in a window above the headline, then the newsrooms and the end frame
  graphic  motion graphics from the post: kinetic headline, then the official series chart (or the licensed photo
           with a slow push, or the key figure), then the newsrooms, then the end frame; about 11 s

How the frames are made: every frame is a static HTML page computed from the time t (no JavaScript, so a frame is
a pure function of the post and t), shot by headless Chrome in parallel. Graphic Reels are opaque frames; footage
Reels are transparent overlays that ffmpeg lays over the cropped clip. The same ffmpeg
settings as reel.assemble() meet Instagram's Reels spec; audit_video() checks the result against it.

    python -m aidaily.video queue/<id>/post.json out.mp4 [--footage clip.mp4 --footage-meta meta.json]
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date as _date, datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import markets as M
from . import render as R
from . import templates as T

W, H, FPS = 1080, 1920, 30
BG, INK, GREY, DIM, LINE = "#0a0a0a", "#f4f4f2", "#9c9c97", "#5e5e5a", "#2b2b29"
UP, DOWN = "#5ad08a", "#ff7a6b"  # only the change figure takes a colour, as on the site
FONTS = Path(__file__).resolve().parent.parent / "assets-site" / "fonts"
# Instagram draws its own UI over a Reel: the name and caption at the bottom, the buttons on the right, the title at the top
TOP, BOTTOM, LEFT, RIGHT = 250, 400, 72, 72

# Official series a story can carry, matched on the headline and dek only (not the body, which wanders).
# (pattern, markets.SERIES key, short subtitle)
SERIES_RULES = (
    (r"\b(?:ecb|european central bank|euro ?zone|eur/usd)\b", "eurusd", "dfr"),
    (r"\b(?:fed|federal reserve|fomc|powell|rate (?:hike|cut|rise)|raise rates|cut rates|2-year)\b", "ust2", ""),
    (r"\b(?:treasury yields?|10-year|bond yields?|bond market)\b", "ust10", ""),
    (r"\b(?:brent|crude|oil price|opec|oil prices)\b", "brent", ""),
    (r"\b(?:gasoline|gas prices|petrol)\b", "gasoline", ""),
    (r"\b(?:bank of england|sterling|pound)\b", "gbpusd", ""),
    (r"\b(?:bank of japan|yen)\b", "usdjpy", ""),
)


def e(s):
    return html.escape(str(s or ""), quote=True)


# ---- easing and timing -----------------------------------------------------------------------------------------

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def p(t, t0, d):
    return clamp((t - t0) / d)


def out3(x):
    return 1 - (1 - x) ** 3


def out5(x):
    return 1 - (1 - x) ** 5


def inout(x):
    return 3 * x * x - 2 * x ** 3


def fade(t, t_in, t_out, d_in=0.35, d_out=0.35):
    """Opacity of a scene visible from t_in to t_out."""
    return min(inout(p(t, t_in, d_in)), 1 - inout(p(t, t_out - d_out, d_out)))


# ---- plan -------------------------------------------------------------------------------------------------------

def series_for(post, m):
    """The official series this story is about, or None. Needs a named institution or instrument in the headline or dek."""
    text = f"{post['headlines'][0]} {post.get('dek', '')}"
    for pat, key, extra in SERIES_RULES:
        if re.search(pat, text, re.I):
            st = M.stat(m, key)
            if not st:
                return None
            label, last, date, ch, pct, hist = st
            hist = hist[-60:]
            _, unit, dec, tag, _, _ = M.SERIES[key]
            extras = []
            if extra == "dfr" and m.get("dfr"):
                since = m["dfr"].get("since", "")
                extras.append(("ECB deposit rate", f"{m['dfr']['value']:.2f}%", f"since {M.dmy(since)}" if since else ""))
            return {"key": key, "label": label, "unit": unit, "dec": dec, "pts": [(d, float(v)) for d, v in hist],
                    "last": last, "date": date, "change": ch, "tag": tag, "extras": extras,
                    "source": {"ust": "U.S. Treasury", "ecb": "ECB", "eia": "U.S. EIA", "calc": "ECB reference rates"}[tag]}
    return None


def photo_ok(post):
    """A photo goes in a video only under CC0, CC BY or public domain. The video crops, moves and overlays it, which
    makes it Adapted Material: under CC BY-SA the whole Reel would have to be shared under CC BY-SA, which
    Instagram's terms do not allow, and ND forbids the adaptation outright."""
    c = post.get("credit", "")
    return bool(c) and not re.search(r"BY-SA|BY-ND|NC", c)


def plan(post, markets=None, photo_file=None, footage=None):
    """Everything a frame needs, derived from the post only (no new claim: the headline, dek and sources are the published ones)."""
    head = post["headlines"][0]
    fig = T.key_figure(head)
    pl = {"id": post["id"], "headline": head, "dek": post.get("dek", ""), "topic": post.get("topic", ""),
          "date": datetime.fromisoformat(post["created"]).strftime("%-d %b"), "sources": list(post.get("sources") or [])[:4],
          "figure": None, "chart": None, "photo": None, "footage": None}
    if footage:
        pl["mode"], pl["footage"] = "footage", footage
        pl["T"] = 10.6
        return pl
    pl["mode"] = "graphic"
    chart = series_for(post, markets) if markets else None
    if chart:
        pl["chart"] = chart
    elif photo_file and photo_ok(post):
        pl["photo"] = {"file": str(photo_file), "credit": post["credit"], "focus": tuple(post.get("focus") or (0.5, 0.12))}
    elif fig:
        tail = head.split(fig, 1)[-1].split()[:4]
        pl["figure"] = {"text": fig, "label": " ".join(tail)}
    pl["T"] = 10.8 if not pl["photo"] else 10.6
    return pl


# ---- frame pieces ----------------------------------------------------------------------------------------------

def head_css():
    face = "".join(f"@font-face{{font-family:'Libre Franklin';font-weight:{w};src:url('{(FONTS / f'LibreFranklin-{w}.woff2').as_uri()}')}}"
                   for w in (400, 500, 600, 800))
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{face}"
            f"*{{margin:0;padding:0;box-sizing:border-box}}html,body{{width:{W}px;height:{H}px;overflow:hidden;background:transparent}}"
            f"body{{font-family:'Libre Franklin',sans-serif;color:{INK};font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}}"
            f".a{{position:absolute}}</style></head><body>")


def words(text, t, t0, size, weight=800, color=INK, track=-0.035, lead=1.04, stagger=0.06, dur=0.6, style=""):
    """A block of text whose words rise out of a mask one after another. Words wrap by the browser."""
    out = []
    for i, w in enumerate(text.split()):
        q = out5(p(t, t0 + i * stagger, dur))
        out.append(f'<span style="display:inline-block;overflow:hidden;vertical-align:top;padding:0 .02em .16em;margin-bottom:-.16em">'
                   f'<span style="display:inline-block;transform:translateY({(1 - q) * 112:.1f}%);opacity:{min(1, q * 2.2):.3f}">{e(w)}</span></span>')
    return (f'<div style="font-size:{size}px;font-weight:{weight};color:{color};letter-spacing:{track}em;line-height:{lead};{style}">'
            f'{" ".join(out)}</div>')


def size_for(text):
    n = len(text)
    return 150 if n <= 26 else 132 if n <= 42 else 118 if n <= 62 else 104 if n <= 84 else 90


def header(t, total, topic, date, light=False):
    a = inout(p(t, 0.0, 0.5))
    return (f'<div class="a" style="left:{LEFT}px;top:{TOP - 8}px;font-size:52px;font-weight:800;letter-spacing:-0.035em;opacity:{a:.3f};text-shadow:0 2px 14px rgba(0,0,0,.55)">boardread.</div>'
            f'<div class="a" style="right:{RIGHT}px;top:{TOP + 4}px;font-size:30px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;'
            f'color:{INK};text-shadow:0 2px 14px rgba(0,0,0,.55);opacity:{a * .78:.3f}">{e(topic)} &middot; {e(date)}</div>'
            f'<div class="a" style="left:{LEFT}px;top:{TOP + 74}px;height:3px;width:{W - LEFT - RIGHT}px;background:{LINE}"></div>'
            f'<div class="a" style="left:{LEFT}px;top:{TOP + 74}px;height:3px;width:{(W - LEFT - RIGHT) * clamp(t / total):.1f}px;background:{INK};opacity:.9"></div>')


def kicker(text, t, t0, top, color=GREY):
    a = inout(p(t, t0, 0.4))
    return (f'<div class="a" style="left:{LEFT}px;top:{top}px;font-size:34px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;'
            f'color:{color};opacity:{a:.3f};transform:translateY({(1 - a) * 14:.1f}px)">{e(text)}</div>')


def group(inner, a, dy=0):
    return f'<div class="a" style="left:0;top:0;width:{W}px;height:{H}px;opacity:{a:.3f};transform:translateY({dy:.1f}px)">{inner}</div>'


def fmt_val(v, dec, unit):
    s = f"{v:,.{dec}f}"
    return f"{s}%" if unit == "%" else s


def chart_scene(t, t0, ch, dek):
    """Count-up value, the series drawn left to right, source line, the dek under it."""
    pts = [v for _, v in ch["pts"]]
    n = len(pts)
    box_l, box_t, box_w, box_h = LEFT, 880, W - LEFT - RIGHT - 120, 470
    lo, hi = min(pts), max(pts)
    pad = (hi - lo) * 0.12 or 0.01
    lo, hi = lo - pad, hi + pad
    xy = [(box_l + box_w * i / (n - 1), box_t + box_h * (1 - (v - lo) / (hi - lo))) for i, v in enumerate(pts)]
    draw = out3(p(t, t0 + 0.35, 1.7))
    k = draw * (n - 1)
    i, f = int(k), k - int(k)
    path = xy[:i + 1] + ([(xy[i][0] + (xy[i + 1][0] - xy[i][0]) * f, xy[i][1] + (xy[i + 1][1] - xy[i][1]) * f)] if i < n - 1 else [])
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in path)
    ex, ey = path[-1]
    grid = ""
    for j in range(4):
        gy = box_t + box_h * j / 3
        val = hi - (hi - lo) * j / 3
        grid += (f'<line x1="{box_l}" x2="{box_l + box_w}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="{LINE}" stroke-width="2"/>'
                 f'<text x="{box_l + box_w + 14}" y="{gy + 10:.1f}" font-size="27" fill="{DIM}" font-weight="500">{val:.{ch["dec"]}f}</text>')
    pulse = p(t, t0 + 2.0, 1.1)
    ring = f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{14 + 34 * out3(pulse):.1f}" fill="none" stroke="{INK}" stroke-width="3" opacity="{(1 - pulse) * 0.7 * (pulse > 0):.3f}"/>'
    first, last_ = pts[0], ch["last"]
    shown = first + (last_ - first) * draw
    chg = ch["change"] or 0
    arrow, col = ("▲", UP) if chg > 0 else ("▼", DOWN) if chg < 0 else ("", GREY)
    sub = f'<span style="color:{col}">{arrow} {abs(chg):.{ch["dec"]}f}{" pts" if ch["unit"] == "%" else ""}</span> <span style="color:{GREY}">vs previous reading</span>' if arrow else ""
    d0, d1 = M.dmy(ch["pts"][0][0]), M.dmy(ch["pts"][-1][0])
    extra = ""
    for j, (lab, val, since) in enumerate(ch["extras"]):
        extra += (f'<div class="a" style="left:{LEFT}px;top:{1372 + j * 0}px;font-size:36px;font-weight:600;color:{INK};opacity:{inout(p(t, t0 + 2.2, 0.5)):.3f}">'
                  f'{e(lab)} <span style="font-weight:800">{e(val)}</span> <span style="color:{GREY};font-weight:500">{e(since)}</span></div>')
    what = {"ust": "Treasury par yield", "ecb": "ECB reference rate", "eia": ch["unit"]}.get(ch["tag"], "")
    body = (kicker(f"{ch['label']} · {what}" if what else ch["label"], t, t0 + 0.05, 440)
            + f'<div class="a" style="left:{LEFT - 6}px;top:490px;font-size:250px;font-weight:800;letter-spacing:-0.05em;line-height:1;'
              f'opacity:{inout(p(t, t0 + 0.1, 0.4)):.3f}">{fmt_val(shown, ch["dec"], ch["unit"])}</div>'
            + f'<div class="a" style="left:{LEFT}px;top:760px;font-size:36px;font-weight:600;opacity:{inout(p(t, t0 + 1.2, 0.5)):.3f}">{sub}</div>'
            + f'<svg class="a" style="left:0;top:0" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{grid}'
              f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>{ring}'
              f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="13" fill="{INK}"/></svg>'
            + f'<div class="a" style="left:{LEFT}px;top:{box_t + box_h + 22}px;font-size:28px;font-weight:500;color:{GREY};opacity:{inout(p(t, t0 + 1.0, 0.5)):.3f}">{e(d0)} &ndash; {e(d1)} &middot; Source: {e(ch["source"].rstrip("."))}</div>'
            + extra)
    if dek:
        body += words(dek, t, t0 + 2.4, 42, 500, INK, -0.01, 1.28, 0.03, 0.5, f"position:absolute;left:{LEFT}px;top:1436px;width:{W - LEFT - RIGHT - 80}px;opacity:.92")
    return body


def figure_scene(t, t0, fg, dek):
    digits = re.sub(r"[^\d.,]", "", fg["text"])
    try:
        target = float(digits.replace(",", ""))
    except ValueError:
        target = None
    q = out3(p(t, t0 + 0.2, 1.3))
    if target is not None and re.search(r"\d", fg["text"]):
        n = target * q
        txt = fg["text"].replace(digits, f"{n:,.0f}" if "," in digits or "." not in digits else f"{n:,.1f}")
    else:
        txt = fg["text"]
    size = 330 if len(txt) <= 4 else 250 if len(txt) <= 7 else 190
    body = (f'<div class="a" style="left:{LEFT - 8}px;top:520px;font-size:{size}px;font-weight:800;letter-spacing:-0.055em;line-height:1;'
            f'opacity:{inout(p(t, t0, 0.4)):.3f}">{e(txt)}</div>'
            + words(fg["label"], t, t0 + 0.9, 76, 800, GREY, -0.03, 1.05, 0.07, 0.6, f"position:absolute;left:{LEFT}px;top:{520 + size + 10}px;width:{W - LEFT - RIGHT - 40}px"))
    if dek:
        body += words(dek, t, t0 + 2.2, 44, 500, INK, -0.01, 1.28, 0.03, 0.5, f"position:absolute;left:{LEFT}px;top:1330px;width:{W - LEFT - RIGHT - 60}px")
    return body


def dek_scene(t, t0, dek):
    return words(dek, t, t0, 68, 600, INK, -0.025, 1.12, 0.045, 0.6, f"position:absolute;left:{LEFT}px;top:560px;width:{W - LEFT - RIGHT - 30}px")


def sources_scene(t, t0, sources, dark=True):
    rows = kicker("Reported by", t, t0, 510)
    for i, s in enumerate(sources):
        q = out5(p(t, t0 + 0.25 + i * 0.16, 0.6))
        rows += (f'<div class="a" style="left:{LEFT}px;top:{600 + i * 118}px;overflow:hidden;height:112px;width:{W - LEFT - RIGHT}px">'
                 f'<div style="font-size:84px;font-weight:800;letter-spacing:-0.035em;line-height:112px;transform:translateY({(1 - q) * 112:.1f}px);opacity:{q:.3f}">{e(s)}</div></div>')
    rows += (f'<div class="a" style="left:{LEFT}px;top:{600 + max(len(sources), 1) * 118 + 50}px;font-size:36px;font-weight:500;color:{GREY};'
             f'opacity:{inout(p(t, t0 + 1.2, 0.5)):.3f}">Written by AI from these reports.</div>')
    return rows


def end_scene(t, t0):
    a = inout(p(t, t0, 0.35))
    return (f'<div class="a" style="left:0;top:0;width:{W}px;height:{H}px;background:{BG};opacity:{a:.3f}">'
            f'<div class="a" style="left:{LEFT}px;top:700px;font-size:176px;font-weight:800;letter-spacing:-0.045em;line-height:1;'
            f'transform:translateY({(1 - out5(p(t, t0 + 0.1, 0.7))) * 40:.1f}px)">boardread.</div>'
            f'<div class="a" style="left:{LEFT}px;top:930px;font-size:64px;font-weight:600;letter-spacing:-0.02em;color:{GREY};'
            f'opacity:{inout(p(t, t0 + 0.4, 0.5)):.3f}">boardread.news</div>'
            f'<div class="a" style="left:{LEFT}px;top:1030px;font-size:36px;font-weight:500;color:{DIM};opacity:{inout(p(t, t0 + 0.6, 0.5)):.3f}">Sources for every story</div></div>')


def scrim(a):
    """Darkens the top of the media window for the header and fades its foot into the ground under the headline."""
    return (f'<div class="a" style="left:0;top:0;width:{W}px;height:1250px;opacity:{a:.3f};background:linear-gradient(to bottom,rgba(10,10,10,.85) 0,'
            f'rgba(10,10,10,0) 27%,rgba(10,10,10,0) 38%,rgba(10,10,10,.92) 82%,{BG} 100%)"></div>')


def photo_layer(t, ph, t_end):
    """The licensed photo in the top 1250 px, pushed in slowly (6.5 per cent over 7.6 s) so the picture moves
    without leaving the subject."""
    k = inout(p(t, 0, 7.6))
    scale = 1.05 + 0.065 * k
    fx, fy = ph["focus"]
    dx = (0.5 - fx) * 10 + (k - 0.5) * -2.4  # per cent: starts on the focus, drifts a little away
    a = fade(t, 0.0, t_end, 0.5, 0.4)
    return (f'<div class="a" style="left:0;top:0;width:{W}px;height:1250px;overflow:hidden;opacity:{a:.3f}">'
            f'<img src="{Path(ph["file"]).resolve().as_uri()}" style="width:100%;height:100%;object-fit:cover;object-position:{fx * 100:.0f}% {fy * 100:.0f}%;'
            f'transform:scale({scale:.4f}) translateX({dx:.2f}%);transform-origin:{fx * 100:.0f}% {fy * 100:.0f}%"></div>' + scrim(a))


# ---- one frame -------------------------------------------------------------------------------------------------

def frame_html(pl, t):
    """The HTML of the frame at time t. Pure: same plan and t give the same page."""
    total = pl["T"]
    h = pl["headline"]
    s = size_for(h)
    parts = [head_css()]
    footage = pl["mode"] == "footage"
    if footage:  # one almost-clear pixel keeps every PNG RGBA; a frame Chrome saves as RGB would glitch ffmpeg's overlay
        parts.append('<div class="a" style="left:0;top:0;width:1px;height:1px;background:rgba(0,0,0,.004)"></div>')
    if not footage:
        parts.append(f'<div class="a" style="left:0;top:0;width:{W}px;height:{H}px;background:{BG}"></div>')
    if pl["photo"] or footage:
        media = pl["photo"] or pl["footage"]
        if pl["photo"]:
            parts.append(photo_layer(t, pl["photo"], 7.6))
        else:  # the clip is laid under this transparent page by ffmpeg; the ground takes over for the closing scenes
            parts.append(scrim(fade(t, 0.0, 7.6, 0.01, 0.4)))
            parts.append(f'<div class="a" style="left:0;top:0;width:{W}px;height:{H}px;background:{BG};opacity:{inout(p(t, 7.3, 0.4)):.3f}"></div>')
        chip = ""
        if footage:
            chip = (f'<div class="a" style="left:{LEFT}px;top:{TOP + 104}px;font-size:26px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;'
                    f'padding:9px 15px;border:2px solid {INK};text-shadow:0 2px 12px rgba(0,0,0,.5);opacity:{inout(p(t, 0.4, 0.4)):.3f}">{e(media["tag"])}</div>')
        column = (f'<div class="a" style="left:{LEFT}px;bottom:{H - 1470}px;width:{W - LEFT - RIGHT}px">'
                  + words(h, t, 0.35, s - 6, 800, INK, -0.035, 1.04, 0.06, 0.6)
                  + (words(pl["dek"], t, 3.3, 42, 500, INK, -0.01, 1.28, 0.03, 0.5, "margin-top:30px;width:" + f"{W - LEFT - RIGHT - 60}px;opacity:.92") if pl["dek"] else "")
                  + "</div>")
        scene = (header(t, total, pl["topic"], pl["date"]) + chip + column
                 + f'<div class="a" style="left:{LEFT}px;top:1490px;font-size:26px;font-weight:500;color:{GREY};width:{W - LEFT - RIGHT - 60}px;opacity:{inout(p(t, 0.6, 0.5)):.3f}">{e(media["credit"])}</div>')
        parts.append(group(scene, fade(t, 0, 7.6, 0.01, 0.4)))
        parts.append(group(sources_scene(t, 7.5, pl["sources"]), fade(t, 7.5, 9.7, 0.35, 0.4)))
        parts.append(header(t, total, pl["topic"], pl["date"]) if t >= 7.5 else "")
        parts.append(end_scene(t, 9.5))
    else:
        hook_out = 3.5 if (pl["chart"] or pl["figure"]) else 4.4
        parts.append(header(t, total, pl["topic"], pl["date"]))
        ka = inout(p(t, 0.0, 0.4))
        hook = (f'<div class="a" style="left:{LEFT}px;bottom:{H - 1330}px;width:{W - LEFT - RIGHT}px">'
                f'<div style="font-size:34px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:{GREY};margin-bottom:34px;opacity:{ka:.3f}">{e(pl["topic"])}</div>'
                + words(h, t, 0.1, s, 800, INK, -0.04, 1.03, 0.05, 0.55) + "</div>")
        parts.append(group(hook, fade(t, 0.0, hook_out, 0.01, 0.4), -14 * p(t, hook_out - 0.4, 0.4)))
        if pl["chart"]:
            parts.append(group(chart_scene(t, 3.3, pl["chart"], pl["dek"]), fade(t, 3.3, 7.6, 0.3, 0.4)))
        elif pl["figure"]:
            parts.append(group(figure_scene(t, 3.3, pl["figure"], pl["dek"]), fade(t, 3.3, 7.6, 0.3, 0.4)))
        else:
            parts.append(group(dek_scene(t, 4.2, pl["dek"]), fade(t, 4.2, 7.6, 0.3, 0.4)))
        parts.append(group(sources_scene(t, 7.5, pl["sources"]), fade(t, 7.5, 9.7, 0.35, 0.4)))
        parts.append(end_scene(t, 9.5))
    return "".join(parts) + "</body></html>"


# ---- rendering -------------------------------------------------------------------------------------------------

def _shoot(html_text, png, transparent, tries=3):
    """One frame. Chrome sometimes exits non-zero under load (a crash, not a bad page), so a failed shot is retried."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html_text)
    try:
        for n in range(tries):
            with tempfile.TemporaryDirectory() as prof:
                cmd = [R.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                       f"--window-size={W},{H}", "--virtual-time-budget=2500", f"--screenshot={png}"]
                if transparent:
                    cmd.append("--default-background-color=00000000")
                try:
                    subprocess.run(cmd + [f"file://{f.name}"], check=True, capture_output=True, timeout=90)
                    if Path(png).exists():
                        return
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    if n == tries - 1:
                        raise
    finally:
        Path(f.name).unlink()


def render_frames(pl, out_dir, workers=10, fps=FPS):
    """PNG sequence 0001.png..; frames that came out as identical HTML are shot once and hard-linked."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    n = int(round(pl["T"] * fps))
    transparent = pl["mode"] == "footage"
    pages = [frame_html(pl, i / fps) for i in range(n)]
    first = {}
    for i, h in enumerate(pages):
        first.setdefault(hashlib.sha1(h.encode()).hexdigest(), i)
    todo = sorted(set(first.values()))

    def one(i):
        _shoot(pages[i], out / f"{i + 1:04d}.png", transparent)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, todo))
    for i, h in enumerate(pages):
        src = out / f"{first[hashlib.sha1(h.encode()).hexdigest()] + 1:04d}.png"
        dst = out / f"{i + 1:04d}.png"
        if not dst.exists():
            os.link(src, dst)
    return n, len(todo)


ENCODE = ["-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "17", "-maxrate", "9M", "-bufsize", "18M",
          "-g", "60", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
          "-color_trc", "bt709", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1", "-shortest",
          "-movflags", "+faststart", "-use_editlist", "0"]


def assemble(pl, frames_dir, out_mp4, clip=None):
    """Same output settings as reel.assemble(). Audio is a silent track: footage audio is always dropped."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    seq = ["-framerate", str(FPS), "-i", str(Path(frames_dir) / "%04d.png")]
    tone = "scale=out_color_matrix=bt709:flags=lanczos,format=yuv420p"
    if clip:
        f = pl["footage"]
        x0, x1 = f.get("pan", (0.38, 0.62))
        start = f.get("start", 0.0)
        # the clip fills the 1080x1250 window above the headline, a window that drifts across the source;
        # a 1.16x upscale from 1080p, where a full-bleed 9:16 crop would be 1.8x
        fy = f.get("fy", 0.4)
        base = (f"[0:v]trim=start={start}:duration=7.9,setpts=PTS-STARTPTS,fps={FPS},"
                f"scale={W}:1250:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={W}:1250:x='(iw-{W})*({x0}+({x1}-{x0})*t/7.9)':y='(ih-1250)*{fy}',"
                f"pad={W}:{H}:0:0:color=0x0a0a0a,tpad=stop_mode=clone:stop_duration=4,format=yuv420p[b];"
                f"[b][1:v]overlay=shortest=1:format=auto,{tone}[v]")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip)] + seq
    else:
        base = f"[0:v]{tone}[v]"
        cmd = ["ffmpeg", "-y", "-loglevel", "error"] + seq
    nin = 2 if clip else 1
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-filter_complex", base, "-map", "[v]", "-map", f"{nin}:a",
            "-t", f"{pl['T']:.2f}", "-r", str(FPS)] + ENCODE + [str(out_mp4)]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)
    return out_mp4


def build(pl, out_mp4, clip=None, workers=10):
    with tempfile.TemporaryDirectory() as tmp:
        n, shot = render_frames(pl, tmp, workers)
        assemble(pl, tmp, out_mp4, clip)
    return n, shot


def cover(mp4, out_jpg, at=2.6):
    """The Reel's cover (thumb): a frame of the finished video once the headline is in."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", str(mp4), "-frames:v", "1", "-q:v", "2", str(out_jpg)],
                   check=True, capture_output=True)


def sheet(mp4, out_jpg, per_second=2.5, cols=7):
    """Contact sheet for review: frames at 2.5 per second, 216 px wide, 7 across."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True).stdout)
    rows = -(-int(dur * per_second) // cols)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    f"fps={per_second},scale=216:384,tile={cols}x{rows}:padding=4:color=0x333333", "-frames:v", "1", "-q:v", "3", str(out_jpg)],
                   check=True, capture_output=True)


# ---- audit -----------------------------------------------------------------------------------------------------

def audit_video(path):
    """Instagram's Reels spec, checked on the file. Returns the list of problems (empty = passes). The API takes
    MP4/MOV, H.264 or HEVC, AAC, 23-60 fps, width up to 1920, 3 s to 15 min, 300 MB; we hold ourselves to the narrower
    set the rest of the pipeline uses, so a Reel never differs from the daily recap in codec or frame rate."""
    out = []
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                  capture_output=True, text=True).stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    if v.get("codec_name") != "h264" or v.get("profile") != "High" or v.get("pix_fmt") != "yuv420p":
        out.append(f"video is {v.get('codec_name')}/{v.get('profile')}/{v.get('pix_fmt')}, not h264/High/yuv420p")
    if (v.get("width"), v.get("height")) != (W, H):
        out.append(f"size {v.get('width')}x{v.get('height')}, not {W}x{H}")
    if v.get("r_frame_rate") != f"{FPS}/1":
        out.append(f"frame rate {v.get('r_frame_rate')}")
    if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000":
        out.append("no AAC 48 kHz audio stream (some clients refuse a Reel without one)")
    dur = float(j["format"]["duration"])
    if not 6 <= dur <= 15:
        out.append(f"duration {dur:.1f} s outside 6 to 15 s")
    if int(j["format"]["size"]) > 50 * 1024 * 1024:
        out.append("file over 50 MB")
    head = Path(path).read_bytes()[:64 * 1024]
    if head.find(b"moov") < 0:
        out.append("moov atom not at the start (no +faststart)")
    return out


def audit_plan(pl, post, c=None, now=None):
    """What the pipeline's audit() must hold before a video is queued or sent. The video adds no claim: its text is the
    published headline, dek and sources, and its data and footage carry their own proof."""
    out = []
    if pl["headline"] != post["headlines"][0]:
        out.append("video headline differs from the post's")
    if set(pl["sources"]) - set(post.get("sources") or []):
        out.append("a source on screen is not in the post's source list")
    if pl["photo"] and not photo_ok(post):
        out.append("photo under a share-alike, no-derivatives or non-commercial licence in a video")
    if pl["photo"] and not pl["photo"]["credit"]:
        out.append("photo without credit")
    if pl["chart"]:
        age = (now or datetime.now(timezone.utc)).date() - _date.fromisoformat(pl["chart"]["pts"][-1][0])
        if age.days > 4:
            out.append(f"chart data is {age.days} days old")
        if not pl["chart"]["source"]:
            out.append("chart without a source line")
    if pl["footage"]:
        f = pl["footage"]
        if not f.get("credit") or not f.get("licence") or not f.get("page"):
            out.append("footage without credit, licence or source page")
        if f.get("source") not in ("nasa", "commons"):
            out.append(f"footage source {f.get('source')!r} is not on the allow-list")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("post")
    ap.add_argument("out")
    ap.add_argument("--footage")
    ap.add_argument("--footage-meta")
    ap.add_argument("--photo")
    ap.add_argument("--markets")
    a = ap.parse_args()
    post = json.load(open(a.post))
    if a.markets:
        M.FILE = Path(a.markets)
    m = M.load(live=False)
    meta = json.load(open(a.footage_meta)) if a.footage_meta else None
    pl = plan(post, m, a.photo, meta)
    print(build(pl, a.out, a.footage), audit_video(a.out), audit_plan(pl, post))
