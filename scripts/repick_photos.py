"""Pick a post's photo again under today's rules and re-render its card, detail slide and thumbnails, keeping its
checked copy, status and schedule.

usage: python3 scripts/repick_photos.py [--audit] [--dry] [--keep-photo] [ID ...]
--keep-photo renders the card and slide again with the photo the post has (after a headline correction)
--audit takes every queued, web or held post whose scene photo audit now holds (a scene that does not fit the
article, a retired one, another sport's). Run `scripts/media.sh pull` first and `scripts/media.sh push` after.
"""
import argparse
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import desk, entities as E, render as R, templates as T  # noqa: E402



def failing():
    out = []
    for p, path in desk.posts():
        # any photo, scene or credit message; a post already on social keeps its post there, only its site copy changes
        if p.get("status") in ("queued", "web", "held", "published") and p.get("kind") != "story" and any(
                w in x for x in desk.audit(p) for w in ("photo", "scene", "credit", "ShareAlike", "retired")):
            out.append(p["id"])
    return out


def repick(pid, dry=False, keep=False):
    path = desk.QUEUE / pid / "post.json"
    post = json.loads(path.read_text())
    head_ = post["headlines"][0]
    sport = post.get("topic") == "Sport"
    story = {"title": head_, "headline": head_, "dek": post.get("dek", ""), "topic": post.get("topic", ""),
             "summary": " ".join(x for x in (post.get("dek", ""), post.get("body", "")) if x),
             "category": (post.get("categories") or ["news"])[0], "published": post.get("created"),
             "source": (post.get("sources") or [""])[0], "newsrooms": post.get("sources") or [],
             "person": post.get("person") or "", "company": post.get("company") or "", "score": post.get("score", 0),
             "figure": post.get("figure", ""), "linkedin_post": post.get("body", ""), "lane": "sport" if sport else "",
             "person_role": post.get("person_role") or "", "image_query": post.get("image_query") or "",
             "orgs": post.get("orgs") or [], "venue": post.get("venue") or ""}
    T.USED.clear()
    T.USED.update(desk.used_photos() - {post.get("photo_file")})
    T.USED.add(post.get("photo_file"))  # never the photo being replaced
    if keep:
        # the photo the record names, fetched again: a hand-edited record (2312-2: CC0 stadium in post.json, BY-SA Rodgers
        # still on the card) gets its card drawn from the record, with the credit read from Commons now
        file_, kind, alt = post["photo_file"], post.get("photo_kind", ""), post.get("photo_alt", "")
        info = E._commons_info(file_, width=1600)
        ok, credit = E.photo_ok(info)
        if not ok:
            print(f"{pid}: {file_!r} fails the licence check; left as it is")
            return False
        ph = E._fetched(info, credit, file_)[0]
    else:
        ph, credit, file_, kind, alt = T.pick_photo(story, head_.lower(), story["company"], fetch=True, sport=sport)
    if not file_:
        print(f"{pid}: no photo passes; left as it is")
        return False
    logos = [E.logo(n) for n in post.get("logo_names") or []]
    logos = [x for x in logos if x]
    story["_assets"] = {"logo": logos[0].as_uri() if logos else "", "backer": "", "ticker": post.get("ticker"),
                        "logos": [x.as_uri() for x in logos], "logo_names": post.get("logo_names") or [],
                        "photo": ph.as_uri(), "credit": credit, "file": file_, "kind": kind, "alt": alt}
    new = dict(post, photo_file=file_, credit=credit, credit_file=file_, photo_kind=kind, photo_alt=alt or "")  # the old photo's alt never describes the new one
    # only what the photo decides: an old post's other notes (a caption from before the SOURCE flag) are not this fix's
    problems = [x for x in desk.audit(new) if any(w in x for w in ("photo", "scene", "credit"))]
    print(f"{pid}: {post.get('photo_file')!r} -> {file_!r} ({kind}){' HELD: ' + '; '.join(problems) if problems else ''}")
    if dry or problems:
        return False
    img = desk.MEDIA / pid
    img.mkdir(parents=True, exist_ok=True)
    # the slide keeps the text it was checked with: an old post's report was written to stand alone, before the rule
    # that the slide prints the dek and then a report that never repeats it
    text = post.get("body") or post.get("dek", "")
    for name, html in (("card", T.card(story)), ("detail", T.detail(story, text, post.get("sources") or []))):
        png = img / f"{name}.png"
        R.shoot(html, png, 1080, 1350)
        R.jpeg(png)
        png.unlink()
    R.thumb(img / "card.jpg", img / "thumb.jpg", 540)
    R.thumb(Path(urllib.parse.unquote(urllib.parse.urlparse(ph.as_uri()).path)), img / "photo.jpg", 1400)
    desk._save(path, new)
    return True


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("ids", nargs="*")
    a.add_argument("--audit", action="store_true")
    a.add_argument("--dry", action="store_true")
    a.add_argument("--keep-photo", action="store_true")
    args = a.parse_args()
    for pid in (failing() if args.audit else []) + args.ids:
        repick(pid, dry=args.dry, keep=args.keep_photo)
