#!/usr/bin/env python3
"""Connect the YouTube channel once: sign in with Google in the browser, and the upload credential goes to GitHub.

Needs a Google Cloud OAuth client of type "Desktop app" (brand/growth/YOUTUBE-SETUP.md). The client ID and secret are read
hidden; Google's sign-in page opens in the browser and sends its answer back to this machine only (a loopback address,
127.0.0.1, on a free port). The refresh token, the client ID and the client secret are handed to `gh secret set` on
stdin: nothing is printed, written to disk, or put on a command line.

The permission asked for is youtube.upload alone: upload videos, nothing else (no reading, deleting or comments).

    python3 scripts/youtube_token.py
"""
import base64
import getpass
import hashlib
import http.server
import json
import os
import secrets
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
REPO = "Keremozdemirra/news"
# python.org builds on macOS ship without CA certificates; the system bundle works everywhere here
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)


def wait_for_code(state):
    """Serve one request on 127.0.0.1 and return (redirect uri, authorisation code)."""
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                got["error"] = "the answer did not match this sign-in (state)"
            elif "error" in q:
                got["error"] = q["error"][0]
            else:
                got["code"] = q.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and go back to the terminal.")

        def log_message(self, *a):  # the request line holds the code: keep it off the terminal
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    t = threading.Thread(target=srv.handle_request, daemon=True)
    return srv, redirect, t, got


def post(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = json.loads(e.read() or b"{}")
        sys.exit(f"Google refused ({e.code}): {body.get('error', '?')} {body.get('error_description', '')[:200]}")


def secret(name, value):
    subprocess.run(["gh", "secret", "set", name, "--repo", REPO], input=value.encode(), check=True)


def main():
    client_id = input("OAuth client ID (ends in .apps.googleusercontent.com): ").strip()
    client_secret = getpass.getpass("OAuth client secret (hidden): ").strip()
    if not client_id.endswith(".apps.googleusercontent.com") or not client_secret:
        sys.exit("a Desktop-app client ID and its secret are needed (brand/growth/YOUTUBE-SETUP.md)")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    srv, redirect, t, got = wait_for_code(state)
    t.start()
    # access_type=offline and prompt=consent: Google returns a refresh token only on a fresh consent
    url = AUTH + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Opening Google sign-in. Choose the Boardread channel when Google asks which account or channel.")
    print(f"If no browser opens, paste this address into one:\n{url}\n")
    webbrowser.open(url)
    t.join(timeout=600)
    srv.server_close()
    if got.get("error") or not got.get("code"):
        sys.exit(f"sign-in did not finish: {got.get('error', 'no answer within 10 minutes')}")
    tok = post(TOKEN, {"code": got["code"], "client_id": client_id, "client_secret": client_secret,
                       "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    if not tok.get("refresh_token"):
        sys.exit("Google sent no refresh token; remove the app's access at myaccount.google.com/permissions and run again")
    if set(tok.get("scope", "").split()) != {SCOPE}:
        sys.exit(f"unexpected permissions granted: {tok.get('scope')!r}; nothing was stored")
    secret("YT_CLIENT_ID", client_id)
    secret("YT_CLIENT_SECRET", client_secret)
    secret("YT_REFRESH_TOKEN", tok["refresh_token"])
    print("done: YT_CLIENT_ID, YT_CLIENT_SECRET and YT_REFRESH_TOKEN are set on GitHub (upload permission only).")
    print('Uploads start when desk.json growth "shorts" is true.')


if __name__ == "__main__":
    main()
