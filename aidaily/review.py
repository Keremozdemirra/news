"""The daily review page: every asset beside the text that goes with it.

Nothing leaves the machine from here. The owner reads, copies and posts; a
posting step, when it exists, reads only what this page marks approved.
"""
import html
from pathlib import Path


def e(s):
    return html.escape(s or "", quote=True)


def _post(title, text):
    return (f'<div class="post"><div class="lbl">{e(title)} · {len(text or "")} chars</div>'
            f'<pre>{e(text)}</pre><button onclick="navigator.clipboard.writeText(this.previousElementSibling.textContent)">'
            f'Copy</button></div>')


def _story(s):
    flag = '<span class="flag">source headline, copy not written</span>' if s.get("copy_status") != "ok" else ""
    return (f'<div class="story"><h3>{e(s.get("headline") or s["title"])} {flag}</h3>'
            f'<div class="meta">{e(s["category"])} · score {s["score"]} · {len(s["outlets"])} outlets · '
            f'<a href="{e(s["url"])}">{e(s["source"])}</a></div>'
            f'{_post("X", s.get("x_post", ""))}{_post("LinkedIn", s.get("linkedin_post", ""))}</div>')


def write(out, slots, files, note):
    out = Path(out)
    media = []
    for f in files:
        rel = Path(f).relative_to(out)
        tag = f'<img src="{rel}" alt="{e(f.stem)}">'
        media.append(f'<figure>{tag}<figcaption>{e(f.name)}</figcaption></figure>')
    sections = "".join(f'<h2>{e(k.replace("_", " "))}</h2>' + "".join(_story(s) for s in v)
                       for k, v in slots.items() if v)
    page = out / "review.html"
    page.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Daily pack {e(out.name)}</title>
<style>
:root{{--bg:#f5f2ea;--ink:#141412;--mute:#5d5a4f;--line:#dcd6c8;--flag:#9a3412}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171613;--ink:#ece8df;--mute:#a19d93;--line:#34322d;--flag:#f0a07a}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}}
figure{{margin:0}} img{{width:100%;border:1px solid var(--line)}}
figcaption,.meta,.lbl{{color:var(--mute);font-size:13px}}
.story{{border-top:1px solid var(--line);padding:16px 0}} h3{{margin:0 0 4px;font-size:18px}}
.flag{{color:var(--flag);font-size:13px;font-weight:500}}
.post{{margin-top:10px}} pre{{white-space:pre-wrap;font:14px/1.45 ui-monospace,monospace;margin:4px 0;padding:10px;border:1px solid var(--line)}}
button{{font:inherit;font-size:13px;padding:8px 14px;min-height:44px;cursor:pointer}} a{{color:inherit}}
</style></head><body><main>
<h1>Daily pack, {e(out.name)}</h1><p class="meta">{e(note)}</p>
<div class="grid">{"".join(media)}</div>{sections}
</main></body></html>""")
    return page
