"""The /play/ hub and the games under it.

Each game is a static folder in games/<slug>/ with its own index.html. Adding a finished game is one line in GAMES
below (set live=True once games/<slug>/ is on main); a line with live=False shows as "Coming soon" and copies nothing.
A game with a build_data.py gets a fresh puzzle at every site build: the script writes assets/data/today.json into the
built copy, and when it fails (no network, upstream down) the committed copy of the last puzzle is served instead.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import site as S

GAMES_DIR = Path(__file__).resolve().parent.parent / "games"
# slug, title, one line, live
GAMES = [
    ("topfloor", "Topfloor", "Seven business prompts, 25 seconds each. The rarer your answer, the higher the lift climbs.", True),
    ("tickerflip", "Tickerflip", "One word from today's stories on a split-flap departure board. Six guesses.", True),
    ("face-the-figure", "Face the Figure", "Two real business figures on a balance. Is the sealed one higher or lower? Ten rounds.", True),
]
SKIP = shutil.ignore_patterns(".cache", "__pycache__", "*.py", "DESIGN.md", ".DS_Store")


def live():
    return [g for g in GAMES if g[3] and (GAMES_DIR / g[0] / "index.html").exists()]


def copy_games(out):
    """Copy every live game to /play/<slug>/ and refresh its daily puzzle; returns the slugs copied."""
    done = []
    for slug, _, _, _ in live():
        dest = out / "play" / slug
        shutil.copytree(GAMES_DIR / slug, dest, ignore=SKIP)
        script = GAMES_DIR / slug / "build_data.py"
        if script.exists() and os.environ.get("DESK_SITE_OFFLINE") != "1":
            tmp = dest / "assets" / "data" / "today.new.json"
            r = subprocess.run([sys.executable, str(script), "--out", str(tmp)], capture_output=True, text=True, timeout=240)
            if r.returncode == 0 and tmp.exists():
                tmp.replace(dest / "assets" / "data" / "today.json")
            else:
                tmp.unlink(missing_ok=True)
                print(f"play: {slug} puzzle not refreshed, serving the committed one: {(r.stderr or r.stdout).strip()[-200:]}")
        done.append(slug)
    return done


def hub_body():
    rows = []
    for slug, title, blurb, is_live in GAMES:
        if is_live and (GAMES_DIR / slug / "index.html").exists():
            rows.append(f'<li><a class="game" href="{S.BASE}/play/{slug}/"><span class="gt">{S.E(title)}</span>'
                        f'<span class="gd">{S.E(blurb)}</span><span class="gm">Play today</span></a></li>')
        else:
            rows.append(f'<li><div class="game soon"><span class="gt">{S.E(title)}</span><span class="gm">Coming soon</span></div></li>')
    return (S.pagehead("Play", "A new puzzle every day at 00:00 UTC. Same puzzle for everyone, no account.")
            + f'<ul class="games">{"".join(rows)}</ul>')


def build(out, shown, sm):
    """Called by sitepages.build once 'play' is in SHIPPED."""
    latest = S.iso(shown[0]["published"]) if shown else None
    S.put(out, "/play/", S.page("Play · boardread.", hub_body(), "Daily games from Boardread: a new puzzle every day.", "/play/",
                                active="play", styles=("views", "play")))
    sm.append((S.SITE + "/play/", latest))
    for slug in copy_games(out):
        sm.append((f"{S.SITE}/play/{slug}/", latest))
