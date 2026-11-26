#!/usr/bin/env python3
"""Renders every story format into brand/preview/formats/ from the real published posts in queue/, and measures
each image for the phone rules (text and pictures inside Instagram's safe zone, type sizes). Calls no API,
writes nothing to queue/ or media/, and never touches desk.json.
  python3 scripts/story_formats_preview.py

The real posts predate the copy step's figure and company fields, so the preview fills them in memory, from the
headline alone, the way the copy step would have. A format the real posts cannot feed (a quiz needs four
companies, a board four posts of one topic) is rendered a second time from a few made-up posts and its file name
ends in -fixture: layout only, never a statement about news.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import desk  # noqa: E402
from aidaily import render as R  # noqa: E402
from aidaily import templates as T  # noqa: E402

OUT = desk.HERE / "brand" / "preview" / "formats"
CACHE = desk.HERE / "assets" / "cache"
NOW = datetime(2026, 11, 26, 20, 40, tzinfo=timezone.utc)  # a Thursday, after every real post was published
MEASURE = """<script>
(()=>{const o={top:1e9,bottom:0,left:1e9,right:0,small:[]};
const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
while(w.nextNode()){const n=w.currentNode;if(!n.nodeValue.trim())continue;
const r=document.createRange();r.selectNodeContents(n);const b=r.getBoundingClientRect();if(!b.width)continue;
const fs=parseFloat(getComputedStyle(n.parentElement).fontSize);
o.top=Math.min(o.top,b.top);o.bottom=Math.max(o.bottom,b.bottom);o.left=Math.min(o.left,b.left);o.right=Math.max(o.right,b.right);
if(fs<34)o.small.push([Math.round(fs),n.nodeValue.trim().slice(0,28)]);}
for(const i of document.images){const b=i.getBoundingClientRect();if(!b.width)continue;
o.top=Math.min(o.top,b.top);o.bottom=Math.max(o.bottom,b.bottom);}
document.body.setAttribute('data-m',JSON.stringify(o));})();
</script>"""
NAMES = ["OpenAI", "SpaceX", "Nvidia", "AMD", "Denny's", "Norse Atlantic", "Hugging Face", "Google", "Meta", "Amazon",
         "Anthropic", "Supermicro", "ElevenLabs", "Character.AI"]  # spelled as the companies spell them
FILL = [  # fixture posts: (headline, topic, company, figure, person)
    ("ElevenLabs in talks to raise at a $33B valuation", "Tech", "ElevenLabs", "$33B", ""),
    ("Mistral valued at $12B after new funding round", "Tech", "Mistral", "$12B", ""),
    ("Nvidia faces new export limits on Southeast Asia", "Tech", "Nvidia", "", ""),
    ("Nvidia posts record quarterly revenue of $57B", "Markets", "Nvidia", "$57B", ""),
    ("Nvidia stock falls after chip export curbs widen", "Markets", "Nvidia", "", ""),
    ("Lisa Su says AMD will double AI chip output", "Tech", "AMD", "", "Lisa Su"),
    ("Satya Nadella defends Microsoft's AI spending", "Tech", "Microsoft", "", "Satya Nadella"),
    ("Banks tighten lending as yields climb", "Markets", "", "", ""),
    ("Oil slips as traders weigh supply forecasts", "Markets", "", "", ""),
    ("Bond selloff deepens across Europe", "Markets", "", "", ""),
    ("Euro zone inflation cools more than expected", "Markets", "", "", ""),
]


def logo_file(company):
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    for ext in ("svg", "png"):
        f = CACHE / f"logo-{slug}.{ext}"
        if f.exists():
            return f
    return None


def enrich(p):
    """In memory only: the figure and company the copy step would have recorded for this headline."""
    head = p["headlines"][0]
    if not p.get("figure"):
        m = re.search(r"[$€£]\d[\d,.]*\s?(?:B|M|K|T|billion|million|trillion)?\b|\d[\d,.]*%|\b\d[\d,.]* (?:million|billion)\b", head)
        p["figure"] = m.group(0).strip() if m else ""
    if not p.get("company"):
        # the company the headline names first, as the copy step would: "Hugging Face ... for AMD" is about Hugging Face
        hits = []
        for n in NAMES:
            m = re.search(rf"\b{re.escape(n)}\b", head, re.I)
            if m:
                hits.append((m.start(), n))
        p["company"] = min(hits)[1] if hits else ""
    return p


def real_pool(media):
    pool = []
    for p, _ in desk.posts():
        if p.get("status") in ("published", "web") and p.get("kind") != "story" and not p["id"].split("-")[2].startswith("about"):
            q = enrich(dict(p, status="published", published=p.get("published") or NOW.isoformat()))
            pool.append(q)
            d = media / q["id"]
            d.mkdir(parents=True, exist_ok=True)
            src = desk.MEDIA / q["id"]
            if (src / "photo.jpg").exists() and p.get("status") == "published":
                (d / "photo.jpg").symlink_to((src / "photo.jpg").resolve())
            lg = logo_file(q.get("company") or "")
            if lg:
                (d / f"logo{lg.suffix}").symlink_to(lg.resolve())
    return pool


def fixture_pool(media):
    pool = []
    for i, (head, topic, co, fig, person) in enumerate(FILL):
        pid = f"2026-11-26-fx{i}"
        when = NOW.replace(hour=15 + i % 4, minute=10 * i % 60).isoformat()
        p = {"id": pid, "status": "published", "published": when, "headlines": [head], "topic": topic, "company": co,
             "figure": fig, "person": person, "score": 9.0 - i / 10, "kind": "post"}
        d = media / pid
        d.mkdir(parents=True, exist_ok=True)
        lg = logo_file(co) if co else None
        if lg:
            (d / f"logo{lg.suffix}").symlink_to(lg.resolve())
        pool.append(p)
    return pool


def measure(html):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html.replace("</body>", MEASURE + "</body>"))
    out = subprocess.run([R.CHROME, "--headless=new", "--disable-gpu", "--window-size=1080,1920", "--virtual-time-budget=6000",
                          "--dump-dom", f"file://{f.name}"], capture_output=True, text=True, timeout=60).stdout
    Path(f.name).unlink()
    m = re.search(r"data-m='([^']*)'|data-m=\"([^\"]*)\"", out)
    return json.loads((m.group(1) or m.group(2)).replace("&quot;", '"')) if m else None


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    media = Path(tempfile.mkdtemp())
    real = real_pool(media)
    both = real + fixture_pool(media)
    pool = {"now": real}
    seen = []

    def queue_story(pid, html, title, delay=0, **extra):
        name = pid[11:] + ("-fixture" if pool["now"] is both else "")
        png = OUT / f"{name}.png"
        R.shoot(html, png, 1080, 1920)
        R.jpeg(png)
        png.unlink()
        seen.append((name, title, measure(html)))
        return OUT / f"{name}.jpg"

    def published(hours):
        cut = (NOW - desk.timedelta(hours=hours)).isoformat()
        return [p for p in pool["now"] if p["published"] > cut]

    patches = [mock.patch.object(desk, "now", return_value=NOW), mock.patch.object(desk, "MEDIA", media),
               mock.patch.object(desk, "_published", published), mock.patch.object(desk, "_queue_story", queue_story),
               mock.patch.object(desk, "_story_posts", lambda *a, **k: [])]
    for p in patches:
        p.start()
    for slot, (_, build) in desk.STORY_SLOTS.items():
        for pool["now"] in (real, both):
            if build(NOW.strftime("%Y-%m-%d"), slot, desk._story_label(slot, NOW)):
                break
    for p in patches:
        p.stop()
    bad = 0
    for name, title, m in sorted(seen):
        notes = []
        if not m:
            notes.append("not measured")
        else:
            if m["top"] < 250 or m["bottom"] > 1670:
                notes.append(f"OUTSIDE SAFE ZONE top {m['top']:.0f} bottom {m['bottom']:.0f}")
            if m["left"] < 40 or m["right"] > 1040:
                notes.append(f"edge: left {m['left']:.0f} right {m['right']:.0f}")
            if m["small"]:
                notes.append("under 34px: " + ", ".join(f"{s}px {t!r}" for s, t in m["small"]))
        bad += any(n.startswith(("OUTSIDE", "edge")) for n in notes)
        span = f"{m['top']:.0f}-{m['bottom']:.0f}" if m else "?"
        print(f"{name:22} {title:28} y {span:10} {'; '.join(notes) or 'ok'}")
    print(f"{len(seen)} images in {OUT}; {bad} outside the safe zone")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
