"""python3 -m aidaily run [--sources PATH] [--out DIR] [--top N]

Fetches every working source, ranks the stories of the last 36 hours and
writes out/<date>/digest.json, digest.md and feeds.log.
"""
import argparse
import json
import os
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
    # sport is ranked on its own: it never competes with business for a slot, and its cap is separate
    is_sport = lambda i: sources.get(i["source_id"], {}).get("category") == "sport"  # noqa: E731
    stories = rank.rank([i for i in items if not is_sport(i)], sources)
    sport = rank.rank([i for i in items if is_sport(i)], sources)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path(args.out) / day
    out.mkdir(parents=True, exist_ok=True)
    slots = plan(stories)
    (out / "digest.json").write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(), "items": len(items),
         "sources": len(sources), "slots": slots, "stories": stories[: args.top], "sport": sport[:args.top]}, indent=1))
    (out / "digest.md").write_text(to_md(day, stories, slots, errors, len(items), len(sources)))
    (out / "feeds.log").write_text("\n".join(errors) + "\n")
    print(f"{len(items)} items, {len(sources)} sources, {len(errors)} failed, {len(stories)} news, {len(sport)} sport -> {out}")
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
    render.T.BATCH.clear()
    render.T.LAST.update(desk.photo_log())
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
    files = render.pack(slots, out / "pack")
    # the ranked slots stay as prepare wrote them, so finish can run again. "final" is written after the cards,
    # so each story keeps the photo, logo and credit its card was rendered with: written before, the queue step
    # resolved them again, the card's photo was already "used", and the detail slide and credit line got
    # another photo or none (two posts held on 2026-11-26 for "photo without a credit line").
    digest["final"], digest["copy_note"], digest["copy_rejected"] = slots, note, rejected
    (out / "digest.json").write_text(json.dumps(digest, indent=1))
    page = review.write(out, slots, files, note)
    print(note)
    print(f"review: {page}")
    return 0


def _dates(d):
    """Meta's two token dates as one line for the ping log."""
    exp, data = d.get("expires"), d.get("data_access")
    return (f"expires {exp:%Y-%m-%d}" if exp else "never expires") + (f"; data access until {data:%Y-%m-%d}" if data else "")


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
    rl = sub.add_parser("reel", help="the daily recap Reel (switch growth.daily_reel): stage due, build or send")
    rl.add_argument("stage", choices=["due", "build", "send"])
    wd = sub.add_parser("withdraw", help="take a post down from the mirrored platforms (owner's request); dry run unless --delete")
    wd.add_argument("post")
    wd.add_argument("--delete", action="store_true")
    sh = sub.add_parser("shorts", help="YouTube Shorts (switch growth.shorts): stage due, run, or render a post locally")
    sh.add_argument("stage", choices=["due", "run", "render"])
    sh.add_argument("post", nargs="?", help="render: the queue id")
    sh.add_argument("out", nargs="?", help="render: the MP4 to write")
    sub.add_parser("insights", help="weekly numbers from every connected platform, weights and learned timing")
    so = sub.add_parser("seo", help="audit a built site directory for Google News, Discover and Search")
    so.add_argument("dir", nargs="?", default="_site")
    gp = sub.add_parser("games-post", help="the daily games post for Threads, Bluesky, Telegram and Facebook (switch growth.games_post); --send posts it once a day")
    gp.add_argument("--send", action="store_true")
    tp = sub.add_parser("telegram-pin", help="print the Telegram pinned post; --send posts it silently and pins it")
    tp.add_argument("--send", action="store_true")
    ix = sub.add_parser("indexnow", help="after a deploy: send the pages new since LIVE_SITEMAP to IndexNow (Bing, Yandex)")
    ix.add_argument("dir", nargs="?", default="_site")
    ix.add_argument("live", nargs="?", default="live-sitemap.xml")
    bf = sub.add_parser("bsky-feed", help="write bsky-feed.json (the Bluesky custom feed's post list) into DIR")
    bf.add_argument("dir", nargs="?", default="_site")
    bg = sub.add_parser("bsky-feed-record", help="print, or with --send write, the Bluesky feed generator record")
    bg.add_argument("host", help="the Worker's hostname, e.g. feed.boardread.news")
    bg.add_argument("--send", action="store_true")
    sub.add_parser("token", help="extend the Instagram token, warn before it expires")
    sub.add_parser("markets", help="refresh state/markets.json from the official sources (never fails)")
    sub.add_parser("site", help="build the news pages into _site/, the status page included")
    st = sub.add_parser("status", help="write status.json and the status page into DIR")
    st.add_argument("dir")
    he = sub.add_parser("health", help="check what needs the owner; open, update or close the one health issue")
    he.add_argument("--weekly", action="store_true", help="the Monday report issue instead")
    rd = sub.add_parser("redirects", help="write meta-refresh stubs for the old address (keremozdemir.de/news/...) into DIR")
    rd.add_argument("dir")
    sub.add_parser("ping", help="check the Instagram token: account name and publishing quota")
    cp = sub.add_parser("crosspost", help="send posts already live on Instagram to the switched-on platforms")
    cp.add_argument("ids", nargs="+", help="post ids, e.g. 2026-11-26-1446-2")
    dl = sub.add_parser("delete", help="delete posts or stories by queue id, and mark them deleted")
    dl.add_argument("ids", nargs="+")
    args = p.parse_args(argv)
    # the Action logs are public: nothing this run prints may carry a secret, whatever printed it
    from . import redact
    if not isinstance(sys.stdout, redact.Stream):
        sys.stdout, sys.stderr = redact.Stream(sys.stdout), redact.Stream(sys.stderr)
    if args.cmd == "serve":
        from . import server
        server.serve(args.port)
        return 0
    if args.cmd == "delete":
        from . import desk
        from .instagram import Client
        c = Client()
        failed = 0
        for pid in args.ids:
            path = desk.QUEUE / pid / "post.json"
            if not path.exists():
                print(f"{pid}: no such post")
                failed += 1
                continue
            post = desk._load(path, {})
            mid = post.get("media_id")
            # one refused id (Meta answers code 10 for posts the app may not delete) must not stop the others
            try:
                ok = c.delete(mid) if mid else False
                if post.get("story_id"):
                    c.delete(post["story_id"])
            except Exception as e:  # noqa: BLE001
                ok = False
                print(f"{pid}: Instagram refused the delete: {str(e)[:200]}; delete it in the app, then mark it deleted")
            post.update(status="deleted" if ok else post.get("status"), deleted=desk.now().isoformat(timespec="seconds") if ok else None)
            desk._save(path, post)
            print(f"{pid}: {'deleted' if ok else 'not deleted'}")
            failed += not ok
        return 1 if failed else 0
    if args.cmd == "crosspost":
        from . import desk
        wanted = set(args.ids)
        for post, path in desk.posts():
            if post["id"] not in wanted:
                continue
            wanted.discard(post["id"])
            # only what Instagram already carries: the other platforms mirror the feed, never lead it
            if post.get("status") != "published" or post.get("kind") in desk.NO_CROSSPOST:
                print(f"{post['id']}: not a published feed post, skipped")
                continue
            desk._cross_post(post, path)
        for pid in sorted(wanted):
            print(f"{pid}: no such post")
        return 0
    if args.cmd == "ping":
        from .instagram import Client
        c = Client() if os.environ.get("IG_TOKEN") else None
        if os.environ.get("IG_TOKEN"):
            print(f"account: @{c.own_username()}; quota: {c.quota()}")
            try:
                print(f"instagram token: {_dates(c.token_expiry())}")
            except Exception as e:  # noqa: BLE001
                print(f"instagram token: expiry unknown ({str(e)[:160]})")
        from . import platforms
        for name, cls in platforms.CLIENTS.items():
            try:
                client = cls()
            except platforms.Missing:
                print(f"{name}: no secrets")
                continue
            if not hasattr(client, "check"):
                print(f"{name}: secrets set, no check yet")
                continue
            try:
                print(f"{name}: {client.check()}")
            except Exception as e:  # noqa: BLE001  report every platform, not only the first broken one
                print(f"{name}: FAILED {e}")
            if hasattr(client, "token_expiry"):
                try:
                    print(f"{name} token: {_dates(client.token_expiry())}")
                except Exception as e:  # noqa: BLE001
                    print(f"{name} token: expiry unknown ({str(e)[:160]})")
        return 0
    if args.cmd == "reel":
        from . import reel
        if args.stage == "due":
            ok, why = reel.due()
            print("reel due" if ok else f"reel not due: {why}")
            return 0 if ok else 1  # the workflow runs the next stages only on 0
        if args.stage == "build":
            return 0 if reel.build() else 1
        reel.send()
        return 0
    if args.cmd == "withdraw":
        from . import withdraw
        rows = withdraw.run(args.post, delete=args.delete)
        return 1 if any(r[3].startswith("NOT deleted") and r[0] != "youtube" for r in rows) else 0
    if args.cmd == "shorts":
        from . import shorts
        if args.stage == "due":
            ok, why = shorts.due()
            print("shorts due" if ok else f"shorts not due: {why}")
            return 0 if ok else 1  # the workflow installs ffmpeg and runs only on 0
        if args.stage == "render":  # local samples: renders, never uploads
            import json as _json
            from . import desk as _desk
            post = _json.loads((_desk.QUEUE / args.post / "post.json").read_text())
            out, _ = shorts.build(post, args.out or f"{args.post}-short.mp4")
            print(out)
            return 0
        shorts.run()
        return 0
    if args.cmd == "markets":
        from . import markets
        try:
            m = markets.load(live=True)
            print("markets:", ", ".join(f"{k} {v[-1][0]}" for k, v in sorted((m or {}).get("series", {}).items())) or "nothing")
        except Exception as e:  # noqa: BLE001 (the markets data must never fail a workflow; the last good file stays)
            print(f"markets: not refreshed ({e!r})")
        return 0
    if args.cmd == "site":
        from . import site, status
        out = site.build()
        try:
            status.write(out / "status")
        except Exception as e:  # noqa: BLE001  the news pages ship even if the status page cannot be made
            print(f"status page failed: {str(e)[:200]}")
        return 0
    if args.cmd == "status":
        from . import status
        status.write(args.dir)
        return 0
    if args.cmd == "health":
        from . import status
        # health never fails its run: a red run is an e-mail, and the issue is the one channel for problems
        try:
            if args.weekly:
                from . import instagram, platforms
                dates = {}
                for name, make in (("instagram", instagram.Client), ("facebook", platforms.Facebook)):
                    try:
                        dates[name] = make().token_expiry()
                    except Exception as e:  # noqa: BLE001  the report goes out without Meta's date
                        print(f"{name} token date unavailable: {str(e)[:160]}")
                status.weekly(meta_expiry=dates)
            else:
                status.health(live_site=status.live_status())
        except Exception as e:  # noqa: BLE001
            print(f"health check crashed: {str(e)[:200]}")
        return 0
    if args.cmd == "seo":
        from . import seo, site
        return seo.main(args.dir, site.SITE)
    if args.cmd == "games-post":
        from . import games_post
        games_post.run(send=args.send)
        return 0
    if args.cmd == "telegram-pin":
        from . import distribution
        distribution.pin(send=args.send)
        return 0
    if args.cmd == "indexnow":
        from . import indexnow, site
        return indexnow.main(args.dir, args.live, site.SITE)
    if args.cmd == "bsky-feed":
        from . import distribution
        distribution.write_skeleton(args.dir)
        return 0
    if args.cmd == "bsky-feed-record":
        from . import distribution
        distribution.publish_generator(args.host, send=args.send)
        return 0
    if args.cmd == "redirects":
        from . import site
        site.redirects(args.dir)
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
            from . import insights
            report = insights.run()
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                    f.write(insights.summary_md(report))
            return 0
        desk.token_check()
        return 0
    return {"run": lambda a: run(a) and 0, "prepare": prepare, "finish": finish}[args.cmd](args)


def sport_lane(args, out, stories):
    """The sport section: its own pick, its own copy call, queued on the web tier only. Sport never reaches a social channel."""
    from . import desk
    picked = desk.select(stories, lane="sport")
    if not picked:
        print("no sport article above the bar this run")
        return 0
    lane = out / "sport"
    lane.mkdir(exist_ok=True)
    for s in picked:
        s["lane"] = "sport"
    (lane / "digest.json").write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(), "slots": {"top": picked}}, indent=1))
    (lane / "copy-request.md").write_text(copy.request(picked, lane="sport"))
    (lane / "chosen.json").write_text(json.dumps(picked, indent=1))
    try:
        (lane / "copy.json").write_text(json.dumps(copy.ask_claude((lane / "copy-request.md").read_text()), indent=1))
    except Exception as e:  # noqa: BLE001  without copy every article falls back and queue refuses it
        print(f"sport copy step failed: {e}")
    args.date = f"{out.name}/sport"
    args.out = out.parent
    finish(args)
    desk.queue(lane)
    return 0


def daily(args):
    """One run of the desk, hourly: fetch, keep the important stories not posted yet, write their copy with
    a no-tool model call, render, queue. Nothing here posts; publishing is a separate step after the veto window."""
    from . import desk
    if desk.paused():
        print("paused: no run")
        return 0
    out = run(args)
    digest = json.loads((out / "digest.json").read_text())
    try:
        desk.scheduled_stories()
    except Exception as e:  # noqa: BLE001  the story slots are extras; the news below must still run
        print(f"scheduled stories failed: {e}")
    try:
        desk.data_carousel()
    except Exception as e:  # noqa: BLE001  same: an extra, never in the news's way
        print(f"data carousel failed: {e}")
    picked = desk.select(digest["stories"])
    if picked:
        business_lane(args, out, digest, picked)
    else:
        print("no new story above the bar this run")
    try:
        sport_lane(args, out, digest.get("sport", []))
    except Exception as e:  # noqa: BLE001  the sport section is an extra; it must never fail the business run
        print(f"sport lane failed: {e}")
    return 0


def business_lane(args, out, digest, picked):
    from . import desk
    # the model only sees stories that will be posted, so an hourly run costs one short call
    digest["slots"] = {"top": picked}
    (out / "digest.json").write_text(json.dumps(digest, indent=1))
    # primary-source facts for the top few stories (switch growth.enrich); a failure leaves every story as it was
    if desk.growth("enrich"):
        try:
            from . import enrich
            ctx = enrich.live_ctx()
            done = enrich.run(picked, ctx)
            print(f"enrich: {sum(1 for _, n in done if n >= enrich.MIN_FACTS)} of {len(done)} stories got primary facts; {'; '.join(ctx.notes[:4])}")
        except Exception as e:  # noqa: BLE001
            print(f"enrich step failed: {e}")
    (out / "copy-request.md").write_text(copy.request(picked, desk.recent_headlines()))
    (out / "chosen.json").write_text(json.dumps(picked, indent=1))
    try:
        rows = copy.ask_claude((out / "copy-request.md").read_text())
        (out / "copy.json").write_text(json.dumps(rows, indent=1))
    except Exception as e:  # noqa: BLE001  without copy, every story falls back and queue refuses it
        print(f"copy step failed: {e}")
    args.date = out.name
    finish(args)
    desk.queue(out)


if __name__ == "__main__":
    sys.exit(main())
