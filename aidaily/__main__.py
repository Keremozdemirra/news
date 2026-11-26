"""python3 -m aidaily run [--sources PATH] [--out DIR] [--top N]

Fetches every working source, ranks the stories of the last 36 hours and
writes out/<date>/digest.json, digest.md and feeds.log.
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import copy, feeds, rank

HERE = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = HERE / "sources.json"


def load_sources(path):
    data = json.loads(Path(path).read_text())
    rows = data["working"] if isinstance(data, dict) else data
    return {r["id"]: r for r in rows if r.get("type") in ("rss", "atom", "json")}


DISCUSSION = {"HN Front Page", "HN Algolia Search AI", "Product Hunt"}


def plan(stories):
    """Assign the day's stories to the recurring formats."""
    # a story only Hacker News carries is a discussion; it needs an outlet or a lab behind it
    ai = [s for s in stories if s["category"] not in ("business", "research")
          and set(s["outlets"]) - DISCUSSION]
    breaking = ai[:3]
    fund = [s for s in ai if s["category"] == "funding" and s not in breaking]
    biz = [s for s in stories if s["category"] in ("business", "markets") and set(s["outlets"]) - DISCUSSION]
    return {
        "breaking": breaking,
        "funding": fund[:3],
        "top": ai[:5],
        "business": biz[:2],
    }


def to_md(day, stories, slots, errors, n_items, n_sources):
    lines = [f"# AI daily digest, {day}", "",
             f"{n_items} items from {n_sources} sources, {len(stories)} stories after clustering. "
             f"{len(errors)} feeds failed (see feeds.log).", ""]
    for name, rows in slots.items():
        lines += [f"## {name}", ""]
        for s in rows:
            lines.append(f"- [{s['title']}]({s['url']}) · {s['category']} · score {s['score']} · "
                         f"{len(s['outlets'])} outlets: {', '.join(s['outlets'])}")
        lines.append("")
    lines += ["## top 30", ""]
    for s in stories[:30]:
        lines.append(f"- {s['score']:6.2f} · {s['category']:9} · [{s['title']}]({s['url']}) ({s['source']})")
    return "\n".join(lines) + "\n"


def run(args):
    sources = load_sources(args.sources)
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(feeds.fetch, sources.values()))
    items, errors = [], []
    for src, (got, err) in zip(sources.values(), results):
        if err:
            errors.append(f"{src['id']}\t{err}")
        items += got
    stories = rank.rank(items, sources)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path(args.out) / day
    out.mkdir(parents=True, exist_ok=True)
    slots = plan(stories)
    (out / "digest.json").write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(), "items": len(items),
         "sources": len(sources), "slots": slots, "stories": stories[: args.top]}, indent=1))
    (out / "digest.md").write_text(to_md(day, stories, slots, errors, len(items), len(sources)))
    (out / "feeds.log").write_text("\n".join(errors) + "\n")
    print(f"{len(items)} items, {len(sources)} sources, {len(errors)} failed, {len(stories)} stories -> {out}")
    return out


def _chosen(slots):
    chosen, seen = [], set()
    for rows in slots.values():
        for s in rows:
            if s["url"] not in seen:
                seen.add(s["url"])
                chosen.append(s)
    return chosen


def prepare(args):
    """Fetch and rank, then write copy-request.md for the Claude session that writes the copy."""
    out = run(args)
    digest = json.loads((out / "digest.json").read_text())
    chosen = _chosen(digest["slots"])
    (out / "copy-request.md").write_text(copy.request(chosen))
    (out / "chosen.json").write_text(json.dumps(chosen, indent=1))
    print(f"copy request: {out / 'copy-request.md'} ({len(chosen)} stories); answer into {out / 'copy.json'}")
    return 0


def finish(args):
    """Check the session's copy against the sources, render the pack and the review page. Posts nothing."""
    from . import desk, render, review
    render.T.USED |= desk.used_photos()
    out = Path(args.out) / (args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    digest = json.loads((out / "digest.json").read_text())
    chosen = json.loads((out / "chosen.json").read_text())
    reply = out / "copy.json"
    if reply.exists():
        rejected = copy.apply(chosen, json.loads(reply.read_text()))
        note = f"copy: {len(chosen) - len(rejected)} written, {len(rejected)} fell back to source headline"
    else:  # no session answered: ship source headlines, flagged for review
        rejected = copy.apply(chosen, [])
        note = "no copy.json; every story uses its source headline"
    # a story whose copy failed or that does not fit its slot stays off the cards
    by_url = {s["url"]: s for s in chosen if s.get("copy_status") == "ok"}
    slots = {k: [by_url[s["url"]] for s in v if s["url"] in by_url] for k, v in digest["slots"].items()}
    # the ranked slots stay as prepare wrote them, so finish can run again
    digest["final"], digest["copy_note"], digest["copy_rejected"] = slots, note, rejected
    (out / "digest.json").write_text(json.dumps(digest, indent=1))
    files = render.pack(slots, out / "pack")
    page = review.write(out, slots, files, note)
    print(note)
    print(f"review: {page}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="aidaily")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch, rank, write the digest")
    r.add_argument("--sources", default=DEFAULT_SOURCES)
    r.add_argument("--out", default=HERE / "out")
    r.add_argument("--top", type=int, default=60)
    pr = sub.add_parser("prepare", help="run, then write the copy request")
    pr.add_argument("--sources", default=DEFAULT_SOURCES)
    pr.add_argument("--out", default=HERE / "out")
    pr.add_argument("--top", type=int, default=60)
    f = sub.add_parser("finish", help="check copy.json, render the pack and review page")
    f.add_argument("--out", default=HERE / "out")
    f.add_argument("--date", help="YYYY-MM-DD, default today UTC")
    sv = sub.add_parser("serve", help="the local share desk on 127.0.0.1")
    sv.add_argument("--port", type=int, default=8742)
    d = sub.add_parser("daily", help="prepare, write copy with a no-tool model call, finish, queue a carousel")
    d.add_argument("--sources", default=DEFAULT_SOURCES)
    d.add_argument("--out", default=HERE / "out")
    d.add_argument("--top", type=int, default=60)
    n = sub.add_parser("notify", help="open the veto issue for queued posts that have none")
    pb = sub.add_parser("publish", help="publish queued posts whose veto window has passed")
    pb.add_argument("--dry", action="store_true")
    en = sub.add_parser("engage", help="answer new comments on recent posts")
    en.add_argument("--dry", action="store_true")
    sub.add_parser("insights", help="weekly numbers and category weights")
    sub.add_parser("token", help="extend the Instagram token, warn before it expires")
    sub.add_parser("site", help="build the news pages into _site/")
    sub.add_parser("ping", help="check the Instagram token: account name and publishing quota")
    args = p.parse_args(argv)
    if args.cmd == "serve":
        from . import server
        server.serve(args.port)
        return 0
    if args.cmd == "ping":
        from .instagram import Client
        c = Client()
        print(f"account: @{c.own_username()}; quota: {c.quota()}")
        return 0
    if args.cmd == "site":
        from . import site
        site.build()
        return 0
    if args.cmd in ("daily", "notify", "publish", "engage", "insights", "token"):
        from . import desk
        if args.cmd == "daily":
            return daily(args)
        if args.cmd == "notify":
            desk.notify()
            return 0
        if args.cmd == "publish":
            desk.publish(dry=args.dry)
            return 0
        if args.cmd == "engage":
            desk.engage(dry=args.dry)
            return 0
        if args.cmd == "insights":
            desk.insights()
            return 0
        desk.token_check()
        return 0
    return {"run": lambda a: run(a) and 0, "prepare": prepare, "finish": finish}[args.cmd](args)


def daily(args):
    """One run of the desk, hourly: fetch, keep the important stories not posted yet, write their copy with
    a no-tool model call, render, queue. Nothing here posts; publishing is a separate step after the veto window."""
    from . import desk
    if desk.paused():
        print("paused: no run")
        return 0
    out = run(args)
    digest = json.loads((out / "digest.json").read_text())
    picked = desk.select(digest["stories"])
    if not picked:
        print("no new story above the bar this run")
        return 0
    # the model only sees stories that will be posted, so an hourly run costs one short call
    digest["slots"] = {"top": picked}
    (out / "digest.json").write_text(json.dumps(digest, indent=1))
    (out / "copy-request.md").write_text(copy.request(picked))
    (out / "chosen.json").write_text(json.dumps(picked, indent=1))
    try:
        rows = copy.ask_claude((out / "copy-request.md").read_text())
        (out / "copy.json").write_text(json.dumps(rows, indent=1))
    except Exception as e:  # noqa: BLE001  without copy, every story falls back and queue refuses it
        print(f"copy step failed: {e}")
    args.date = out.name
    finish(args)
    desk.queue(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
