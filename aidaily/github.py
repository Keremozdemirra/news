"""GitHub issues as the veto desk. Uses the workflow's own GITHUB_TOKEN, scoped to this repository.

Each queued post opens an issue with its cards and caption; the owner gets it as a
phone notification. Closing the issue or labelling it `veto` stops the post.
"""
import json
import os
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


def vetoed(number):
    """A closed issue or a `veto` label stops the post. Anything we cannot read counts as a veto."""
    try:
        got = issue(number)
    except RuntimeError:
        return True
    labels = {lb["name"].lower() for lb in got.get("labels", [])}
    return got.get("state") != "open" or "veto" in labels


def comment(number, text, close=False):
    _call("POST", f"issues/{number}/comments", {"body": text})
    if close:
        _call("PATCH", f"issues/{number}", {"state": "closed", "state_reason": "completed"})
