"""The photo numbers of the live site (plan item 9): tier mix, scene share, repeats, licence and label gaps.

usage: python3 scripts/photo_metrics.py
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aidaily import desk, entities as E, site  # noqa: E402


def main():
    live = [p for p, _ in desk.posts() if p.get("status") in ("published", "web") and p.get("kind") != "story"]
    kinds = collections.Counter(p.get("photo_kind") or "unknown" for p in live)
    files = collections.Counter(p.get("photo_file") for p in live if p.get("photo_file"))
    repeats = {f: n for f, n in files.items() if n > 1}
    bad_licence = [p["id"] for p in live if re.search(r"BY-SA|OGL|\bNC\b|\bND\b", p.get("credit", ""))]
    mismatch = [p["id"] for p in live if p.get("credit_file") and p["credit_file"] != p.get("photo_file")]
    unlabelled = [p["id"] for p in live if p.get("credit") and not site.credit_line(p).startswith("Archive photo")]
    retired = [p["id"] for p in live if p.get("photo_file") in E.never_use()]
    print(f"live posts: {len(live)}")
    print("tier mix: " + ", ".join(f"{k} {n} ({100 * n // len(live)}%)" for k, n in kinds.most_common()))
    print(f"files on more than one post: {len(repeats)} " + "; ".join(f"{f[:40]} x{n}" for f, n in sorted(repeats.items(), key=lambda x: -x[1])[:8]))
    print(f"licence not CC0/PD/CC BY: {bad_licence}")
    print(f"credit of another file: {mismatch}")
    print(f"no archive label: {unlabelled}")
    print(f"retired file still live: {retired}")


if __name__ == "__main__":
    main()
