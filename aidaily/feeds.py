"""Fetch and normalise feeds. Standard library only.

Every parser returns dicts with the same keys: title, url, published (UTC
datetime or None), summary, source_id. A feed that fails returns [] and the
error goes to the caller's log; one dead feed must never stop the run.
"""
import gzip
import html
import json
import os
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# the contact URL is the public repository, so the code carries no personal address
UA = f"loopbrief/0.2 (+{os.environ.get('DESK_CONTACT_URL', 'https://github.com/Keremozdemirra/loopbrief-desk')})"
# python.org builds ship without a CA bundle; macOS keeps one here
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)
TAG = re.compile(r"<[^>]+>")


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        body = r.read()
    # some servers gzip without saying so (DeepMind, 2026-09-28)
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def clean(text, limit=600):
    text = html.unescape(TAG.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def parse_xml(raw, source_id):
    root = ET.fromstring(raw.lstrip(b"\xef\xbb\xbf \t\r\n"))
    out = []
    for el in root.iter():
        kind = _local(el.tag)
        if kind not in ("item", "entry"):
            continue
        t = _child(el, "title")
        link = _child(el, "link")
        url = ""
        if link is not None:
            url = (link.get("href") or link.text or "").strip()
        if not url:
            g = _child(el, "guid", "id")
            url = (g.text or "").strip() if g is not None else ""
        d = _child(el, "pubDate", "published", "updated", "date")
        s = _child(el, "description", "summary", "content", "encoded")
        title = clean(t.text if t is not None else "", 300)
        if title and url.startswith("http"):
            out.append({"title": title, "url": url, "source_id": source_id,
                        "published": parse_date(d.text if d is not None else None),
                        "summary": clean(s.text if s is not None else "")})
    return out


def parse_json(raw, source_id):
    data = json.loads(raw)
    out = []
    if isinstance(data, dict) and "hits" in data:  # HN Algolia
        for h in data["hits"]:
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            out.append({"title": clean(h.get("title"), 300), "url": url, "source_id": source_id,
                        "published": parse_date(h.get("created_at")), "summary": "",
                        "points": h.get("points") or 0, "comments": h.get("num_comments") or 0})
    elif isinstance(data, dict) and "data" in data and "children" in data["data"]:  # Reddit
        for c in data["data"]["children"]:
            p = c.get("data", {})
            if p.get("stickied"):
                continue
            url = p.get("url_overridden_by_dest") or "https://www.reddit.com" + p.get("permalink", "")
            out.append({"title": clean(p.get("title"), 300), "url": url, "source_id": source_id,
                        "published": datetime.fromtimestamp(p.get("created_utc", 0), timezone.utc),
                        "summary": clean(p.get("selftext")), "points": p.get("score") or 0,
                        "comments": p.get("num_comments") or 0})
    elif isinstance(data, list) and data and "paper" in data[0]:  # HF daily papers
        for d in data:
            p = d["paper"]
            out.append({"title": clean(p.get("title"), 300), "url": f"https://huggingface.co/papers/{p.get('id')}",
                        "source_id": source_id, "published": parse_date(d.get("publishedAt") or p.get("publishedAt")),
                        "summary": clean(p.get("summary")), "points": p.get("upvotes") or 0})
    return [i for i in out if i["title"]]


def fetch(source):
    """Fetch one source dict ({id, url, type}); returns (items, error)."""
    try:
        raw = http_get(source["url"])
        if source.get("type") == "json" or raw.lstrip()[:1] in (b"{", b"["):
            return parse_json(raw, source["id"]), None
        return parse_xml(raw, source["id"]), None
    except Exception as e:  # noqa: BLE001  one bad feed is logged, never fatal
        return [], f"{type(e).__name__}: {e}"
