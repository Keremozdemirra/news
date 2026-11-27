#!/usr/bin/env python3
"""Build the daily Face the Figure puzzle: assets/data/today.json.

One chain per UTC day, deterministic from the date: the figure just revealed stays on the balance
as A of the next round, and no company is weighed twice. Each round pairs two figures of the
same kind and unit (USD revenue vs USD revenue, headcount vs headcount, founding year vs
founding year, ...). Two sources, both shown to the player:

  1. our own articles: queue/*/post.json, numbers in the headline or dek that carry a unit
     (post["figure"] counts only when it appears in the headline or dek).
  2. Wikidata, for companies named in those articles: revenue (P2139), employees (P1128),
     inception year (P571). No market data (no market cap, no prices).

Rules the build enforces:
  - a Wikidata figure needs a point-in-time year no older than MAX_AGE years; revenue needs a
    currency unit; two same-year statements that disagree drop the figure (ambiguous)
  - the two figures of a round are at most MAX_YEAR_APART years apart (founding years excepted)
  - pairs within 5 percent of each other are skipped (founding years: a gap under 2 years)
  - no company comes back once it has been weighed; no two figures of a round are a tie
  - the larger figure of a round is at most MAX_RATIO times the smaller (founding years excepted); a day that
    cannot be dealt that way is dealt once more at RELAXED_RATIO
  - at most MAX_FOUNDED rounds ask for a founding year
  - a company from Wikidata must be one a reader can place: on a Topfloor list, the named company of a
    Boardread story of the last KNOWN_DAYS days, or with MIN_SITELINKS Wikipedia language editions
  - when the pool cannot make a chain of six, the day falls back to ten separate pairs

Usage: python3 build_data.py [--date YYYY-MM-DD] [--queue ../../queue] [--out assets/data/today.json]
Standard library only. Wikidata responses are cached in .cache/ for 24 h.
"""
import argparse, datetime as dt, hashlib, json, math, random, re, ssl, sys, time, unicodedata
import urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "BoardreadGames/0.1 (prototype; https://boardread.news)", "Accept": "application/json"}
API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
LAUNCH = dt.date(2026, 11, 27)  # puzzle No. 1
ROUNDS = 10
MAX_AGE = 4          # a Wikidata figure must be this many years old or newer
MIN_GAP = 0.05       # skip pairs closer than this (relative to the larger value)
MIN_YEAR_GAP = 2     # founding years: skip pairs closer than this many years
MAX_YEAR_APART = 2   # the two figures of a round come from years this close or closer
MAX_PER_SUBJECT = 2
MAX_PER_KIND = 4
MAX_RATIO = 8        # 2,850x apart is a gimme; inside 8x the call has to be thought about
RELAXED_RATIO = 15   # one wider deal for a thin day before the build gives up
MAX_FOUNDED = 2      # founding-year rounds in a day
MIN_SITELINKS = 20   # Wikipedia language editions: the floor for a company no list or story of ours names
KNOWN_DAYS = 30
SKIP_STATUS = {"held", "deleted", "failed", "expired"}

try:
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except Exception:
    CTX = ssl.create_default_context()

CURRENCY = {"Q4917": ("usd", "$"), "Q4916": ("eur", "€"), "Q25224": ("gbp", "£")}
WHAT = {"usd": "Annual revenue", "eur": "Annual revenue", "gbp": "Annual revenue", "people": "Headcount", "founded": "Year founded", "pct": "Percentage"}


# ---------------------------------------------------------------- http + cache
def http(url, retries=3):
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
                return json.load(r)
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def cached(key, url):
    cdir = HERE / ".cache"
    cdir.mkdir(exist_ok=True)
    f = cdir / (hashlib.md5(key.encode()).hexdigest()[:16] + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < 86400:
        return json.loads(f.read_text())
    data = http(url)
    f.write_text(json.dumps(data))
    return data


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w]+|_", " ", s.replace("&", " and "))
    return re.sub(r"^the ", "", re.sub(r"\s+", " ", s).strip())


# ---------------------------------------------------------------- our articles
MULT = {"trillion": 1e12, "tn": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
MONEY = re.compile(r"([$€£])\s?(\d[\d,]*(?:\.\d+)?)\s?(trillion|billion|million|thousand|tn|bn|m|k)?\b", re.I)
PCT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent\b)")
COUNT = re.compile(r"(?<![\w$€£.])(\d[\d,]*(?:\.\d+)?)\s?(trillion|billion|million|thousand)?\s+((?:[A-Za-z][\w&'-]*\s?){1,2})")
PEOPLE = re.compile(r"^(job cuts?|jobs|workers|employees|staff|roles|layoffs?|people)\b", re.I)
SYM = {"$": "usd", "€": "eur", "£": "gbp"}


def article_url(d):
    if d.get("permalink"):
        return d["permalink"]
    for u in (d.get("source_urls") or d.get("urls") or []):
        if u.startswith("http"):
            return u
    return None


def article_figures(d):
    """Numbers with a unit from the headline and dek. One list of figure dicts per post."""
    head = (d.get("headlines") or [""])[0]
    text = f"{head}. {d.get('dek') or ''}"
    url = article_url(d)
    if not url or not head:
        return []
    subject = d.get("company") or (d.get("logo_names") or [None])[0] or d.get("topic") or "Boardread"
    created = str(d.get("created", ""))[:4] or "2026"
    base = {"subject": subject, "headline": head, "year": int(created), "src": {"name": "Boardread", "url": url, "label": "Boardread story"}}
    out, seen = [], set()
    for m in MONEY.finditer(text):
        v = float(m.group(2).replace(",", "")) * MULT.get((m.group(3) or "").lower(), 1)
        k = SYM[m.group(1)]
        if v >= 1e6 and (k, v) not in seen:
            seen.add((k, v)); out.append({**base, "kind": k, "value": v, "what": "Figure in the story", "show": m.group(0).strip()})
    for m in PCT.finditer(text):
        v = float(m.group(1))
        if ("pct", v) not in seen:
            seen.add(("pct", v)); out.append({**base, "kind": "pct", "value": v, "what": "Figure in the story", "show": m.group(0)})
    for m in COUNT.finditer(text):
        raw, mult, noun = m.group(1), (m.group(2) or "").lower(), m.group(3).strip()
        v = float(raw.replace(",", "")) * MULT.get(mult, 1)
        if re.fullmatch(r"(19|20)\d\d", raw) or v < 10 or ("count", v) in seen:
            continue
        # only counts that are people can meet a Wikidata headcount; other units have no partner
        if PEOPLE.match(noun):
            seen.add(("count", v))
            out.append({**base, "kind": "people", "value": v, "what": "Jobs in the story", "show": f"{raw} {mult} {PEOPLE.match(noun).group(1)}".replace("  ", " ").strip()})
    return out


def read_queue(queue):
    posts = []
    for f in sorted(queue.glob("*/post.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if d.get("status") in SKIP_STATUS or not d.get("headlines") or str(d["headlines"][0]).startswith("About "):
            continue
        posts.append(d)
    return posts


# ---------------------------------------------------------------- Wikidata
CAND = re.compile(r"\b([A-Z0-9][\w&'’.-]*(?:\s[A-Z0-9][\w&'’.-]*){0,2})\b")


def candidate_names(posts):
    names = {}
    for d in posts:
        head = (d.get("headlines") or [""])[0]
        for n in [d.get("company"), *(d.get("logo_names") or [])]:
            if n:
                names.setdefault(norm(n), (n, d))
        for m in CAND.finditer(f"{head}. {d.get('dek') or ''}"):
            n = m.group(1).strip(" .-’'")
            parts = n.split()
            for k in range(len(parts), 0, -1):  # longest prefix first, so "Hugging Face introduces" tries "Hugging Face"
                s = " ".join(parts[:k])
                if len(s) > 2:
                    names.setdefault(norm(s), (s, d))
    return names


def wd_companies(names):
    """name -> Wikidata id when the top hits match the name and the item is a business."""
    cand = {}
    for key, (name, d) in names.items():
        try:
            r = cached("s|" + key, API + "?action=wbsearchentities&language=en&type=item&limit=4&format=json&search=" + urllib.parse.quote(name))
        except Exception:
            continue
        for hit in r.get("search", []):
            labels = {norm(hit.get("label", "")), norm(hit.get("match", {}).get("text", ""))}
            if key in labels:
                cand[key] = hit["id"]
                break
    ids = sorted(set(cand.values()))
    biz = set()
    for i in range(0, len(ids), 60):
        chunk = ids[i:i + 60]
        q = "SELECT ?x WHERE { VALUES ?x { " + " ".join("wd:" + x for x in chunk) + " } ?x wdt:P31/wdt:P279* wd:Q4830453 . FILTER NOT EXISTS { ?x wdt:P31/wdt:P279* ?bad . VALUES ?bad { wd:Q66344 wd:Q327333 wd:Q7210356 } } }"
        for b in cached("biz|" + q, SPARQL + "?format=json&query=" + urllib.parse.quote(q))["results"]["bindings"]:
            biz.add(b["x"]["value"].rsplit("/", 1)[1])
    return {k: q for k, q in cand.items() if q in biz}


def snak_year(claim, props=("P585",)):
    for p in props:
        for s in claim.get("qualifiers", {}).get(p, []):
            t = s.get("datavalue", {}).get("value", {}).get("time")
            if t:
                return int(t[1:5])
    return None


def pick_latest(claims, fn):
    """Latest dated statement; None when two same-year statements disagree."""
    rows = []
    for c in claims:
        if c.get("rank") == "deprecated":
            continue
        r = fn(c)
        if r:
            rows.append((r, c.get("rank") == "preferred"))
    if not rows:
        return None
    top = max(r[0][0] for r in rows)
    same = [(r, pref) for r, pref in rows if r[0] == top]
    pref = [r for r, p in same if p]
    pool = pref or [r for r, _ in same]
    if len({round(p[1], 3) for p in pool}) > 1:
        return None
    return pool[0]


def wd_figures(qid, ent, today_year):
    label = ent.get("labels", {}).get("en", {}).get("value")
    if not label:
        return []
    cl = ent.get("claims", {})
    page = "https://www.wikidata.org/wiki/" + qid
    out = []

    def rev(c):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        y = snak_year(c)
        if not v or y is None:
            return None
        cur = CURRENCY.get(v.get("unit", "").rsplit("/", 1)[-1])
        amt = float(v["amount"])
        return (y, amt, cur[0]) if cur and amt > 0 else None

    def emp(c):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        y = snak_year(c)
        if not v or y is None:
            return None
        amt = float(v["amount"])
        return (y, amt) if amt > 0 else None

    def inc(c):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if not v or v.get("precision", 0) < 9:
            return None
        return (int(v["time"][1:5]), float(int(v["time"][1:5])))

    r = pick_latest(cl.get("P2139", []), rev)
    if r and today_year - r[0] <= MAX_AGE:
        out.append({"kind": r[2], "value": r[1], "year": r[0], "what": WHAT[r[2]], "anchor": "P2139"})
    r = pick_latest(cl.get("P1128", []), emp)
    if r and today_year - r[0] <= MAX_AGE:
        out.append({"kind": "people", "value": r[1], "year": r[0], "what": "Employees", "anchor": "P1128"})
    # one inception statement only: two disagreeing founding dates make the question unfair
    incs = [inc(c) for c in cl.get("P571", []) if c.get("rank") != "deprecated"]
    incs = [i for i in incs if i]
    if len({i[0] for i in incs}) == 1:
        out.append({"kind": "founded", "value": incs[0][1], "year": incs[0][0], "what": "Year founded", "anchor": "P571"})
    return [{**f, "subject": label, "qid": qid, "src": {"name": "Wikidata", "url": page + "#" + f["anchor"], "label": "Wikidata"}} for f in out]


def squash(s):
    return norm(s).replace(" ", "")


def topfloor_names():
    """Every answer Topfloor accepts, spellings included: a company on those lists is one players are asked to name."""
    names = set()
    for f in sorted((HERE.parent / "topfloor" / "assets" / "data" / "lists").glob("*.json")):
        try:
            for e in json.loads(f.read_text())["entries"]:
                names.add(squash(e[0])); names.update(e[3])
        except Exception:
            continue
    return names


def story_companies(posts, today):
    """The company a recent story of ours is about (its company and logo fields, not every capitalised word in it)."""
    names = set()
    for d in posts:
        try:
            age = (today - dt.date.fromisoformat(str(d.get("created", ""))[:10])).days
        except ValueError:
            continue
        if 0 <= age <= KNOWN_DAYS:
            names.update(squash(n) for n in [d.get("company"), *(d.get("logo_names") or [])] if n)
    return names


def wiki_editions(ent):
    return sum(1 for k in ent.get("sitelinks", {}) if k.endswith("wiki") and k not in ("commonswiki", "specieswiki", "metawiki", "wikidatawiki"))


def known_subject(subject, editions, listed, named):
    k = squash(subject)
    return k in listed or k in named or editions >= MIN_SITELINKS


def wikidata_pool(posts, today_year, report, today=None):
    names = candidate_names(posts)
    found = wd_companies(names)
    report.append(f"candidate names {len(names)}, resolved to businesses {len(found)}")
    ids = sorted(set(found.values()))
    ents = {}
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        url = API + "?action=wbgetentities&props=claims|labels|sitelinks&languages=en&format=json&ids=" + "|".join(chunk)
        ents.update(cached("es|" + "|".join(chunk), url)["entities"])
    listed, named = topfloor_names(), story_companies(posts, today or dt.datetime.now(dt.timezone.utc).date())
    figs, unknown = [], []
    for qid in ids:
        ent = ents.get(qid, {})
        got = wd_figures(qid, ent, today_year)
        if got and not known_subject(got[0]["subject"], wiki_editions(ent), listed, named):
            unknown.append(got[0]["subject"])
            continue
        figs.extend(got)
    report.append(f"left out as not widely known {len(unknown)}: " + ", ".join(sorted(unknown)))
    return figs


# ---------------------------------------------------------------- pairing
def gap(a, b):
    """How far apart two values are, in the same sense the 5 percent rule uses."""
    if a["kind"] == "founded":
        return abs(a["value"] - b["value"]) / 40.0, abs(a["value"] - b["value"]) >= MIN_YEAR_GAP
    hi, lo = max(a["value"], b["value"]), min(a["value"], b["value"])
    return math.log(hi / lo), (hi - lo) / hi >= MIN_GAP


def ratio(a, b):
    """Larger over smaller; founding years have no ratio to cap."""
    if a["kind"] == "founded":
        return 1.0
    return max(a["value"], b["value"]) / min(a["value"], b["value"])


def key_of(f):
    return f.get("qid") or norm(f["subject"] + f["headline"])


def build_pairs(figs):
    by = {}
    for f in figs:
        by.setdefault(f["kind"], []).append(f)
    pairs = []
    for kind, lst in by.items():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                if key_of(a) == key_of(b) or (a["src"]["name"] == "Boardread" and b["src"]["name"] == "Boardread" and a["headline"] == b["headline"]):
                    continue
                # "10,000 job cuts" is not a headcount and a deal size is not a year's revenue: a story's figure
                # only meets another story's figure, a company's reported figure only another reported one
                if (a["src"]["name"] == "Boardread") != (b["src"]["name"] == "Boardread"):
                    continue
                d, ok = gap(a, b)
                # a 2022 figure against a 2025 figure is not a fair duel; founding years are fixed points
                if kind != "founded" and abs(a["year"] - b["year"]) > MAX_YEAR_APART:
                    continue
                if ok:
                    pairs.append({"a": a, "b": b, "kind": kind, "d": d, "ratio": ratio(a, b),
                                  "news": (a["src"]["name"] == "Boardread") + (b["src"]["name"] == "Boardread")})
    return pairs


def choose(pairs, rng, max_ratio=MAX_RATIO):
    """Ten rounds: wide gaps first, narrow last. News figures get a heavier draw."""
    pairs = [p for p in pairs if p["ratio"] <= max_ratio]
    used, kinds, picked = {}, {}, []
    order = sorted({p["d"] for p in pairs}, reverse=True)
    for i in range(ROUNDS):
        target = 1 - i / (ROUNDS - 1)  # 1 = widest gap, 0 = narrowest
        pool = [p for p in pairs if p not in picked
                and used.get(key_of(p["a"]), 0) < MAX_PER_SUBJECT and used.get(key_of(p["b"]), 0) < MAX_PER_SUBJECT
                and kinds.get(p["kind"], 0) < (MAX_FOUNDED if p["kind"] == "founded" else MAX_PER_KIND)]
        if not pool:
            return None
        ranks = sorted(pool, key=lambda p: -p["d"])
        n = len(ranks)
        want = round((1 - target) * (n - 1))  # index into ranks, widest first
        window = sorted(range(n), key=lambda k: abs(k - want))[:max(3, n // 12)]
        weights = [1 + 2 * ranks[k]["news"] for k in window]
        k = rng.choices(window, weights=weights)[0]
        p = ranks[k]
        picked.append(p)
        for f in (p["a"], p["b"]):
            used[key_of(f)] = used.get(key_of(f), 0) + 1
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    return picked


def public(f):
    keep = {k: f[k] for k in ("kind", "subject", "what", "value", "year", "src") if k in f}
    for k in ("headline", "show", "unit"):
        if k in f:
            keep[k] = f[k]
    return keep


# ---------------------------------------------------------------- the chain
CHAIN_MIN = 6        # a shorter chain than this is not a day's game; the build falls back to separate pairs
MAX_SAME_ANSWER = 3  # in a row


def subject_key(f):
    return norm(f["subject"])


def chain(figs, pairs, rng, tries=6000, max_ratio=MAX_RATIO):
    """One run for the day: the figure just revealed stays on the balance as A of the next round.

    Nodes are subjects (a company is weighed once and never comes back), an edge is a valid pair of
    one kind. When the next round is another kind, the same company stays in pan A with its figure
    for that kind. Returns [(a, b, link)], link in start / same / turn."""
    fig = {}
    for f in figs:
        fig.setdefault((subject_key(f), f["kind"]), f)
    edges = {}
    for p in pairs:
        ka, kb = subject_key(p["a"]), subject_key(p["b"])
        if p["ratio"] > max_ratio:
            continue
        if ka == kb or fig[(ka, p["kind"])] is not p["a"] or fig[(kb, p["kind"])] is not p["b"]:
            continue
        edges.setdefault(ka, []).append((kb, p["kind"], p["d"], p["news"]))
        edges.setdefault(kb, []).append((ka, p["kind"], p["d"], p["news"]))
    best, best_score = None, -1e9
    starts = sorted(edges)
    for _ in range(tries if starts else 0):
        cur = rng.choice(starts)
        seen, path, kind, run_ans, last_ans, kinds = {cur}, [], None, 0, None, {}
        while len(path) < ROUNDS:
            opts = []
            for nb, k, d, news in edges[cur]:
                if nb in seen:
                    continue
                ans = "higher" if fig[(nb, k)]["value"] > fig[(cur, k)]["value"] else "lower"
                if ans == last_ans and run_ans >= MAX_SAME_ANSWER:
                    continue
                if kinds.get(k, 0) >= (MAX_FOUNDED if k == "founded" else 6):
                    continue
                w = (3.0 if k == kind else 1.0) * (1 + 2 * news) * (1.5 if ans != last_ans else 1.0)
                opts.append((w, nb, k, d, ans))
            if not opts:
                break
            _, nb, k, d, ans = rng.choices(opts, weights=[o[0] for o in opts])[0]
            path.append((cur, nb, k, d, ans, "start" if not path else "same" if k == kind else "turn"))
            run_ans = run_ans + 1 if ans == last_ans else 1
            last_ans, kind, cur = ans, k, nb
            kinds[k] = kinds.get(k, 0) + 1
            seen.add(nb)
        if len(path) < CHAIN_MIN:
            continue
        hi = sum(1 for x in path if x[4] == "higher")
        turns = sum(1 for x in path if x[5] == "turn")
        # long, balanced, a few column changes but not one every round, the wide gaps early
        order = sum(1 for i in range(1, len(path)) if path[i][3] <= path[i - 1][3])
        sc = len(path) * 100 - abs(2 * hi - len(path)) * 6 - abs(turns - 2) * 4 + order * 1.5 + len(kinds) * 3
        if sc > best_score:
            best, best_score = path, sc
    if not best:
        return None
    return [(fig[(a, k)], fig[(b, k)], link) for a, b, k, d, ans, link in best]


def build(date, queue):
    report = []
    posts = read_queue(queue)
    report.append(f"posts read {len(posts)}")
    news = []
    for d in posts:
        news.extend(article_figures(d))
    report.append(f"figures from articles {len(news)}: " + ", ".join(f"{f['show']} ({f['kind']})" for f in news))
    wd = wikidata_pool(posts, dt.datetime.now(dt.timezone.utc).year, report, date)
    kinds = {}
    for f in wd:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    report.append(f"figures from Wikidata {len(wd)}: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    pairs = build_pairs(news + wd)
    report.append(f"valid pairs {len(pairs)} (news in {sum(1 for p in pairs if p['news'])})")
    rng = random.Random(int(hashlib.sha256(f"face-the-figure|{date.isoformat()}".encode()).hexdigest(), 16))
    rounds, cap = [], MAX_RATIO
    links = chain(news + wd, pairs, rng)
    if not links:      # a thin day: one wider deal before the chain is given up
        cap, links = RELAXED_RATIO, chain(news + wd, pairs, rng, max_ratio=RELAXED_RATIO)
    report.append(f"figures at most {cap}x apart")
    if links:
        report.append(f"chain of {len(links)} links, {sum(1 for l in links if l[2] == 'turn')} column changes")
        for a, b, link in links:
            rounds.append({"kind": a["kind"], "what": a["what"] if a["what"] == b["what"] else WHAT.get(a["kind"], "Figure"),
                           "a": public(a), "b": public(b), "answer": "higher" if b["value"] > a["value"] else "lower", "link": link})
    else:
        report.append("no chain in this pool: separate pairs")
        picked = choose(pairs, rng) or choose(pairs, rng, RELAXED_RATIO)
        if not picked:
            return None, report
        # balance: five of each answer, in a seeded order, so a pattern cannot be guessed
        ans = ["higher"] * (ROUNDS // 2) + ["lower"] * (ROUNDS - ROUNDS // 2)
        rng.shuffle(ans)
        for p, want in zip(picked, ans):
            a, b = p["a"], p["b"]
            higher = b["value"] > a["value"]
            if (want == "higher") != higher:
                a, b = b, a
            rounds.append({"kind": p["kind"], "what": a["what"] if a["what"] == b["what"] else WHAT.get(p["kind"], "Figure"),
                           "a": public(a), "b": public(b), "answer": want, "link": "start"})
    # the practice chain is dealt on the player's device from the same figures, one per subject and kind
    pool, seen = [], set()
    for f in news + wd:
        k = (subject_key(f), f["kind"])
        if k not in seen:
            seen.add(k)
            pool.append({**public(f), "k": k[0]})
    sig = hashlib.sha256("|".join(r["a"]["subject"] + ">" + r["b"]["subject"] + r["kind"] for r in rounds).encode()).hexdigest()[:10]
    return {"v": 3, "date": date.isoformat(), "no": (date - LAUNCH).days + 1, "sig": sig,
            "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "rounds": rounds, "pool": pool,
            "rules": {"gap": MIN_GAP, "year_gap": MIN_YEAR_GAP, "years_apart": MAX_YEAR_APART, "ratio": cap, "founded": MAX_FOUNDED},
            "credit": "Figures: Boardread stories and Wikidata (CC0). Each card links to its source. No market data is used."}, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--queue", default=str(HERE.parent.parent / "queue"))
    ap.add_argument("--out", default=str(HERE / "assets/data/today.json"))
    a = ap.parse_args()
    data, report = build(dt.date.fromisoformat(a.date), Path(a.queue))
    print("\n".join(report))
    if not data:
        sys.exit("could not build a chain or ten pairs from this pool")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB), puzzle No. {data['no']}")


if __name__ == "__main__":
    main()
