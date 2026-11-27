"""The /play/ hub and the games under it.

Each game is a static folder in games/<slug>/ with its own index.html. Adding a finished game is one line in GAMES
below (set live=True once games/<slug>/ is on main); a line with live=False shows as "Coming soon" and copies nothing.
A game with a build_data.py gets its puzzle from that script at site build: it writes assets/data/today.json into the
built copy, and when it fails (no network, upstream down) the committed copy of the last puzzle is served instead.
The first puzzle published for a UTC day is kept by every later build of that day (same_day_same_puzzle).
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
    ("face-the-figure", "Face the Figure", "Real business figures on a balance. Is the sealed one higher or lower? Each answer carries into the next: a chain of ten.", True),
]
SKIP = shutil.ignore_patterns(".cache", "__pycache__", "*.py", "DESIGN.md", "lockup.html", "extras.json", ".DS_Store")


def live():
    return [g for g in GAMES if g[3] and (GAMES_DIR / g[0] / "index.html").exists()]


def same_day_same_puzzle(fresh, live, today):
    """True when the puzzle already on the site is today's and has the shape this build writes.

    The site is rebuilt many times a day and the queue grows between builds, so a fresh build would deal another word
    and another chain at noon than at nine. The first puzzle published for a UTC day stays for that day. A change of
    format (another version, another set of fields) is the one thing that replaces it."""
    return (isinstance(live, dict) and live.get("date") == today and fresh.get("date") == today
            and live.get("v") == fresh.get("v") and set(live) == set(fresh))


def published_today(slug, fresh_path):
    """The text of the puzzle the live site serves for this game, when it must be kept; None to publish the fresh one."""
    if os.environ.get("PLAY_REDEAL") in ("1", slug):          # a deliberate new deal, by hand
        return None
    try:
        import datetime as dt, json, urllib.request
        fresh = json.loads(Path(fresh_path).read_text())
        req = urllib.request.Request(f"{S.SITE}/play/{slug}/assets/data/today.json", headers={"User-Agent": "BoardreadSiteBuild/1", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=20) as f:
            text = f.read().decode("utf-8")
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        return text if same_day_same_puzzle(fresh, json.loads(text), today) else None
    except Exception as e:          # first day, site unreachable, not JSON: the fresh puzzle is the day's puzzle
        print(f"play: {slug} live puzzle not read ({type(e).__name__}), publishing the fresh one")
        return None


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
                kept = published_today(slug, tmp)
                if kept is not None:
                    tmp.write_text(kept)
                tmp.replace(dest / "assets" / "data" / "today.json")
            else:
                tmp.unlink(missing_ok=True)
                print(f"play: {slug} puzzle not refreshed, serving the committed one: {(r.stderr or r.stdout).strip()[-200:]}")
        done.append(slug)
    return done


def hub_body():
    """Three games, three worlds: each tile is the game's own key art (its logo in its scene), not a row of text."""
    rows = []
    for slug, title, blurb, is_live in GAMES:
        if is_live and (GAMES_DIR / slug / "index.html").exists():
            art = f'<img class="ga" src="{S.BASE}/play/{slug}/assets/share.jpg" alt="" width="1200" height="630" loading="lazy">' if (GAMES_DIR / slug / "assets" / "share.jpg").exists() else ""
            rows.append(f'<li><a class="game" href="{S.BASE}/play/{slug}/">{art}<span class="gt">{S.E(title)}</span>'
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
