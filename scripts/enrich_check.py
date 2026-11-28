"""One manual look at the SEC path: find today's stories that name a US-listed company and print what EDGAR gives.
Run by .github/workflows/enrich-check.yml with DESK_SEC_CONTACT set; the address is never printed."""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import enrich, feeds, rank  # noqa: E402
from aidaily.__main__ import DEFAULT_SOURCES, load_sources  # noqa: E402

src = load_sources(DEFAULT_SOURCES)
with ThreadPoolExecutor(max_workers=12) as ex:
    items = [i for got, _ in ex.map(feeds.fetch, src.values()) for i in got]
stories = rank.rank([i for i in items if src.get(i["source_id"], {}).get("category") != "sport"], src)
ctx = enrich.live_ctx()
print("contact configured:", bool(ctx.contact))
tickers = ctx.json(enrich.SEC_TICKERS, f"Boardread news desk {ctx.contact}")
hits = 0
for s in stories[:400]:
    reg = enrich.match_registrant(s, tickers)
    if not reg:
        continue
    kept = enrich.enrich_story(s, ctx)
    print(f"\n{s['title']}\n  registrant: {reg['title']} ({reg['ticker']}); facts kept {len(kept)}; dropped {s.get('enrich_dropped')}")
    for f in kept:
        print("  +", f["text"], f["url"])
    hits += 1
    if hits >= 4:
        break
print("\nnotes:", ctx.notes)
