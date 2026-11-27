"""Repair live articles against the rules of the 2026-11-27 site audit. Social posts are never sent again: only the
site's copy of an article changes, or the article leaves the site (status "held", with the reason and the status it
had, so it can be restored).

usage: python3 scripts/repair_reports.py [--dry] [--local-login] [--digest PATH ...]
--local-login: run the model call on this machine's own sign-in (it needs the full environment; CI uses the token)

1. A report that is empty, one sentence, or opens leaning on a missing sentence, or an empty dek: the copy is written
   again from today's feeds (the lead newsroom and the others that carried it) with the same model call and checks
   as the desk. The posted headline stays. When the sources still hold too little, the article is held.
2. An article centred on deaths or violence (desk.SKIP on headline or dek): held.
3. --digest: a digest the current ranker wrote on the same day's feeds. Articles queued under the ranker before
   2026-11-27T01:25Z get the score the current one gives their story at the time they were queued (the old one
   counted feeds, not newsrooms, and chained unrelated pieces: Denny's plaque scored 13.3, 7.8 under the current
   ranker). The old score stays in score_before.
"""
import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aidaily import copy, desk, feeds, rank  # noqa: E402
from aidaily.__main__ import DEFAULT_SOURCES, load_sources  # noqa: E402

RANKER_CHANGED = "2026-11-27T01:25:00+00:00"


def live():
    return [(p, path) for p, path in desk.posts()
            if p.get("status") in ("published", "web") and p.get("kind") != "story"]


def broken(p):
    why = copy.thin({"dek": p.get("dek", ""), "linkedin_post": p.get("body", "")})
    body = (p.get("body") or "").strip()
    if not why and body and copy.LEANS.search(copy.sentences(body)[0]):
        why = "report opens leaning on a sentence that is not there"
    return why


def hold(path, p, why, dry):
    print(f"  HOLD {p['id']}: {why}")
    if not dry:
        desk._save(path, dict(p, status="held", held=[why], held_from=p["status"]))


def stories_now():
    sources = load_sources(DEFAULT_SOURCES)
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(feeds.fetch, sources.values()))
    items = [i for got, _ in results for i in got]
    # no age cut: an article from yesterday is matched to whatever the feeds still carry of it
    return rank.rank(items, sources, max_age_h=24 * 7)


def rewrite(todo, dry):
    """todo: [(post, path, why)]. Writes dek and report again where the feeds still carry the story."""
    found = stories_now()
    by_link = {u: s for s in found for u in s.get("links") or [s["url"]]}
    batch = []
    for p, path, why in todo:
        s = next((by_link[u] for u in (p.get("links") or []) + (p.get("source_urls") or []) + (p.get("urls") or [])
                  if u in by_link), None)
        if s is None:
            hold(path, p, f"{why}; the feeds no longer carry the story", dry)
        else:
            batch.append((p, path, why, dict(s)))
    for i in range(0, len(batch), 8):
        chunk = batch[i:i + 8]
        stories = [s for *_, s in chunk]
        try:
            rows = copy.ask_claude(copy.request(stories))
        except Exception as e:  # one failed call holds nothing: those posts are left as they are and reported
            print(f"  copy call failed ({e}); {len(chunk)} left unchanged")
            continue
        copy.apply(stories, rows)
        for p, path, why, s in chunk:
            head_ = p["headlines"][0]
            if s.get("copy_status") != "ok":
                hold(path, p, f"{why}; copy did not pass its checks", dry)
                continue
            # the posted headline stays: the report is checked against it, not against the one the model wrote now
            dek = s["dek"] if s.get("dek") and not copy.repeats(s["dek"], head_) else ""
            post = copy.drop_repeats(copy.drop_restated_lead(s["linkedin_post"], head_), [dek] if dek else [], head_)
            if not dek:
                first = copy.sentences(copy.body_of(post))[:1]
                if first and len(first[0]) <= 160 and not copy.LEANS.search(first[0]):
                    dek = first[0]
                    post = copy.drop_repeats(post, [dek], head_)
            new = {"dek": dek, "linkedin_post": post}
            if copy.thin(new):
                hold(path, p, f"{why}; rewritten, still {copy.thin(new)}", dry)
                continue
            body = desk.body(new)
            m = desk.SKIP.search(f"{head_} {dek}")
            if m:
                hold(path, p, f"{why}; the rewrite is centred on deaths or violence ({m.group(0)!r})", dry)
                continue
            print(f"  REWRITE {p['id']}: {head_}\n    dek: {dek}\n    report: {body}")
            if not dry:
                desk._save(path, dict(p, dek=dek, body=body, rewritten={"at": desk.now().isoformat(), "why": why,
                                                                        "dek": p.get("dek", ""), "body": p.get("body", "")}))


def rescore(digests, dry):
    scored = {}
    for d in digests:
        g = json.loads(Path(d).read_text())
        stories = g.get("stories", [])
        when = g.get("generated") or max((s["published"] for s in stories if s.get("published")), default=None)
        for s in stories:
            for u in s.get("links") or [s["url"]]:
                scored.setdefault(u, (s, when))
    for p, path in live():
        if p["created"] >= RANKER_CHANGED or p.get("score_before") is not None:
            continue
        hit = next((scored[u] for u in p.get("links") or p.get("urls") or [] if u in scored), None)
        if not hit:
            continue
        s, when = hit

        def recency(at):
            age = (datetime.fromisoformat(at) - datetime.fromisoformat(s["published"])).total_seconds() / 3600
            return 3.0 * math.exp(-max(age, 0) / 18)
        new = round(s["score"] - recency(when) + recency(p["created"]), 3)
        print(f"  SCORE {p['id']}: {p.get('score')} -> {new}  {p['headlines'][0][:60]}")
        if not dry:
            desk._save(path, dict(p, score=new, score_before=p.get("score")))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dry", action="store_true")
    a.add_argument("--digest", nargs="*", default=[])
    a.add_argument("--local-login", action="store_true")
    args = a.parse_args()
    if args.local_login:
        copy.cli_env = lambda environ=None: dict(os.environ)
    todo = []
    for p, path in live():
        text = " ".join([p["headlines"][0], p.get("dek", "")])
        m = desk.SKIP.search(text)
        if m:
            hold(path, p, f"centred on deaths or violence ({m.group(0)!r})", args.dry)
            continue
        why = broken(p)
        if why:
            todo.append((p, path, why))
    print(f"{len(todo)} articles to write again")
    if todo:
        rewrite(todo, args.dry)
    if args.digest:
        rescore(args.digest, args.dry)


if __name__ == "__main__":
    main()
