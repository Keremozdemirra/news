"""Create the Boardread Bluesky starter pack once: a reference list of accounts plus the starter pack record.

Run by hand through .github/workflows/starter.yml. Creation is not idempotent on Bluesky's side, so the script
first looks for a pack of the same name on the account and stops if one exists.
Lexicons: app.bsky.graph.list, app.bsky.graph.listitem, app.bsky.graph.starterpack (docs.bsky.app).
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import platforms  # noqa: E402

NAME = "Business & Markets News"
DESCRIPTION = "Business, markets, economy and tech news from newsrooms on Bluesky, plus Boardread."
MEMBERS = ["boardread.news", "financialtimes.com", "theverge.com", "reuters.com", "techcrunch.com",
           "wsj.com", "economist.com", "axios.com", "businessinsider.com", "cnbc.com", "opinion.bloomberg.com",
           "fortune.com", "hbr.org", "marketwatch.com"]
PUBLIC = "https://public.api.bsky.app/xrpc"


def public(name, **params):
    with urllib.request.urlopen(f"{PUBLIC}/{name}?{urllib.parse.urlencode(params)}", timeout=30) as r:
        return json.loads(r.read())


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main():
    bs = platforms.Bluesky()
    sess = bs.xrpc("com.atproto.server.createSession",
                   {"identifier": bs.env["BSKY_HANDLE"], "password": bs.env["BSKY_APP_PASSWORD"]})
    jwt, did = sess["accessJwt"], sess["did"]
    packs = public("app.bsky.graph.getActorStarterPacks", actor=did).get("starterPacks", [])
    if any((p.get("record") or {}).get("name") == NAME for p in packs):
        print(f"starter pack {NAME!r} already exists; nothing created")
        return 0
    dids = []
    for h in MEMBERS:
        try:
            dids.append(public("com.atproto.identity.resolveHandle", handle=h)["did"])
        except Exception as e:  # noqa: BLE001  one renamed account must not stop the pack
            print(f"skip {h}: {e}")
    if len(dids) < 7:  # the app needs at least seven accounts for a pack to be useful
        print(f"only {len(dids)} accounts resolved; nothing created")
        return 1

    def create(collection, record):
        return bs.xrpc("com.atproto.repo.createRecord", {"repo": did, "collection": collection, "record": record}, jwt)

    lst = create("app.bsky.graph.list", {"$type": "app.bsky.graph.list", "purpose": "app.bsky.graph.defs#referencelist",
                                         "name": NAME, "description": DESCRIPTION, "createdAt": stamp()})["uri"]
    for d in dids:
        create("app.bsky.graph.listitem", {"$type": "app.bsky.graph.listitem", "subject": d, "list": lst, "createdAt": stamp()})
    pack = create("app.bsky.graph.starterpack", {"$type": "app.bsky.graph.starterpack", "name": NAME,
                                                 "description": DESCRIPTION, "list": lst, "createdAt": stamp()})["uri"]
    rkey = pack.rsplit("/", 1)[-1]
    print(f"created starter pack with {len(dids)} accounts: https://bsky.app/starter-pack/{bs.env['BSKY_HANDLE']}/{rkey}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
