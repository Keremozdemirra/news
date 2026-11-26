#!/usr/bin/env python3
"""Review page for the growth switches: brand/preview/growth.html, with images and the video embedded.

Reads real published posts from queue/ and media/, forces every growth switch on in memory only (desk.json is
never written), and calls no API. The "what it means" lines are the model's answers, unedited;
a line that fails the grounding checks is shown with its reasons and the slide is rendered without it.
  python3 scripts/growth_preview.py [--ask]   (--ask calls the claude CLI again for the lines)
"""
import base64
import html
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import copy, desk, reel  # noqa: E402
from aidaily import render as R  # noqa: E402

OUT = desk.HERE / "brand" / "preview"
IDS = ["2026-11-26-1446-9", "2026-11-26-1446-6", "2026-11-26-1520-1", "2026-11-26-1542-4", "2026-11-26-1613-4",
       "2026-11-26-1613-5", "2026-11-26-1613-6", "2026-11-26-1542-6"]
SAMPLES_FILE = OUT / "growth" / "so_what.json"


def source_text(post):
    """The feed summary the copy step saw, found in out/ by link; the published body when the run is gone."""
    for f in sorted(desk.HERE.glob("out/*/digest.json")) + sorted(desk.HERE.glob("out/*/chosen.json")):
        found = []

        def walk(x):
            if isinstance(x, dict):
                if x.get("url") == post["urls"][0] and x.get("summary"):
                    found.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(json.loads(f.read_text()))
        if found:
            return found[0].get("title") or post["headlines"][0], found[0]["summary"]
    return post["headlines"][0], post.get("body", "") + " " + post.get("dek", "")


def ask():
    """One model call on the sample posts with the so_what field on; answers are saved as given, none edited.
    Needs a logged-in claude CLI, run with the full environment (the desk's stripped one is for CI)."""
    import subprocess
    stories, posts = [], []
    for pid in IDS:
        post = json.loads((desk.QUEUE / pid / "post.json").read_text())
        title, summary = source_text(post)
        stories.append({"source": (post.get("sources") or [""])[0], "title": title, "summary": summary})
        posts.append(post)
    with mock.patch.object(copy, "switch", lambda n: True):
        rows = copy.ask_claude(copy.request(stories), lambda *a, **k: subprocess.run(*a, **{**k, "env": None}))
    out = {}
    for pid, st, row in zip(IDS, stories, rows):
        out[pid] = {"title": st["title"], "summary": st["summary"], "so_what": row.get("so_what") or "",
                    "row": {k: row.get(k, "") for k in ("headline", "dek", "linkedin_post")}, "origin": "claude CLI (sonnet), unedited"}
    SAMPLES_FILE.write_text(json.dumps(out, indent=1))


def b64(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def esc(x):
    return html.escape(x or "")


def first125(text):
    return f'<mark>{esc(text[:125])}</mark>{esc(text[125:])}'


def story_from(post, so_what):
    logo = next(iter((desk.MEDIA / post["id"]).glob("logo.*")), None)
    return {"title": post["headlines"][0], "headline": post["headlines"][0], "dek": post.get("dek", ""),
            "topic": post.get("topic", ""), "company": post.get("company", ""), "person": post.get("person", ""),
            "published": post.get("published") or post["created"], "source": (post.get("sources") or [""])[0],
            "linkedin_post": post.get("body", "") + "\n\nSource: x", "so_what": so_what, "outlets": post.get("sources", []),
            "_assets": {"logo": logo.resolve().as_uri() if logo else "", "backer": "", "logos": [], "logo_names": [],
                        "photo": "", "credit": "", "file": ""}}


def main():
    (OUT / "growth").mkdir(parents=True, exist_ok=True)
    if "--ask" in sys.argv:
        ask()
    SAMPLES = json.loads(SAMPLES_FILE.read_text())
    on = {k: True for k in ("so_what", "send_prompt", "alt_text", "keyword_caption", "daily_reel")}
    cards = []
    with mock.patch.dict(desk.CONFIG["growth"], on), mock.patch.object(copy, "switch", lambda n: True):
        for pid in IDS:
            post = json.loads((desk.QUEUE / pid / "post.json").read_text())
            sm = SAMPLES[pid]
            s = story_from(post, "")
            verdict = copy.check_so_what({"title": sm["title"], "summary": sm["summary"]}, sm["row"], sm["so_what"])
            s["so_what"] = "" if verdict else sm["so_what"]
            m = {"headline": post["headlines"][0], "source": s["source"]}
            png = OUT / "growth" / f"{pid}-detail.png"
            R.shoot(R.T.detail(s, desk.body(s), post.get("sources", []), so_what=desk.so_what(s)), png, 1080, 1350)
            R.jpeg(png)
            png.unlink()
            new = desk.caption(m, s)
            post2 = {**post, "so_what": s["so_what"]}
            cards.append({"id": pid, "post": post, "sm": sm, "verdict": verdict, "so": s["so_what"], "new": new,
                          "alts": desk.alt_texts(post2), "detail": png.with_suffix(".jpg"),
                          "card": desk.MEDIA / pid / "card.jpg"})
        mp4 = OUT / "growth" / "recap.mp4"
        posts = reel.top_posts()
        with tempfile.TemporaryDirectory() as tmp:
            reel.assemble(reel.frames(posts, tmp), mp4, 3)
        reel_caption = reel.caption(posts)
    rows = []
    for c in cards:
        p = c["post"]
        line = c["sm"]["so_what"]
        verdict = ("model returned nothing: no consequence supported, nothing shown" if not line else
                   "accepted by the grounding checks" if not c["verdict"] else "rejected, not shown: " + "; ".join(c["verdict"]))
        rows.append(f"""<section><h2>{esc(p['headlines'][0])}</h2>
<p class="m">{esc(p['id'])} · {esc(p.get('topic'))} · {esc(c['sm']['origin'])}</p>
<p><b>Line:</b> {esc(line) or '(empty)'}<br><b>Result:</b> {verdict}</p>
<div class="imgs"><figure><img src="{b64(c['card'], 'image/jpeg')}"><figcaption>card (unchanged)</figcaption></figure>
<figure><img src="{b64(c['detail'], 'image/jpeg')}"><figcaption>detail slide, new</figcaption></figure></div>
<div class="cols"><div><h3>Caption now (as published)</h3><pre>{esc(p['caption'])}</pre></div>
<div><h3>Caption with switches on</h3><pre>{first125(c['new'])}</pre><p class="m">Highlight = the first 125 characters.</p></div></div>
<h3>Alt text</h3><pre>card: {esc(c['alts'][0])}
detail: {esc(c['alts'][1])}</pre></section>""")
    summary = "".join(
        f"<tr><td>{esc(c['post']['headlines'][0][:60])}</td><td>{esc(c['sm']['so_what']) or '(empty)'}</td>"
        f"<td>{'shown' if c['so'] else 'not shown: ' + esc('; '.join(c['verdict']) if c['sm']['so_what'] else 'model returned nothing')}</td></tr>"
        for c in cards)
    page = f"""<!doctype html><meta charset="utf-8"><title>boardread growth switches</title>
<style>body{{font:16px/1.5 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#111}}
.imgs{{display:flex;gap:20px}}figure{{margin:0}}img{{width:100%;max-width:520px;border:1px solid #ddd}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}pre{{white-space:pre-wrap;background:#f4f4f2;padding:14px;font:14px/1.45 ui-monospace,monospace}}
td{{padding:4px 10px;border-bottom:1px solid #ddd;font-size:14px;vertical-align:top}}mark{{background:#ffe9a8}}.m,figcaption{{color:#666;font-size:14px}}section{{border-top:2px solid #111;margin-top:48px;padding-top:12px}}</style>
<h1>Growth switches, preview</h1><p class="m">All five ship off in desk.json. This page forces them on in memory. Nothing was sent anywhere.</p>
<h2>All "what it means" lines</h2><table>{summary}</table>
{''.join(rows)}
<section><h2>Daily recap Reel</h2><p class="m">1080x1920 H.264, silent AAC track, {len(posts)} stories of today by score.</p>
<video controls style="max-width:360px" src="{b64(mp4, 'video/mp4')}"></video>
<h3>Reel caption</h3><pre>{esc(reel_caption)}</pre></section>"""
    (OUT / "growth.html").write_text(page)
    print(f"wrote {OUT / 'growth.html'}")


if __name__ == "__main__":
    main()
