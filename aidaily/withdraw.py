"""Take a published post down from the platforms it was copied to, on the owner's request.

`python3 -m aidaily withdraw POST_ID` (dry run, prints what it would delete) or `... --delete` (deletes), run from the
manual-only withdraw workflow where the platform secrets live. Instagram is left alone: the owner archives or
deletes it in the app (the API cannot archive). YouTube is reported, not deleted: the token is upload-only by
design (videos.delete needs a wider scope). The site article is untouched.

Each platform is on its own; a refusal is reported with its reason and never stops the others. Endpoints:
  Telegram  deleteMessage (core.telegram.org/bots/api#deletemessage: a bot can delete its own channel posts)
  Threads   DELETE /{threads-media-id} (developers.facebook.com/docs/threads/posts, needs threads_delete)
  Bluesky   com.atproto.repo.deleteRecord on the app.bsky.feed.post record
  Facebook  DELETE /{post-id} with the Page token
"""
import json
import os
import urllib.request

from . import desk
from . import platforms as P


def copies(post):
    """[(platform, id, url)] of every recorded copy of the post on the mirrored platforms."""
    out = []
    for name, slot in (post.get("platforms") or {}).items():
        if slot.get("id") and not slot.get("removed"):
            out.append((name, str(slot["id"]), slot.get("url", "")))
    return out


def short_of(post_id):
    st = desk._load(desk.STATE / "shorts.json", {})
    rec = (st.get("attempted") or {}).get(post_id) or {}
    return rec.get("url", "")


def _delete(name, pid, client):
    if name == "telegram":
        client.call("deleteMessage", {"chat_id": client.env["TG_CHANNEL"], "message_id": int(pid)})
    elif name == "threads":
        client.call("DELETE", pid, {})
    elif name == "bluesky":
        sess = client.xrpc("com.atproto.server.createSession",
                           {"identifier": client.env["BSKY_HANDLE"], "password": client.env["BSKY_APP_PASSWORD"]})
        client.xrpc("com.atproto.repo.deleteRecord", {"repo": sess["did"], "collection": "app.bsky.feed.post",
                                                      "rkey": pid.rsplit("/", 1)[-1]}, jwt=sess["accessJwt"])
    elif name == "facebook":
        tok = client.page_token()
        req = urllib.request.Request(f"{client.host}/{client.version}/{pid}?access_token={tok}", method="DELETE")
        client._open(req, "facebook DELETE post")
    else:
        raise P.PlatformError(f"no delete for {name}")


def run(post_id, delete=False, factories=None):
    """Returns [(platform, id, url, outcome)] and records each removal on the post."""
    path = desk.QUEUE / post_id / "post.json"
    post = desk._load(path, {})
    if not post:
        raise SystemExit(f"{post_id}: no such post")
    rows = []
    for name, pid, url in copies(post):
        if not delete:
            rows.append((name, pid, url, "would delete"))
            continue
        try:
            client = (factories or P.CLIENTS)[name]()
            _delete(name, pid, client)
            post["platforms"][name]["removed"] = desk.now().isoformat(timespec="seconds")
            rows.append((name, pid, url, "deleted"))
        except Exception as e:  # noqa: BLE001  one platform's refusal never stops the others
            post["platforms"][name]["remove_error"] = str(e)[:300]
            rows.append((name, pid, url, f"NOT deleted: {str(e)[:200]}"))
    if delete:
        desk._save(path, post)
    if post.get("permalink"):
        rows.append(("instagram", post.get("media_id", ""), post["permalink"], "left to the owner (archived in the app)"))
    yt = short_of(post_id)
    rows.append(("youtube", "", yt, "NOT deleted: the token is upload-only; delete it in YouTube Studio" if yt else "no Short made"))
    for r in rows:
        print(" | ".join(r))
    return rows
