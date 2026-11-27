#!/usr/bin/env python3
"""Build the daily Topfloor puzzle: assets/data/today.json.

Seven prompts per UTC day, deterministic from the date:
  six from a Wikidata pool (instance-of classes) + one "company in today's Boardread".
Rarity comes from Wikipedia sitelink counts, as percentiles inside each prompt
(statement count breaks ties). No player data is involved; this is an offline
familiarity score, not a measured player rarity.

Usage: python3 build_data.py [--date YYYY-MM-DD] [--queue ../../queue] [--out assets/data/today.json]
Standard library only. Wikidata responses are cached in .cache/ for 24 h.
"""
import argparse, datetime as dt, hashlib, json, random, re, ssl, sys, time, unicodedata
import urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "BoardreadGames/0.1 (prototype; https://boardread.news)", "Accept": "application/json"}
SPARQL = "https://query.wikidata.org/sparql"
API = "https://www.wikidata.org/w/api.php"
LAUNCH = dt.date(2026, 11, 26)  # puzzle No. 1

# python.org builds ship without system roots; macOS keeps them in /etc/ssl/cert.pem
try:
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except Exception:
    CTX = ssl.create_default_context()

# id, prompt text, Wikidata class, min size to keep the prompt
POOL = [
    ("central-bank", "Name a central bank", "Q66344"),
    ("carmaker", "Name a carmaker", "Q786820"),
    ("airline", "Name an airline", "Q46970"),
    ("exchange", "Name a stock exchange", "Q11691"),
    ("currency", "Name a currency", "Q8142"),
    ("bank", "Name a bank", "Q22687"),
    ("crypto", "Name a cryptocurrency", "Q13479982"),
    ("supermarket", "Name a supermarket chain", "Q18043413"),
    ("index", "Name a stock market index", "Q223371"),
    ("fast-food", "Name a fast food chain", "Q18509232"),
    ("publisher", "Name a video game publisher", "Q1137109"),
    ("brewery", "Name a brewery", "Q131734"),
]
MIN_WIKI = 40       # drop a pool prompt thinner than this
MIN_BOARDREAD = 6   # drop the Boardread prompt thinner than this
TIER_CUTS = [0.10, 0.30, 0.60, 0.85]  # share of entries more familiar than this one, per tier edge
TIERS = [
    {"id": "lobby", "name": "Lobby", "pts": 10},
    {"id": "mezzanine", "name": "Mezzanine", "pts": 30},
    {"id": "corner", "name": "Corner Office", "pts": 60},
    {"id": "penthouse", "name": "Penthouse", "pts": 85},
    {"id": "helipad", "name": "Helipad", "pts": 100},
]

_MAP = str.maketrans({"ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "ı": "i", "þ": "th", "ð": "d", "ß": "ss"})
SUFFIX = re.compile(r"\s(inc|incorporated|ltd|limited|plc|llc|corp|corporation|co|company|ag|sa|se|nv|spa|gmbh|group|holdings|holding|ab|oyj|asa|bv)$")


def norm(s: str) -> str:
    """Case, diacritics and punctuation folded. Must match norm() in js/match.js."""
    s = unicodedata.normalize("NFKD", s.lower().translate(_MAP))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w]+|_", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def keys_for(label: str, aliases) -> list:
    out = []
    for name in [label, *aliases]:
        k = norm(name)
        if not k or len(k) < 2:
            continue
        for v in (k, SUFFIX.sub("", k)):
            if len(v) >= 2 and v not in out:
                out.append(v)
    return out


def http(url, retries=3):
    for i in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120, context=CTX) as r:
                return json.load(r)
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))


def sparql(query, cache_key):
    cdir = HERE / ".cache"
    cdir.mkdir(exist_ok=True)
    f = cdir / f"{cache_key}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 86400:
        return json.loads(f.read_text())
    data = http(SPARQL + "?format=json&query=" + urllib.parse.quote(query))["results"]["bindings"]
    f.write_text(json.dumps(data))
    return data


def fetch_class(qid):
    q = f"""SELECT ?x ?l ?s ?st (GROUP_CONCAT(DISTINCT ?al; SEPARATOR="|") AS ?als) WHERE {{
      ?x wdt:P31 wd:{qid}. ?x wikibase:sitelinks ?s. ?x wikibase:statements ?st.
      FILTER(?s >= 3)
      FILTER NOT EXISTS {{ ?x wdt:P576 [] }}
      FILTER NOT EXISTS {{ ?x wdt:P582 [] }}
      FILTER EXISTS {{ ?a schema:about ?x; schema:isPartOf <https://en.wikipedia.org/> }}
      ?x rdfs:label ?l. FILTER(lang(?l) = "en")
      OPTIONAL {{ ?x skos:altLabel ?al. FILTER(lang(?al) = "en") }}
    }} GROUP BY ?x ?l ?s ?st LIMIT 3500"""
    rows = []
    for b in sparql(q, qid):
        label = b["l"]["value"]
        if re.fullmatch(r"Q\d+", label) or label.lower().startswith("list of"):
            continue
        als = [a for a in b.get("als", {}).get("value", "").split("|") if a]
        rows.append({"id": b["x"]["value"].rsplit("/", 1)[1], "label": label, "sl": int(b["s"]["value"]),
                     "st": int(b["st"]["value"]), "aliases": als})
    return rows


def assign_tiers(rows):
    """Tier by familiarity rank inside the prompt. Fewer sitelinks (then fewer statements) = rarer."""
    order = sorted(rows, key=lambda r: (-r["sl"], -r["st"], r["label"]))
    n = len(order)
    for i, r in enumerate(order):
        share = i / n  # share of entries more familiar than this one
        r["rank"] = i
        r["tier"] = sum(share >= c for c in TIER_CUTS)
    return order


def pack(rows, extra=None):
    """Entries sorted most familiar first; one key owns one entry (the more familiar wins ties)."""
    order = assign_tiers(rows)
    seen, entries = {}, []
    for r in order:
        ks = [k for k in keys_for(r["label"], r["aliases"]) if k not in seen]
        if not ks:
            continue
        idx = len(entries)
        for k in ks:
            seen[k] = idx
        e = [r["label"], r["sl"], r["tier"], ks]
        if extra and r["id"] in extra:
            e.append(extra[r["id"]])
        entries.append(e)
    return entries


def pick_rare(entries, k=2):
    pool = [e for e in entries if e[2] == 4] or entries[-10:]
    pool = sorted(pool, key=lambda e: (e[1], e[0]))[:12]
    return [e[0] for e in pool[:k]]


def boardread_names(queue: Path, date: dt.date):
    """Companies named in published or queued posts created on `date` (held posts are not public)."""
    found = {}
    for f in sorted(queue.glob("*/post.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if not str(d.get("created", "")).startswith(date.isoformat()) or d.get("status") == "held":
            continue
        head = (d.get("headlines") or [""])[0]
        for name in [d.get("company"), *(d.get("logo_names") or [])]:
            if name and norm(name) not in found:
                found[norm(name)] = (name, head)
    return found


def wd_lookup(names):
    """name -> {id,label,aliases,sl,st} when the top hit matches the name and is a business."""
    cand = {}
    for name in names:
        r = http(API + "?action=wbsearchentities&language=en&type=item&limit=5&format=json&search=" + urllib.parse.quote(name))
        for hit in r.get("search", []):
            labels = [hit.get("label", ""), hit.get("match", {}).get("text", "")]
            if norm(name) in {norm(x) for x in labels}:
                cand[name] = hit["id"]
                break
    if not cand:
        return {}
    ids = " ".join("wd:" + q for q in set(cand.values()))
    biz = {b["x"]["value"].rsplit("/", 1)[1] for b in sparql(
        f"SELECT ?x WHERE {{ VALUES ?x {{ {ids} }} ?x wdt:P31/wdt:P279* wd:Q4830453 }}",
        "biz-" + hashlib.md5(ids.encode()).hexdigest()[:10])}
    out = {}
    for name, q in cand.items():
        if q not in biz:
            continue
        e = http(API + f"?action=wbgetentities&ids={q}&props=labels|aliases|sitelinks&languages=en&format=json")["entities"][q]
        sl = len(e.get("sitelinks", {}))
        als = [a["value"] for a in e.get("aliases", {}).get("en", [])]
        # statement count is not fetched here; sitelinks alone rank this small set
        out[name] = {"id": q, "label": e["labels"]["en"]["value"], "aliases": als, "sl": sl, "st": 0}
    return out


def build(date: dt.date, queue: Path):
    rng = random.Random(int(hashlib.sha256(f"topfloor|{date.isoformat()}".encode()).hexdigest(), 16))
    order = POOL[:]
    rng.shuffle(order)
    prompts, report = [], []
    for pid, text, qid in order:
        if len(prompts) == 6:
            break
        rows = fetch_class(qid)
        if len(rows) < MIN_WIKI:
            report.append(f"dropped {pid}: {len(rows)} answers")
            continue
        entries = pack(rows)
        prompts.append({"id": pid, "text": text, "src": f"wikidata:{qid}", "n": len(entries),
                        "rare": pick_rare(entries), "easy": [e[0] for e in entries[:2]], "entries": entries})
        report.append(f"kept {pid}: {len(entries)} answers")

    # today's Boardread: widen the window one day at a time until there are enough companies
    names, span = {}, 0
    while len(names) < MIN_BOARDREAD and span < 4:
        names = {}
        for d in range(span + 1):
            names.update(boardread_names(queue, date - dt.timedelta(days=d)))
        span += 1
    looked = wd_lookup([n for n, _ in names.values()])
    rows, heads = [], {}
    for k, (name, head) in names.items():
        w = looked.get(name)
        if w:
            rows.append({**w, "aliases": [*w["aliases"], name]})
            heads[w["id"]] = head
    if len(rows) >= MIN_BOARDREAD:
        entries = pack(rows, heads)
        prompts.append({"id": "boardread", "text": "Name a company in today’s Boardread", "src": "boardread",
                        "n": len(entries), "rare": pick_rare(entries), "easy": [e[0] for e in entries[:2]],
                        "entries": entries})
        report.append(f"kept boardread: {len(entries)} companies (window {span} d)")
    else:
        report.append(f"dropped boardread: {len(rows)} companies")
        extra = [p for p in order if p[0] not in {x['id'] for x in prompts}]
        for pid, text, qid in extra:
            rows = fetch_class(qid)
            if len(rows) >= MIN_WIKI:
                entries = pack(rows)
                prompts.append({"id": pid, "text": text, "src": f"wikidata:{qid}", "n": len(entries),
                                "rare": pick_rare(entries), "easy": [e[0] for e in entries[:2]], "entries": entries})
                report.append(f"filled with {pid}")
                break
    # Boardread closes the round when present
    prompts.sort(key=lambda p: p["id"] == "boardread")
    return {"v": 1, "date": date.isoformat(), "no": (date - LAUNCH).days + 1,
            "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seconds": 25, "tiers": TIERS, "prompts": prompts,
            "credit": "Answer lists: Wikidata (CC0). Rarity: Wikipedia sitelink percentile per prompt."}, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--queue", default=str(HERE.parent.parent / "queue"))
    ap.add_argument("--out", default=str(HERE / "assets/data/today.json"))
    a = ap.parse_args()
    data, report = build(dt.date.fromisoformat(a.date), Path(a.queue))
    if len(data["prompts"]) < 7:
        print("\n".join(report), file=sys.stderr)
        sys.exit(f"only {len(data['prompts'])} prompts built, need 7")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print("\n".join(report))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB), puzzle No. {data['no']}")


if __name__ == "__main__":
    main()
