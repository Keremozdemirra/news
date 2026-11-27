#!/usr/bin/env python3
"""Build the daily Topfloor puzzle: assets/data/today.json.

Seven prompts per UTC day, deterministic from the date:
  six from the committed answer lists (assets/data/lists/, built by build_lists.py) + one "company in today's
  Boardread", which is the only part that asks Wikidata at build time.
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

EXTRAS = json.loads((HERE / "extras.json").read_text())
from names import variants, spaced, core, norm, LEGAL, STOP, GENERIC, FUZZ_MIN
from build_lists import POOL

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


def load_list(pid):
    f = HERE / "assets" / "data" / "lists" / f"{pid}.json"
    return json.loads(f.read_text()) if f.exists() else None


def pack(rows, extra=None):
    """The Boardread prompt, in the same shape as a list: most familiar first, one key owns one entry."""
    order = sorted(rows, key=lambda r: (-r["sl"], -r["st"], r["label"]))
    n, seen, entries = len(order), {}, []
    for i, r in enumerate(order):
        tier = sum(i / n >= c for c in TIER_CUTS)
        names = [r["label"], *r["aliases"]]
        ks = [k for nm in names for k in variants(nm) if k not in seen]
        ks = list(dict.fromkeys(ks))
        if not ks:
            continue
        for k in ks:
            seen[k] = len(entries)
        cores = list(dict.fromkeys(c for nm in names for sp in spaced(nm) if (c := core(sp, "boardread"))))
        entries.append([r["label"], r["sl"], tier, ks, cores, (extra or {}).get(r["id"], "")])
    for e in entries:
        e[4] = [c for c in e[4] if c not in seen]
    return entries


def pick_rare(entries, seed="", k=2):
    # The example shown to the player comes from the highest tier on the list. Everything in that tier is
    # equally obscure, so the day picks among the entries that read as a name (no initials, no catalogue rows).
    top = max(e[2] for e in entries)
    pool = [e for e in entries if e[2] == top]
    plain = [e for e in pool if re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}", e[0]) and 5 <= len(e[0]) <= 24] or pool
    plain = sorted(plain, key=lambda e: (-e[1], e[0]))
    best = [e for e in plain if e[1] == plain[0][1]]
    random.Random(int(hashlib.sha256(f"rare|{seed}".encode()).hexdigest(), 16)).shuffle(best)
    return [e[0] for e in best[:k]]


def pick_easy(entries, pid, k=2):
    hide = set(EXTRAS.get(pid, {}).get("noexample", []))
    return [e[0] for e in entries if e[0] not in hide][:k]


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
    def from_list(pid):
        d = load_list(pid)
        if not d or d["n"] < MIN_WIKI:
            report.append(f"dropped {pid}: no list or too thin")
            return None
        e = d["entries"]
        report.append(f"kept {pid}: {d['n']} answers")
        return {"id": pid, "text": d["text"], "src": d["src"], "n": d["n"], "rare": pick_rare(e, f"{date}|{pid}"), "easy": pick_easy(e, pid),
                "list": f"assets/data/lists/{pid}.json", "generic": GENERIC.get(pid, "").split()}
    for pid, text, qid in order:
        if len(prompts) == 6:
            break
        p = from_list(pid)
        if p:
            prompts.append(p)

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
                        "n": len(entries), "rare": pick_rare(entries, f"{date}|boardread"), "easy": [e[0] for e in entries[:2]],
                        "generic": [], "entries": entries})
        report.append(f"kept boardread: {len(entries)} companies (window {span} d)")
    else:
        report.append(f"dropped boardread: {len(rows)} companies")
        for pid, text, qid in [p for p in order if p[0] not in {x['id'] for x in prompts}]:
            p = from_list(pid)
            if p:
                prompts.append(p)
                report.append(f"filled with {pid}")
                break
    # Boardread closes the round when present
    prompts.sort(key=lambda p: p["id"] == "boardread")
    # the practice building draws from every list, today's or not
    have = {p["id"]: p for p in prompts}
    pool = [x for x in (have.get(pid) or from_list(pid) for pid, _, _ in POOL) if x]
    return {"v": 2, "date": date.isoformat(), "no": (date - LAUNCH).days + 1,
            "match": {"legal": LEGAL, "stop": sorted(STOP), "fuzz": FUZZ_MIN},
            "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seconds": 25, "tiers": TIERS, "prompts": prompts, "pool": pool,
            "credit": "Answer lists: Wikidata (CC0), the class, its subclasses and its industry, plus chains added by hand. Rarity: Wikipedia sitelink percentile per prompt."}, report


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
