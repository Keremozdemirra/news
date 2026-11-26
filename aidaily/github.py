"""GitHub issues as the veto desk. Uses the workflow's own GITHUB_TOKEN, scoped to this repository.

Each queued post opens an issue with its cards and caption; the owner gets it as a
phone notification. Closing the issue or labelling it `veto` stops the post.
"""
import json
import os
import re
import urllib.error
import urllib.request

from .feeds import CTX

API = "https://api.github.com"


def _repo():
    return os.environ.get("GITHUB_REPOSITORY", "")


def enabled():
    return bool(os.environ.get("GITHUB_TOKEN") and _repo())


def _call(method, path, body=None):
    req = urllib.request.Request(f"{API}/repos/{_repo()}/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub {method} {path}: HTTP {e.code}: {e.read()[:300]!r}") from None


def open_issue(title, body, labels=()):
    # no labels by default: a label that does not exist yet would have to be created first
    return _call("POST", "issues", {"title": title, "body": body, "labels": list(labels)})["number"]


def issue(number):
    return _call("GET", f"issues/{number}")


VETO = re.compile(r"^\s*veto\s+(all|\d+(?:\s*,\s*\d+)*)\s*$", re.I | re.M)


def owner():
    return _repo().split("/")[0].lower()


def vetoed(number, n=1):
    """Post n of the issue's batch is stopped by a closed issue, a `veto` label, or a comment from the
    repository owner reading `veto all` or `veto <n>`. Anything we cannot read counts as a veto."""
    try:
        got = issue(number)
        notes = _call("GET", f"issues/{number}/comments?per_page=100")
    except RuntimeError:
        return True
    labels = {lb["name"].lower() for lb in got.get("labels", [])}
    if got.get("state") != "open" or "veto" in labels:
        return True
    for c in notes:
        if (c.get("user") or {}).get("login", "").lower() != owner():
            continue  # anyone can comment on a public issue; only the owner can veto
        for m in VETO.finditer(c.get("body", "")):
            if m.group(1).lower() == "all" or n in {int(x) for x in re.findall(r"\d+", m.group(1))}:
                return True
    return False


def close(number):
    _call("PATCH", f"issues/{number}", {"state": "closed", "state_reason": "completed"})


def comment(number, text, close=False):
    _call("POST", f"issues/{number}/comments", {"body": text})
    if close:
        _call("PATCH", f"issues/{number}", {"state": "closed", "state_reason": "completed"})
