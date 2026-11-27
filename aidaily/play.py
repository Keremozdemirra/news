"""The /play/ hub and the games under it.

Each game is a static folder in games/<slug>/ with its own index.html. Adding a finished game is one line in GAMES
below (set live=True once games/<slug>/ is on main); a line with live=False shows as "Coming soon" and copies nothing.
A game with a build_data.py gets its puzzle from that script at site build: it writes assets/data/today.json into the
built copy, and when it fails (no network, upstream down) the committed copy of the last puzzle is served instead.
The first puzzle published for a UTC day is kept by every later build of that day (same_day_same_puzzle).
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import site as S

GAMES_DIR = Path(__file__).resolve().parent.parent / "games"
# slug, title, one line, live
GAMES = [
    ("topfloor", "Topfloor", "Seven questions. The rarer your answer, the higher the lift goes.", True),
    ("tickerflip", "Tickerflip", "One word from today's news. Six guesses.", True),
    ("face-the-figure", "Face the Figure", "Higher or lower? Each figure meets the next.", True),
]
# "frames" and "png" are the lossless renders and older frame sets under a game's art/: sources, never served
SKIP = shutil.ignore_patterns(".cache", "__pycache__", "*.py", "DESIGN.md", "lockup.html", "extras.json", ".DS_Store", "frames", "png")


def live():
    return [g for g in GAMES if g[3] and (GAMES_DIR / g[0] / "index.html").exists()]


def same_day_same_puzzle(fresh, live, today):
    """True when the puzzle already on the site is today's and has the shape this code writes (fresh: any puzzle
    in the current format, the committed one will do).

    The site is rebuilt many times a day and the queue grows between builds, so a fresh build would deal another word
    and another chain at noon than at nine. The first puzzle published for a UTC day stays for that day. A change of
    format (another version, another set of fields) is the one thing that replaces it."""
    return (isinstance(live, dict) and isinstance(fresh, dict) and live.get("date") == today
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
            today_json = dest / "assets" / "data" / "today.json"
            kept = published_today(slug, today_json)       # the committed copy shows the format this code writes
            if kept is not None:
                today_json.write_text(kept)                 # today's puzzle is already out: no new deal, no upstream calls
            else:
                tmp = dest / "assets" / "data" / "today.new.json"
                try:
                    r = subprocess.run([sys.executable, str(script), "--out", str(tmp)], capture_output=True, text=True, timeout=240)
                    ok, why = r.returncode == 0 and tmp.exists(), (r.stderr or r.stdout).strip()[-200:]
                except subprocess.TimeoutExpired:           # a slow upstream must not take the whole site build down
                    ok, why = False, "the puzzle script ran over 240 s"
                if ok:
                    tmp.replace(today_json)
                else:
                    tmp.unlink(missing_ok=True)
                    print(f"play: {slug} puzzle not refreshed, serving the committed one: {why}")
        dated_share(slug, dest)
        done.append(slug)
    return done


SHARE_FONT = GAMES_DIR / "_fonts" / "LibreFranklin-600.ttf"


def dated_share(slug, dest):
    """Draw the puzzle's number and date on the game's share image, and point the page's preview tags at a URL that
    changes with the day, so X, WhatsApp and Telegram fetch the new picture. Build-time only: Pillow is imported here
    and nowhere else; without it the committed, undated card is served as it is. Returns True when the date was drawn."""
    card, page = dest / "assets" / "share.jpg", dest / "index.html"
    try:
        puzzle = json.loads((dest / "assets" / "data" / "today.json").read_text())
        when = dt.date.fromisoformat(puzzle["date"])
        from PIL import Image, ImageDraw, ImageFont
        im = Image.open(card).convert("RGB")
        if im.size != (1200, 630):
            return False
        font, draw, x = ImageFont.truetype(str(SHARE_FONT), 20), ImageDraw.Draw(im), 72.0
        for ch in f"No. {puzzle['no']} · {when:%a} {when.day} {when:%b %Y}".upper():      # set letter by letter: tracked caps, as on the card
            draw.text((x, 504), ch, font=font, fill=(90, 90, 90))
            x += font.getlength(ch) + 2.4
        im.save(card, "JPEG", quality=90, optimize=True)
    except Exception as e:  # noqa: BLE001  a share image without a date is still a share image
        print(f"play: {slug} share image left undated ({type(e).__name__})")
        return False
    html = page.read_text()
    page.write_text(html.replace("/assets/share.jpg\"", f"/assets/share.jpg?d={puzzle['date']}\""))
    return True


def hub_body():
    """The games as three entries in the site's own type: a rule, the name, one line, and where to go."""
    rows = []
    for slug, title, blurb, is_live in GAMES:
        if is_live and (GAMES_DIR / slug / "index.html").exists():
            rows.append(f'<li><a class="game" href="{S.BASE}/play/{slug}/"><span class="gt">{S.E(title)}</span>'
                        f'<span class="gd">{S.E(blurb)}</span><span class="gm">Play today</span></a></li>')
        else:
            rows.append(f'<li><div class="game soon"><span class="gt">{S.E(title)}</span><span class="gm">Coming soon</span></div></li>')
    return (S.pagehead("Play", "Three games. New every day.")
            + f'<ul class="games">{"".join(rows)}</ul>')


def build(out, shown, sm):
    """Called by sitepages.build once 'play' is in SHIPPED."""
    latest = S.iso(shown[0]["published"]) if shown else None
    S.put(out, "/play/", S.page("Play · boardread.", hub_body(), "Daily games from Boardread: a new puzzle every day.", "/play/",
                                active="play", styles=("views", "play")))
    sm.append((S.SITE + "/play/", latest))
    for slug in copy_games(out):
        sm.append((f"{S.SITE}/play/{slug}/", latest))
    # the end screens link to the article that leads the day: one small file, rewritten with every build
    top = (S.by_score(S.window(shown)) or shown)[:1]
    if top:
        (out / "play" / "top.json").write_text(json.dumps({"h": top[0]["headlines"][0], "url": S.href(top[0])}, ensure_ascii=False))
