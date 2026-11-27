#!/usr/bin/env python3
"""Build the daily Tickerflip puzzle: assets/data/today.json.

The answer is one word taken from Boardread's own articles for the UTC day:
  - the featured company's name (one word, or one word of a longer name),
  - the verified ticker (post["ticker"], when the desk has set one), or
  - a key headline word.
All are 5-6 letters, letters only, and no stopwords. The pick is deterministic: candidates are
sorted alphabetically and indexed by a SHA-256 of the date, so the same queue gives the same word.

Valid guesses = the bundled English list (assets/data/words.txt, SCOWL, see words-NOTICE.txt)
plus every 5-6 letter word, company name and ticker in any published or web article.
Only the extras go into today.json; the browser loads words.txt itself.

Usage: python3 build_data.py [--date YYYY-MM-DD] [--queue ../../queue] [--out assets/data/today.json]
Standard library only. The answer is stored base64-reversed so it is not readable at a glance;
this is a prototype and the file is public, so it is not secrecy.
"""
import argparse, base64, datetime as dt, hashlib, json, re, sys, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH = dt.date(2026, 11, 27)  # puzzle No. 1
MIN_LEN, MAX_LEN = 5, 6   # five or six cells: the size a phone can show big
MIN_CANDIDATES = 8    # widen the window one day at a time until there are this many
MAX_WINDOW = 4        # days, today included
MORE_BOARDS = 5       # extra boards a player can open after the day's word
SITE = "https://boardread.news/s/{}/"
LIVE = {"published", "web"}

STOP = set("""
about above after again against also among because been before being below between both bring came come could
does doing done down during each either else ever every from gets give given goes going gone have having here
hers into itself just keep kept knew know less like made make many more most much must near need never next none
only onto other others otherwise ours over same says said seem seen shall should since some soon still such take
taken tell than that thats their theirs them then there these they thing think this those though three through
thus told took toward under until upon used uses very want wants well went were what when where whether which
while whom whose will with within without would your yours amid says plans says amid
""".split())

WORD = re.compile(r"[A-Za-z]+")


def possessive(t: str) -> str:
    """Possessives dropped and accents folded, so Hernández is one word and not Hern + ndez."""
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[’']s\b", "", t)


def tokens(text: str):
    """(word, was_capitalised_mid_sentence) pairs, possessives dropped, hyphen and digit splits kept apart."""
    out = []
    for i, m in enumerate(WORD.finditer(possessive(text))):
        w = m.group(0)
        out.append((w, w[0].isupper() and i > 0))
    return out


def ok_len(w: str) -> bool:
    return MIN_LEN <= len(w) <= MAX_LEN and w.isalpha() and w.isascii()


def load_words(path: Path) -> set:
    return {w.strip().lower() for w in path.read_text().split() if w.strip()}


def ticker_of(t) -> str:
    """The desk writes a ticker as "TGT" or as {"exchange": "NYSE", "symbol": "TGT"}; anything else is no ticker."""
    if isinstance(t, dict):
        t = t.get("symbol")
    return t.strip() if isinstance(t, str) else ""


def load_posts(queue: Path):
    posts = []
    for f in sorted(queue.glob("*/post.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if d.get("status") not in LIVE or d.get("kind") == "story":
            continue
        heads = d.get("headlines") or []
        if isinstance(heads, str):
            heads = [heads]
        if not heads or not d.get("id"):
            continue
        srcs = d.get("sources") or []
        posts.append({
            "id": d["id"], "day": str(d.get("created", ""))[:10], "head": heads[0],
            "src": srcs[0] if srcs else "", "company": (d.get("company") or "").strip(),
            "ticker": ticker_of(d.get("ticker")), "logos": d.get("logo_names") or [],
            "text": " ".join([*heads, d.get("dek") or "", d.get("body") or ""]),
        })
    return posts


def candidates(posts, dic: set):
    """word -> {kind, ids}. Kind priority: ticker, company, headline."""
    c = {}

    def add(word, kind, post):
        w = word.lower()
        if not ok_len(word) or w in STOP:
            return
        e = c.setdefault(w, {"kind": kind, "ids": []})
        rank = {"ticker": 0, "company": 1, "headline": 2}
        if rank[kind] < rank[e["kind"]]:
            e["kind"] = kind
        if post["id"] not in e["ids"]:
            e["ids"].append(post["id"])

    for p in posts:
        t = p["ticker"]
        if t and ok_len(t) and t.isalpha():
            add(t, "ticker", p)
        name = p["company"]
        if name:
            joined = re.sub(r"[^A-Za-z]", "", name)
            if ok_len(joined):
                add(joined, "company", p)
            for w in re.findall(r"[A-Za-z]+", possessive(name)):
                add(w, "company", p)
        for w, cap in tokens(p["head"]):
            # key words only: dictionary words, or capitalised names that are not the sentence opener
            if w.lower() in dic or cap:
                add(w, "headline", p)
    return c


def build(date: dt.date, queue: Path, words: Path):
    dic = load_words(words)
    posts = load_posts(queue)
    pool, span = {}, 0
    while span < MAX_WINDOW:
        days = {(date - dt.timedelta(days=i)).isoformat() for i in range(span + 1)}
        win = [p for p in posts if p["day"] in days]
        pool = candidates(win, dic)
        span += 1
        if len(pool) >= MIN_CANDIDATES:
            break
    if not pool:
        sys.exit(f"no candidates for {date}: no published or web articles in the window")
    names = sorted(pool)
    i = int(hashlib.sha256(f"tickerflip|{date.isoformat()}".encode()).hexdigest(), 16) % len(names)
    answer = names[i]
    by_id = {p["id"]: p for p in posts}
    arts = [{"id": k, "h": by_id[k]["head"], "src": by_id[k]["src"], "url": SITE.format(k)} for k in pool[answer]["ids"][:3]]

    # extra boards for the same day: the next words round the list, a different length or story where there is one
    stop_hint = {"company": "a company in the news", "ticker": "a stock ticker", "headline": "a word from a headline"}
    more, used_ids = [], set(pool[answer]["ids"])
    for k in range(1, len(names)):
        w = names[(i + k * 7) % len(names)]
        if w == answer or any(m["w"] == w for m in more) or (set(pool[w]["ids"]) <= used_ids and len(names) > 12):
            continue
        used_ids |= set(pool[w]["ids"])
        more.append({"w": w, "a": base64.b64encode(w[::-1].encode()).decode(), "len": len(w), "kind": pool[w]["kind"], "clue": stop_hint[pool[w]["kind"]],
                     "articles": [{"id": x, "h": by_id[x]["head"], "src": by_id[x]["src"], "url": SITE.format(x)} for x in pool[w]["ids"][:3]]})
        if len(more) == MORE_BOARDS:
            break

    extra = set()
    for p in posts:
        for w, _ in tokens(p["text"]):
            if ok_len(w):
                extra.add(w.lower())
        for n in [p["company"], p["ticker"], *p["logos"]]:
            j = re.sub(r"[^A-Za-z]", "", n or "")
            if ok_len(j):
                extra.add(j.lower())
            for w in re.findall(r"[A-Za-z]+", possessive(n or "")):
                if ok_len(w):
                    extra.add(w.lower())
    extra.add(answer)
    extra |= {m.pop("w") for m in more}
    extra -= dic  # the browser already has the dictionary
    data = {
        "v": 1, "date": date.isoformat(), "no": (date - LAUNCH).days + 1,
        "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "len": len(answer), "tries": 6,
        "a": base64.b64encode(answer[::-1].encode()).decode(),
        "kind": pool[answer]["kind"], "clue": stop_hint[pool[answer]["kind"]],
        "articles": arts, "extra": sorted(extra), "more": more,
        "credit": "Word list: SCOWL via Hunspell en_US (see words-NOTICE.txt), plus every word in Boardread's articles.",
    }
    report = [f"window {span} d, {len(pool)} candidates from {sum(1 for p in posts if p['day'] in days)} articles",
              f"answer index {i} of {len(names)}", f"kind {data['kind']}, {len(arts)} article(s)",
              f"extras {len(extra)} words beyond the bundled list"]
    return data, answer, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--queue", default=str(HERE.parent.parent / "queue"))
    ap.add_argument("--words", default=str(HERE / "assets/data/words.txt"))
    ap.add_argument("--out", default=str(HERE / "assets/data/today.json"))
    ap.add_argument("--show-answer", action="store_true", help="print the answer (for testing only)")
    a = ap.parse_args()
    data, answer, report = build(dt.date.fromisoformat(a.date), Path(a.queue), Path(a.words))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print("\n".join(report))
    if a.show_answer:
        print("answer:", answer)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB), puzzle No. {data['no']}")


if __name__ == "__main__":
    main()
