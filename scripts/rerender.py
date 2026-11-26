"""Re-render one post's card, detail slide and thumbnails after a fix, keeping its checked copy.

usage: python3 scripts/rerender.py <queue id> [--photo "<Commons file>"] [--logos "SpaceX,Nvidia"] [--new-id ID]
With --new-id the corrected post is queued again under that id (for a post already on Instagram that was
deleted by hand); without it the queued post is changed in place.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import desk, entities as E, render as R, templates as T  # noqa: E402

a = argparse.ArgumentParser()
a.add_argument("pid")
a.add_argument("--photo")
a.add_argument("--logos", default="")
a.add_argument("--new-id")
args = a.parse_args()
old = json.loads((desk.QUEUE / args.pid / "post.json").read_text())
pid = args.new_id or args.pid
img = desk.MEDIA / pid
img.mkdir(parents=True, exist_ok=True)
photo_file = args.photo or old.get("photo_file")
info = E._commons_info(photo_file, width=1600)
ok, credit = E.photo_ok(info)
assert ok, f"{photo_file}: licence not reusable"
raw = img / "_src.jpg"
raw.write_bytes(E._get(info.get("thumburl") or info["url"], raw=True))
logos = [E.logo(n) for n in args.logos.split(",") if n.strip()]
logos = [x for x in logos if x]
n = int(old.get("score") or 0)
story = {"title": old["headlines"][0], "headline": old["headlines"][0], "dek": old.get("dek", ""),
         "topic": old.get("topic", ""), "category": (old.get("categories") or ["news"])[0],
         "published": datetime.now(timezone.utc).isoformat(), "source": (old.get("sources") or [""])[0],
         "outlets": old.get("sources") or [], "timeline": [0] * max(len(old.get("sources") or []), 1),
         "person": old.get("person") or "",
         "_assets": {"logo": logos[0].as_uri() if logos else "", "backer": "", "logos": [x.as_uri() for x in logos],
                     "photo": raw.resolve().as_uri(), "credit": credit, "file": photo_file}}
for name, html in (("card", T.card(story)), ("detail", T.detail(story, old.get("body", ""), old.get("sources") or []))):
    png = img / f"{name}.png"
    R.shoot(html, png, 1080, 1350)
    R.jpeg(png)
    png.unlink()
R.thumb(img / "card.jpg", img / "thumb.jpg", 540)
R.thumb(raw, img / "photo.jpg", 1400)
raw.unlink()
new = dict(old)
for k in ("media_id", "permalink", "published", "deleted", "note", "issue", "story_id", "story_error", "error"):
    new.pop(k, None)
new.update(id=pid, status="queued", photo_file=photo_file, credit=credit, story="",
           publish_after=datetime.now(timezone.utc).isoformat(timespec="seconds"))
if args.new_id:
    new.update(created=datetime.now(timezone.utc).isoformat(timespec="seconds"), batch=pid.rsplit("-", 1)[0])
desk._save(desk.QUEUE / pid / "post.json", new)
print(f"{pid}: card, detail, thumbs rendered; photo {photo_file}; logos {[x.name for x in logos]}")
