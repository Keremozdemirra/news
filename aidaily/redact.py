"""Removes secrets from text before it reaches a public place: a committed queue/state file or an Action log.

The repository and its logs are public. GitHub masks the exact secret values it knows, but not a value derived
from one (the Facebook Page token read through the user token) and not anything written into a committed file.
So every JSON file the desk saves and everything it prints passes through scrub(): the value of every secret
environment variable, then the shapes tokens have even when their variable is unknown.

A value shorter than MIN_LEN is not replaced: THREADS_USER_ID is "me", and replacing every "me" turned an error
message into "<secret>ssage". Short values are identifiers, not credentials.
"""
import os
import re
import urllib.parse

SECRET_ENV = ("IG_TOKEN", "THREADS_TOKEN", "FB_PAGE_TOKEN", "BSKY_APP_PASSWORD", "TG_BOT_TOKEN",
              "CLAUDE_CODE_OAUTH_TOKEN", "GITHUB_TOKEN", "GH_TOKEN", "EIA_API_KEY", "_page_token")
MIN_LEN = 12

PATTERNS = (
    # Meta tokens: EAA... (Facebook/Instagram), IGAA/IGQV... (Instagram login), THAA/THQV... (Threads)
    (re.compile(r"\b(EAA|IGAA|IGQV|THAA|THQV)[A-Za-z0-9_\-]{20,}"), "<token>"),
    # Telegram bot token: <digits>:<35 chars>
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}"), "<token>"),
    # GitHub tokens
    (re.compile(r"\b(ghp|gho|ghs|ghu|ghr|github_pat)_[A-Za-z0-9_]{20,}"), "<token>"),
    # Anthropic / Claude Code OAuth tokens
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "<token>"),
    # a token in a query string or a header, whatever its shape
    (re.compile(r"((?:access_token|api_key|apikey|token|password)=)[^&\s\"'<>]+", re.I), r"\1<token>"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{12,}", re.I), r"\1<token>"),
)


def values(environ=None):
    environ = os.environ if environ is None else environ
    got = {environ.get(k, "").strip() for k in SECRET_ENV}
    return sorted((v for v in got if len(v) >= MIN_LEN), key=len, reverse=True)


def scrub(text, environ=None, extra=(), patterns=True):
    """patterns=False replaces only the known secret values: for whole files, where a token-shaped pattern
    could also match a story's URL. Error strings and log lines get both."""
    if not text:
        return text
    text = str(text)
    for v in [*values(environ), *(x for x in extra if x and len(x) >= MIN_LEN)]:
        text = text.replace(v, "<secret>").replace(urllib.parse.quote(v, safe=""), "<secret>")
    if patterns:
        for rx, sub in PATTERNS:
            text = rx.sub(sub, text)
    return text


ERROR_KEY = re.compile(r"error", re.I)


def scrub_data(data, environ=None):
    """A JSON-able structure with every string under an *error* key fully scrubbed; other strings keep their
    shape (the caller still runs a values-only pass over the serialised file)."""
    if isinstance(data, dict):
        return {k: (scrub(v, environ) if isinstance(v, str) and ERROR_KEY.search(str(k)) else scrub_data(v, environ))
                for k, v in data.items()}
    if isinstance(data, list):
        return [scrub_data(v, environ) for v in data]
    return data


class Stream:
    """A text stream that scrubs every write: wraps sys.stdout and sys.stderr for the whole run."""

    def __init__(self, inner):
        self.inner = inner

    def write(self, s):
        return self.inner.write(scrub(s))

    def __getattr__(self, name):
        return getattr(self.inner, name)
