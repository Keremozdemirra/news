#!/usr/bin/env python3
"""Build the full answer list of every Topfloor prompt: assets/data/lists/<id>.json.

Run by hand when the lists should be refreshed (it asks Wikidata a few hundred questions and takes minutes):
    python3 build_lists.py [id ...]
The daily build (build_data.py) only reads these files, so a site build never waits on Wikidata for them.

An answer is every Wikidata item that is an instance of the prompt's class or of any subclass of it and has at
least one Wikipedia article in any language. A Landesbank is a bank; a dissolved bank is still a bank. Its names
are its label, aliases, short name (P1813), official name (P1448) and native label (P1705) in the languages
below, as long as a Latin keyboard can type them. names.py turns the names into the keys a guess is matched on.
"""
import json, ssl, sys, time, urllib.parse, urllib.request
from pathlib import Path
from names import variants, spaced, core, latin, norm

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "data" / "lists"
UA = {"User-Agent": "BoardreadGames/0.2 (https://boardread.news)", "Accept": "application/sparql-results+json"}
try:
    CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
except Exception:
    CTX = ssl.create_default_context()
LANGS = "en de fr es it pt nl tr sv da nb fi pl cs hu ro id ms mul".split()
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
# Wikidata files many companies under "business" and says what they are with industry (P452) or product (P1056)
# instead: Tesla is no "automobile manufacturer" there, Kaufland no "supermarket chain". These routes fetch them.
ROUTES = {
    "bank": {"P31": ["Q141145821"], "P452": ["Q806718", "Q3435731", "Q112165989", "Q22687"], "P1056": ["Q1548025"]},
    "brewery": {"P452": ["Q11644505", "Q869095", "Q131734"], "P1056": ["Q44"]},
    "supermarket": {"P31": ["Q105615608", "Q750656", "Q261428", "Q142177163"], "P452": ["Q15825471", "Q180846", "Q1295201"], "P1056": ["Q180846", "Q750656", "Q261428", "Q1295201"]},
    "carmaker": {"P31": ["Q10429667"], "P452": ["Q190117", "Q786820", "Q29584629"], "P1056": ["Q1420", "Q1144312", "Q193692", "Q274586"]},
    "publisher": {"P31": ["Q210167"], "P452": ["Q941594", "Q112165928"]},
    "fast-food": {"P452": ["Q81799", "Q57497035", "Q1442415"]},
    "airline": {"P452": ["Q2055808", "Q46970"]},
}
EXTRAS = json.loads((HERE / "extras.json").read_text())
TIER_CUTS = [0.10, 0.30, 0.60, 0.85]   # share of the well-known entries more familiar than this one, per tier edge
KNOWN = 3                              # sitelinks from which an entry is ranked; below it, it is simply rare


def sparql(q, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.Request("https://query.wikidata.org/sparql", data=urllib.parse.urlencode({"query": q}).encode(), headers=UA)
            with urllib.request.urlopen(r, timeout=120, context=CTX) as f:
                return json.load(f)["results"]["bindings"]
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def members(pid, qid):
    """id -> (sitelinks, statements) over the class, its subclasses, the industry and product routes and extras.json."""
    r = ROUTES.get(pid, {})
    parts = [f"{{ ?x wdt:P31/wdt:P279* wd:{c}. }}" for c in [qid, *r.get("P31", [])]]
    parts += [f"{{ ?x wdt:{p} wd:{v}. }}" for p in ("P452", "P1056") for v in r.get(p, [])]
    add = EXTRAS.get(pid, {}).get("add", [])
    if add:
        parts.append("{ VALUES ?x { " + " ".join("wd:" + a for a in add) + " } }")
    out = {}
    for part in parts:                                  # one question per route: a union of them times out
        rows = sparql(f"""SELECT ?x (MAX(?s) AS ?sl) (MAX(?st) AS ?stn) WHERE {{ {part}
          ?x wikibase:sitelinks ?s. ?x wikibase:statements ?st. FILTER(?s >= 1)
          FILTER NOT EXISTS {{ ?x wdt:P31 wd:Q5 }} }} GROUP BY ?x""")
        for b in rows:
            out[b["x"]["value"].rsplit("/", 1)[1]] = (int(b["sl"]["value"]), int(b["stn"]["value"]))
        print(f"  route {part[:44]} ... {len(rows)}", flush=True)
        time.sleep(0.5)
    return out


def names_of(ids):
    """id -> (english label or None, [every usable name])"""
    langs = ", ".join(f'"{l}"' for l in LANGS)
    out = {}
    for i in range(0, len(ids), 250):
        vals = " ".join("wd:" + q for q in ids[i:i + 250])
        rows = sparql(f"""SELECT ?x ?l ?k WHERE {{ VALUES ?x {{ {vals} }}
          {{ ?x rdfs:label ?l. BIND("l" AS ?k) FILTER(lang(?l) IN ({langs})) }} UNION {{ ?x skos:altLabel ?l. BIND("a" AS ?k) FILTER(lang(?l) IN ({langs})) }}
          UNION {{ ?x wdt:P1813 ?l. BIND("s" AS ?k) }} UNION {{ ?x wdt:P1448 ?l. BIND("s" AS ?k) }} UNION {{ ?x wdt:P1705 ?l. BIND("s" AS ?k) }}
          UNION {{ ?x wdt:P498 ?l. BIND("s" AS ?k) }} UNION {{ ?x wdt:P249 ?l. BIND("s" AS ?k) }} UNION {{ ?x wdt:P229 ?l. BIND("s" AS ?k) }} UNION {{ ?x wdt:P230 ?l. BIND("s" AS ?k) }} }}""")   # ISO 4217, ticker, IATA, ICAO
        for b in rows:
            q = b["x"]["value"].rsplit("/", 1)[1]; text = b["l"]["value"].strip(); lang = b["l"].get("xml:lang", "")
            if not text or not latin(text) or len(text) > 80:
                continue
            en, names = out.setdefault(q, [None, []])
            if b["k"]["value"] == "l" and (lang == "en" or (lang == "mul" and not en)):
                out[q][0] = text
            if text not in names:
                (names.insert(0, text) if b["k"]["value"] == "l" else names.append(text))
        print(f"  names {min(i + 250, len(ids))}/{len(ids)}", flush=True)
        time.sleep(0.4)
    return out


def build(pid, text, qid):
    mem = members(pid, qid)
    nm = names_of(sorted(mem))
    for q, al in EXTRAS.get(pid, {}).get("alias", {}).items():
        if q in nm:
            nm[q][1].extend(a for a in al if a not in nm[q][1])
    rows = []
    for q, (sl, st) in mem.items():
        en, names = nm.get(q, (None, []))
        label = en or (names[0] if names else None)
        if not label or label.lower().startswith(("list of", "lists of", "category:", "template:")) or norm(label) == q.lower():
            continue
        rows.append({"id": q, "label": label, "sl": sl, "st": st, "names": names})
    rows.sort(key=lambda r: (-r["sl"], -r["st"], r["label"]))
    known = sum(r["sl"] >= KNOWN for r in rows) or 1
    seen, seen_core, entries = {}, {}, []
    for i, r in enumerate(rows):
        tier = sum(i / known >= c for c in TIER_CUTS) if r["sl"] >= KNOWN else 4
        keys, cores = [], []
        for n in r["names"]:
            for k in variants(n):
                if k not in seen:
                    seen[k] = len(entries); keys.append(k)
            for sp in spaced(n):
                c = core(sp, pid)
                if c and c not in seen and c not in seen_core:
                    seen_core[c] = len(entries); cores.append(c)
        if not keys:
            continue            # every spelling of it already belongs to a better known entry
        entries.append([r["label"], r["sl"], tier, keys, cores])
    for e in entries:           # a core that is also somebody's full key never steals it
        e[4] = [c for c in e[4] if c not in seen]
    return {"v": 2, "id": pid, "text": text, "src": f"wikidata:{qid}", "built": time.strftime("%Y-%m-%d"), "n": len(entries), "entries": entries}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(sys.argv[1:])
    for pid, text, qid in POOL:
        if want and pid not in want:
            continue
        print(pid, flush=True)
        d = build(pid, text, qid)
        (OUT / f"{pid}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
        print(f"  {d['n']} answers, {sum(len(e[3]) for e in d['entries'])} keys, {(OUT / (pid + '.json')).stat().st_size // 1024} KB", flush=True)
