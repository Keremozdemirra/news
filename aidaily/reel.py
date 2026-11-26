"""The daily recap Reel: the day's top feed posts as one short vertical video, switched by growth.daily_reel.

Why a Reel: a carousel reaches followers, a Reel is the format Instagram shows to non-followers
(brand/GROWTH-RESEARCH.md). The video is built from posts that are already published and checked, so it adds
no new claim: each card is shown as it went out, the caption is the headlines already published.

Three stages, so the workflow can push the video to the media branch between build and send:
  due()    the switch is on, it is past reel_hour UTC, today has no reel yet, enough posts exist
  build()  frames with headless Chrome, assembled with ffmpeg into media/<id>/reel.mp4
  send()   upload from the media branch's public URL and publish as REELS

State lives in state/reel.json, not in queue/: a reel is not a feed post, so the feed counters, the site, the
evening digest and the cross-posters never see it. The day is marked before the send, like every send here:
a run killed mid-upload can never produce a second reel.
"""
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from . import desk
from . import render as R
from . import templates as T

MAX_BUILD_FAILURES = 3  # a broken renderer must not retry every five minutes all evening


def _state():
    return desk._load(desk.STATE / "reel.json", {})


def _save(state):
    desk._save(desk.STATE / "reel.json", state)


def today():
    return f"{desk.now():%Y-%m-%d}"


def date_label(now=None):
    return f"{(now or desk.now()):%-d %b}"


def cfg(name, default):
    return desk.CONFIG.get("growth", {}).get(name, default)


def top_posts():
    """Today's published feed posts (UTC date), highest score first. Stories and earlier reels never count."""
    day = today()
    rows = [p for p, _ in desk.posts()
            if p.get("status") == "published" and p.get("kind") not in desk.NO_CROSSPOST
            and (p.get("published") or "").startswith(day) and p.get("headlines")]
    rows.sort(key=lambda p: (p.get("score") or 0, p.get("published", "")), reverse=True)
    return rows[:cfg("reel_size", 5)]


def due():
    """(True, "") when a reel should be built now, else (False, why)."""
    if not desk.growth("daily_reel"):
        return False, "switch off"
    if desk.paused():
        return False, "paused"
    if desk.now().hour < cfg("reel_hour", 18):
        return False, "before reel_hour"
    st = _state()
    if st.get("date") == today():
        return False, "already handled today"
    if desk.cooldown_until():
        return False, "Instagram cooldown"
    if st.get("build_date") == today() and st.get("build_failures", 0) >= MAX_BUILD_FAILURES:
        return False, "build failed repeatedly today"
    if len(top_posts()) < cfg("reel_min", 3):
        return False, "too few posts today"
    return True, ""


def caption(posts):
    """The headlines as a numbered list, then where the sources are. The AI note stays, as on every post."""
    lines = [f"{i}. {p['headlines'][0]}" for i, p in enumerate(posts, 1)]
    return "\n".join(lines + ["", f"Sources for each story: {desk.brand_domain()}", "",
                              desk.CONFIG["ai_note"]])


def frames(posts, out_dir, now=None):
    """Cover, one frame per post, end frame, as 1080x1920 PNGs. Returns the paths in order."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages = [("00-cover", T.reel_cover(date_label(now)))]  # wordmark "boardread." above the date
    for i, p in enumerate(posts, 1):
        card = desk.MEDIA / p["id"] / "card.jpg"
        uri = card.resolve().as_uri() if card.exists() else ""
        pages.append((f"{i:02d}-card", T.reel_card(i, len(posts), p["headlines"][0], p.get("topic", ""), uri)))
    pages.append(("99-end", T.reel_end(desk.brand_domain())))
    paths = []
    for name, html in pages:
        png = out / f"{name}.png"
        R.shoot(html, png, 1080, 1920)
        paths.append(png)
    return paths


def assemble(pngs, out_mp4, seconds=3, cover_seconds=2, end_seconds=2, fade=0.3):
    """Frames joined by a short crossfade (ffmpeg xfade), 30 fps. Built to Instagram's Reels spec: MP4, H.264
    4:2:0 progressive with a closed GOP, AAC 48 kHz mono (a silent track: some clients refuse a Reel with no audio
    stream), 1080x1920, no edit lists (-use_editlist 0), moov atom first (+faststart). Each frame holds for its
    full time; the fade overlaps the start of the next one, so the total is the sum of the holds."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    holds = [cover_seconds] + [seconds] * (len(pngs) - 2) + [end_seconds]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for i, (png, d) in enumerate(zip(pngs, holds)):
        cmd += ["-framerate", "30", "-loop", "1", "-t", f"{d + (fade if i < len(pngs) - 1 else 0):.2f}", "-i", str(png)]
    chain, label, at = [], "[0:v]", 0.0
    for i in range(1, len(pngs)):
        at += holds[i - 1]
        out = f"[x{i}]"
        chain.append(f"{label}[{i}:v]xfade=transition=fade:duration={fade}:offset={at:.2f}{out}")
        label = out
    chain.append(f"{label}scale=1080:1920,fps=30,format=yuv420p[v]")
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-filter_complex", ";".join(chain), "-map", "[v]",
            "-map", f"{len(pngs)}:a", "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "20",
            "-maxrate", "8M", "-bufsize", "16M", "-g", "60", "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1", "-shortest",
            "-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    return out_mp4


def build(out_dir=None):
    """Render and assemble today's reel into media/<id>/reel.mp4 and record it in state. Returns the state, or
    None when it did not build (the reason is printed and counted)."""
    ok, why = due()
    if not ok:
        print(f"reel: not building ({why})")
        return None
    posts = top_posts()
    rid = f"{desk.now():%Y-%m-%d-%H%M}-reel"
    st = _state()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pngs = frames(posts, tmp)
            assemble(pngs, Path(out_dir) if out_dir else desk.MEDIA / rid / "reel.mp4", cfg("reel_seconds", 3))
    except Exception as e:  # noqa: BLE001  a failed render is counted, never fatal to the publish run
        failures = (st.get("build_failures", 0) if st.get("build_date") == today() else 0) + 1
        _save({**st, "build_date": today(), "build_failures": failures, "build_error": str(e)[-300:]})
        print(f"reel: build failed ({failures}): {str(e)[-200:]}")
        return None
    st = {"build_date": today(), "id": rid, "posts": [p["id"] for p in posts], "built": desk.now().isoformat(timespec="seconds")}
    _save(st)
    print(f"reel: built {rid} from {len(posts)} posts")
    return st


def send(client=None):
    """Upload the built reel and publish it. Returns the media id or None. Never retried: see the module note."""
    st = _state()
    if not desk.growth("daily_reel") or desk.paused():
        return None
    if st.get("date") == today() or not st.get("id") or st.get("build_date") != today() or st.get("attempted"):
        print("reel: nothing to send")
        return None
    if desk.cooldown_until():
        print("reel: Instagram cooldown, not sent")
        return None
    if client is None:
        from .instagram import Client
        client = Client()
    posts = {p["id"]: p for p, _ in desk.posts()}
    ordered = [posts[i] for i in st["posts"] if i in posts]
    st.update(date=today(), attempted=desk.now().isoformat(timespec="seconds"))
    _save(st)  # on disk before the call
    try:
        media, link = client.reel(desk.media_url(st["id"], "reel.mp4"), caption(ordered), share_to_feed=True,
                                  trial=cfg("reel_trial", ""))
    except Exception as e:  # noqa: BLE001
        desk.note_block(e)
        st["error"] = str(e)[:300]
        _save(st)
        print(f"reel: failed, not retried: {st['error'][:200]}")
        return None
    st.update(media_id=media, permalink=link, published=desk.now().isoformat(timespec="seconds"))
    st.pop("error", None)
    _save(st)
    print(f"reel: published {link}")
    return media
