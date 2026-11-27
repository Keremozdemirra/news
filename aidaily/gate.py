"""The visual gate: every rendered card and story frame is measured before it is queued.

Kerem, 2026-11-27: "make sure all content is always perfect", after a wrong logo (OpenAIRE on an OpenAI post), a logo
squeezed under Instagram's slide counter and cards half empty. A person checking each post cannot keep up with the
desk, so the rules are checked on the rendered page itself:

- text: every text box inside the canvas, none clipped by its own box, no two text blocks overlapping
- platform zones: nothing of ours in the space the app draws over (zones() per format)
- logo chips: the one chip spec (templates.logo_chip): its height, the same padding on all sides, one corner radius
- credit: 22 px or more on a 1080 px canvas
- faces: no text over the face of the person in the photo (focus.detect_face, mapped through the crop)
- dead space: no empty band across the canvas deeper than DEAD of its height (measured on the screenshot)
- photo: shown only when it is of the story (feedlayouts.photo_fit "high")
- variety: not the layout the platform's previous post had

check() returns a list of problems, [] when the asset passes. The queue (desk._card) renders a failing card again in
the safest layout (pure type: no photo, no logo); if that fails too the post is held with the problems in its record.
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

from . import focus
from . import render as R
from . import templates as T

DEAD = 0.15
CREDIT_MIN = 22

MEASURE = """<script>(document.fonts?document.fonts.ready:Promise.resolve()).then(()=>setTimeout(()=>{
const out={text:[],chips:[],credits:[],clipped:[]};
// a text box is its glyph area: tight leading (a figure at line-height .82) leaves the font's content area
// hanging past the line box, where nothing is drawn, so that overhang is taken off before any check
const walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
const seen=new Set();const els=[];
while(walk.nextNode()){const n=walk.currentNode;if(!n.textContent.trim())continue;const el=n.parentElement;
 if(!el||seen.has(el)||el.closest('script,style'))continue;seen.add(el);const s=getComputedStyle(el);
 if(s.visibility==='hidden'||s.display==='none'||+s.opacity===0)continue;
 const r=document.createRange();r.selectNodeContents(el);const b=r.getBoundingClientRect();
 if(b.width<1||b.height<1)continue;
 const fs=parseFloat(s.fontSize),lh=s.lineHeight==='normal'?fs*1.2:parseFloat(s.lineHeight),pad=Math.max(0,(fs*1.15-lh)/2);
 out.text.push({t:el.textContent.trim().slice(0,40),x1:b.left,y1:b.top+pad,x2:b.right,y2:b.bottom-pad,fs:fs,
   block:(el.closest('h1,h2,p,[data-text],[data-credit],span,div')||el).tagName});els.push(el);
 if(el.scrollWidth>el.clientWidth+2&&s.overflow!=='visible'||el.scrollHeight>el.clientHeight+2&&s.overflow==='hidden')
   out.clipped.push(el.textContent.trim().slice(0,40));}
out.text.forEach((t,i)=>{t.nest=els.map((e,j)=>j!==i&&(e.contains(els[i])||els[i].contains(e))?j:-1).filter(j=>j>=0)});
document.querySelectorAll('[data-chip]').forEach(c=>{const s=getComputedStyle(c);const b=c.getBoundingClientRect();
 out.chips.push({x1:b.left,y1:b.top,x2:b.right,y2:b.bottom,h:b.height,p:[s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft],r:s.borderTopLeftRadius});});
document.querySelectorAll('[data-credit]').forEach(c=>{out.credits.push(parseFloat(getComputedStyle(c).fontSize))});
document.body.setAttribute('data-gate',JSON.stringify(out));},400))</script></body>"""


def zones(fmt):
    """[(x1, y1, x2, y2)] the app draws over, on the format's canvas.

    feed (1080x1350): Instagram's carousel counter ("2/2") in the top right.
    story (1080x1920): Instagram's progress bar and account row at the top, the reply bar at the bottom; the frame's
    own safe area (templates.SAFE_TOP / SAFE_BOTTOM, 250 px each) is what the stories were built to.
    reel (1080x1920): the Reels player's crop and button column: text only from x 120 to 880 and y 250 to 1500
    (reelcard.py, measured on a 19.5:9 phone by the video session, 2026-11-27)."""
    if fmt == "feed":
        return [(1080 - T.IG_COUNTER, 0, 1080, T.IG_COUNTER)]
    if fmt == "story":
        return [(0, 0, 1080, T.SAFE_TOP - 1), (0, 1920 - T.SAFE_BOTTOM + 1, 1080, 1920)]
    if fmt == "reel":
        return [(0, 0, 1080, 249), (0, 1501, 1080, 1920), (0, 0, 119, 1920), (881, 0, 1080, 1920)]
    return []


def size(fmt):
    return (1080, 1350) if fmt == "feed" else (1080, 1920)


def measure(html, fmt):
    """The page's text boxes, chips and credit sizes as the browser lays them out."""
    w, h = size(fmt)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "g.html"
        f.write_text(html.replace("</body>", MEASURE, 1) if "</body>" in html else html + MEASURE)
        with tempfile.TemporaryDirectory() as profile:
            dom = subprocess.run([R.CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                                  f"--window-size={w},{h}", "--virtual-time-budget=6000", "--dump-dom", f.as_uri()],
                                 capture_output=True, text=True, timeout=90).stdout
    m = re.search(r'data-gate="([^"]*)"', dom)
    if not m:
        raise RuntimeError("the page did not report its layout")
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def _hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def layout_problems(m, fmt):
    """Problems found in a measure() result."""
    w, h = size(fmt)
    out = []
    for t in m["text"]:
        box = (t["x1"], t["y1"], t["x2"], t["y2"])
        if t["x1"] < -1 or t["y1"] < -1 or t["x2"] > w + 1 or t["y2"] > h + 1:
            out.append(f"text off the canvas: {t['t']!r}")
        for z in zones(fmt):
            if _hit(box, z):
                out.append(f"text in the app's zone {z}: {t['t']!r}")
                break
    for c in m["clipped"]:
        out.append(f"text clipped by its box: {c!r}")
    texts = m["text"]
    for i, a in enumerate(texts):
        for j in range(i + 1, len(texts)):
            b = texts[j]
            if j in a.get("nest", []):  # a span inside its own line is not an overlap
                continue
            if _hit((a["x1"] + 2, a["y1"] + 2, a["x2"] - 2, a["y2"] - 2), (b["x1"] + 2, b["y1"] + 2, b["x2"] - 2, b["y2"] - 2)):
                out.append(f"text overlaps: {a['t']!r} and {b['t']!r}")
    for c in m["chips"]:
        pads = {round(float(p.rstrip("px"))) for p in c["p"]}
        if len(pads) != 1 or abs(next(iter(pads)) - round(c["h"] * T.CHIP_PAD)) > 1:
            out.append(f"logo chip padding {sorted(pads)} is not the chip spec")
        if abs(round(float(str(c["r"]).rstrip("px") or 0)) - round(c["h"] * T.CHIP_RADIUS)) > 1:
            out.append(f"logo chip corner radius {c['r']} is not the chip spec")
        for z in zones(fmt):
            if _hit((c["x1"], c["y1"], c["x2"], c["y2"]), z):
                out.append(f"logo chip in the app's zone {z}")
    for fs in m["credits"]:
        if fs < CREDIT_MIN:
            out.append(f"photo credit at {fs:.0f} px, below {CREDIT_MIN}")
    return out


def dead_space(png, fmt):
    """The deepest band across the whole canvas with nothing in it, as a share of its height. Measured on a 54-wide
    grey decode: a row is empty when its pixels hardly differ from one another."""
    w, h = 54, (67 if fmt == "feed" else 96)
    try:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(png), "-vf", f"scale={w}:{h}:flags=area",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return 0.0
    if len(raw) < w * h:
        return 0.0
    # only the part of the canvas we may fill: the app's own bands (a story's top and bottom 250 px) are empty by rule
    lo, hi = (0, h) if fmt == "feed" else (round(h * T.SAFE_TOP / 1920), round(h * (1920 - T.SAFE_BOTTOM) / 1920))
    if fmt == "reel":
        lo, hi = round(h * 250 / 1920), round(h * 1500 / 1920)
    run = best = 0
    for y in range(lo, hi):
        row = raw[y * w:(y + 1) * w]
        empty = max(row) - min(row) < 10
        run = run + 1 if empty else 0
        best = max(best, run)
    return best / h  # as a share of the whole canvas


def face_box(photo_uri, box_w, box_h, top=0, about=None):
    """(x1, y1, x2, y2) on the canvas of the face in a photo drawn at (0, top) as box_w x box_h with object-fit cover
    and the crop the templates use, or None."""
    from urllib.parse import unquote, urlparse
    path = unquote(urlparse(photo_uri).path) if photo_uri.startswith("file:") else ""
    if not path or not Path(path).exists():
        return None
    found = focus.detect_face(path)
    dims = focus.jpeg_size(path)
    if not found or not dims:
        return None
    fx, fy, fw = found
    iw, ih = dims
    scale = max(box_w / iw, box_h / ih)
    dw, dh = iw * scale, ih * scale
    px, py = (float(v.rstrip("%")) / 100 for v in T._pos(photo_uri, box_w, box_h, about).split())
    ox, oy = (box_w - dw) * px, (box_h - dh) * py
    cx, cy, r = ox + fx * dw, top + oy + fy * dh, fw * dw / 2
    return (cx - r, cy - r * 1.3, cx + r, cy + r * 1.3)


def check(html, fmt="feed", png=None, story=None, layout="", prev="", face=None):
    """Every problem with one rendered asset. png: its screenshot (for dead space); story: the story it shows (photo
    and logo rules); face: the face box on the canvas, when a photo of a person is drawn under text."""
    m = measure(html, fmt)
    problems = layout_problems(m, fmt)
    if png is not None:
        d = dead_space(png, fmt)
        if d > DEAD:
            problems.append(f"empty band {d:.0%} of the canvas deep")
    if layout and prev and layout == prev:
        problems.append(f"same layout as the previous post ({layout})")
    if story is not None:
        from . import feedlayouts as FL
        a = story.get("_assets") or {}
        if a.get("photo") and layout in ("photo", "split", "place") and FL.photo_fit(story) != "high":
            problems.append("photo shown that is not of the story")
        head_ = (story.get("headline") or story.get("title") or "").lower()
        for n in a.get("logo_names") or []:
            if not T.in_headline(n, head_):
                problems.append(f"logo of {n}, whom the headline does not name")
    if face:
        for t in m["text"]:
            if _hit((t["x1"], t["y1"], t["x2"], t["y2"]), face):
                problems.append(f"text over the face: {t['t']!r}")
                break
    return problems
