#!/usr/bin/env python3
"""Renew the Threads credential in one step.

Paste a short-lived Threads token (from the Meta app's Threads "User Token Generator") and the app secret.
Both are read hidden, sent only to graph.threads.net, and handed to `gh secret set` on stdin: nothing is
printed, written to disk, or put on a command line.

    python3 scripts/threads_token.py
"""
import getpass
import json
import os
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request

HOST = "https://graph.threads.net"
# python.org builds on macOS ship without CA certificates; the system bundle works everywhere here
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)


def get(path, params, fail=True):
    # Meta documents both calls as GET over HTTPS; the query never leaves this process and graph.threads.net
    req = urllib.request.Request(f"{HOST}/{path}?{urllib.parse.urlencode(params)}")
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if not fail:
            return {}
        sys.exit(f"Threads refused ({e.code}): {json.loads(body).get('error', {}).get('message', body)[:200]}")


def secret(name, value):
    subprocess.run(["gh", "secret", "set", name, "--repo", "Keremozdemirra/news"], input=value.encode(), check=True)


def main():
    short = getpass.getpass("Threads token from the User Token Generator (hidden): ").strip()
    if not short:
        sys.exit("a token is needed")
    # the dashboard's generator already gives a long-lived token: refreshing it needs no app secret and
    # restarts its 60 days; only a short-lived token has to be exchanged with the secret
    long = get("refresh_access_token", {"grant_type": "th_refresh_token", "access_token": short}, fail=False)
    if not long.get("access_token"):
        # a token under a day old cannot be refreshed yet; one from the generator is already long-lived
        long = get("access_token", {"grant_type": "th_exchange_token", "access_token": short}, fail=False) or \
            {"access_token": short, "expires_in": 60 * 86400}
    token = long["access_token"]
    me = get("v1.0/me", {"fields": "id,username", "access_token": token})
    if not me.get("id"):
        sys.exit("the new token could not read its own profile")
    secret("THREADS_TOKEN", token)
    secret("THREADS_USER_ID", me["id"])
    import datetime
    until = datetime.date.today() + datetime.timedelta(seconds=int(long.get("expires_in", 0)))
    print(f"done: @{me.get('username', '?')}, valid until about {until}")


if __name__ == "__main__":
    main()
