"""Distribution helpers that run outside the posting loop: the Telegram pinned post, and the Bluesky custom feed.

Bluesky custom feed. The AppView asks a feed generator for app.bsky.feed.getFeedSkeleton over HTTPS and rejects any
answer not served as application/json (atproto xrpc client, readPayload / matchesEncoding). GitHub Pages picks the
content type from the file extension, and the XRPC path has none, so the static site cannot answer it. The split:
  - the site build writes /bsky-feed.json (our own Bluesky post URIs, newest first) with skeleton(), a static file;
  - scripts/bsky-feed-worker.js, a 60-line Cloudflare Worker (free tier), serves did.json, describeFeedGenerator and
    getFeedSkeleton from that file; no firehose, no database;
  - generator_record() is the one record written into the Boardread Bluesky repo that announces the feed. It is
    printed by default and written only with --send, after the owner has deployed the Worker (brand/growth/DISTRIBUTION.md).
"""
import json
from datetime import datetime, timezone

from . import desk

FEED_RKEY = "boardread"
FEED_NAME = "Boardread: business news"  # lexicon app.bsky.feed.generator: displayName max 24 graphemes
FEED_DESC = ("Every Boardread story on Bluesky, newest first: markets, economy, policy, tech and AI, each with its "
             "sources linked. Automated desk, written by AI from named newsrooms.")
MAX_FEED = 100


def skeleton(rows=None, limit=MAX_FEED):
    """{"feed": [{"post": at-uri}]}: Boardread's own Bluesky posts, newest first, the shape getFeedSkeleton returns."""
    rows = rows if rows is not None else [p for p, _ in desk.posts()]
    got = []
    for p in rows:
        slot = (p.get("platforms") or {}).get("bluesky") or {}
        uri, at = slot.get("id") or "", slot.get("at") or p.get("published") or ""
        if uri.startswith("at://") and "/app.bsky.feed.post/" in uri:
            got.append((at, uri))
    got.sort(reverse=True)
    return {"feed": [{"post": u} for _, u in got[:limit]],
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def write_skeleton(out_dir):
    from pathlib import Path
    data = skeleton()
    (Path(out_dir) / "bsky-feed.json").write_text(json.dumps(data, separators=(",", ":")))
    print(f"bsky-feed.json: {len(data['feed'])} posts")
    return data


def generator_record(service_did, now=None):
    """The app.bsky.feed.generator record (lexicon app.bsky.feed.generator: did, displayName, description, createdAt)."""
    return {"$type": "app.bsky.feed.generator", "did": service_did, "displayName": FEED_NAME[:24],
            "description": FEED_DESC[:300],
            "createdAt": (now or datetime.now(timezone.utc)).isoformat(timespec="milliseconds").replace("+00:00", "Z")}


def publish_generator(host, send=False, client=None):
    """Print, or with send=True write, the feed's generator record. host is the Worker's hostname, e.g.
    feed.boardread.news; its DID is did:web:<host>. putRecord with a fixed rkey makes a second run replace the
    record instead of minting a second feed."""
    did = f"did:web:{host}"
    record = generator_record(did)
    if not send:
        print(json.dumps({"collection": "app.bsky.feed.generator", "rkey": FEED_RKEY, "record": record}, indent=1))
        print("dry run: nothing written. Add --send once the Worker answers https://%s/.well-known/did.json" % host)
        return record
    from . import platforms
    bs = client or platforms.Bluesky()
    sess = bs.xrpc("com.atproto.server.createSession",
                   {"identifier": bs.env["BSKY_HANDLE"], "password": bs.env["BSKY_APP_PASSWORD"]})
    got = bs.xrpc("com.atproto.repo.putRecord", {"repo": sess["did"], "collection": "app.bsky.feed.generator",
                                                 "rkey": FEED_RKEY, "record": record}, sess["accessJwt"])
    print(f"feed record written: {got.get('uri')}  ->  https://bsky.app/profile/{bs.env['BSKY_HANDLE']}/feed/{FEED_RKEY}")
    return record


# Telegram

def pin_text():
    """The channel's pinned post: what this is, how it works, where else it lives, how to search it."""
    site = desk.CONFIG["site_url"]
    others = [a for a in desk.CONFIG.get("accounts", []) if a.get("url") and a["name"] != "Telegram"]
    tags = " ".join(dict.fromkeys(desk.CONFIG["topic_tags"].values()))
    lines = [
        "Boardread: the news that moves business.",
        "",
        "Markets, economy, policy, world, tech and AI, as it happens. Routine posts arrive silently; only breaking "
        "stories notify. One digest of the day's top stories every evening.",
        "",
        f"Every post links its sources on {site.split('://')[-1]}. Written by an automated desk with AI; every number is "
        "checked against the source text before anything is posted.",
        f"Corrections and standards: {site}/standards/",
        "",
        "Also on: " + ", ".join(f"{a['name']} {a['url']}" for a in others),
        "",
        f"Find posts by topic: {tags}",
    ]
    return "\n".join(lines)


def pin(send=False, client=None):
    text = pin_text()
    if not send:
        print(text)
        print("\ndry run: nothing sent. Add --send to post this silently and pin it.")
        return None
    from . import platforms
    got = (client or platforms.Telegram()).pin(text)
    print(f"pinned message {got['id']}")
    return got
