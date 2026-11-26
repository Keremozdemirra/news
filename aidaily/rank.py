"""Classify, cluster and score items into ranked stories.

A story is a cluster of items about the same event. Its score rises with the
number of independent sources that carry it, which is the signal that it is
news and one outlet's angle is not.
"""
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

AI_TERMS = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|llms?|gpt[-\w.]*|chatgpt|claude|gemini|openai|anthropic|"
    r"deepmind|mistral|llama|deepseek|qwen|grok|xai|copilot|nvidia|gpus?|data ?cent(er|re)s?|"
    r"machine learning|neural|transformer|agents?|agentic|chatbots?|genai|diffusion|hugging ?face|"
    r"perplexity|cursor|robotics?|humanoid|superintelligence|agi|inference|foundation models?|"
    r"frontier models?|reasoning models?)\b", re.I)

CATEGORIES = [
    ("funding", r"\b(raises?|raised|funding|series [a-h]\b|seed round|valuation|valued at|backed by|"
                r"investment|invests?|financing|acquires?|acquisition|acquired|buys)\b"),
    ("policy", r"\b(regulat\w*|ai act|lawsuit|sues?|sued|court|ban(s|ned)?|senate|congress|ftc|"
               r"antitrust|copyright|executive order|white house|commission|probe)\b"),
    ("markets", r"\b(stocks?|shares|ipo|earnings|market cap|nasdaq|s&p|revenue|quarter|guidance)\b"),
    ("launch", r"\b(launch(es|ed)?|releases?|released|unveils?|introduc(es|ing)|rolls? out|debuts?|"
               r"now available|open[- ]sources?|ships?|announces?|new model|preview|beta)\b"),
    ("research", r"\b(paper|arxiv|study|benchmark|researchers?|dataset|state[- ]of[- ]the[- ]art)\b"),
    ("statement", r"\b(says?|said|warns?|interview|testif\w+|tweet(ed)?|posted|according to|claims?)\b"),
]
CATEGORIES = [(n, re.compile(p, re.I)) for n, p in CATEGORIES]

BIG = re.compile(r"\b(openai|anthropic|google|deepmind|meta|microsoft|apple|nvidia|amazon|xai|"
                 r"mistral|deepseek|alibaba|tesla|sam altman|dario amodei|demis hassabis|"
                 r"jensen huang|elon musk|satya nadella|sundar pichai|mark zuckerberg)\b", re.I)

WEIGHT = {"lab": 3.0, "news": 2.0, "newsletter": 1.5, "funding": 2.0, "community": 1.0,
          "research": 1.0, "business": 0.8}

STOP = set("a an the of to in on for and or with by at from as is are was be its it this that "
           "after over new into how why what who will can up out about more than says said have has would "
           "could amid report reportedly".split())
# verbs every launch headline shares; two stories agreeing on these alone are two stories
GENERIC = set("launches launch releases release raises raised announces unveils ships model models "
              "startup company new first world".split())
PUBLISHER_SUFFIX = re.compile(r"\s+[-|]\s+[^-|]{2,60}$")


def is_ai(item):
    return bool(AI_TERMS.search(item["title"] + " " + item.get("summary", "")[:300]))


def classify(title, summary=""):
    text = title + " " + summary[:200]
    for name, rx in CATEGORIES:
        if rx.search(title):
            return name
    for name, rx in CATEGORIES:
        if rx.search(text):
            return name
    return "news"


def tokens(title):
    title = PUBLISHER_SUFFIX.sub("", title)  # Google News appends " - AP News"
    words = re.findall(r"[a-z0-9$][a-z0-9$.\-]*", title.lower())
    return {w.strip(".-") for w in words if w not in STOP and len(w) > 2}


def norm_url(url):
    p = urlsplit(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


def similar(a, b, threshold=0.34):
    a, b = a - GENERIC, b - GENERIC
    if not a or not b:
        return False
    if len(a & b) / len(a | b) >= threshold:
        return True
    # paraphrased headlines of one event share its names, not its wording
    shared = a & b
    return len(shared) >= 3 and len(shared) / min(len(a), len(b)) >= 0.5


SECTION = re.compile(r"\s+(AI|Main|Technology|Tech|Companies|Top ?Stories|Venture)$")


def publisher(item, sources):
    """One newsroom counts once: TechCrunch AI and TechCrunch Main are TechCrunch; Google News names its outlet."""
    name = sources.get(item["source_id"], {}).get("name", item["source_id"])
    if name == "Techmeme":
        m = re.search(r"\((?:[^()/]+/)?([^()]+)\)\s*$", item["title"])
        if m:
            return m.group(1).strip()
    if name.startswith("Google News"):
        m = PUBLISHER_SUFFIX.search(item["title"])
        if m:
            return m.group(0).strip(" -|")
    while SECTION.search(name):
        name = SECTION.sub("", name)
    return name


def trace(items, sources):
    """First publish time per newsroom, oldest first."""
    first = {}
    for i in items:
        if i.get("published"):
            p = publisher(i, sources)
            if p not in first or i["published"] < first[p]:
                first[p] = i["published"]
    return [[p, t.isoformat()] for p, t in sorted(first.items(), key=lambda kv: kv[1])]


def cluster(items):
    stories = []
    for it in items:
        it["_tok"] = tokens(it["title"])
        it["_url"] = norm_url(it["url"])
        home = None
        for s in stories:
            if it["_url"] in s["urls"] or any(similar(it["_tok"], o["_tok"]) for o in s["items"]):
                home = s
                break
        if home is None:
            home = {"items": [], "urls": set()}
            stories.append(home)
        home["items"].append(it)
        home["urls"].add(it["_url"])
    return stories


def score_story(story, sources, now=None):
    now = now or datetime.now(timezone.utc)
    items = story["items"]
    cats = {sources.get(i["source_id"], {}).get("category", "news") for i in items}
    outlets = {i["source_id"] for i in items}
    base = max(WEIGHT.get(c, 1.0) for c in cats)
    breadth = 2.0 * math.log2(1 + len(outlets))
    newest = max((i["published"] for i in items if i.get("published")), default=None)
    age_h = (now - newest).total_seconds() / 3600 if newest else 36
    recency = 3.0 * math.exp(-max(age_h, 0) / 18)
    engage = math.log10(1 + sum(i.get("points", 0) + 2 * i.get("comments", 0) for i in items))
    lead = pick_lead(items, sources)
    big = 1.0 if BIG.search(lead["title"]) else 0.0
    if all(sources.get(i["source_id"], {}).get("category") == "research" for i in items):
        # papers arrive fifty a day with identical timestamps; without this they bury the news
        return round(0.6 * (base + breadth + recency + engage), 3), "research", newest
    cat = classify(lead["title"], lead.get("summary", ""))
    bonus = {"launch": 1.0, "funding": 0.8, "statement": 0.3}.get(cat, 0.0)
    return round(base + breadth + recency + engage + big + bonus, 3), cat, newest


def pick_lead(items, sources):
    """The item whose outlet ranks highest carries the headline and the link."""
    order = {"lab": 0, "news": 1, "funding": 1, "newsletter": 2, "research": 3, "community": 4, "business": 2}
    return min(items, key=lambda i: (order.get(sources.get(i["source_id"], {}).get("category"), 5),
                                     -(i["published"].timestamp() if i.get("published") else 0)))


def rank(items, sources, now=None, max_age_h=36):
    now = now or datetime.now(timezone.utc)
    keep = []
    for it in items:
        cat = sources.get(it["source_id"], {}).get("category")
        if it.get("published") and (now - it["published"]).total_seconds() > max_age_h * 3600:
            continue
        if cat in ("lab",) or cat == "business" or is_ai(it):
            keep.append(it)
    out = []
    for s in cluster(keep):
        score, cat, newest = score_story(s, sources, now)
        lead = pick_lead(s["items"], sources)
        biz = all(sources.get(i["source_id"], {}).get("category") == "business" for i in s["items"])
        out.append({
            "score": score, "category": "business" if biz and not is_ai(lead) else cat,
            "title": lead["title"], "url": lead["url"], "summary": lead.get("summary", ""),
            "source": publisher(lead, sources),
            "published": newest.isoformat() if newest else None,
            "outlets": sorted({sources.get(i["source_id"], {}).get("name", i["source_id"]) for i in s["items"]}),
            "links": sorted({i["url"] for i in s["items"]}),
            # when each newsroom first ran it: the coverage trace printed on every card
            "timeline": trace(s["items"], sources),
            # the lab's own feed carried it: announced, not reported
            "primary": next((sources[i["source_id"]]["name"] for i in s["items"]
                             if sources.get(i["source_id"], {}).get("category") == "lab"), ""),
        })
    out.sort(key=lambda s: -s["score"])
    return diversify(out)


def diversify(stories, per_source=4):
    """Keep the order but push a source's fifth and later stories below everyone else's."""
    seen, head, tail = {}, [], []
    for s in stories:
        seen[s["source"]] = seen.get(s["source"], 0) + 1
        (head if seen[s["source"]] <= per_source else tail).append(s)
    return head + tail
