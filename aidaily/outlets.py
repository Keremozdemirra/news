"""Which outlets a reader is shown for a story, and which article belongs to which outlet.

Aggregators and social accounts point at reporting; they are not newsrooms. They are dropped from every displayed
list wherever a real newsroom exists, and kept only when nothing else is left, so a story never shows an empty list.
"""
import json
import re
from urllib.parse import urlsplit

from . import desk

AGGREGATOR_NAME = re.compile(r"techmeme|google news|hacker news|^hn\b|product ?hunt|^twitter|^x$|^x\b.*\(twitter\)|^@|reddit", re.I)
AGGREGATOR_URL = re.compile(r"(^|\.)(news\.google\.com|news\.ycombinator\.com|producthunt\.com|techmeme\.com|twitter\.com|x\.com|reddit\.com)$")
# Hosts the feed list in sources.json cannot name: wire copies and sites whose feed name differs from the outlet.
KNOWN = {"bbc.co.uk": "BBC", "bbc.com": "BBC", "nytimes.com": "The New York Times", "wsj.com": "The Wall Street Journal",
         "ft.com": "Financial Times", "theguardian.com": "The Guardian", "the-decoder.com": "The Decoder",
         "theverge.com": "The Verge", "npr.org": "NPR", "dw.com": "DW", "aljazeera.com": "Al Jazeera", "cnbc.com": "CNBC",
         "axios.com": "Axios", "engadget.com": "Engadget", "fortune.com": "Fortune", "businessinsider.com": "Business Insider",
         "techcrunch.com": "TechCrunch", "reuters.com": "Reuters", "bloomberg.com": "Bloomberg", "huggingface.co": "Hugging Face Blog"}


def is_aggregator(name):
    return bool(AGGREGATOR_NAME.search((name or "").strip()))


def newsrooms(p):
    """Distinct outlet names of a story, aggregators dropped unless nothing else remains. Order is the post's own."""
    seen, out = set(), []
    for n in p.get("sources") or []:
        k = (n or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(n.strip())
    real = [n for n in out if not is_aggregator(n)]
    return real or out


def host(url):
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _domain_map():
    m = {}
    try:
        feeds = json.loads((desk.HERE / "sources.json").read_text()).get("working", [])
    except (OSError, ValueError):
        feeds = []
    for f in feeds:
        h = host(f.get("url", ""))
        if h and not h.startswith("search.") and f.get("name"):
            m.setdefault(".".join(h.split(".")[-2:]), desk.outlet(f["name"]))
    m.update(KNOWN)
    return m


_MAP = None


def outlet_of(url):
    """The outlet an article URL belongs to: the feed list and the table above by registrable domain, else the bare domain."""
    global _MAP
    _MAP = _MAP or _domain_map()
    h = host(url)
    for k in (h, ".".join(h.split(".")[-2:])):
        if k in _MAP:
            return _MAP[k]
    return h


def source_mix(p):
    """[(outlet, url)] one link per outlet, from the story's article URLs, aggregators dropped when real outlets remain."""
    urls = list(dict.fromkeys(p.get("source_urls") or p.get("urls") or []))
    rows, seen = [], set()
    for u in urls:
        o = outlet_of(u)
        if o.lower() not in seen:
            seen.add(o.lower())
            rows.append((o, u, bool(AGGREGATOR_URL.search(host(u))) or is_aggregator(o)))
    real = [(o, u) for o, u, agg in rows if not agg]
    # the coverage meter counts the outlets the post names; a link to an outlet it does not name would make the list
    # longer than the count beside it, so only those are listed (all of them when none matches by name)
    named = {n.lower() for n in newsrooms(p)}
    agreed = [(o, u) for o, u in real if o.lower() in named]
    return agreed or real or [(o, u) for o, u, _ in rows]
