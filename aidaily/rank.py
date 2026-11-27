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
               r"antitrust|copyright|executive order|white house|commission|probe|"
               r"attorneys? general|state ags|export controls?|sanctions?)\b"),
    ("markets", r"\b(stocks?|shares|ipo|earnings|market cap|nasdaq|s&p|revenue|quarter|guidance)\b"),
    ("launch", r"\b(launch(es|ed)?|releases?|released|unveils?|introduc(es|ing)|rolls? out|debuts?|"
               r"now available|open[- ]sources?|ships?|announces?|new model|preview|beta)\b"),
    ("research", r"\b(paper|arxiv|study|benchmark|researchers?|dataset|state[- ]of[- ]the[- ]art)\b"),
    ("statement", r"\b(says?|said|warns?|interview|testif\w+|tweet(ed)?|posted|according to|claims?)\b"),
]
CATEGORIES = [(n, re.compile(p, re.I)) for n, p in CATEGORIES]

# Hard news: what changes money, law, jobs or power somewhere. A headline with one of these is news a manager
# acts on; a lab's own launch post or a column is not, however big the company behind it.
HARD = re.compile(r"\b(central bank|interest rates?|rate (cut|hike|rise)s?|raises? rates|cuts? rates|inflation|gdp|"
                  r"recession|unemployment|jobs report|payrolls|tariffs?|sanctions?|trade (deal|war|talks)|"
                  r"elections?|votes?|parliament|ceasefire|coup|resigns?|resignation|impeach\w*|indicted|"
                  r"verdict|ruling|rules|judge|supreme court|antitrust|fines?|fined|bans?|banned|"
                  r"mergers?|acquires?|acquisition|takeover|buyout|bids?|deal for|ipo|bankrupt\w*|insolven\w*|"
                  r"collapse|default\w*|bailout|layoffs?|job cuts|cuts? \d[\d,]* jobs|strikes?|recall\w*|"
                  r"earnings|profit|revenue|guidance|downgrade\w*|credit rating|bond|yields?|oil|opec|"
                  r"breach|hack(ed|ers)?|cyber-?attack|outage|appoint\w*|"
                  r"approves?|approval|clears?|blocks?|suspends?|halts?|probe|investigation)\b", re.I)
# Soft formats: comment, advice, explainers, lists and lifestyle. They may still run on the site when they
# clear the bar on breadth alone, but they never outrank the news itself.
SOFT = re.compile(r"(^opinion\b|^analysis\b|^explainer\b|^photos?:|^watch:|^live:|\blive updates\b|"
                  r"\bam i\b|\bshould i\b|\bi[’']m\b|\bi hate\b|\bmy (husband|wife|401)|\b(your|my) 401\(k\)|"
                  r"\bwhat we learned\b|\bwhat is\b|\bhow to\b|\bwhy you\b|\bbest .{0,30}(deals|of 20\d\d)\b|"
                  r"\bdeals?\b.{0,20}\b(black friday|cyber monday|prime day)\b|\b(black friday|cyber monday) deals\b|"
                  r"\bmarket talk\b|\broundup\b|\bthe latest$|\bquiz\b|\bpodcast\b|\brecipe|\bnewsletter\b|"
                  r"\bhere'?s what\b|\bthings to know\b|\bproves why\b|\b(a|one) (good|bad) thing\b|\|\s*[A-Z][a-z]+ [A-Z][a-z]+$|"
                  r"\bwhat it means\b|\brecap\w*|\bexplained\b|\bhere'?s why\b|\?\s*$)", re.I)

WEIGHT = {"lab": 2.0, "news": 2.0, "newsletter": 1.5, "funding": 2.0, "community": 1.0,
          "research": 1.0, "business": 2.0, "world": 2.0, "politics": 2.0, "culture": 1.2, "sport": 2.0}

# The competitions and events the sport section leads with; a headline naming one outranks a league's routine news.
SPORT_BIG = re.compile(r"\b(premier league|champions league|europa league|bundesliga|la liga|serie a|world cup|euros?|"
                       r"olympics?|olympic games|formula (1|one)|f1|grand prix|nba|nba finals|nfl|super bowl|wimbledon|"
                       r"us open|french open|roland garros|australian open|the masters|the open|pga championship|"
                       r"ryder cup|ashes|test match|world title|title fight)\b", re.I)
# moves that are news in any league: smaller than a major competition
SPORT_MOVE = re.compile(r"\b(transfer|signs|signing|sacked|appointed|record|ruled out|banned)\b", re.I)

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


SUFFIX = re.compile(r"(ations?|itions?|ings?|ers?|ed|es|s|al|ly)$")


def stem(w):
    """One stem for the forms of a word, so paraphrases of one event meet: "approved" and "approval",
    "satellites" and "satellite". Seven letters after the suffix, so "investigations" and "investors" stay apart."""
    return (SUFFIX.sub("", w) if len(w) > 5 else w)[:7]


def similar(a, b, threshold=0.34, weight=None):
    """Two titles report one event. With `weight` (token -> rarity), shared words count by how rare they are
    that day: on the day Nvidia's CEO returned, forty different pieces shared "Jensen Huang Nvidia", and an
    unweighted overlap chained a Denny's PR item, two columns and an investigation into one 16-outlet cluster."""
    a, b = {stem(t) for t in a - GENERIC}, {stem(t) for t in b - GENERIC}
    if not a or not b:
        return False
    shared = a & b
    if weight is None:
        if len(shared) / len(a | b) >= threshold:
            return True
        # paraphrased headlines of one event share its names, not its wording
        return len(shared) >= 3 and len(shared) / min(len(a), len(b)) >= 0.5
    w = lambda ts: sum(weight.get(t, 1.0) for t in ts)  # noqa: E731
    if not shared:
        return False
    if w(shared) / w(a | b) >= threshold:
        return True
    # the paraphrase rule needs one shared word that is not among the day's common names: "Nvidia Jensen Huang"
    # alone joins a Denny's plaque to an investigation
    cut = getattr(weight, "cut", 0.0)
    return len(shared) >= 3 and w(shared) / min(w(a), w(b)) >= 0.5 and any(weight.get(t, 9) >= cut for t in shared)


def rarity(items):
    """token -> weight, high for words few titles share today, low for the day's common names."""
    df = {}
    for it in items:
        for t in {stem(x) for x in it["_tok"]}:
            df[t] = df.get(t, 0) + 1
    n = max(len(items), 1)
    out = Weights({t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()})
    # a word in more than 0.4% of the day's titles (and at least 8) is one of the day's common names
    out.cut = math.log((n + 1) / (max(8, 0.004 * n) + 0.5))
    return out


class Weights(dict):
    cut = 0.0


# a newsroom's section feeds are one newsroom: BBC World and BBC Business, Bloomberg Markets and Bloomberg Politics
SECTION = re.compile(r"\s+(AI|Main|Technology|Tech|Companies|Top ?Stories|Top News|Venture|Business|World|"
                     r"US Politics|Politics|Economy|Economics|Markets|Finance|Asia)$")


def publisher(item, sources):
    """One newsroom counts once: TechCrunch AI and TechCrunch Main are TechCrunch; Google News names its outlet."""
    src = sources.get(item["source_id"], {})
    name = src.get("publisher") or src.get("name", item["source_id"])
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
    weight = rarity(items) if len(items) >= 50 else None  # too few titles say nothing about which words are common
    for it in items:
        home = None
        for s in stories:
            # joining needs the cluster's first item too, so one bridging title cannot chain two events together
            if it["_url"] in s["urls"] or (similar(it["_tok"], s["items"][0]["_tok"], weight=weight) or
                                           sum(similar(it["_tok"], o["_tok"], weight=weight) for o in s["items"]) * 3 >= len(s["items"])):
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
    # one newsroom counts once however many of its feeds ran the piece: BBC World, Business and Technology
    # carrying one wire read as three outlets
    outlets = {publisher(i, sources) for i in items}
    base = max(WEIGHT.get(c, 1.0) for c in cats)
    breadth = 2.0 * math.log2(1 + len(outlets))
    newest = max((i["published"] for i in items if i.get("published")), default=None)
    age_h = (now - newest).total_seconds() / 3600 if newest else 36
    recency = 3.0 * math.exp(-max(age_h, 0) / 18)
    engage = math.log10(1 + sum(i.get("points", 0) + 2 * i.get("comments", 0) for i in items))
    lead = pick_lead(items, sources)
    hard = 1.0 if any(HARD.search(i["title"]) for i in items) else 0.0
    # a cluster whose every title is a column, an explainer or a list is commentary on the news
    soft = 2.5 if all(SOFT.search(i["title"]) for i in items) else 0.0
    sport = all(sources.get(i["source_id"], {}).get("category") == "sport" for i in items)
    big = ((1.5 if SPORT_BIG.search(lead["title"]) else 0.0) + (0.5 if SPORT_MOVE.search(lead["title"]) else 0.0)) if sport else 0.0
    if all(sources.get(i["source_id"], {}).get("category") == "research" for i in items):
        # papers arrive fifty a day with identical timestamps; without this they bury the news
        return round(0.6 * (base + breadth + recency + engage), 3), "research", newest
    if sport:  # "buys" and "signs" are transfers here, not funding rounds, so the business classes do not apply
        return round(base + breadth + recency + engage + big, 3), "sport", newest
    cat = classify(lead["title"], lead.get("summary", ""))
    bonus = {"launch": 0.3, "funding": 0.5, "policy": 0.5, "markets": 0.3}.get(cat, 0.0)
    return round(base + breadth + recency + engage + hard + bonus - soft, 3), cat, newest


def reports(items, lead, sources, cap=4):
    """Title and summary from up to `cap` other newsrooms, one each, the longest summary first: never a discussion
    board, a column or the lead's own outlet."""
    seen, out = {publisher(lead, sources)}, []
    for i in sorted(items, key=lambda i: -len(i.get("summary") or "")):
        p = publisher(i, sources)
        if (p in seen or sources.get(i["source_id"], {}).get("category") == "community" or SOFT.search(i["title"])
                or not (i.get("summary") or "").strip()):
            continue
        seen.add(p)
        out.append({"outlet": p, "title": i["title"], "summary": i["summary"][:600]})
    return out[:cap]


def pick_lead(items, sources):
    """The item whose outlet ranks highest carries the headline and the link."""
    order = {"lab": 0, "news": 1, "funding": 1, "world": 1, "politics": 1, "business": 1, "culture": 2, "sport": 1,
             "newsletter": 2, "research": 3, "community": 4}
    # a column or an explainer never carries the headline while a news report of the same event is in the cluster
    return min(items, key=lambda i: (bool(SOFT.search(i["title"])),
                                     order.get(sources.get(i["source_id"], {}).get("category"), 5),
                                     -(i["published"].timestamp() if i.get("published") else 0)))


def rank(items, sources, now=None, max_age_h=36):
    now = now or datetime.now(timezone.utc)
    keep = []
    for it in items:
        cat = sources.get(it["source_id"], {}).get("category")
        if it.get("published") and (now - it["published"]).total_seconds() > max_age_h * 3600:
            continue
        # the desk covers what a consultant or manager needs to know, not only AI: every newsroom item is
        # kept, and discussion boards only when they are about AI (relevance is judged later, per story)
        if cat != "community" or is_ai(it):
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
            "outlets": sorted({sources.get(i["source_id"], {}).get("publisher") or sources.get(i["source_id"], {}).get("name", i["source_id"]) for i in s["items"]}),
            # who reported it, oldest first: one name per newsroom, never a discussion board or a search feed.
            # The card's count and the detail slide's list both come from this, so they cannot disagree.
            "newsrooms": [p for p, _ in trace([i for i in s["items"]
                                               if sources.get(i["source_id"], {}).get("category") != "community"], sources)],
            "links": sorted({i["url"] for i in s["items"]}),
            # links inside the items' own text: only a primary-source link is ever followed (enrich.py)
            "hrefs": sorted({h for i in s["items"] for h in i.get("hrefs", [])})[:12],
            # what the other newsrooms wrote: the copy step reads them and checks every word against them, so a
            # report can carry facts the lead outlet's one-line summary leaves out (26 of 91 articles had no report
            # beyond the dek on 2026-11-27, each written from a single summary)
            "reports": reports(s["items"], lead, sources),
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
