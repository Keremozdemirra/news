"""Replay the photo picker on posts and show what it picks now beside what they carry (plan item 9). Nothing is written to
the queue or the media branch: the sheet goes to OUT_DIR, outside the repo, for a person to grade on the 0-3 scale.

usage: python3 scripts/photo_replay.py OUT_DIR [--latest N | ID ...]
"""
import html
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import desk, entities as E, render as R, templates as T  # noqa: E402


def thumb(f):
    if not f:
        return ""
    try:
        return E._commons_info(f, width=360).get("thumburl", "")
    except Exception:  # noqa: BLE001  a file Commons will not describe shows as a blank cell
        return ""


def pick(post):
    head_ = post["headlines"][0]
    sport = post.get("topic") == "Sport"
    story = {"title": head_, "headline": head_, "dek": post.get("dek", ""), "topic": post.get("topic", ""),
             "summary": " ".join(x for x in (post.get("dek", ""), post.get("body", "")) if x),
             "person": post.get("person") or "", "company": post.get("company") or "",
             "person_role": post.get("person_role") or "", "image_query": post.get("image_query") or "",
             "venue": post.get("venue") or "", "orgs": post.get("orgs") or [], "lane": "sport" if sport else ""}
    _, credit, f, kind, alt = T.pick_photo(story, head_.lower(), story["company"], fetch=True, sport=sport)
    return f, kind, credit


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    args = sys.argv[2:]
    live = sorted((p for p, _ in desk.posts() if p.get("status") in ("published", "web") and p.get("kind") != "story"),
                  key=lambda p: p["created"], reverse=True)
    posts = live[:int(args[1])] if args[:1] == ["--latest"] else [p for p in live if p["id"] in args]
    T.USED.clear()
    T.USED.update(desk.used_photos())
    T.BATCH.clear()  # the replayed posts are one batch: no scene twice among them
    rows = []
    for p in posts:
        T.USED.discard(p.get("photo_file"))
        # what repick does: a subject photo that passes the audit stays (old records carry no person_role to ask again)
        ok = p.get("photo_kind") in ("person", "company", "place", "photo") and not any(
            w in x for x in desk.audit(p) for w in ("photo", "scene", "credit", "ShareAlike", "retired"))
        f, kind, credit = (p["photo_file"], p["photo_kind"], p.get("credit", "")) if ok else pick(p)
        if f:
            T.BATCH.add(f)
        rows.append({"id": p["id"], "headline": p["headlines"][0], "topic": p.get("topic", ""),
                     "before": p.get("photo_file", ""), "before_kind": p.get("photo_kind", ""), "after": f, "after_kind": kind,
                     "credit": credit})
        print(f'{p["id"]}: {p.get("photo_file", "")[:40]!r} -> {f[:40]!r} ({kind})')
    (out / "replay.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    cells = "".join(
        f'<div class="r"><b>{n}</b><div class="h">{html.escape(r["headline"])}<i>{html.escape(r["topic"])}</i></div>'
        f'<figure><img src="{html.escape(thumb(r["before"]))}"><figcaption>before · {html.escape(r["before_kind"])}</figcaption></figure>'
        f'<figure><img src="{html.escape(thumb(r["after"]))}"><figcaption>after · {html.escape(r["after_kind"])} · '
        f'{html.escape(r["after"][:50])}</figcaption></figure></div>' for n, r in enumerate(rows, 1))
    page = ("<html><body style='margin:0;font:14px sans-serif;background:#fff'><style>.r{display:grid;grid-template-columns:"
            "40px 360px 260px 260px;gap:10px;padding:6px 10px;border-bottom:1px solid #ddd;align-items:center}"
            ".r b{font-size:20px}.h i{display:block;color:#777;font-style:normal}figure{margin:0}img{width:260px;height:150px;"
            f"object-fit:cover;background:#eee}}figcaption{{font-size:11px;color:#555}}</style>{cells}</body></html>")
    R.shoot(page, out / "replay.png", 980, 175 * len(rows) + 20)
    print(f"sheet: {out / 'replay.png'}")


if __name__ == "__main__":
    main()
